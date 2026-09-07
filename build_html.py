import json, os

players = json.load(open("players.json"))
players_json = json.dumps(players, separators=(',',':'))

PICK_POS = 6
TEAMS = 12
ROUNDS = 16

paul_picks = []
for r in range(1, ROUNDS+1):
    if r % 2 == 1:
        pick = (r-1)*TEAMS + PICK_POS
    else:
        pick = r*TEAMS - PICK_POS + 1
    paul_picks.append(pick)

paul_picks_js = json.dumps(paul_picks)

html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2026 Fantasy Football Draft Guide</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --card2: #22253a; --border: #2d3150;
    --text: #e8eaf0; --muted: #6b7094; --accent: #5b6af0;
    --QB: #e05252; --RB: #3fb86a; --WR: #4a9eff; --TE: #f0922b;
    --K: #b05fe0; --DST: #20b2aa;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; }

  #topbar { background: var(--card); border-bottom: 1px solid var(--border); padding: 10px 16px;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap; position: sticky; top: 0; z-index: 100; }
  #topbar h1 { font-size: 15px; font-weight: 700; color: var(--accent); white-space: nowrap; }
  .pick-badge { background: var(--accent); color: #fff; padding: 4px 10px; border-radius: 20px;
    font-weight: 700; font-size: 13px; white-space: nowrap; }
  .pick-badge.my-turn { background: #3fb86a; animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.7 } }
  #my-next { font-size: 12px; color: #3fb86a; font-weight: 600; }
  #pick-round { font-size: 13px; color: var(--muted); }
  #sync-btn { margin-left: auto; background: var(--card2); border: 1px solid var(--border);
    color: var(--text); padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
  #sync-btn:hover { border-color: var(--accent); }
  #sync-status { font-size: 11px; color: var(--muted); }

  #layout { display: flex; height: calc(100vh - 49px); overflow: hidden; }
  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

  #controls { padding: 8px 12px; border-bottom: 1px solid var(--border);
    display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  #search { background: var(--card2); border: 1px solid var(--border); color: var(--text);
    padding: 6px 10px; border-radius: 6px; font-size: 13px; width: 190px; }
  #search:focus { outline: none; border-color: var(--accent); }
  .pos-tabs { display: flex; gap: 3px; }
  .pos-tab { background: var(--card2); border: 1px solid var(--border); color: var(--muted);
    padding: 4px 9px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600; }
  .pos-tab:hover { color: var(--text); }
  .pos-tab.active[data-pos="All"] { background: var(--accent); color:#fff; border-color:transparent; }
  .pos-tab.active[data-pos="QB"] { background: var(--QB); color:#fff; border-color:transparent; }
  .pos-tab.active[data-pos="RB"] { background: var(--RB); color:#fff; border-color:transparent; }
  .pos-tab.active[data-pos="WR"] { background: var(--WR); color:#fff; border-color:transparent; }
  .pos-tab.active[data-pos="TE"] { background: var(--TE); color:#fff; border-color:transparent; }
  .pos-tab.active[data-pos="K"]  { background: var(--K);  color:#fff; border-color:transparent; }
  .pos-tab.active[data-pos="DST"]{ background: var(--DST);color:#fff; border-color:transparent; }
  .show-toggle { margin-left:auto; display:flex; align-items:center; gap:5px; font-size:12px; color:var(--muted); cursor:pointer; }

  #player-list { flex: 1; overflow-y: auto; }
  .player-row { display: flex; align-items: center; gap: 8px; padding: 7px 10px;
    border-bottom: 1px solid var(--border); cursor: pointer; transition: background .1s; }
  .player-row:hover:not(.drafted) { background: var(--card2); }
  .player-row.drafted { opacity: 0.3; }
  .player-row.drafted .pname { text-decoration: line-through; }
  .player-row.my-pick { background: #1a2a1a; border-left: 3px solid var(--RB); }
  .rank-n { width: 28px; text-align: right; color: var(--muted); font-size: 11px; flex-shrink:0; }
  .pbadge { width: 34px; text-align: center; font-size: 11px; font-weight: 700;
    padding: 2px 3px; border-radius: 3px; flex-shrink:0; }
  .pbadge.QB { background:#3d1c1c; color:var(--QB); }
  .pbadge.RB { background:#1a2f22; color:var(--RB); }
  .pbadge.WR { background:#1a2440; color:var(--WR); }
  .pbadge.TE { background:#2f1f0f; color:var(--TE); }
  .pbadge.K  { background:#28173d; color:var(--K); }
  .pbadge.DST{ background:#0f2525; color:var(--DST); }
  .pname { flex:1; font-weight:600; font-size:13px; }
  .pteam { color:var(--muted); font-size:12px; width:32px; }
  .pbye { color:var(--muted); font-size:11px; width:42px; text-align:right; }
  .pdraft-info { font-size:11px; color:var(--muted); font-style:italic; }

  #sidebar { width: 255px; border-left: 1px solid var(--border); display:flex; flex-direction:column; overflow:hidden; flex-shrink:0; }
  .sb-sec { padding: 10px 10px 8px; border-bottom: 1px solid var(--border); }
  .sb-title { font-size:10px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.07em; margin-bottom:7px; }

  .adv-row { display:flex; align-items:center; gap:7px; padding:4px 0; border-bottom:1px solid var(--border); font-size:12px; }
  .adv-row:last-child { border:none; }
  .adv-rank { color:var(--muted); font-size:11px; width:24px; text-align:right; }

  #round-dots { display:flex; flex-wrap:wrap; gap:3px; }
  .rdot { width:23px; height:23px; border-radius:50%; font-size:9px; font-weight:700;
    display:flex; align-items:center; justify-content:center;
    border:2px solid var(--border); color:var(--muted); cursor:default; }
  .rdot.done { background:var(--accent); border-color:var(--accent); color:#fff; }
  .rdot.curr { border-color:#3fb86a; color:#3fb86a; }

  #team-list { flex:1; overflow-y:auto; padding:8px; }
  .tslot { display:flex; align-items:center; gap:6px; padding:4px 7px; border-radius:4px;
    font-size:12px; margin-bottom:2px; background:var(--card2); border:1px solid var(--border); }
  .tslot.empty { opacity:.35; }
  .tslot .slabel { color:var(--muted); font-size:10px; width:28px; flex-shrink:0; }
  .tslot .spname { flex:1; }
  .tslot .steam { color:var(--muted); font-size:11px; }

  ::-webkit-scrollbar { width:4px; }
  ::-webkit-scrollbar-track { background:transparent; }
  ::-webkit-scrollbar-thumb { background:var(--border); border-radius:2px; }
</style>
</head>
<body>

<div id="topbar">
  <h1>2026 FF Draft — Pick #6</h1>
  <span class="pick-badge" id="pick-badge">Pick #1</span>
  <span id="pick-round">Round 1</span>
  <span id="my-next"></span>
  <button id="sync-btn" onclick="trySync()">↻ Yahoo Sync</button>
  <span id="sync-status"></span>
</div>

<div id="layout">
  <div id="main">
    <div id="controls">
      <input type="text" id="search" placeholder="Search name or team..." oninput="renderList()">
      <div class="pos-tabs">
        <button class="pos-tab active" data-pos="All" onclick="filterPos('All')">All</button>
        <button class="pos-tab" data-pos="QB" onclick="filterPos('QB')">QB</button>
        <button class="pos-tab" data-pos="RB" onclick="filterPos('RB')">RB</button>
        <button class="pos-tab" data-pos="WR" onclick="filterPos('WR')">WR</button>
        <button class="pos-tab" data-pos="TE" onclick="filterPos('TE')">TE</button>
        <button class="pos-tab" data-pos="K" onclick="filterPos('K')">K</button>
        <button class="pos-tab" data-pos="DST" onclick="filterPos('DST')">DST</button>
      </div>
      <label class="show-toggle">
        <input type="checkbox" id="showDrafted" checked onchange="renderList()">
        Show drafted
      </label>
    </div>
    <div id="player-list"></div>
  </div>

  <div id="sidebar">
    <div class="sb-sec">
      <div class="sb-title">Best Available (by need)</div>
      <div id="adv-list"></div>
    </div>
    <div class="sb-sec">
      <div class="sb-title">Round Tracker &nbsp;<span id="draft-count" style="color:var(--text)">0</span>/192</div>
      <div id="round-dots"></div>
    </div>
    <div class="sb-sec" style="display:flex;justify-content:space-between;align-items:center;padding-bottom:6px;">
      <div class="sb-title" style="margin:0">My Team</div>
      <button onclick="clearAll()" style="font-size:11px;color:var(--muted);background:none;border:none;cursor:pointer;">Clear all</button>
    </div>
    <div id="team-list"></div>
  </div>
</div>

<script>
const PLAYERS = """ + players_json + """;
const MY_PICKS = """ + paul_picks_js + """;
const TOTAL = 192, MY_POS = 6, NTEAMS = 12;

let state = { drafted: {}, pick: 1 };

const save = () => localStorage.setItem('ff26', JSON.stringify(state));
const load = () => { try { const s = JSON.parse(localStorage.getItem('ff26')||'null'); if(s) state=s; } catch(e){} };

const isDrafted = r => Object.values(state.drafted).some(d => d.rank===r);
const myTeam    = () => Object.entries(state.drafted)
  .filter(([k])=>MY_PICKS.includes(+k)).map(([k,d])=>({...d,pick:+k})).sort((a,b)=>a.pick-b.pick);

function draftAt(rank) {
  if (isDrafted(rank)) {
    const k = Object.keys(state.drafted).find(k => state.drafted[k].rank===rank);
    if (k) delete state.drafted[k];
    state.pick = nextFree();
  } else {
    const p = PLAYERS.find(x=>x.rank===rank);
    if (!p) return;
    state.drafted[state.pick] = {rank, name:p.name, team:p.team, pos:p.pos};
    state.pick = nextFree();
  }
  save(); render();
}

function nextFree(from) {
  let p = (from ?? state.pick) + 1;
  if (from==null) {
    // Advance from current or recompute
    const used = Object.keys(state.drafted).map(Number);
    p = used.length ? Math.max(...used)+1 : state.pick;
    while (p<=TOTAL && state.drafted[p]) p++;
  } else {
    while (p<=TOTAL && state.drafted[p]) p++;
  }
  return Math.min(p, TOTAL+1);
}

let posFilter = 'All';
function filterPos(p) {
  posFilter = p;
  document.querySelectorAll('.pos-tab').forEach(t=>t.classList.toggle('active',t.dataset.pos===p));
  renderList();
}

function renderList() {
  const q = document.getElementById('search').value.toLowerCase();
  const showD = document.getElementById('showDrafted').checked;
  const container = document.getElementById('player-list');
  const mt = myTeam();

  const rows = PLAYERS.filter(p => {
    if (posFilter!=='All' && p.pos!==posFilter) return false;
    if (!showD && isDrafted(p.rank)) return false;
    if (q && !p.name.toLowerCase().includes(q) && !p.team.toLowerCase().includes(q)) return false;
    return true;
  }).map(p => {
    const dr = isDrafted(p.rank);
    const mine = mt.some(t=>t.rank===p.rank);
    return `<div class="player-row ${dr?'drafted':''} ${mine?'my-pick':''}" onclick="draftAt(${p.rank})">
      <span class="rank-n">${p.rank}</span>
      <span class="pbadge ${p.pos}">${p.pos}</span>
      <span class="pname">${p.name}</span>
      <span class="pteam">${p.team}</span>
      <span class="pbye">Bye ${p.bye||'?'}</span>
      ${dr ? `<span class="pdraft-info">${mine?'★ Mine':'✗'}</span>` : ''}
    </div>`;
  }).join('');

  container.innerHTML = rows || '<div style="color:var(--muted);padding:20px;text-align:center">No players match</div>';
}

function renderAdvisor() {
  const mt = myTeam();
  const cnt = {};
  mt.forEach(p => cnt[p.pos]=(cnt[p.pos]||0)+1);
  const need = {QB:2,RB:4,WR:5,TE:2,K:1,DST:1};
  const avail = PLAYERS.filter(p=>!isDrafted(p.rank));

  const recs = Object.entries(need)
    .map(([pos,slots]) => ({pos, gap: slots-(cnt[pos]||0)}))
    .filter(x=>x.gap>0)
    .sort((a,b)=>b.gap-a.gap)
    .slice(0,5)
    .map(({pos,gap}) => {
      const best = avail.find(p=>p.pos===pos);
      if (!best) return '';
      return `<div class="adv-row">
        <span class="pbadge ${pos}" style="flex-shrink:0">${pos}</span>
        <span style="flex:1">${best.name}</span>
        <span class="adv-rank">#${best.rank}</span>
      </div>`;
    }).join('');

  document.getElementById('adv-list').innerHTML = recs || '<div style="color:var(--muted);font-size:12px">Roster filled!</div>';
}

function renderPickInfo() {
  const pick = state.pick;
  const round = Math.ceil(pick/NTEAMS);
  const isMe = MY_PICKS.includes(pick);

  const badge = document.getElementById('pick-badge');
  badge.textContent = `Pick #${pick}`;
  badge.className = 'pick-badge'+(isMe?' my-turn':'');
  document.getElementById('pick-round').textContent = `Round ${round}`;

  const nxt = MY_PICKS.find(p=>p>=pick);
  const el = document.getElementById('my-next');
  if (nxt) {
    const diff = nxt-pick;
    el.textContent = diff===0 ? '★ YOUR PICK NOW!' : `Next: #${nxt} (in ${diff})`;
    el.style.color = diff===0 ? '#3fb86a' : '#8ca0ff';
  } else {
    el.textContent = 'Draft complete';
  }

  const dots = document.getElementById('round-dots');
  dots.innerHTML = MY_PICKS.map((mp,i)=>{
    const done = !!state.drafted[mp];
    const curr = round===(i+1)&&!done;
    return `<div class="rdot ${done?'done':''} ${curr?'curr':''}" title="R${i+1}: Pick #${mp}">${i+1}</div>`;
  }).join('');

  document.getElementById('draft-count').textContent = Object.keys(state.drafted).length;
}

function renderTeam() {
  const mt = myTeam();
  const queues = {};
  mt.forEach(p=>{if(!queues[p.pos])queues[p.pos]=[];queues[p.pos].push(p);});

  const slots = [
    {l:'QB1',pos:'QB'},{l:'QB2',pos:'QB'},
    {l:'RB1',pos:'RB'},{l:'RB2',pos:'RB'},{l:'RB3',pos:'RB'},{l:'RB4',pos:'RB'},
    {l:'WR1',pos:'WR'},{l:'WR2',pos:'WR'},{l:'WR3',pos:'WR'},{l:'WR4',pos:'WR'},{l:'WR5',pos:'WR'},
    {l:'TE1',pos:'TE'},{l:'TE2',pos:'TE'},
    {l:'K',pos:'K'},{l:'DST',pos:'DST'},{l:'FLEX',pos:'FLEX'},
  ];

  // Any overflow goes to FLEX
  const allOverflow = [];
  const placed = new Set();

  const html = slots.map(s=>{
    let p = null;
    if (s.pos==='FLEX') {
      p = allOverflow.shift()||null;
    } else if (queues[s.pos]&&queues[s.pos].length>0) {
      p = queues[s.pos].shift();
    }
    if (p) {
      return `<div class="tslot my-pick" onclick="draftAt(${p.rank})">
        <span class="slabel">${s.l}</span>
        <span class="pbadge ${p.pos}">${p.pos}</span>
        <span class="spname">${p.name}</span>
        <span class="steam">${p.team}</span>
      </div>`;
    }
    return `<div class="tslot empty">
      <span class="slabel">${s.l}</span>
      <span style="color:var(--muted);font-size:11px">—</span>
    </div>`;
  }).join('');

  // Collect overflow (extra picks beyond slot count)
  const extras = Object.values(queues).flat().concat(allOverflow);
  const extHtml = extras.map(p=>`<div class="tslot my-pick" onclick="draftAt(${p.rank})">
    <span class="slabel">+</span>
    <span class="pbadge ${p.pos}">${p.pos}</span>
    <span class="spname">${p.name}</span>
    <span class="steam">${p.team}</span>
  </div>`).join('');

  document.getElementById('team-list').innerHTML = html+extHtml;
}

function clearAll() {
  if (!confirm('Clear all picks?')) return;
  state = {drafted:{},pick:1};
  save(); render();
}

function render() { renderPickInfo(); renderList(); renderAdvisor(); renderTeam(); }

// Arrow keys to advance/rewind current pick
document.addEventListener('keydown', e=>{
  if (e.key==='ArrowRight'&&!e.target.matches('input')) { state.pick=Math.min(state.pick+1,TOTAL); save(); renderPickInfo(); }
  if (e.key==='ArrowLeft'&&!e.target.matches('input'))  { state.pick=Math.max(state.pick-1,1);    save(); renderPickInfo(); }
});

async function trySync() {
  const st = document.getElementById('sync-status');
  st.textContent = 'Syncing...';
  try {
    const r = await fetch('/api/state',{signal:AbortSignal.timeout(3000)});
    const d = await r.json();
    if (d.drafted && Object.keys(d.drafted).length) {
      Object.assign(state.drafted, d.drafted);
      const used = Object.keys(state.drafted).map(Number);
      state.pick = used.length ? Math.max(...used)+1 : 1;
      save(); render();
      st.textContent = `✓ ${Object.keys(d.drafted).length} picks synced`;
    } else { st.textContent = 'No picks yet'; }
  } catch(e) { st.textContent = 'Offline (standalone)'; }
  setTimeout(()=>st.textContent='', 4000);
}

load(); render();
setInterval(trySync, 30000);
</script>
</body>
</html>"""

os.makedirs("public", exist_ok=True)
with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Written public/index.html ({len(html)} bytes)")
