"""
build_html.py
-------------
Lê data/df_batters.csv e data/df_pitchers.csv e gera docs/index.html
no formato de dashboard: cards de líderes na visão geral + abas com
tabelas completas de batters e pitchers (agregados por jogador, sem
quebra por time, já que jogadores podem ser trocados durante a temporada).

Uso:
    python scripts/build_html.py
"""

import json
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"


def load_data():
    db = pd.read_csv(DATA_DIR / "df_batters.csv",  low_memory=False)
    dp = pd.read_csv(DATA_DIR / "df_pitchers.csv", low_memory=False)
    db["RBI"]        = db["RBI"].fillna(0).astype(int)
    dp["total_outs"] = dp["total_outs"].fillna(0).astype(int)
    return db, dp


def build_html(db: pd.DataFrame, dp: pd.DataFrame) -> str:
    seasons = sorted(set(
        db["season"].dropna().astype(int).unique().tolist() +
        dp["season"].dropna().astype(int).unique().tolist()
    ))
    seasons_opts = "".join(f'<option>{s}</option>' for s in seasons)
    latest_season = seasons[-1] if seasons else ""

    MONTH_NAMES = {
        "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
        "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
        "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro",
    }
    month_names_json = json.dumps(MONTH_NAMES, ensure_ascii=False)

    b_cols = ["game_pk", "season", "ref", "batting_team", "fielding_team", "batter", "bat_side", "batter_split",
              "men_on_base", "pitcher", "day_night", "home_away_batting",
              "PA", "AB", "H", "singles", "doubles", "triples", "HR",
              "RBI", "BB", "IBB", "SO", "HBP", "SF"]
    p_cols = ["game_pk", "season", "ref", "fielding_team", "batting_team", "pitcher", "pitch_hand", "pitcher_split",
              "men_on_base", "batter", "day_night", "home_away_pitching",
              "BF", "AB", "H", "singles", "doubles", "triples", "HR",
              "BB", "IBB", "SO", "HBP", "SF", "total_outs"]

    b_json = db[[c for c in b_cols if c in db.columns]].to_json(orient="records", force_ascii=False)
    p_json = dp[[c for c in p_cols if c in dp.columns]].to_json(orient="records", force_ascii=False)

    season = str(db["season"].iloc[0]) if "season" in db.columns else "2026"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MLB Stats {season}</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tabler-icons/3.1.0/iconfont/tabler-icons.min.css">
<style>
:root{{
  --bg:#0a1628; --surface:#0f2138; --surface2:#142a45; --border:rgba(255,255,255,.08);
  --border2:rgba(255,255,255,.14); --text:#e8eaf0; --text2:#8892a4; --text3:#5a6478;
  --accent:#f5c518; --accent-dim:rgba(245,197,24,.12);
  --hi:#16a34a; --md:#ca8a04; --lo:#dc2626;
  --row-hover:rgba(245,197,24,.06);
}}
[data-theme="light"]{{
  --bg:#f7f8fa; --surface:#ffffff; --surface2:#f1f3f6; --border:rgba(10,22,40,.10);
  --border2:rgba(10,22,40,.16); --text:#0f1a2b; --text2:#5a6478; --text3:#8892a4;
  --accent:#b8860b; --accent-dim:rgba(184,134,11,.10);
  --hi:#16a34a; --md:#b45309; --lo:#dc2626;
  --row-hover:rgba(184,134,11,.06);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;transition:background .15s,color .15s}}

header{{padding:1.1rem 2rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);z-index:20}}
header h1{{font-size:1.15rem;font-weight:600;color:var(--accent);display:flex;align-items:center;gap:8px;white-space:nowrap}}
nav{{display:flex;gap:4px;margin-left:auto}}
.nav-btn{{padding:7px 16px;border-radius:8px;border:1px solid transparent;background:transparent;color:var(--text2);font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;display:flex;align-items:center;gap:6px}}
.nav-btn:hover{{color:var(--text);background:rgba(128,128,128,.08)}}
.nav-btn.active{{background:var(--accent-dim);color:var(--accent);border-color:var(--accent)}}
.theme-toggle{{width:34px;height:34px;border-radius:8px;border:1px solid var(--border2);background:var(--surface2);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}}
.theme-toggle:hover{{color:var(--accent);border-color:var(--accent)}}

