"""
send_report.py
--------------
Gera e envia o report diário de MLB via Resend.

Uso:
    python scripts/send_report.py --date 2026-06-26
    python scripts/send_report.py              # padrão: ontem
"""

import argparse
import os
import requests
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

BASE_URL         = "https://statsapi.mlb.com/api/v1"
RAW_DIR          = Path(__file__).parent.parent / "data" / "raw"
SESSION          = requests.Session()
SESSION.headers.update({"User-Agent": "mlb-statleaders/1.0"})
VALID_GAME_TYPES = {"R", "F", "D", "L", "W"}
FINAL_STATUSES   = {"Final", "Completed Early"}


# ── Scores ────────────────────────────────────────────────────────────────────

def get_scores(game_date: str) -> list:
    try:
        r = SESSION.get(
            f"{BASE_URL}/schedule",
            params={"sportId": 1, "date": game_date, "hydrate": "team,linescore"},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠ Erro ao buscar schedule: {e}")
        return []

    games = []
    for entry in r.json().get("dates", []):
        games.extend(entry.get("games", []))

    scores = []
    for g in games:
        if g.get("gameType", "") not in VALID_GAME_TYPES:
            continue
        if g.get("status", {}).get("detailedState", "") not in FINAL_STATUSES:
            continue

        innings    = g.get("linescore", {}).get("currentInning", 9)
        away       = g.get("teams", {}).get("away", {})
        home       = g.get("teams", {}).get("home", {})
        away_name  = away.get("team", {}).get("name", "")
        home_name  = home.get("team", {}).get("name", "")
        away_score = away.get("score", 0) or 0
        home_score = home.get("score", 0) or 0
        winner     = home_name if home_score > away_score else away_name

        scores.append({
            "top_team":  away_name,
            "top_score": away_score,
            "bot_team":  home_name,
            "bot_score": home_score,
            "winner":    winner,
            "venue":     g.get("venue", {}).get("name", ""),
            "innings":   innings,
            "game_type": g.get("gameType", "R"),
        })

    return scores


# ── Stats do dia ──────────────────────────────────────────────────────────────

NOT_AB      = ["Walk", "Intent Walk", "Hit By Pitch", "Sac Fly", "Sac Bunt", "Catcher Interference"]
HITS        = ["Single", "Double", "Triple", "Home Run"]
EXCLUDE_PA  = "Pickoff|Caught Stealing|Runner Out|Balk|Wild Pitch|Stolen Base"


def load_day_stats(game_date: str):
    path = RAW_DIR / f"{game_date}.parquet"
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame()

    df = pd.read_parquet(path)
    df = df[df["game_type"].isin(VALID_GAME_TYPES)]
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # ── Batters ──────────────────────────────────────────────
    bat = df[df["record_type"] == "pitch"].copy()
    bat_agg = pd.DataFrame()
    if not bat.empty:
        event         = bat["event"].fillna("")
        is_excluded   = event.str.contains(EXCLUDE_PA, na=False)
        bat["is_pa"]  = event.ne("") & ~is_excluded
        bat["is_ab"]  = event.ne("") & ~event.isin(NOT_AB) & ~is_excluded
        bat["is_hit"] = event.isin(HITS)
        bat["is_hr"]  = event == "Home Run"
        bat["is_bb"]  = event == "Walk"
        bat["is_ibb"] = event == "Intent Walk"
        bat["is_so"]  = event == "Strikeout"

        bat_agg = bat.groupby(["batter", "batter_id", "batting_team"]).agg(
            PA=("is_pa",  "sum"), AB=("is_ab",  "sum"), H=("is_hit", "sum"),
            HR=("is_hr",  "sum"), BB=("is_bb",  "sum"), IBB=("is_ibb", "sum"),
            SO=("is_so",  "sum"), RBI=("rbi",   "sum"),
        ).reset_index()

    # ── Pitchers ─────────────────────────────────────────────
    pit = df[df["record_type"] == "pitch"].copy()
    pit_agg = pd.DataFrame()
    if not pit.empty:
        event         = pit["event"].fillna("")
        is_excluded   = event.str.contains(EXCLUDE_PA, na=False)
        pit["is_bf"]  = event.ne("") & ~is_excluded
        pit["is_hit"] = event.isin(HITS)
        pit["is_hr"]  = event == "Home Run"
        pit["is_bb"]  = event == "Walk"
        pit["is_ibb"] = event == "Intent Walk"
        pit["is_so"]  = event == "Strikeout"
        pit["is_hbp"] = event == "Hit By Pitch"

        pit_agg = pit.groupby(["pitcher", "pitcher_id", "fielding_team"]).agg(
            BF=("is_bf",  "sum"), H=("is_hit", "sum"), HR=("is_hr",  "sum"),
            BB=("is_bb",  "sum"), IBB=("is_ibb", "sum"), SO=("is_so", "sum"),
            HBP=("is_hbp", "sum"), outs=("total_outs", "sum"),
        ).reset_index()

        # outs de baserunning
        br = df[df["record_type"] == "baserunning"].copy()
        if not br.empty:
            br_total = br.groupby("pitcher_id")["total_outs"].sum().reset_index()
            br_total.columns = ["pitcher_id", "br_outs"]
            pit_agg = pit_agg.merge(br_total, on="pitcher_id", how="left")
            pit_agg["outs"] = pit_agg["outs"] + pit_agg["br_outs"].fillna(0)

        pit_agg["ip_outs"] = pit_agg["outs"].astype(int)
        pit_agg["ip_val"]  = pit_agg["ip_outs"] / 3
        pit_agg["IP"]      = pit_agg["ip_outs"].apply(lambda o: f"{o//3}.{o%3}")

    return bat_agg, pit_agg


# ── Highlights ────────────────────────────────────────────────────────────────

def detect_highlights(bat_agg: pd.DataFrame, pit_agg: pd.DataFrame) -> list:
    highlights = []

    if not pit_agg.empty:
        for _, row in pit_agg.iterrows():
            if row["ip_val"] >= 9 and row["H"] == 0:
                if row["BB"] == 0 and row["IBB"] == 0 and row["HBP"] == 0:
                    highlights.append({
                        "type": "perfect_game", "label": "Perfect game",
                        "badge": "PERFECT GAME", "color": "pitching",
                        "detail": f"{row['pitcher']} ({row['fielding_team']}) — {row['IP']} IP, 0 H, 0 BB, {int(row['SO'])} K",
                        "pitcher": row["pitcher"], "team": row["fielding_team"],
                    })
                else:
                    highlights.append({
                        "type": "no_hitter", "label": "No-hitter",
                        "badge": "NO-HITTER", "color": "pitching",
                        "detail": f"{row['pitcher']} ({row['fielding_team']}) — {row['IP']} IP, 0 H, 0 ER, {int(row['SO'])} K",
                        "pitcher": row["pitcher"], "team": row["fielding_team"],
                    })
            if row["SO"] >= 10:
                highlights.append({
                    "type": "pit_explosion", "label": "Pitching explosion",
                    "badge": f"{int(row['SO'])} K", "color": "pitching",
                    "detail": f"{row['pitcher']} ({row['fielding_team']}) — {int(row['SO'])} K in {row['IP']} IP",
                    "pitcher": row["pitcher"], "team": row["fielding_team"],
                })

    if not bat_agg.empty:
        for _, row in bat_agg.iterrows():
            if row["HR"] >= 3 or row["RBI"] >= 8:
                highlights.append({
                    "type": "offense", "label": "Offensive explosion",
                    "badge": f"{int(row['HR'])} HR · {int(row['RBI'])} RBI",
                    "color": "offense",
                    "detail": f"{row['batter']} ({row['batting_team']}) — {int(row['HR'])} HR, {int(row['RBI'])} RBI, {int(row['H'])} H",
                    "batter": row["batter"], "team": row["batting_team"],
                })

    return highlights


# ── Inline style constants ────────────────────────────────────────────────────

S = {
    "font":       "font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif;",
    "mono":       "font-family:Courier New,Courier,monospace;",
    "rank":       "font-size:11px;color:#9CA3AF;font-family:Courier New,monospace;width:20px;min-width:20px;vertical-align:middle;",
    "rank_gold":  "font-size:11px;color:#E0A847;font-weight:600;font-family:Courier New,monospace;width:20px;min-width:20px;vertical-align:middle;",
    "name":       "font-size:13px;font-weight:600;color:#1A1D23;margin:0 0 1px 0;",
    "team":       "font-size:11px;color:#9CA3AF;margin:0;",
    "stat":       "font-size:13px;font-weight:600;color:#1A1D23;font-family:Courier New,monospace;text-align:right;white-space:nowrap;vertical-align:middle;",
    "stat_green": "font-size:13px;font-weight:600;color:#0F9D63;font-family:Courier New,monospace;text-align:right;white-space:nowrap;vertical-align:middle;",
    "sublabel":   "font-size:10px;color:#9CA3AF;text-align:right;margin:0;",
    "badge_nh":   "font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600;margin-left:5px;background:#FBE2D3;color:#D8500F;",
    "badge_pg":   "font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600;margin-left:5px;background:#D7F2E5;color:#0F6E56;",
    "badge_off":  "font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600;margin-left:5px;background:#D7F2E5;color:#0F6E56;",
    "row_border": "border-bottom:1px solid #E2E0DA;padding:8px 0;",
    "row_last":   "padding:8px 0;",
}


# ── Helpers de renderização ───────────────────────────────────────────────────

def offense_badge(batter: str, highlights: list) -> str:
    for h in highlights:
        if h["type"] == "offense" and h.get("batter") == batter:
            return f'<span style="{S["badge_off"]}">{h["badge"]}</span>'
    return ""


def pitcher_badge(pitcher: str, highlights: list) -> str:
    for h in highlights:
        if h["type"] in ("no_hitter", "perfect_game", "pit_explosion") and h.get("pitcher") == pitcher:
            bs = S["badge_pg"] if h["type"] == "perfect_game" else S["badge_nh"]
            return f'<span style="{bs}">{h["badge"]}</span>'
    return ""


def section_title(title: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">'
        f'<tr><td style="font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;'
        f'color:#9CA3AF;white-space:nowrap;padding-right:10px;{S["font"]}">{title}</td>'
        f'<td style="border-top:1px solid #E2E0DA;">&nbsp;</td></tr></table>'
    )


def render_row(rank: int, name_html: str, team: str, stat: str, sublabel: str, last: bool = False) -> str:
    rs  = S["rank_gold"] if rank == 1 else S["rank"]
    ss  = S["stat_green"] if rank == 1 else S["stat"]
    row = S["row_last"] if last else S["row_border"]
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="{row}">'
        f'<tr>'
        f'<td style="{rs}">{rank}</td>'
        f'<td style="padding-left:8px;">'
        f'<p style="{S["name"]}{S["font"]}">{name_html}</p>'
        f'<p style="{S["team"]}{S["font"]}">{team}</p>'
        f'</td>'
        f'<td style="text-align:right;white-space:nowrap;vertical-align:middle;">'
        f'<p style="{ss}">{stat}</p>'
        f'<p style="{S["sublabel"]}{S["font"]}">{sublabel}</p>'
        f'</td>'
        f'</tr></table>'
    )


