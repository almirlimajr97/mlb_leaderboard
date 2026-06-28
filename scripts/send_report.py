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

        if home_score > away_score:
            winner, loser           = home_name, away_name
            winner_score, loser_score = home_score, away_score
        else:
            winner, loser           = away_name, home_name
            winner_score, loser_score = away_score, home_score

        scores.append({
            "winner":       winner,
            "loser":        loser,
            "winner_score": winner_score,
            "loser_score":  loser_score,
            "venue":        g.get("venue", {}).get("name", ""),
            "innings":      innings,
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

    if not bat_agg.empty:
        for _, row in bat_agg.iterrows():
            if row["HR"] >= 3 or (row["HR"] >= 2 and row["RBI"] >= 8):
                highlights.append({
                    "type": "offense", "label": "Offensive explosion",
                    "badge": f"{int(row['HR'])} HR · {int(row['RBI'])} RBI",
                    "color": "offense",
                    "detail": f"{row['batter']} ({row['batting_team']}) — {int(row['HR'])} HR, {int(row['RBI'])} RBI, {int(row['H'])} H",
                    "batter": row["batter"], "team": row["batting_team"],
                })

    return highlights


# ── Helpers de renderização ───────────────────────────────────────────────────

def offense_badge(batter: str, highlights: list) -> str:
    for h in highlights:
        if h["type"] == "offense" and h.get("batter") == batter:
            return f'<span class="badge offense">{h["badge"]}</span>'
    return ""


def pitcher_badge(pitcher: str, highlights: list) -> str:
    for h in highlights:
        if h["type"] in ("no_hitter", "perfect_game") and h.get("pitcher") == pitcher:
            cls = "perfgame" if h["type"] == "perfect_game" else "nohitter"
            return f'<span class="badge {cls}">{h["badge"]}</span>'
    return ""


def render_section(title: str, rows_html: str) -> str:
    if not rows_html.strip():
        return ""
    return f'<div class="section"><div class="section-title">{title}</div>{rows_html}</div>'


def rows_pit_ip(pit_agg: pd.DataFrame, highlights: list) -> str:
    if pit_agg.empty:
        return ""
    top = pit_agg.sort_values(["ip_val", "SO"], ascending=[False, False]).head(3)
    html = ""
    for i, (_, r) in enumerate(top.iterrows()):
        rc = "gold" if i == 0 else ""
        sc = "green" if i == 0 else ""
        html += f'<div class="row"><span class="rank {rc}">{i+1}</span><div class="player"><div class="player-name">{r["pitcher"]} {pitcher_badge(r["pitcher"], highlights)}</div><div class="player-team">{r["fielding_team"]}</div></div><div><div class="stat {sc}">{r["IP"]}</div><div class="stat-label">IP · {int(r["SO"])} K · {int(r["H"])} H</div></div></div>'
    return html


def rows_pit_k(pit_agg: pd.DataFrame, highlights: list) -> str:
    if pit_agg.empty:
        return ""
    top = pit_agg.sort_values(["SO", "ip_val"], ascending=[False, False]).head(3)
    html = ""
    for i, (_, r) in enumerate(top.iterrows()):
        rc = "gold" if i == 0 else ""
        sc = "green" if i == 0 else ""
        html += f'<div class="row"><span class="rank {rc}">{i+1}</span><div class="player"><div class="player-name">{r["pitcher"]}</div><div class="player-team">{r["fielding_team"]}</div></div><div><div class="stat {sc}">{int(r["SO"])}</div><div class="stat-label">K · {r["IP"]} IP</div></div></div>'
    return html


def rows_bat_h(bat_agg: pd.DataFrame, highlights: list) -> str:
    if bat_agg.empty:
        return ""
    top = bat_agg.sort_values(["H", "HR"], ascending=[False, False]).head(3)
    html = ""
    for i, (_, r) in enumerate(top.iterrows()):
        rc = "gold" if i == 0 else ""
        sc = "green" if i == 0 else ""
        html += f'<div class="row"><span class="rank {rc}">{i+1}</span><div class="player"><div class="player-name">{r["batter"]} {offense_badge(r["batter"], highlights)}</div><div class="player-team">{r["batting_team"]}</div></div><div><div class="stat {sc}">{int(r["H"])}</div><div class="stat-label">H · {int(r["AB"])} AB · {int(r["HR"])} HR</div></div></div>'
    return html


def rows_bat_hr(bat_agg: pd.DataFrame, highlights: list) -> str:
    if bat_agg.empty:
        return ""
    top = bat_agg[bat_agg["HR"] > 0].sort_values(["HR", "RBI"], ascending=[False, False]).head(3)
    if top.empty:
        return ""
    html = ""
    for i, (_, r) in enumerate(top.iterrows()):
        rc = "gold" if i == 0 else ""
        sc = "green" if i == 0 else ""
        html += f'<div class="row"><span class="rank {rc}">{i+1}</span><div class="player"><div class="player-name">{r["batter"]} {offense_badge(r["batter"], highlights)}</div><div class="player-team">{r["batting_team"]}</div></div><div><div class="stat {sc}">{int(r["HR"])} HR</div><div class="stat-label">{int(r["RBI"])} RBI</div></div></div>'
    return html


def rows_bat_rbi(bat_agg: pd.DataFrame, highlights: list) -> str:
    if bat_agg.empty:
        return ""
    top = bat_agg[bat_agg["RBI"] > 0].sort_values(["RBI", "HR"], ascending=[False, False]).head(3)
    if top.empty:
        return ""
    html = ""
    for i, (_, r) in enumerate(top.iterrows()):
        rc = "gold" if i == 0 else ""
        sc = "green" if i == 0 else ""
        html += f'<div class="row"><span class="rank {rc}">{i+1}</span><div class="player"><div class="player-name">{r["batter"]} {offense_badge(r["batter"], highlights)}</div><div class="player-team">{r["batting_team"]}</div></div><div><div class="stat {sc}">{int(r["RBI"])}</div><div class="stat-label">RBI · {int(r["HR"])} HR</div></div></div>'
    return html


def render_highlights_html(highlights: list) -> str:
    if not highlights:
        return ""
    rows = ""
    for h in highlights:
        bc = "nohitter" if h["type"] == "no_hitter" else ("perfgame" if h["type"] == "perfect_game" else "offense")
        rows += f'<div class="hl-box {h["color"]}"><p class="hl-title">{h["label"]} <span class="badge {bc}">{h["badge"]}</span></p><p class="hl-sub">{h["detail"]}</p></div>'
    return f'<div class="section"><div class="section-title">Highlights</div>{rows}</div>'


def render_scores_html(scores: list, highlights: list) -> str:
    if not scores:
        return ""
    hl_pit_teams = {h["team"] for h in highlights if h["type"] in ("no_hitter", "perfect_game")}
    hl_bat_teams = {h["team"] for h in highlights if h["type"] == "offense"}

    cards = ""
    for s in scores:
        note     = "F/9" if s["innings"] == 9 else f"F/{s['innings']}"
        card_cls = "score-card"
        if s["winner"] in hl_pit_teams:
            card_cls += " featured"
            for h in highlights:
                if h["type"] in ("no_hitter", "perfect_game") and h["team"] == s["winner"]:
                    note += f" · {h['badge']}"
        elif s["winner"] in hl_bat_teams or s["loser"] in hl_bat_teams:
            card_cls += " featured-off"
            for h in highlights:
                if h["type"] == "offense" and h["team"] in (s["winner"], s["loser"]):
                    note += f" · {h['batter'].split()[-1]}: {h['badge']}"

        cards += f'<div class="{card_cls}"><div class="score-teams"><div class="score-team"><span class="name winner">{s["winner"]}</span><span class="runs winner">{s["winner_score"]}</span></div><div class="score-divider"></div><div class="score-team"><span class="name">{s["loser"]}</span><span class="runs">{s["loser_score"]}</span></div></div><div class="score-meta"><span>{s["venue"]}</span><span>{note}</span></div></div>'

    return f'<div class="section"><div class="section-title">Scores</div>{cards}</div>'


# ── HTML completo ─────────────────────────────────────────────────────────────

def build_html(game_date: str, scores: list, bat_agg: pd.DataFrame,
               pit_agg: pd.DataFrame, highlights: list) -> str:
    n_games  = len(scores)
    date_fmt = pd.Timestamp(game_date).strftime("%b %d, %Y")

    s_highlights = render_highlights_html(highlights)
    s_pit_ip     = render_section("Pitching — innings pitched", rows_pit_ip(pit_agg, highlights))
    s_pit_k      = render_section("Pitching — strikeouts",      rows_pit_k(pit_agg, highlights))
    s_bat_h      = render_section("Batting — hits",             rows_bat_h(bat_agg, highlights))
    s_bat_hr     = render_section("Batting — home runs (sorted by RBI)", rows_bat_hr(bat_agg, highlights))
    s_bat_rbi    = render_section("Batting — RBI",              rows_bat_rbi(bat_agg, highlights))
    s_scores     = render_scores_html(scores, highlights)

    div = '<div class="divider"></div>'
    pit_block = f"{div}{s_pit_ip}{s_pit_k}" if (s_pit_ip or s_pit_k) else ""
    bat_block = f"{div}{s_bat_h}{s_bat_hr}{s_bat_rbi}" if (s_bat_h or s_bat_hr or s_bat_rbi) else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MLB Daily Report · {date_fmt}</title>
<style>
body{{margin:0;padding:20px;background:#F5F4F1;font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif}}
.wrap{{max-width:600px;margin:0 auto}}
.header{{background:#0A0E14;border-radius:12px 12px 0 0;padding:24px 28px}}
.header h1{{color:#E8EAED;font-size:16px;font-weight:500;margin:0 0 4px;letter-spacing:1px}}
.header p{{color:#7A8699;font-size:12px;margin:0;font-family:monospace}}
.dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#3DDC97;margin-right:6px}}
.body{{background:#FFFFFF;border:1px solid #E2E0DA;border-top:none;border-radius:0 0 12px 12px;padding:24px 28px}}
.section-title{{font-size:11px;font-weight:500;letter-spacing:1px;text-transform:uppercase;color:#9CA3AF;margin:0 0 12px;display:flex;align-items:center;gap:8px}}
.section-title::after{{content:'';flex:1;height:1px;background:#E2E0DA}}
.section{{margin-bottom:24px}}
.row{{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #E2E0DA}}
.row:last-child{{border-bottom:none}}
.rank{{font-size:11px;color:#9CA3AF;font-family:monospace;width:16px;flex-shrink:0}}
.rank.gold{{color:#E0A847;font-weight:500}}
.player{{flex:1}}
.player-name{{font-size:13px;font-weight:500;color:#1A1D23}}
.player-team{{font-size:11px;color:#9CA3AF}}
.stat{{font-family:monospace;font-size:13px;font-weight:500;text-align:right;color:#1A1D23}}
.stat.green{{color:#0F9D63}}
.stat-label{{font-size:10px;color:#9CA3AF;text-align:right}}
.badge{{font-size:10px;padding:2px 8px;border-radius:4px;font-weight:500;margin-left:4px}}
.badge.nohitter{{background:#FBE2D3;color:#D8500F}}
.badge.perfgame{{background:#D7F2E5;color:#0F6E56}}
.badge.offense{{background:#D7F2E5;color:#0F6E56}}
.hl-box{{background:#FBFAF8;border:1px solid #E2E0DA;border-radius:0 6px 6px 0;padding:10px 14px;margin-bottom:8px}}
.hl-box.pitching{{border-left:3px solid #D8500F}}
.hl-box.offense{{border-left:3px solid #0F9D63}}
.hl-box .hl-title{{font-size:12px;font-weight:500;color:#1A1D23;margin:0 0 2px}}
.hl-box .hl-sub{{font-size:11px;color:#6B7280;margin:0}}
.divider{{height:1px;background:#E2E0DA;margin:20px 0}}
.games-pill{{display:inline-block;background:#FBFAF8;border:1px solid #E2E0DA;border-radius:4px;padding:2px 8px;font-size:11px;color:#6B7280;margin-bottom:16px;font-family:monospace}}
.footer{{text-align:center;padding-top:16px}}
.footer p{{font-size:11px;color:#9CA3AF;margin:0}}
.footer a{{color:#D8500F;text-decoration:none}}
.score-card{{background:#FBFAF8;border:1px solid #E2E0DA;border-radius:8px;padding:10px 12px;margin-bottom:8px}}
.score-card.featured{{border-color:#D8500F}}
.score-card.featured-off{{border-color:#0F9D63}}
.score-teams{{display:flex;flex-direction:column;gap:3px}}
.score-team{{display:flex;justify-content:space-between;align-items:center}}
.score-team .name{{font-size:12px;color:#6B7280;font-weight:400}}
.score-team .name.winner{{color:#1A1D23;font-weight:500}}
.score-team .runs{{font-family:monospace;font-size:13px;color:#6B7280;font-weight:400}}
.score-team .runs.winner{{color:#1A1D23;font-weight:500}}
.score-divider{{height:1px;background:#E2E0DA;margin:4px 0}}
.score-meta{{font-size:10px;color:#9CA3AF;margin-top:5px;font-family:monospace;display:flex;justify-content:space-between}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>&#9918; STAT LEADERS &middot; MLB</h1>
    <p><span class="dot"></span>Daily report &middot; {date_fmt} &middot; {n_games} game{"s" if n_games != 1 else ""} played</p>
  </div>
  <div class="body">
    <span class="games-pill">{date_fmt} &mdash; Regular Season</span>
    {s_highlights}
    {pit_block}
    {bat_block}
    <div class="divider"></div>
    {s_scores}
    <div class="footer">
      <p>Stat Leaders &middot; MLB &mdash; <a href="https://almirlimajr97.github.io/mlb_statleaders/">almirlimajr97.github.io/mlb_statleaders</a></p>
      <p style="margin-top:4px">Data: MLB Stats API &middot; Generated automatically via GitHub Actions</p>
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