.page{{display:none;padding:1.5rem 2rem 3rem}}
.page.active{{display:block}}

.section-title{{font-size:13px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:.06em;margin:2rem 0 .9rem}}
.section-title:first-child{{margin-top:0}}

.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
.kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.1rem 1.25rem;position:relative;overflow:hidden}}
.kpi-card .kpi-icon{{position:absolute;right:14px;top:14px;font-size:22px;color:var(--border2)}}
.kpi-label{{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:.06em;font-weight:600;margin-bottom:10px}}
.kpi-row{{display:flex;align-items:baseline;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border)}}
.kpi-row:last-child{{border-bottom:none}}
.kpi-name{{font-size:13.5px;color:var(--text);font-weight:500}}
.kpi-value{{font-size:14px;color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums}}
.kpi-rank{{font-size:11px;color:var(--text3);width:16px;display:inline-block}}

.filters{{display:flex;gap:10px;padding:.8rem 0 1.1rem;flex-wrap:wrap;align-items:flex-end;border-bottom:1px solid var(--border);margin-bottom:1rem}}
.fg{{display:flex;flex-direction:column;gap:3px}}
.fg label{{font-size:10.5px;color:var(--text2);text-transform:uppercase;letter-spacing:.05em}}
input,select{{background:var(--surface2);border:1px solid var(--border2);color:var(--text);padding:6px 10px;border-radius:6px;font-size:13px;outline:none}}
input:focus,select:focus{{border-color:var(--accent)}}
select option{{background:var(--surface)}}
input::placeholder{{color:var(--text3)}}

.info-bar{{font-size:12px;color:var(--text2);padding-bottom:.7rem}}
.info-bar b{{color:var(--accent)}}

.wrap{{overflow-x:auto;border:1px solid var(--border);border-radius:10px}}
table{{width:100%;border-collapse:collapse;font-size:13px;min-width:820px}}
thead tr{{background:var(--surface)}}
th{{padding:9px 12px;text-align:right;font-weight:600;color:var(--text2);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;cursor:pointer;user-select:none;background:var(--surface)}}
th:first-child,th:nth-child(2){{text-align:left}}
th:hover{{color:var(--accent)}}
th.asc::after{{content:' ↑';color:var(--accent)}}
th.desc::after{{content:' ↓';color:var(--accent)}}
tbody tr{{border-top:1px solid var(--border)}}
tbody tr:hover{{background:var(--row-hover)}}
td{{padding:8px 12px;text-align:right;color:var(--text);font-variant-numeric:tabular-nums}}
td:first-child{{text-align:left;color:var(--text3);font-size:11px}}
td:nth-child(2){{text-align:left;font-weight:500;color:var(--text);white-space:nowrap}}
.hi{{color:var(--hi);font-weight:600}}
.md{{color:var(--md);font-weight:500}}
.lo{{color:var(--lo)}}
.empty{{text-align:center;color:var(--text3);padding:3rem;font-size:14px}}
</style>
</head>
<body>
<header>
  <h1><i class="ti ti-baseball" aria-hidden="true"></i>MLB Stats {season}</h1>
  <nav>
    <button class="nav-btn active" data-page="overview"><i class="ti ti-layout-dashboard" aria-hidden="true"></i>Visão geral</button>
    <button class="nav-btn" data-page="bat"><i class="ti ti-baseball-bat" aria-hidden="true"></i>Batters</button>
    <button class="nav-btn" data-page="pit"><i class="ti ti-circle-dot" aria-hidden="true"></i>Pitchers</button>
  </nav>
  <button class="theme-toggle" id="theme-toggle" aria-label="Alternar tema claro/escuro"><i class="ti ti-moon" aria-hidden="true" id="theme-icon"></i></button>
</header>

<div class="page active" id="page-overview">
  <div class="section-title">Líderes — batting</div>
  <div class="kpi-grid" id="kpi-bat"></div>
  <div class="section-title">Líderes — pitching</div>
  <div class="kpi-grid" id="kpi-pit"></div>
