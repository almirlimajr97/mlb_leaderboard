"""
fetch_data.py
-------------
Busca play-by-play de todos os jogos de uma data e salva em data/raw/YYYY-MM-DD.csv

Uso:
    python scripts/fetch_data.py --date 2026-03-25
    python scripts/fetch_data.py              # padrão: ontem
"""

import argparse
import time
import requests
import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path

# ── Configurações ──────────────────────────────────────────
BASE_URL        = "https://statsapi.mlb.com/api/v1"
FINAL_STATUSES  = {"Final", "Completed Early"}
RAW_DIR         = Path(__file__).parent.parent / "data" / "raw"
SESSION         = requests.Session()
SESSION.headers.update({"User-Agent": "mlb-leaderboard/1.0"})


# ── Funções de coleta ──────────────────────────────────────

def get_games(game_date: str) -> pd.DataFrame:
    r = SESSION.get(
        f"{BASE_URL}/schedule",
        params={"sportId": 1, "date": game_date, "hydrate": "team,linescore"},
        timeout=10,
    )
    r.raise_for_status()

    games = []
    for entry in r.json().get("dates", []):
        games.extend(entry.get("games", []))

    if not games:
        return pd.DataFrame()

    rows = []
    for g in games:
        rows.append({
            "season":             g.get("season"),
            "game_type":          g.get("gameType"),
            "series_description": g.get("seriesDescription"),
            "game_date":          g.get("officialDate"),
            "game_pk":            g.get("gamePk"),
            "day_night":          g.get("dayNight"),
            "venue":              g.get("venue", {}).get("name"),
            "series_game":        g.get("seriesGameNumber"),
            "away":               g.get("teams", {}).get("away", {}).get("team", {}).get("name"),
            "away_score":         g.get("teams", {}).get("away", {}).get("score", "-"),
            "home":               g.get("teams", {}).get("home", {}).get("team", {}).get("name"),
            "home_score":         g.get("teams", {}).get("home", {}).get("score", "-"),
            "status":             g.get("status", {}).get("detailedState"),
        })
    return pd.DataFrame(rows)


