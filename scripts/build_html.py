"""
build_html.py
-------------
Lê data/df_batters_<season>.parquet e data/df_pitchers_<season>.parquet
(particionados por temporada pelo build_stats.py) e gera:
    - docs/index.html                    (estrutura/estilo/lógica, leve)
    - docs/data/batters_<season>.json    (um arquivo por temporada)
    - docs/data/pitchers_<season>.json   (um arquivo por temporada)

Os dados são particionados por temporada (tanto entrada quanto saída) para
não esbarrar no limite de 100MB por arquivo do GitHub conforme acumulamos
mais anos de histórico. O HTML carrega via fetch() só a temporada
selecionada no filtro de Ano, recarregando sob demanda quando o usuário
troca de ano.

Uso:
    python scripts/build_html.py
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"

# Colunas exportadas para o JSON consumido pelo front-end (uma por temporada).
B_COLS = ["game_pk", "season", "ref", "game_type", "series_description", "venue", "batting_team", "fielding_team", "batter", "batter_id", "bat_side", "batter_split",
          "men_on_base", "pitcher", "day_night", "home_away_batting",
          "PA", "AB", "H", "singles", "doubles", "triples", "HR",
          "RBI", "BB", "IBB", "SO", "HBP", "SF"]
P_COLS = ["game_pk", "season", "ref", "game_type", "series_description", "venue", "fielding_team", "batting_team", "pitcher", "pitcher_id", "pitch_hand", "pitcher_split",
          "men_on_base", "batter", "day_night", "home_away_pitching",
          "BF", "AB", "H", "singles", "doubles", "triples", "HR",
          "BB", "IBB", "SO", "HBP", "SF", "total_outs"]


def discover_seasons() -> list[int]:
    """Descobre quais temporadas têm dados disponíveis, a partir dos
    nomes dos arquivos particionados data/df_batters_<season>.parquet."""
    seasons = set()
    for f in DATA_DIR.glob("df_batters_*.parquet"):
        try:
            seasons.add(int(f.stem.replace("df_batters_", "")))
        except ValueError:
            continue
    for f in DATA_DIR.glob("df_pitchers_*.parquet"):
        try:
            seasons.add(int(f.stem.replace("df_pitchers_", "")))
        except ValueError:
            continue
    return sorted(seasons)


def load_season(season: int):
    """Lê os Parquets particionados de uma temporada específica."""
    b_path = DATA_DIR / f"df_batters_{season}.parquet"
    p_path = DATA_DIR / f"df_pitchers_{season}.parquet"
    db = pd.read_parquet(b_path) if b_path.exists() else pd.DataFrame()
    dp = pd.read_parquet(p_path) if p_path.exists() else pd.DataFrame()
    if not db.empty:
        db["RBI"] = db["RBI"].fillna(0).astype(int)
    if not dp.empty:
        dp["total_outs"] = dp["total_outs"].fillna(0).astype(int)
    return db, dp


def load_data():
    """Lê e concatena todas as temporadas disponíveis (usado só para
    construir a estrutura do HTML — filtros, anos disponíveis, etc.
    Os dados completos por temporada são lidos separadamente em main()
    para gerar os JSONs particionados sem manter tudo em memória)."""
    seasons = discover_seasons()
    b_parts, p_parts = [], []
    for season in seasons:
        db_s, dp_s = load_season(season)
        if not db_s.empty:
            b_parts.append(db_s)
        if not dp_s.empty:
            p_parts.append(dp_s)
    db = pd.concat(b_parts, ignore_index=True) if b_parts else pd.DataFrame(columns=["season"])
    dp = pd.concat(p_parts, ignore_index=True) if p_parts else pd.DataFrame(columns=["season"])
    return db, dp


def build_html(db: pd.DataFrame, dp: pd.DataFrame):
    MIN_PA_KPI = 200
    MIN_BF_KPI = 200

    seasons = sorted(set(
        db["season"].dropna().astype(int).unique().tolist() +
        dp["season"].dropna().astype(int).unique().tolist()
    ))
    seasons_opts = "".join(f'<option>{s}</option>' for s in seasons)
    latest_season = seasons[-1] if seasons else ""

    last_updated = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%b %d %Y, %H:%M")

    MONTH_NAMES = {
        "01": "January", "02": "February", "03": "March", "04": "April",
        "05": "May", "06": "June", "07": "July", "08": "August",
        "09": "September", "10": "October", "11": "November", "12": "December",
    }
    month_names_json = json.dumps(MONTH_NAMES, ensure_ascii=False)

    season = str(latest_season) if latest_season != "" else "2026"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stat Leaders · MLB (2022-present)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tabler-icons/3.1.0/iconfont/tabler-icons.min.css">
<style>
:root{{
  --bg:#0A0E14; --surface:#0F1520; --surface2:#131B28;
  --border:#1C2533; --border2:#26313F;
  --text:#E8EAED; --text2:#7A8699; --text3:#4A5568;
  --accent:#FF6B35; --accent-dim:#7A3D24;
  --hi:#3DDC97; --hi-dim:#1E5C44; --md:#E0A847; --lo:#7A8699; --bad:#E5484D;
  --row-hover:#131B28;
  --mono:'JetBrains Mono',monospace; --sans:'Inter',sans-serif;
}}
[data-theme="light"]{{
  --bg:#F5F4F1; --surface:#FFFFFF; --surface2:#FBFAF8;
  --border:#E2E0DA; --border2:#D2CFC6;
  --text:#1A1D23; --text2:#6B7280; --text3:#9CA3AF;
  --accent:#D8500F; --accent-dim:#FBE2D3;
  --hi:#0F9D63; --hi-dim:#D7F2E5; --md:#B45309; --lo:#9CA3AF; --bad:#C53030;
  --row-hover:#FBFAF8;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text);font-size:13px;-webkit-font-smoothing:antialiased;transition:background .15s,color .15s;display:flex;flex-direction:column}}

header{{height:52px;padding:0 1.5rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:1.25rem;flex-wrap:nowrap;position:sticky;top:0;background:var(--surface);z-index:20;flex-shrink:0}}
.title-block{{display:flex;align-items:baseline;gap:8px;white-space:nowrap}}
header h1{{font-family:var(--mono);font-size:13px;font-weight:600;letter-spacing:.5px;color:var(--text)}}
.last-updated{{font-family:var(--mono);font-size:11px;color:var(--text2);display:flex;align-items:center;gap:6px;white-space:nowrap}}
.live-dot{{width:6px;height:6px;border-radius:50%;background:var(--hi);box-shadow:0 0 0 3px var(--hi-dim);animation:pulse 2s infinite;flex-shrink:0}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
nav{{display:flex;gap:2px;margin-left:auto}}
.nav-btn{{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.5px;padding:6px 14px;border-radius:6px;border:1px solid transparent;background:transparent;color:var(--text2);cursor:pointer;transition:.15s;display:flex;align-items:center;gap:6px}}
.nav-btn:hover{{color:var(--text)}}
.nav-btn.active{{background:var(--accent-dim);color:var(--accent);border-color:var(--accent-dim)}}
.theme-toggle{{width:32px;height:32px;border-radius:6px;border:1px solid var(--border2);background:var(--surface2);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0;margin-left:12px}}
.theme-toggle:hover{{color:var(--accent);border-color:var(--accent)}}

.app{{display:flex;min-height:0;padding-bottom:52px}}
.filters-sidebar{{width:200px;background:var(--surface);border-right:1px solid var(--border);flex-shrink:0;padding:16px 14px;display:none}}
.filters-sidebar.active{{display:block}}
.fs-title{{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--text3);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--border)}}
.fg{{display:flex;flex-direction:column;gap:4px;margin-bottom:14px}}
.fg label{{font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.6px;color:var(--text3)}}
.fg-row{{display:flex;gap:8px}}
.fg-row .fg{{flex:1;margin-bottom:0}}
input,select{{width:100%;background:var(--surface2);border:1px solid var(--border2);color:var(--text);font-family:var(--mono);font-size:11px;padding:6px 8px;border-radius:4px;outline:none}}
input:hover,select:hover{{border-color:var(--text3)}}
input:focus,select:focus{{border-color:var(--accent)}}
select option{{background:var(--surface)}}
input::placeholder{{color:var(--text3)}}

.main{{flex:1;min-width:0}}
.page{{display:none;padding:18px 22px}}
.page.active{{display:block}}

.section-title{{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text2);margin:24px 0 10px;display:flex;align-items:center;gap:8px}}
.section-title:first-child{{margin-top:0}}
.section-title::after{{content:'';flex:1;height:1px;background:var(--border)}}
.section-title .yr{{color:var(--accent)}}
.section-title .min{{color:var(--text2)}}

.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:8px}}
.kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px 14px}}
.kpi-card .hd{{display:flex;align-items:center;gap:6px;margin-bottom:10px;color:var(--text2);font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-family:var(--mono)}}
.kpi-card .hd i{{font-size:14px;color:var(--accent)}}
.kpi-row{{display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:12px}}
.kpi-row .rank{{color:var(--text3);font-family:var(--mono);width:16px;font-size:11px}}
.kpi-row .name{{flex:1;color:var(--text);font-family:var(--mono)}}
.kpi-row .val{{font-family:var(--mono);font-weight:600;color:var(--text)}}
.kpi-row:first-child .val{{color:var(--accent)}}

.info-bar{{font-family:var(--mono);font-size:11px;color:var(--text2);margin-bottom:10px}}
footer{{height:52px;padding:0 1.5rem;border-top:1px solid var(--border);display:flex;align-items:center;gap:1.25rem;flex-wrap:nowrap;background:var(--surface);flex-shrink:0;position:fixed;bottom:0;left:0;right:0;z-index:20}}
.footer-text{{font-family:var(--mono);font-size:11px;color:var(--text2)}}
.footer-links{{display:flex;align-items:center;gap:16px;margin-left:auto}}
.footer-links a{{color:var(--text2);font-family:var(--mono);font-size:11px;text-decoration:none;transition:.15s}}
.footer-links a:hover{{color:var(--accent)}}
.info-bar b{{color:var(--text)}}

.wrap{{overflow-x:auto;border:1px solid var(--border);border-radius:6px}}
table{{width:100%;border-collapse:collapse;font-family:var(--mono);min-width:820px}}
thead th{{position:sticky;top:0;background:var(--surface);font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--text3);text-align:right;padding:8px 10px;border-bottom:1px solid var(--border2);cursor:pointer;user-select:none;white-space:nowrap}}
thead th:first-child,thead th:nth-child(2){{text-align:left}}
thead th:hover{{color:var(--text2)}}
th.asc::after{{content:' ↑';color:var(--accent)}}
th.desc::after{{content:' ↓';color:var(--accent)}}
tbody td{{text-align:right;padding:6px 10px;font-size:12px;border-bottom:1px solid var(--border);white-space:nowrap;font-variant-numeric:tabular-nums}}
tbody td:first-child{{text-align:right;color:var(--text3);font-size:11px}}
tbody td:nth-child(2){{text-align:left;color:var(--text);font-weight:500}}
tbody tr:hover{{background:var(--row-hover)}}
tbody tr:nth-child(even){{background:rgba(128,128,128,.02)}}
.hi{{color:var(--hi);font-weight:600}}
.md{{color:var(--text2);font-weight:500}}
.lo{{color:var(--bad)}}
.empty{{text-align:center;color:var(--text3);padding:3rem;font-size:14px;font-family:var(--mono)}}
</style>
</head>
<body>
<header>
  <div class="title-block">
    <h1>STAT LEADERS·MLB</h1>
    <span style="color:var(--text2);font-family:var(--mono);font-size:11px">2022—PRESENT</span>
  </div>
  <div class="last-updated"><span class="live-dot"></span>{last_updated}</div>
  <nav>
    <button class="nav-btn active" data-page="overview">Overview</button>
    <button class="nav-btn" data-page="bat">Batters</button>
    <button class="nav-btn" data-page="pit">Pitchers</button>
  </nav>
  <button class="theme-toggle" id="theme-toggle" aria-label="Toggle light/dark theme"><i class="ti ti-moon" aria-hidden="true" id="theme-icon"></i></button>
</header>
<div id="loading-bar" style="font-family:var(--mono);font-size:11px;color:var(--text2);padding:.5rem 1.5rem;border-bottom:1px solid var(--border)">Loading data...</div>

<div class="app">
  <div class="filters-sidebar" id="filters-bat">
    <div class="fs-title">Filters · Batters</div>
    <div class="fg"><label>Player</label><input id="b-q" placeholder="Search..."/></div>
    <div class="fg-row">
      <div class="fg"><label>Year</label><select id="b-season"><option value="all">All</option>{seasons_opts}</select></div>
      <div class="fg"><label>Min. PA</label><input id="b-mpa" type="number" value="10" min="1"/></div>
    </div>
    <div class="fg"><label>Game Type</label><select id="b-gt"><option value="">All</option><option value="R" selected>Regular Season</option><option value="playoffs">Playoffs</option></select></div>
    <div class="fg"><label>Round</label><select id="b-rd"><option value="">All</option></select></div>
    <div class="fg"><label>Month</label><select id="b-ref"><option value="">All</option></select></div>
    <div class="fg"><label>Team</label><select id="b-tm"><option value="">All</option></select></div>
    <div class="fg"><label>Opponent</label><select id="b-ft"><option value="">All</option></select></div>
    <div class="fg"><label>Venue</label><select id="b-vn"><option value="">All</option></select></div>
    <div class="fg-row">
      <div class="fg"><label>Bat Side</label><select id="b-bs"><option value="">Both</option><option value="R">Right (R)</option><option value="L">Left (L)</option></select></div>
      <div class="fg"><label>Split</label><select id="b-sp"><option value="">All</option><option value="vs_RHP">vs RHP</option><option value="vs_LHP">vs LHP</option></select></div>
    </div>
    <div class="fg-row">
      <div class="fg"><label>Situation</label><select id="b-mo"><option value="">All</option><option value="Empty">Empty</option><option value="Men_On">Men On</option><option value="RISP">RISP</option><option value="Loaded">Loaded</option></select></div>
      <div class="fg"><label>Home/Away</label><select id="b-ha"><option value="">All</option><option value="home">Home</option><option value="away">Away</option></select></div>
    </div>
  </div>

  <div class="filters-sidebar" id="filters-pit">
    <div class="fs-title">Filters · Pitchers</div>
    <div class="fg"><label>Pitcher</label><input id="p-q" placeholder="Search..."/></div>
    <div class="fg-row">
      <div class="fg"><label>Year</label><select id="p-season"><option value="all">All</option>{seasons_opts}</select></div>
      <div class="fg"><label>Min. BF</label><input id="p-mbf" type="number" value="10" min="1"/></div>
    </div>
    <div class="fg"><label>Game Type</label><select id="p-gt"><option value="">All</option><option value="R" selected>Regular Season</option><option value="playoffs">Playoffs</option></select></div>
    <div class="fg"><label>Round</label><select id="p-rd"><option value="">All</option></select></div>
    <div class="fg"><label>Month</label><select id="p-ref"><option value="">All</option></select></div>
    <div class="fg"><label>Team</label><select id="p-tm"><option value="">All</option></select></div>
    <div class="fg"><label>Opponent</label><select id="p-ft"><option value="">All</option></select></div>
    <div class="fg"><label>Venue</label><select id="p-vn"><option value="">All</option></select></div>
    <div class="fg-row">
      <div class="fg"><label>Hand</label><select id="p-ph"><option value="">Both</option><option value="R">Right (R)</option><option value="L">Left (L)</option></select></div>
      <div class="fg"><label>Split</label><select id="p-sp"><option value="">All</option><option value="vs_RHB">vs RHB</option><option value="vs_LHB">vs LHB</option></select></div>
    </div>
    <div class="fg-row">
      <div class="fg"><label>Situation</label><select id="p-mo"><option value="">All</option><option value="Empty">Empty</option><option value="Men_On">Men On</option><option value="RISP">RISP</option><option value="Loaded">Loaded</option></select></div>
      <div class="fg"><label>Home/Away</label><select id="p-ha"><option value="">All</option><option value="home">Home</option><option value="away">Away</option></select></div>
    </div>
  </div>

  <div class="main">
    <div class="page active" id="page-overview">
      <div class="section-title">Batting leaders<span class="yr">· {season} ·</span><span class="min">min. {MIN_PA_KPI} PA</span></div>
      <div class="kpi-grid" id="kpi-bat"></div>
      <div class="section-title">Pitching leaders<span class="yr">· {season} ·</span><span class="min">min. {MIN_BF_KPI} BF</span></div>
      <div class="kpi-grid" id="kpi-pit"></div>
    </div>

    <div class="page" id="page-bat">
      <div class="info-bar" id="b-info"></div>
      <div class="wrap"><table><thead id="b-thead"></thead><tbody id="b-tb"></tbody></table></div>
      <div class="empty" id="b-emp" style="display:none">No results found.</div>
    </div>

    <div class="page" id="page-pit">
      <div class="info-bar" id="p-info"></div>
      <div class="wrap"><table><thead id="p-thead"></thead><tbody id="p-tb"></tbody></table></div>
      <div class="empty" id="p-emp" style="display:none">No results found.</div>
    </div>
  </div>
</div>

<footer>
  <span class="footer-text">Built by Almir Lima Jr. · Data: MLB Stats API</span>
  <div class="footer-links">
    <a href="https://github.com/almirlimajr97/mlb_leaderboard" target="_blank" rel="noopener">GitHub</a>
    <a href="mailto:almirlimajr97@icloud.com">Email</a>
  </div>
</footer>

<script>
let BRAW=[], PRAW=[];
const SEASONS={json.dumps(seasons)};
const MONTH_NAMES={month_names_json};
let sortBatK='PA', sortBatAsc=false;
let sortPitK='BF', sortPitAsc=false;

// In-memory cache per season, so we never re-fetch the same year twice.
const batCache = {{}};
const pitCache = {{}};

async function fetchSeasonData(season){{
  if(!batCache[season]){{
    const [bRes, pRes] = await Promise.all([
      fetch(`data/batters_${{season}}.json`),
      fetch(`data/pitchers_${{season}}.json`),
    ]);
    batCache[season] = await bRes.json();
    pitCache[season] = await pRes.json();
  }}
}}

async function loadSeason(season){{
  if(season === 'all'){{
    await Promise.all(SEASONS.map(s=>fetchSeasonData(s)));
    BRAW = SEASONS.flatMap(s=>batCache[s]);
    PRAW = SEASONS.flatMap(s=>pitCache[s]);
  }} else {{
    await fetchSeasonData(season);
    BRAW = batCache[season];
    PRAW = pitCache[season];
  }}
}}

function refLabel(ref){{
  const s=String(ref);
  const yyyy=s.slice(0,4), mm=s.slice(4,6);
  return (MONTH_NAMES[mm]||mm)+'/'+yyyy;
}}

// Repopulates Month/Team/Opponent/Venue based on the selected Year,
// preserving the current selection when still valid (e.g. a team that
// exists in both years).
function refreshDependentFilters(prefix, rawData, teamField, oppField){{
  const seasonVal = document.getElementById(prefix+'-season').value;
  const scoped = (seasonVal && seasonVal !== 'all') ? rawData.filter(r=>String(r.season)===seasonVal) : rawData;

  const refSel = document.getElementById(prefix+'-ref');
  const curRef = refSel.value;
  const refs = [...new Set(scoped.map(r=>String(r.ref)))].sort();
  refSel.innerHTML = '<option value="">All</option>' +
    refs.map(r=>`<option value="${{r}}">${{refLabel(r)}}</option>`).join('');
  if(refs.includes(curRef)) refSel.value = curRef;

  const tmSel = document.getElementById(prefix+'-tm');
  const curTm = tmSel.value;
  const teams = [...new Set(scoped.map(r=>r[teamField]).filter(Boolean))].sort();
  tmSel.innerHTML = '<option value="">All</option>' +
    teams.map(t=>`<option>${{t}}</option>`).join('');
  if(teams.includes(curTm)) tmSel.value = curTm;

  const ftSel = document.getElementById(prefix+'-ft');
  const curFt = ftSel.value;
  const opps = [...new Set(scoped.map(r=>r[oppField]).filter(Boolean))].sort();
  ftSel.innerHTML = '<option value="">All</option>' +
    opps.map(t=>`<option>${{t}}</option>`).join('');
  if(opps.includes(curFt)) ftSel.value = curFt;

  const vnSel = document.getElementById(prefix+'-vn');
  const curVn = vnSel.value;
  const venues = [...new Set(scoped.map(r=>r.venue).filter(Boolean))].sort();
  vnSel.innerHTML = '<option value="">All</option>' +
    venues.map(v=>`<option>${{v}}</option>`).join('');
  if(venues.includes(curVn)) vnSel.value = curVn;

  // Round (series_description) is scoped by season AND the selected game
  // type, since it only meaningfully varies within Playoffs.
  const gtVal = document.getElementById(prefix+'-gt').value;
  const gtScoped = gtVal
    ? scoped.filter(r=> gtVal==='R' ? r.game_type==='R' : r.game_type!=='R')
    : scoped;
  const rdSel = document.getElementById(prefix+'-rd');
  const curRd = rdSel.value;
  const rounds = [...new Set(gtScoped.map(r=>r.series_description).filter(Boolean))].sort();
  rdSel.innerHTML = '<option value="">All</option>' +
    rounds.map(r=>`<option>${{r}}</option>`).join('');
  if(rounds.includes(curRd)) rdSel.value = curRd;
}}

function fmt3(v){{ return v===0?'.000':v.toFixed(3).replace('0.','.'); }}
function fmtPct(v){{ return (v*100).toFixed(1)+'%'; }}
function fmtIP(o){{ return Math.floor(o/3)+'.'+(o%3); }}
function cls(v,hi,md,inv=false){{
  if(inv) return v<=hi?'hi':v<=md?'md':'lo';
  return v>=hi?'hi':v>=md?'md':'lo';
}}

function aggBat(rows){{
  const m={{}};
  for(const r of rows){{
    const k=r.batter_id;
    if(!m[k]) m[k]={{batter:r.batter,games:new Set(),PA:0,AB:0,H:0,singles:0,doubles:0,triples:0,HR:0,RBI:0,BB:0,IBB:0,SO:0,HBP:0,SF:0}};
    const a=m[k];
    a.games.add(r.game_pk);
    a.PA+=r.PA;a.AB+=r.AB;a.H+=r.H;a.singles+=r.singles;
    a.doubles+=r.doubles;a.triples+=r.triples;a.HR+=r.HR;
    a.RBI+=r.RBI;a.BB+=r.BB;a.IBB+=r.IBB;a.SO+=r.SO;a.HBP+=r.HBP;a.SF+=r.SF;
  }}
  return Object.values(m).map(a=>{{
    const avg=a.AB>0?a.H/a.AB:0;
    const obp=(a.AB+a.BB+a.IBB+a.HBP+a.SF)>0?(a.H+a.BB+a.IBB+a.HBP)/(a.AB+a.BB+a.IBB+a.HBP+a.SF):0;
    const slg=a.AB>0?(a.singles+2*a.doubles+3*a.triples+4*a.HR)/a.AB:0;
    const bbpct=a.PA>0?(a.BB+a.IBB)/a.PA:0;
    const kpct=a.PA>0?a.SO/a.PA:0;
    const babipDenom=a.AB-a.SO-a.HR+a.SF;
    const babip=babipDenom>0?(a.H-a.HR)/babipDenom:0;
    return {{...a,G:a.games.size,AVG:+avg.toFixed(3),OBP:+obp.toFixed(3),SLG:+slg.toFixed(3),OPS:+(obp+slg).toFixed(3),BBpct:+bbpct.toFixed(3),Kpct:+kpct.toFixed(3),BABIP:+babip.toFixed(3),BBtotal:a.BB+a.IBB}};
  }});
}}

function aggPit(rows){{
  const m={{}};
  for(const r of rows){{
    const k=r.pitcher_id;
    if(!m[k]) m[k]={{pitcher:r.pitcher,games:new Set(),BF:0,AB:0,H:0,singles:0,doubles:0,triples:0,HR:0,BB:0,IBB:0,SO:0,HBP:0,SF:0,outs:0}};
    const a=m[k];
    a.games.add(r.game_pk);
    a.BF+=r.BF;a.AB+=r.AB;a.H+=r.H;a.singles+=r.singles;
    a.doubles+=r.doubles;a.triples+=r.triples;a.HR+=r.HR;
    a.BB+=r.BB;a.IBB+=r.IBB;a.SO+=r.SO;a.HBP+=r.HBP;a.SF+=r.SF;
    a.outs+=r.total_outs;
  }}
  return Object.values(m).map(a=>{{
    const baa=a.AB>0?a.H/a.AB:0;
    const obp=(a.AB+a.BB+a.IBB+a.HBP+a.SF)>0?(a.H+a.BB+a.IBB+a.HBP)/(a.AB+a.BB+a.IBB+a.HBP+a.SF):0;
    const slg=a.AB>0?(a.singles+2*a.doubles+3*a.triples+4*a.HR)/a.AB:0;
    const kpct=a.BF>0?a.SO/a.BF:0;
    const bbpct=a.BF>0?(a.BB+a.IBB)/a.BF:0;
    const ip=a.outs/3;
    const whip=ip>0?(a.BB+a.IBB+a.H)/ip:0;
    return {{...a,G:a.games.size,IP:fmtIP(a.outs),BAA:+baa.toFixed(3),OBP:+obp.toFixed(3),SLG:+slg.toFixed(3),OPS:+(obp+slg).toFixed(3),Kpct:+kpct.toFixed(3),BBpct:+bbpct.toFixed(3),WHIP:+whip.toFixed(2),BBtotal:a.BB+a.IBB}};
  }});
}}

const MIN_PA_KPI = {MIN_PA_KPI};
const MIN_BF_KPI = {MIN_BF_KPI};

function kpiCard(label, icon, sorted, key, fmt){{
  return `<div class="kpi-card">
    <div class="hd"><i class="ti ${{icon}}" aria-hidden="true"></i>${{label}}</div>
    ${{sorted.map((d,i)=>`<div class="kpi-row">
      <span class="rank">${{i+1}}</span><span class="name">${{d.batter||d.pitcher}}</span>
      <span class="val">${{fmt(d[key])}}</span>
    </div>`).join('')}}
  </div>`;
}}

function top5(rows,key,asc=false){{
  return [...rows].sort((a,b)=>asc?a[key]-b[key]:b[key]-a[key]).slice(0,5);
}}

function renderKPIs(){{
  const latestSeason = '{latest_season}';
  const batScoped = batCache[latestSeason] || [];
  const pitScoped = pitCache[latestSeason] || [];
  const batAgg = aggBat(batScoped).filter(a=>a.PA>=MIN_PA_KPI);
  const pitAgg = aggPit(pitScoped).filter(a=>a.BF>=MIN_BF_KPI);

  document.getElementById('kpi-bat').innerHTML = [
    kpiCard('OPS','ti-bolt',top5(batAgg,'OPS'),'OPS',fmt3),
    kpiCard('Hits (H)','ti-baseball-bat',top5(batAgg,'H'),'H',v=>v),
    kpiCard('Home runs','ti-ball-baseball',top5(batAgg,'HR'),'HR',v=>v),
    kpiCard('RBI','ti-flag',top5(batAgg,'RBI'),'RBI',v=>v),
  ].join('');

  document.getElementById('kpi-pit').innerHTML = [
    kpiCard('Innings (IP)','ti-clock',top5(pitAgg,'outs'),'outs',v=>fmtIP(v)),
    kpiCard('WHIP (lowest)','ti-shield',top5(pitAgg,'WHIP',true),'WHIP',v=>v.toFixed(2)),
    kpiCard('OPS against (lowest)','ti-shield-check',top5(pitAgg,'OPS',true),'OPS',fmt3),
    kpiCard('K%','ti-percentage',top5(pitAgg,'Kpct'),'Kpct',fmtPct),
  ].join('');
}}

function renderBat(){{
  refreshDependentFilters('b', BRAW, 'batting_team', 'fielding_team');
  const q=document.getElementById('b-q').value.toLowerCase();
  const season=document.getElementById('b-season').value;
  const ref=document.getElementById('b-ref').value;
  const gt=document.getElementById('b-gt').value;
  const rd=document.getElementById('b-rd').value;
  const tm=document.getElementById('b-tm').value;
  const ft=document.getElementById('b-ft').value;
  const vn=document.getElementById('b-vn').value;
  const bs=document.getElementById('b-bs').value;
  const sp=document.getElementById('b-sp').value;
  const mo=document.getElementById('b-mo').value;
  const ha=document.getElementById('b-ha').value;
  const mpa=+document.getElementById('b-mpa').value||1;

  let rows=BRAW.filter(r=>
    (!q||r.batter.toLowerCase().includes(q))&&
    (!season||season==='all'||String(r.season)===season)&&(!ref||String(r.ref)===ref)&&
    (!gt||(gt==='R'?r.game_type==='R':r.game_type!=='R'))&&(!rd||r.series_description===rd)&&
    (!tm||r.batting_team===tm)&&(!ft||r.fielding_team===ft)&&(!vn||r.venue===vn)&&
    (!bs||r.bat_side===bs)&&(!sp||r.batter_split===sp)&&
    (!mo||r.men_on_base===mo)&&(!ha||r.home_away_batting===ha)
  );
  let data=aggBat(rows).filter(a=>a.PA>=mpa);
  data.sort((a,b)=>{{let av=a[sortBatK],bv=b[sortBatK];if(typeof av==='string'){{av=av.toLowerCase();bv=bv.toLowerCase();}}return sortBatAsc?(av>bv?1:-1):(av<bv?1:-1);}});

  document.getElementById('b-info').innerHTML=`Showing <b>${{data.length}}</b> players · Min. <b>${{mpa}} PA</b>`;

  document.getElementById('b-thead').innerHTML=`<tr>
    <th data-k="rank">#</th><th data-k="batter">Player</th>
    <th data-k="PA">PA</th><th data-k="AB">AB</th><th data-k="H">H</th>
    <th data-k="doubles">2B</th><th data-k="triples">3B</th><th data-k="HR">HR</th>
    <th data-k="RBI">RBI</th><th data-k="BBtotal">BB</th><th data-k="IBB">IBB</th>
    <th data-k="SO">K</th><th data-k="HBP">HBP</th><th data-k="SF">SF</th>
    <th data-k="AVG">AVG</th><th data-k="OBP">OBP</th><th data-k="SLG">SLG</th>
    <th data-k="OPS">OPS</th><th data-k="BABIP">BABIP</th><th data-k="BBpct">BB%</th><th data-k="Kpct">K%</th>
  </tr>`;
  bindSortBat();

  const emp=document.getElementById('b-emp');
  if(!data.length){{document.getElementById('b-tb').innerHTML='';emp.style.display='block';return;}}
  emp.style.display='none';
  document.getElementById('b-tb').innerHTML=data.map((d,i)=>`<tr>
    <td>${{i+1}}</td><td>${{d.batter}}</td>
    <td>${{d.PA}}</td><td>${{d.AB}}</td><td>${{d.H}}</td>
    <td>${{d.doubles}}</td><td>${{d.triples}}</td><td>${{d.HR}}</td>
    <td>${{d.RBI}}</td><td>${{d.BBtotal}}</td><td>${{d.IBB}}</td>
    <td>${{d.SO}}</td><td>${{d.HBP}}</td><td>${{d.SF}}</td>
    <td class="${{cls(d.AVG,.3,.22)}}">${{fmt3(d.AVG)}}</td>
    <td class="${{cls(d.OBP,.36,.30)}}">${{fmt3(d.OBP)}}</td>
    <td class="${{cls(d.SLG,.45,.35)}}">${{fmt3(d.SLG)}}</td>
    <td class="${{cls(d.OPS,.8,.7)}}">${{fmt3(d.OPS)}}</td>
    <td class="${{cls(d.BABIP,.320,.290)}}">${{fmt3(d.BABIP)}}</td>
    <td class="${{cls(d.BBpct,.12,.07)}}">${{fmtPct(d.BBpct)}}</td>
    <td class="${{cls(d.Kpct,.18,.30,true)}}">${{fmtPct(d.Kpct)}}</td>
  </tr>`).join('');
}}

function bindSortBat(){{
  document.querySelectorAll('#b-thead th[data-k]').forEach(th=>{{
    th.addEventListener('click',()=>{{
      const k=th.dataset.k; if(k==='rank') return;
      if(sortBatK===k) sortBatAsc=!sortBatAsc; else{{sortBatK=k;sortBatAsc=false;}}
      renderBat();
    }});
  }});
  const th=document.querySelector(`#b-thead th[data-k="${{sortBatK}}"]`);
  if(th) th.className=sortBatAsc?'asc':'desc';
}}

function renderPit(){{
  refreshDependentFilters('p', PRAW, 'fielding_team', 'batting_team');
  const q=document.getElementById('p-q').value.toLowerCase();
  const season=document.getElementById('p-season').value;
  const ref=document.getElementById('p-ref').value;
  const gt=document.getElementById('p-gt').value;
  const rd=document.getElementById('p-rd').value;
  const tm=document.getElementById('p-tm').value;
  const ft=document.getElementById('p-ft').value;
  const vn=document.getElementById('p-vn').value;
  const ph=document.getElementById('p-ph').value;
  const sp=document.getElementById('p-sp').value;
  const mo=document.getElementById('p-mo').value;
  const ha=document.getElementById('p-ha').value;
  const mbf=+document.getElementById('p-mbf').value||1;

  let rows=PRAW.filter(r=>
    (!q||r.pitcher.toLowerCase().includes(q))&&
    (!season||season==='all'||String(r.season)===season)&&(!ref||String(r.ref)===ref)&&
    (!gt||(gt==='R'?r.game_type==='R':r.game_type!=='R'))&&(!rd||r.series_description===rd)&&
    (!tm||r.fielding_team===tm)&&(!ft||r.batting_team===ft)&&(!vn||r.venue===vn)&&
    (!ph||r.pitch_hand===ph)&&(!sp||r.pitcher_split===sp)&&
    (!mo||r.men_on_base===mo)&&(!ha||r.home_away_pitching===ha)
  );
  let data=aggPit(rows).filter(a=>a.BF>=mbf);
  data.sort((a,b)=>{{
    const sk=sortPitK==='IP'?'outs':sortPitK;
    let av=a[sk],bv=b[sk];
    if(typeof av==='string'){{av=av.toLowerCase();bv=bv.toLowerCase();}}
    return sortPitAsc?(av>bv?1:-1):(av<bv?1:-1);
  }});

  document.getElementById('p-info').innerHTML=`Showing <b>${{data.length}}</b> pitchers · Min. <b>${{mbf}} BF</b>`;

  document.getElementById('p-thead').innerHTML=`<tr>
    <th data-k="rank">#</th><th data-k="pitcher">Pitcher</th>
    <th data-k="G">G</th><th data-k="IP">IP</th><th data-k="BF">BF</th><th data-k="AB">AB</th>
    <th data-k="H">H</th><th data-k="doubles">2B</th><th data-k="triples">3B</th><th data-k="HR">HR</th>
    <th data-k="BBtotal">BB</th><th data-k="IBB">IBB</th><th data-k="SO">K</th>
    <th data-k="HBP">HBP</th><th data-k="SF">SF</th>
    <th data-k="BAA">BAA</th><th data-k="OBP">OBP</th><th data-k="SLG">SLG</th>
    <th data-k="OPS">OPS</th><th data-k="WHIP">WHIP</th><th data-k="BBpct">BB%</th><th data-k="Kpct">K%</th>
  </tr>`;
  bindSortPit();

  const emp=document.getElementById('p-emp');
  if(!data.length){{document.getElementById('p-tb').innerHTML='';emp.style.display='block';return;}}
  emp.style.display='none';
  document.getElementById('p-tb').innerHTML=data.map((d,i)=>`<tr>
    <td>${{i+1}}</td><td>${{d.pitcher}}</td>
    <td>${{d.G}}</td><td>${{d.IP}}</td><td>${{d.BF}}</td><td>${{d.AB}}</td>
    <td>${{d.H}}</td><td>${{d.doubles}}</td><td>${{d.triples}}</td><td>${{d.HR}}</td>
    <td>${{d.BBtotal}}</td><td>${{d.IBB}}</td><td>${{d.SO}}</td>
    <td>${{d.HBP}}</td><td>${{d.SF}}</td>
    <td class="${{cls(d.BAA,.22,.30,true)}}">${{fmt3(d.BAA)}}</td>
    <td class="${{cls(d.OBP,.30,.36,true)}}">${{fmt3(d.OBP)}}</td>
    <td class="${{cls(d.SLG,.35,.45,true)}}">${{fmt3(d.SLG)}}</td>
    <td class="${{cls(d.OPS,.7,.8,true)}}">${{fmt3(d.OPS)}}</td>
    <td class="${{cls(d.WHIP,1.10,1.30,true)}}">${{d.WHIP.toFixed(2)}}</td>
    <td class="${{cls(d.BBpct,.08,.1,true)}}">${{fmtPct(d.BBpct)}}</td>
    <td class="${{cls(d.Kpct,.25,.18)}}">${{fmtPct(d.Kpct)}}</td>
  </tr>`).join('');
}}

function bindSortPit(){{
  document.querySelectorAll('#p-thead th[data-k]').forEach(th=>{{
    th.addEventListener('click',()=>{{
      const k=th.dataset.k; if(k==='rank') return;
      if(sortPitK===k) sortPitAsc=!sortPitAsc; else{{sortPitK=k;sortPitAsc=false;}}
      renderPit();
    }});
  }});
  const th=document.querySelector(`#p-thead th[data-k="${{sortPitK}}"]`);
  if(th) th.className=sortPitAsc?'asc':'desc';
}}

document.querySelectorAll('.nav-btn').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    document.querySelectorAll('.filters-sidebar').forEach(f=>f.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('page-'+btn.dataset.page).classList.add('active');
    const fs = document.getElementById('filters-'+btn.dataset.page);
    if(fs) fs.classList.add('active');
  }});
}});

const themeToggle = document.getElementById('theme-toggle');
const themeIcon = document.getElementById('theme-icon');
function applyTheme(t){{
  document.documentElement.setAttribute('data-theme', t);
  themeIcon.className = t==='light' ? 'ti ti-sun' : 'ti ti-moon';
}}
const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
applyTheme(prefersLight ? 'light' : 'dark');
themeToggle.addEventListener('click', ()=>{{
  const cur = document.documentElement.getAttribute('data-theme');
  applyTheme(cur==='light' ? 'dark' : 'light');
}});

['b-q','b-ref','b-gt','b-rd','b-tm','b-ft','b-vn','b-bs','b-sp','b-mo','b-ha','b-mpa'].forEach(id=>
  document.getElementById(id).addEventListener('input',renderBat)
);
['p-q','p-ref','p-gt','p-rd','p-tm','p-ft','p-vn','p-ph','p-sp','p-mo','p-ha','p-mbf'].forEach(id=>
  document.getElementById(id).addEventListener('input',renderPit)
);

document.getElementById('b-season').value = '{latest_season}';
document.getElementById('p-season').value = '{latest_season}';

let currentSeason = '{latest_season}';

async function switchSeason(season){{
  currentSeason = season;
  document.getElementById('loading-bar').style.display = 'block';
  document.getElementById('loading-bar').textContent = season === 'all'
    ? 'Loading all seasons...'
    : `Loading ${{season}} season...`;
  try {{
    await loadSeason(season);
  }} catch(e) {{
    document.getElementById('loading-bar').textContent = 'Error loading data.';
    console.error('Error loading data:', e);
    return;
  }}
  document.getElementById('loading-bar').style.display = 'none';
  renderKPIs();
  renderBat();
  renderPit();
}}

document.getElementById('b-season').addEventListener('change', (e)=>{{
  document.getElementById('p-season').value = e.target.value;
  switchSeason(e.target.value);
}});
document.getElementById('p-season').addEventListener('change', (e)=>{{
  document.getElementById('b-season').value = e.target.value;
  switchSeason(e.target.value);
}});

switchSeason(currentSeason);
</script>
</body>
</html>"""

    return html, seasons


def main():
    print("Carregando dados...")
    db, dp = load_data()

    print("Gerando HTML...")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUT_DIR = DOCS_DIR / "data"
    DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)

    html, seasons = build_html(db, dp)

    out_html = DOCS_DIR / "index.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"  Salvo em {out_html} ({len(html):,} chars)")

    print("Gerando dados por temporada...")
    for season in seasons:
        db_s, dp_s = load_season(season)

        b_records = db_s[[c for c in B_COLS if c in db_s.columns]].to_dict(orient="records") if not db_s.empty else []
        p_records = dp_s[[c for c in P_COLS if c in dp_s.columns]].to_dict(orient="records") if not dp_s.empty else []

        out_bat = DATA_OUT_DIR / f"batters_{season}.json"
        out_bat.write_text(json.dumps(b_records, ensure_ascii=False), encoding="utf-8")

        out_pit = DATA_OUT_DIR / f"pitchers_{season}.json"
        out_pit.write_text(json.dumps(p_records, ensure_ascii=False), encoding="utf-8")

        print(f"  {season}: batters={out_bat.stat().st_size/1024/1024:.1f}MB, "
              f"pitchers={out_pit.stat().st_size/1024/1024:.1f}MB")


if __name__ == "__main__":
    main()