</div>

<div class="page" id="page-bat">
  <div class="filters">
    <div class="fg"><label>Jogador</label><input id="b-q" placeholder="Buscar..."/></div>
    <div class="fg"><label>Ano</label><select id="b-season">{seasons_opts}</select></div>
    <div class="fg"><label>Mês</label><select id="b-ref"><option value="">Todos</option></select></div>
    <div class="fg"><label>Time (bat)</label><select id="b-tm"><option value="">Todos</option></select></div>
    <div class="fg"><label>Adversário</label><select id="b-ft"><option value="">Todos</option></select></div>
    <div class="fg"><label>Lado</label><select id="b-bs"><option value="">Ambos</option><option value="R">Direita (R)</option><option value="L">Esquerda (L)</option></select></div>
    <div class="fg"><label>Split</label><select id="b-sp"><option value="">Todos</option><option value="vs_RHP">vs RHP</option><option value="vs_LHP">vs LHP</option></select></div>
    <div class="fg"><label>Situação</label><select id="b-mo"><option value="">Todas</option><option value="Empty">Empty</option><option value="Men_On">Men On</option><option value="RISP">RISP</option><option value="Loaded">Loaded</option></select></div>
    <div class="fg"><label>Home/Away</label><select id="b-ha"><option value="">Todos</option><option value="home">Home</option><option value="away">Away</option></select></div>
    <div class="fg"><label>Mín. PA</label><input id="b-mpa" type="number" value="10" min="1" style="width:65px"/></div>
  </div>
  <div class="info-bar" id="b-info"></div>
  <div class="wrap"><table><thead id="b-thead"></thead><tbody id="b-tb"></tbody></table></div>
  <div class="empty" id="b-emp" style="display:none">Nenhum resultado encontrado.</div>
</div>

<div class="page" id="page-pit">
  <div class="filters">
    <div class="fg"><label>Pitcher</label><input id="p-q" placeholder="Buscar..."/></div>
    <div class="fg"><label>Ano</label><select id="p-season">{seasons_opts}</select></div>
    <div class="fg"><label>Mês</label><select id="p-ref"><option value="">Todos</option></select></div>
    <div class="fg"><label>Time (pit)</label><select id="p-tm"><option value="">Todos</option></select></div>
    <div class="fg"><label>Adversário</label><select id="p-ft"><option value="">Todos</option></select></div>
    <div class="fg"><label>Mão</label><select id="p-ph"><option value="">Ambas</option><option value="R">Direita (R)</option><option value="L">Esquerda (L)</option></select></div>
    <div class="fg"><label>Split</label><select id="p-sp"><option value="">Todos</option><option value="vs_RHB">vs RHB</option><option value="vs_LHB">vs LHB</option></select></div>
    <div class="fg"><label>Situação</label><select id="p-mo"><option value="">Todas</option><option value="Empty">Empty</option><option value="Men_On">Men On</option><option value="RISP">RISP</option><option value="Loaded">Loaded</option></select></div>
    <div class="fg"><label>Home/Away</label><select id="p-ha"><option value="">Todos</option><option value="home">Home</option><option value="away">Away</option></select></div>
    <div class="fg"><label>Mín. BF</label><input id="p-mbf" type="number" value="10" min="1" style="width:65px"/></div>
  </div>
  <div class="info-bar" id="p-info"></div>
  <div class="wrap"><table><thead id="p-thead"></thead><tbody id="p-tb"></tbody></table></div>
  <div class="empty" id="p-emp" style="display:none">Nenhum resultado encontrado.</div>
</div>

<script>
const BRAW={b_json};
const PRAW={p_json};
const MONTH_NAMES={month_names_json};
let sortBatK='PA', sortBatAsc=false;
let sortPitK='BF', sortPitAsc=false;

function refLabel(ref){{
  const s=String(ref);
  const yyyy=s.slice(0,4), mm=s.slice(4,6);
  return (MONTH_NAMES[mm]||mm)+'/'+yyyy;
}}