def render_section(title: str, rows_html: str) -> str:
    if not rows_html.strip():
        return ""
    return (
        f'<div style="margin-bottom:24px;">'
        f'{section_title(title)}'
        f'{rows_html}'
        f'</div>'
    )


def rows_pit_ip(pit_agg: pd.DataFrame, highlights: list) -> str:
    if pit_agg.empty:
        return ""
    top = pit_agg.sort_values(["ip_val", "SO"], ascending=[False, False]).head(3).reset_index(drop=True)
    return "".join(render_row(
        i+1,
        f'{r["pitcher"]}{pitcher_badge(r["pitcher"], highlights)}',
        r["fielding_team"],
        r["IP"],
        f'IP &middot; {int(r["SO"])} K &middot; {int(r["H"])} H',
        last=(i == len(top)-1)
    ) for i, r in top.iterrows())


def rows_pit_k(pit_agg: pd.DataFrame, highlights: list) -> str:
    if pit_agg.empty:
        return ""
    top = pit_agg.sort_values(["SO", "ip_val"], ascending=[False, False]).head(3).reset_index(drop=True)
    return "".join(render_row(
        i+1, r["pitcher"], r["fielding_team"],
        str(int(r["SO"])), f'K &middot; {r["IP"]} IP',
        last=(i == len(top)-1)
    ) for i, r in top.iterrows())