def get_play_by_play(game_pk: int) -> pd.DataFrame:
    # Busca info do jogo
    r_schedule = SESSION.get(
        f"{BASE_URL}/schedule",
        params={"sportId": 1, "gamePk": game_pk},
        timeout=10,
    )
    g = r_schedule.json()["dates"][0]["games"][0]
    away  = g.get("teams", {}).get("away", {}).get("team", {}).get("name")
    home  = g.get("teams", {}).get("home", {}).get("team", {}).get("name")
    venue = g.get("venue", {}).get("name")

    # Busca play-by-play
    r = SESSION.get(f"{BASE_URL}/game/{game_pk}/playByPlay", timeout=10)
    r.raise_for_status()
    pbp = r.json()

    rows = []
    for play in pbp.get("allPlays", []):
        result  = play.get("result", {})
        about   = play.get("about", {})
        matchup = play.get("matchup", {})
        splits  = matchup.get("splits", {})

        is_top        = about.get("isTopInning", True)
        batting_team  = away if is_top else home
        fielding_team = home if is_top else away

        home_away_batting  = "home" if batting_team  == home else "away"
        home_away_pitching = "home" if fielding_team == home else "away"

        all_events   = play.get("playEvents", [])
        pitch_index  = play.get("pitchIndex", [])
        pitch_events = [all_events[i] for i in pitch_index if i < len(all_events)]

        # ── Pitch (último da PA) ────────────────────────────
        if pitch_events:
            last_pitch = pitch_events[-1]
            pitch_data = last_pitch.get("pitchData", {})
            breaks     = pitch_data.get("breaks", {})
            details    = last_pitch.get("details", {})
            hit_data   = last_pitch.get("hitData", {})

            runner_outs = sum(
                1 for r_ in play.get("runners", [])
                if r_.get("movement", {}).get("isOut") and
                r_.get("details", {}).get("runner", {}).get("id") != matchup.get("batter", {}).get("id")
            )
            batter_out       = 1 if result.get("isOut") else 0
            total_outs_pitch = batter_out + runner_outs

            rows.append({
                "record_type":        "pitch",
                "game_pk":            game_pk,
                "game_date":          g.get("officialDate"),
                "season":             g.get("season"),
                "ref":                g.get("officialDate", "")[:7].replace("-", ""),
                "venue":              venue,
                "batting_team":       batting_team,
                "fielding_team":      fielding_team,
                "home_away_batting":  home_away_batting,
                "home_away_pitching": home_away_pitching,
                "day_night":          g.get("dayNight"),
                "batter":             matchup.get("batter",  {}).get("fullName"),
                "batter_id":          matchup.get("batter",  {}).get("id"),
                "bat_side":           matchup.get("batSide", {}).get("code"),
                "batter_split":       splits.get("batter"),
                "pitcher":            matchup.get("pitcher", {}).get("fullName"),
                "pitcher_id":         matchup.get("pitcher", {}).get("id"),
                "pitch_hand":         matchup.get("pitchHand", {}).get("code"),
                "pitcher_split":      splits.get("pitcher"),
                "men_on_base":        splits.get("menOnBase"),
                "event":              result.get("event"),
                "event_type":         result.get("eventType"),
                "rbi":                result.get("rbi", 0),
                "is_out":             result.get("isOut"),
                "is_scoring":         about.get("isScoringPlay"),
                "total_outs":         total_outs_pitch,
                "description":        result.get("description"),
                "pitch_type":         details.get("type", {}).get("description"),
                "pitch_call":         details.get("call", {}).get("description"),
                "speed_mph":          pitch_data.get("startSpeed"),
                "spin_rate":          breaks.get("spinRate"),
                "break_vertical":     breaks.get("breakVertical"),
                "break_horizontal":   breaks.get("breakHorizontal"),
                "launch_speed":       hit_data.get("launchSpeed"),
                "launch_angle":       hit_data.get("launchAngle"),
                "total_distance":     hit_data.get("totalDistance"),
                "trajectory":         hit_data.get("trajectory"),
                "hardness":           hit_data.get("hardness"),
            })

        # ── Baserunning com out ─────────────────────────────
        for event in all_events:
            if event.get("type") == "action" and event.get("details", {}).get("isOut"):
                details_a = event.get("details", {})
                count_a   = event.get("count", {})
                rows.append({
                    "record_type":        "baserunning",
                    "game_pk":            game_pk,
                    "game_date":          g.get("officialDate"),
                    "season":             g.get("season"),
                    "ref":                g.get("officialDate", "")[:7].replace("-", ""),
                    "venue":              venue,
                    "batting_team":       batting_team,
                    "fielding_team":      fielding_team,
                    "home_away_batting":  home_away_batting,
                    "home_away_pitching": home_away_pitching,
                    "day_night":          g.get("dayNight"),
                    "batter":             matchup.get("batter",  {}).get("fullName"),
                    "batter_id":          matchup.get("batter",  {}).get("id"),
                    "bat_side":           matchup.get("batSide", {}).get("code"),
                    "batter_split":       splits.get("batter"),
                    "pitcher":            matchup.get("pitcher", {}).get("fullName"),
                    "pitcher_id":         matchup.get("pitcher", {}).get("id"),
                    "pitch_hand":         matchup.get("pitchHand", {}).get("code"),
                    "pitcher_split":      splits.get("pitcher"),
                    "men_on_base":        splits.get("menOnBase"),
                    "event":              details_a.get("event"),
                    "event_type":         details_a.get("eventType"),
                    "rbi":                0,
                    "is_out":             True,
                    "is_scoring":         details_a.get("isScoringPlay"),
                    "total_outs":         1,
                    "description":        details_a.get("description"),
                    "pitch_type":         None, "pitch_call":       None,
                    "speed_mph":          None, "spin_rate":        None,
                    "break_vertical":     None, "break_horizontal": None,
                    "launch_speed":       None, "launch_angle":     None,
                    "total_distance":     None, "trajectory":       None,
                    "hardness":           None,
                })

    df = pd.DataFrame(rows).sort_values("game_pk").reset_index(drop=True)
    return df


# ── Main ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Data no formato YYYY-MM-DD (padrão: ontem)")
    args = parser.parse_args()

    game_date = args.date or (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Sanity check: não busca datas absurdamente antigas (a MLB Stats API
    # tem dados desde 1876, mas isso evita erro de digitação na data).
    if game_date < "1900-01-01":
        print(f"Data {game_date} parece inválida. Nada a fazer.")
        return

    print(f"Buscando jogos de {game_date}...")
    df_games = get_games(game_date)

    if df_games.empty:
        print("Nenhum jogo encontrado.")
        return

    df_games = df_games[
        (df_games["status"].isin(FINAL_STATUSES)) &
        (df_games["game_type"] == "R")
    ]

    if df_games.empty:
        print("Nenhum jogo finalizado encontrado.")
        return

    print(f"  {len(df_games)} jogo(s) encontrado(s).")

    all_dfs = []
    for _, game in df_games.iterrows():
        try:
            df_pbp = get_play_by_play(game["game_pk"])
            all_dfs.append(df_pbp)
            print(f"  ✓ {game['away']} @ {game['home']} ({game['game_pk']})")
        except Exception as e:
            print(f"  ⚠ Erro no jogo {game['game_pk']}: {e}")
        time.sleep(0.3)

    if not all_dfs:
        print("Nenhum dado coletado.")
        return

    df_day = pd.concat(all_dfs, ignore_index=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{game_date}.csv"
    df_day.to_csv(out_path, index=False)
    print(f"\nSalvo em {out_path} ({len(df_day)} linhas)")


if __name__ == "__main__":
    main()