// Repopula Mês/Time/Adversário com base no Ano selecionado, preservando
// a seleção atual quando ainda válida (ex: time que existe nos dois anos).
function refreshDependentFilters(prefix, rawData, teamField, oppField){{
  const seasonVal = document.getElementById(prefix+'-season').value;
  const scoped = seasonVal ? rawData.filter(r=>String(r.season)===seasonVal) : rawData;

  const refSel = document.getElementById(prefix+'-ref');
  const curRef = refSel.value;
  const refs = [...new Set(scoped.map(r=>String(r.ref)))].sort();
  refSel.innerHTML = '<option value="">Todos</option>' +
    refs.map(r=>`<option value="${{r}}">${{refLabel(r)}}</option>`).join('');
  if(refs.includes(curRef)) refSel.value = curRef;

  const tmSel = document.getElementById(prefix+'-tm');
  const curTm = tmSel.value;
  const teams = [...new Set(scoped.map(r=>r[teamField]).filter(Boolean))].sort();
  tmSel.innerHTML = '<option value="">Todos</option>' +
    teams.map(t=>`<option>${{t}}</option>`).join('');
  if(teams.includes(curTm)) tmSel.value = curTm;

  const ftSel = document.getElementById(prefix+'-ft');
  const curFt = ftSel.value;
  const opps = [...new Set(scoped.map(r=>r[oppField]).filter(Boolean))].sort();
  ftSel.innerHTML = '<option value="">Todos</option>' +
    opps.map(t=>`<option>${{t}}</option>`).join('');
  if(opps.includes(curFt)) ftSel.value = curFt;
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
    const k=r.batter;
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
    return {{...a,G:a.games.size,AVG:+avg.toFixed(3),OBP:+obp.toFixed(3),SLG:+slg.toFixed(3),OPS:+(obp+slg).toFixed(3)}};
  }});
}}

function aggPit(rows){{
  const m={{}};
  for(const r of rows){{
    const k=r.pitcher;
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
    return {{...a,G:a.games.size,IP:fmtIP(a.outs),BAA:+baa.toFixed(3),OBP:+obp.toFixed(3),SLG:+slg.toFixed(3),OPS:+(obp+slg).toFixed(3),Kpct:+kpct.toFixed(3),BBpct:+bbpct.toFixed(3)}};
  }});
}}

const MIN_PA_KPI = 15;
const MIN_BF_KPI = 15;

function kpiCard(label, icon, sorted, key, fmt){{
  return `<div class="kpi-card">
    <i class="ti ${{icon}} kpi-icon" aria-hidden="true"></i>
    <div class="kpi-label">${{label}}</div>
    ${{sorted.map((d,i)=>`<div class="kpi-row">
      <span><span class="kpi-rank">${{i+1}}</span><span class="kpi-name">${{d.batter||d.pitcher}}</span></span>
      <span class="kpi-value">${{fmt(d[key])}}</span>
    </div>`).join('')}}
  </div>`;
}}

function top5(rows,key,asc=false){{
  return [...rows].sort((a,b)=>asc?a[key]-b[key]:b[key]-a[key]).slice(0,5);
}}

function renderKPIs(){{
  const latestSeason = '{latest_season}';
  const batScoped = BRAW.filter(r=>String(r.season)===latestSeason);
  const pitScoped = PRAW.filter(r=>String(r.season)===latestSeason);
  const batAgg = aggBat(batScoped).filter(a=>a.PA>=MIN_PA_KPI);
  const pitAgg = aggPit(pitScoped).filter(a=>a.BF>=MIN_BF_KPI);

  document.getElementById('kpi-bat').innerHTML = [
    kpiCard('Home runs','ti-ball-baseball',top5(batAgg,'HR'),'HR',v=>v),
    kpiCard('Average (AVG)','ti-chart-bar',top5(batAgg,'AVG'),'AVG',fmt3),
    kpiCard('OPS','ti-bolt',top5(batAgg,'OPS'),'OPS',fmt3),
    kpiCard('RBI','ti-flag',top5(batAgg,'RBI'),'RBI',v=>v),
  ].join('');

  document.getElementById('kpi-pit').innerHTML = [
    kpiCard('Strikeouts (K)','ti-target',top5(pitAgg,'SO'),'SO',v=>v),
    kpiCard('K%','ti-percentage',top5(pitAgg,'Kpct'),'Kpct',fmtPct),
    kpiCard('BAA (menor)','ti-shield',top5(pitAgg,'BAA',true),'BAA',fmt3),
    kpiCard('Innings (IP)','ti-clock',top5(pitAgg,'outs'),'outs',v=>fmtIP(v)),
  ].join('');
}}