def rows_bat_h(bat_agg: pd.DataFrame, highlights: list) -> str:
    if bat_agg.empty:
        return ""
    top = bat_agg.sort_values(["H", "HR"], ascending=[False, False]).head(3).reset_index(drop=True)
    return "".join(render_row(
        i+1,
        f'{r["batter"]}{offense_badge(r["batter"], highlights)}',
        r["batting_team"],
        str(int(r["H"])),
        f'H &middot; {int(r["AB"])} AB &middot; {int(r["HR"])} HR',
        last=(i == len(top)-1)
    ) for i, r in top.iterrows())


def rows_bat_hr(bat_agg: pd.DataFrame, highlights: list) -> str:
    if bat_agg.empty:
        return ""
    top = bat_agg[bat_agg["HR"] > 0].sort_values(["HR", "RBI"], ascending=[False, False]).head(3).reset_index(drop=True)
    if top.empty:
        return ""
    return "".join(render_row(
        i+1,
        f'{r["batter"]}{offense_badge(r["batter"], highlights)}',
        r["batting_team"],
        f'{int(r["HR"])} HR',
        f'{int(r["RBI"])} RBI',
        last=(i == len(top)-1)
    ) for i, r in top.iterrows())


def rows_bat_rbi(bat_agg: pd.DataFrame, highlights: list) -> str:
    if bat_agg.empty:
        return ""
    top = bat_agg[bat_agg["RBI"] > 0].sort_values(["RBI", "HR"], ascending=[False, False]).head(3).reset_index(drop=True)
    if top.empty:
        return ""
    return "".join(render_row(
        i+1,
        f'{r["batter"]}{offense_badge(r["batter"], highlights)}',
        r["batting_team"],
        str(int(r["RBI"])),
        f'RBI &middot; {int(r["HR"])} HR',
        last=(i == len(top)-1)
    ) for i, r in top.iterrows())


