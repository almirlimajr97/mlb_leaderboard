# MLB Stat Leaders

An MLB batting and pitching stats dashboard, automatically updated via GitHub Actions from the [MLB Stats API](https://statsapi.mlb.com).

**🔗 [View the live dashboard](https://almirlimajr97.github.io/mlb_statleaders/)**

## What it is

A terminal-style leaderboard (dark mode, dense, data-driven) with batting and pitching stats covering regular season and playoffs. Data is collected daily and processed into a granular cube by game/situation, enabling advanced filtering without losing context.

### Features

- **Overview** with KPI cards for the current season's leaders (batting: OPS, Hits, Home Runs, RBI; pitching: Innings, WHIP, OPS against, K%) — scoped to Regular Season only
- **Full tables** for Batters and Pitchers, with traditional columns (AVG, OBP, SLG, OPS, BAA) and advanced ones (BABIP, BB%, K%, WHIP)
- **Team display** below each player's name — players who appeared for more than one team within the active filter context will have all represented teams listed
- **Color-coded stats**: green (elite) → gray (average) → red (poor), with thresholds calibrated per stat and direction (higher is better for batters, lower for pitchers)
- **Granular filters**: season, game type (regular season/playoffs), playoff round, month, team, opponent, venue, batting/pitching side, runners-on situation, home/away
- **Interactive sorting** on any table column
- **Light/dark theme** toggle
- **Performance**: data partitioned by season and lazy-loaded on demand
- **Daily email report**: automated HTML newsletter delivered every morning with the previous day's scores, pitching leaders (innings pitched, strikeouts), batting leaders (hits, home runs, RBI), and special highlights (no-hitters, perfect games, complete games, pitching explosions ≥ 10 K, offensive explosions ≥ 3 HR or ≥ 8 RBI)

## Architecture

```
mlb_statleaders/
├── .github/workflows/
│   └── update.yml          # Schedules the daily collection + allows manual reprocessing
├── scripts/
│   ├── fetch_data.py        # Collects play-by-play from the MLB Stats API
│   ├── build_stats.py       # Aggregates raw data into batting/pitching cubes
│   ├── build_html.py        # Generates the dashboard (HTML + JSON per season)
│   └── send_report.py       # Generates and sends the daily email report via Resend
├── data/
│   ├── raw/                 # One Parquet file per date, pitch/baserunning granularity
│   ├── df_batters_<season>.parquet
│   └── df_pitchers_<season>.parquet
└── docs/                    # Published via GitHub Pages
    ├── index.html
    └── data/
        ├── batters_<season>.json
        └── pitchers_<season>.json
```

### Data pipeline

1. **`fetch_data.py`** fetches the play-by-play for every finished game on a given date (regular season and playoffs), saving two row categories per at-bat:
   - `pitch`: the main result of each plate appearance
   - `baserunning`: Caught Stealing, Pickoff, Runner Out, Wild Pitch, and Balk plays captured separately, since they can occur outside the batter's main result

2. **`build_stats.py`** reads the full history in `data/raw/`, deduplicates, calculates outs (including correct baserunning logic), and aggregates into two cubes — batters and pitchers — partitioned by season.

3. **`build_html.py`** reads the aggregates and generates the dashboard: the HTML fetches only the selected season on demand, keeping the initial payload light even with multiple years of history.

4. **`send_report.py`** reads the raw data for the previous day, computes per-game stats, detects highlights (no-hitters, perfect games, offensive explosions), and sends an HTML email report via [Resend](https://resend.com).

The GitHub Actions workflow runs daily, collecting the previous day, re-aggregating the full history, republishing the site, and sending the email report. Manual reprocessing (date range) can be triggered via `workflow_dispatch`.

## Stack

- **Collection & processing**: Python, pandas, requests, PyArrow (Parquet)
- **Front-end**: vanilla HTML/CSS/JS, no framework — JetBrains Mono for tabular data, Inter for UI
- **Email delivery**: Resend API
- **Automation**: GitHub Actions
- **Hosting**: GitHub Pages

## Built with Claude

This project was built with the help of [Claude](https://claude.ai/), Anthropic's AI assistant — from the data pipeline and aggregation logic to the dashboard design, bug fixes, and performance optimizations.

## Data source

All data comes from the [MLB Stats API](https://statsapi.mlb.com), a public, unofficial API. This project is not affiliated with MLB.