function renderBat(){{
  refreshDependentFilters('b', BRAW, 'batting_team', 'fielding_team');
  const q=document.getElementById('b-q').value.toLowerCase();
  const season=document.getElementById('b-season').value;
  const ref=document.getElementById('b-ref').value;
  const tm=document.getElementById('b-tm').value;
  const ft=document.getElementById('b-ft').value;
  const bs=document.getElementById('b-bs').value;
  const sp=document.getElementById('b-sp').value;
  const mo=document.getElementById('b-mo').value;
  const ha=document.getElementById('b-ha').value;
  const mpa=+document.getElementById('b-mpa').value||1;

  let rows=BRAW.filter(r=>
    (!q||r.batter.toLowerCase().includes(q))&&
    (!season||String(r.season)===season)&&(!ref||String(r.ref)===ref)&&
    (!tm||r.batting_team===tm)&&(!ft||r.fielding_team===ft)&&
    (!bs||r.bat_side===bs)&&(!sp||r.batter_split===sp)&&
    (!mo||r.men_on_base===mo)&&(!ha||r.home_away_batting===ha)
  );
  let data=aggBat(rows).filter(a=>a.PA>=mpa);
  data.sort((a,b)=>{{let av=a[sortBatK],bv=b[sortBatK];if(typeof av==='string'){{av=av.toLowerCase();bv=bv.toLowerCase();}}return sortBatAsc?(av>bv?1:-1):(av<bv?1:-1);}});

  document.getElementById('b-info').innerHTML=`Exibindo <b>${{data.length}}</b> jogadores · <b>${{rows.length}}</b> linhas · Mín. <b>${{mpa}} PA</b>`;

  document.getElementById('b-thead').innerHTML=`<tr>
    <th data-k="rank">#</th><th data-k="batter">Jogador</th>
    <th data-k="PA">PA</th><th data-k="AB">AB</th><th data-k="H">H</th>
    <th data-k="doubles">2B</th><th data-k="triples">3B</th><th data-k="HR">HR</th>
    <th data-k="RBI">RBI</th><th data-k="BB">BB</th><th data-k="IBB">IBB</th>
    <th data-k="SO">K</th><th data-k="HBP">HBP</th><th data-k="SF">SF</th>
    <th data-k="AVG">AVG</th><th data-k="OBP">OBP</th><th data-k="SLG">SLG</th><th data-k="OPS">OPS</th>
  </tr>`;
  bindSortBat();

  const emp=document.getElementById('b-emp');
  if(!data.length){{document.getElementById('b-tb').innerHTML='';emp.style.display='block';return;}}
  emp.style.display='none';
  document.getElementById('b-tb').innerHTML=data.map((d,i)=>`<tr>
    <td>${{i+1}}</td><td>${{d.batter}}</td>
    <td>${{d.PA}}</td><td>${{d.AB}}</td><td>${{d.H}}</td>
    <td>${{d.doubles}}</td><td>${{d.triples}}</td><td>${{d.HR}}</td>
    <td>${{d.RBI}}</td><td>${{d.BB}}</td><td>${{d.IBB}}</td>
    <td>${{d.SO}}</td><td>${{d.HBP}}</td><td>${{d.SF}}</td>
    <td class="${{cls(d.AVG,.3,.22)}}">${{fmt3(d.AVG)}}</td>
    <td class="${{cls(d.OBP,.36,.30)}}">${{fmt3(d.OBP)}}</td>
    <td class="${{cls(d.SLG,.45,.35)}}">${{fmt3(d.SLG)}}</td>
    <td class="${{cls(d.OPS,.9,.7)}}">${{fmt3(d.OPS)}}</td>
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
  const tm=document.getElementById('p-tm').value;
  const ft=document.getElementById('p-ft').value;
  const ph=document.getElementById('p-ph').value;
  const sp=document.getElementById('p-sp').value;
  const mo=document.getElementById('p-mo').value;
  const ha=document.getElementById('p-ha').value;
  const mbf=+document.getElementById('p-mbf').value||1;

  let rows=PRAW.filter(r=>
    (!q||r.pitcher.toLowerCase().includes(q))&&
    (!season||String(r.season)===season)&&(!ref||String(r.ref)===ref)&&
    (!tm||r.fielding_team===tm)&&(!ft||r.batting_team===ft)&&
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

  document.getElementById('p-info').innerHTML=`Exibindo <b>${{data.length}}</b> pitchers · <b>${{rows.length}}</b> linhas · Mín. <b>${{mbf}} BF</b>`;

  document.getElementById('p-thead').innerHTML=`<tr>
    <th data-k="rank">#</th><th data-k="pitcher">Pitcher</th>
    <th data-k="G">G</th><th data-k="IP">IP</th><th data-k="BF">BF</th><th data-k="AB">AB</th>
    <th data-k="H">H</th><th data-k="doubles">2B</th><th data-k="triples">3B</th><th data-k="HR">HR</th>
    <th data-k="BB">BB</th><th data-k="IBB">IBB</th><th data-k="SO">K</th>
    <th data-k="HBP">HBP</th><th data-k="SF">SF</th>
    <th data-k="BAA">BAA</th><th data-k="OBP">OBP</th><th data-k="SLG">SLG</th><th data-k="OPS">OPS</th>
    <th data-k="Kpct">K%</th><th data-k="BBpct">BB%</th>
  </tr>`;
  bindSortPit();

  const emp=document.getElementById('p-emp');
  if(!data.length){{document.getElementById('p-tb').innerHTML='';emp.style.display='block';return;}}
  emp.style.display='none';
  document.getElementById('p-tb').innerHTML=data.map((d,i)=>`<tr>
    <td>${{i+1}}</td><td>${{d.pitcher}}</td>
    <td>${{d.G}}</td><td>${{d.IP}}</td><td>${{d.BF}}</td><td>${{d.AB}}</td>
    <td>${{d.H}}</td><td>${{d.doubles}}</td><td>${{d.triples}}</td><td>${{d.HR}}</td>
    <td>${{d.BB}}</td><td>${{d.IBB}}</td><td>${{d.SO}}</td>
    <td>${{d.HBP}}</td><td>${{d.SF}}</td>
    <td class="${{cls(d.BAA,.3,.22,true)}}">${{fmt3(d.BAA)}}</td>
    <td class="${{cls(d.OBP,.36,.30,true)}}">${{fmt3(d.OBP)}}</td>
    <td class="${{cls(d.SLG,.45,.35,true)}}">${{fmt3(d.SLG)}}</td>
    <td class="${{cls(d.OPS,.9,.7,true)}}">${{fmt3(d.OPS)}}</td>
    <td class="${{cls(d.Kpct,.25,.18)}}">${{fmtPct(d.Kpct)}}</td>
    <td class="${{cls(d.BBpct,.1,.08,true)}}">${{fmtPct(d.BBpct)}}</td>
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
    btn.classList.add('active');
    document.getElementById('page-'+btn.dataset.page).classList.add('active');
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

['b-q','b-season','b-ref','b-tm','b-ft','b-bs','b-sp','b-mo','b-ha','b-mpa'].forEach(id=>
  document.getElementById(id).addEventListener('input',renderBat)
);
['p-q','p-season','p-ref','p-tm','p-ft','p-ph','p-sp','p-mo','p-ha','p-mbf'].forEach(id=>
  document.getElementById(id).addEventListener('input',renderPit)
);

document.getElementById('b-season').value = '{latest_season}';
document.getElementById('p-season').value = '{latest_season}';

renderKPIs();
renderBat();
renderPit();
</script>
</body>
</html>"""


def main():
    print("Carregando dados...")
    db, dp = load_data()

    print("Gerando HTML...")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    html = build_html(db, dp)

    out = DOCS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Salvo em {out} ({len(html):,} chars)")


if __name__ == "__main__":
    main()