def render_highlights_html(highlights: list) -> str:
    if not highlights:
        return ""
    rows = ""
    for h in highlights:
        if h["type"] == "perfect_game":
            bs = S["badge_pg"]
        elif h["type"] in ("no_hitter", "pit_explosion"):
            bs = S["badge_nh"]
        else:
            bs = S["badge_off"]
        color = "#D8500F" if h["color"] == "pitching" else "#0F9D63"
        rows += (
            f'<div style="background:#FBFAF8;border:1px solid #E2E0DA;border-left:3px solid {color};'
            f'border-radius:0 6px 6px 0;padding:10px 14px;margin-bottom:8px;">'
            f'<p style="font-size:12px;font-weight:600;color:#1A1D23;margin:0 0 2px;{S["font"]}">'
            f'{h["label"]} <span style="{bs}">{h["badge"]}</span></p>'
            f'<p style="font-size:11px;color:#6B7280;margin:0;{S["font"]}">{h["detail"]}</p>'
            f'</div>'
        )
    return render_section("Highlights", rows)


def render_scores_html(scores: list, highlights: list) -> str:
    if not scores:
        return ""
    hl_pit_teams = {h["team"] for h in highlights if h["type"] in ("no_hitter", "perfect_game", "pit_explosion")}
    hl_bat_teams = {h["team"] for h in highlights if h["type"] == "offense"}

    cards = ""
    for s in scores:
        note       = "F/9" if s["innings"] == 9 else f"F/{s['innings']}"
        border_clr = "#E2E0DA"
        winner     = s["winner"]

        if winner in hl_pit_teams:
            border_clr = "#D8500F"
            for h in highlights:
                if h["type"] in ("no_hitter", "perfect_game", "pit_explosion") and h["team"] == winner:
                    note += f" &middot; {h['badge']}"
        elif s["top_team"] in hl_bat_teams or s["bot_team"] in hl_bat_teams:
            border_clr = "#0F9D63"
            for h in highlights:
                if h["type"] == "offense" and h["team"] in (s["top_team"], s["bot_team"]):
                    note += f" &middot; {h['batter'].split()[-1]}: {h['badge']}"

        def team_style(team):
            if team == winner:
                return "font-size:12px;font-weight:600;color:#1A1D23;"
            return "font-size:12px;font-weight:400;color:#6B7280;"

        def runs_style(team):
            if team == winner:
                return f"font-size:13px;font-weight:600;color:#1A1D23;text-align:right;{S['mono']}"
            return f"font-size:13px;font-weight:400;color:#6B7280;text-align:right;{S['mono']}"

        cards += (
            f'<div style="background:#FBFAF8;border:1px solid {border_clr};border-radius:8px;'
            f'padding:10px 12px;margin-bottom:8px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="{team_style(s["top_team"])}{S["font"]}">{s["top_team"]}</td>'
            f'<td style="{runs_style(s["top_team"])}">{s["top_score"]}</td></tr>'
            f'</table>'
            f'<div style="height:1px;background:#E2E0DA;margin:4px 0;"></div>'
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="{team_style(s["bot_team"])}{S["font"]}">{s["bot_team"]}</td>'
            f'<td style="{runs_style(s["bot_team"])}">{s["bot_score"]}</td></tr>'
            f'</table>'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:5px;">'
            f'<tr><td style="font-size:10px;color:#9CA3AF;{S["mono"]}">{s["venue"]}</td>'
            f'<td style="font-size:10px;color:#9CA3AF;text-align:right;{S["mono"]}">{note}</td></tr>'
            f'</table>'
            f'</div>'
        )

    return render_section("Scores", cards)


# ── HTML completo ─────────────────────────────────────────────────────────────

def build_html(game_date: str, scores: list, bat_agg: pd.DataFrame,
               pit_agg: pd.DataFrame, highlights: list) -> str:
    n_games    = len(scores)
    date_fmt   = pd.Timestamp(game_date).strftime("%b %d, %Y")
    game_types = {s["game_type"] for s in scores}
    season_lbl = "Regular Season" if game_types == {"R"} else "Playoffs"

    s_highlights = render_highlights_html(highlights)
    s_pit_ip     = render_section("Pitching — innings pitched", rows_pit_ip(pit_agg, highlights))
    s_pit_k      = render_section("Pitching — strikeouts",      rows_pit_k(pit_agg, highlights))
    s_bat_h      = render_section("Batting — hits",             rows_bat_h(bat_agg, highlights))
    s_bat_hr     = render_section("Batting — home runs",        rows_bat_hr(bat_agg, highlights))
    s_bat_rbi    = render_section("Batting — RBI",              rows_bat_rbi(bat_agg, highlights))
    s_scores     = render_scores_html(scores, highlights)

    divider   = '<div style="height:1px;background:#E2E0DA;margin:20px 0;"></div>'
    pit_block = f"{divider}{s_pit_ip}{s_pit_k}" if (s_pit_ip or s_pit_k) else ""
    bat_block = f"{divider}{s_bat_h}{s_bat_hr}{s_bat_rbi}" if (s_bat_h or s_bat_hr or s_bat_rbi) else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MLB Daily Report &middot; {date_fmt}</title>
</head>
<body style="margin:0;padding:20px;background:#F5F4F1;{S['font']}">
<div style="max-width:600px;margin:0 auto;">

  <!-- Header -->
  <div style="background:#0A0E14;border-radius:12px 12px 0 0;padding:24px 28px;">
    <p style="color:#E8EAED;font-size:16px;font-weight:600;margin:0 0 4px;letter-spacing:1px;">&#9918; STAT LEADERS &middot; MLB</p>
    <p style="color:#7A8699;font-size:12px;margin:0;{S['mono']}">
      <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#3DDC97;margin-right:6px;"></span>
      Daily report &middot; {date_fmt} &middot; {n_games} game{"s" if n_games != 1 else ""} played
    </p>
  </div>

  <!-- Body -->
  <div style="background:#FFFFFF;border:1px solid #E2E0DA;border-top:none;border-radius:0 0 12px 12px;padding:24px 28px;">

    <span style="display:inline-block;background:#FBFAF8;border:1px solid #E2E0DA;border-radius:4px;
      padding:2px 8px;font-size:11px;color:#6B7280;margin-bottom:20px;{S['mono']}">{date_fmt} &mdash; {season_lbl}</span>

    {s_highlights}
    {pit_block}
    {bat_block}
    {divider}
    {s_scores}

    <!-- Footer -->
    <div style="text-align:center;padding-top:16px;border-top:1px solid #E2E0DA;margin-top:8px;">
      <p style="font-size:11px;color:#9CA3AF;margin:0;{S['font']}">
        Stat Leaders &middot; MLB &mdash;
        <a href="https://almirlimajr97.github.io/mlb_statleaders/" style="color:#D8500F;text-decoration:none;">
          almirlimajr97.github.io/mlb_statleaders</a>
      </p>
      <p style="font-size:11px;color:#9CA3AF;margin:4px 0 0;{S['font']}">
        Data: MLB Stats API &middot; Generated automatically via GitHub Actions
      </p>
    </div>

  </div>
</div>
</body>
</html>"""


# ── Envio via Resend ──────────────────────────────────────────────────────────

def send_email(html: str, game_date: str) -> bool:
    api_key  = os.environ.get("RESEND_API_KEY", "")
    to_email = os.environ.get("REPORT_EMAIL", "")

    if not api_key or not to_email:
        print("  ⚠ RESEND_API_KEY ou REPORT_EMAIL não definidos.")
        return False

    date_fmt = pd.Timestamp(game_date).strftime("%b %d, %Y")
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from":    "Stat Leaders MLB <onboarding@resend.dev>",
                "to":      [to_email],
                "subject": f"⚾ MLB Daily Report · {date_fmt}",
                "html":    html,
            },
            timeout=15,
        )
        r.raise_for_status()
        print(f"  ✓ E-mail enviado para {to_email}")
        return True
    except Exception as e:
        print(f"  ⚠ Erro ao enviar e-mail: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="", help="Data (YYYY-MM-DD). Padrão: ontem.")
    args = parser.parse_args()

    game_date = args.date.strip() or (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Gerando report para {game_date}...")

    scores = get_scores(game_date)
    if not scores:
        print("  Nenhum jogo finalizado encontrado. Nada a enviar.")
        return

    bat_agg, pit_agg = load_day_stats(game_date)
    if bat_agg.empty and pit_agg.empty:
        print("  Sem dados de stats para essa data. Nada a enviar.")
        return

    highlights = detect_highlights(bat_agg, pit_agg)
    if highlights:
        print(f"  {len(highlights)} highlight(s) detectado(s).")

    html = build_html(game_date, scores, bat_agg, pit_agg, highlights)
    send_email(html, game_date)


if __name__ == "__main__":
    main()
