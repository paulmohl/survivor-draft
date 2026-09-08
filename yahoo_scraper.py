"""
Yahoo Fantasy Football Draft Scraper
Watches Yahoo's draft room via network intercept + WebSocket + DOM scraping.
No API keys needed.

Usage:  python yahoo_scraper.py
"""

import asyncio, json, re, time, urllib.request, urllib.error
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Run: pip install playwright && playwright install chromium")
    raise

LEAGUE_ID  = "728916"
STATE_FILE = Path("draft_state.json")
SERVER     = "http://localhost:5050"

# ── Player index ──────────────────────────────────────
ALL_PLAYERS = []
BY_NAME     = {}
BY_KEY      = {}

if Path("players.json").exists():
    for p in json.loads(Path("players.json").read_text()):
        ALL_PLAYERS.append(p)
        nl = p["name"].lower()
        BY_NAME[nl] = p
        # last name
        parts = nl.split()
        if parts:
            last = parts[-1].strip(".")
            BY_NAME.setdefault(last, p)
        # abbreviated: "J. Smith" → try first initial + last
        if len(parts) >= 2:
            abbr = parts[0][0] + ". " + " ".join(parts[1:])
            BY_NAME.setdefault(abbr, p)


def find_player(name: str):
    if not name or len(name) < 3:
        return None
    nl = name.lower().strip()
    if nl in BY_NAME:
        return BY_NAME[nl]
    clean = re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b', '', nl).strip()
    if clean in BY_NAME:
        return BY_NAME[clean]
    for k, p in BY_NAME.items():
        if len(k) > 5 and (k in nl or nl in k):
            return p
    return None


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"drafted": {}, "lastSync": None, "yahooConnected": False}


state = load_state()
_dirty = False


def flush():
    global _dirty
    if not _dirty:
        return
    state["lastSync"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["yahooConnected"] = True
    STATE_FILE.write_text(json.dumps(state, indent=2))
    _dirty = False
    print(f"  [Saved] {len(state['drafted'])} total picks")


def post_server(entry: dict):
    try:
        data = json.dumps(entry).encode()
        req = urllib.request.Request(
            f"{SERVER}/api/draft_pick", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def record(pick_num: int, name: str, team: str = "", pos: str = "", by: str = "Yahoo") -> bool:
    global _dirty
    k = str(pick_num)
    if k in state["drafted"] and state["drafted"][k].get("name"):
        return False
    p = find_player(name)
    entry = {
        "pick": pick_num,
        "rank": p["rank"] if p else None,
        "name": p["name"] if p else name,
        "team": p.get("team", team) if p else team,
        "pos":  p.get("pos", pos) if p else pos,
        "by":   by,
        "yahoo": True,
        "at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    state["drafted"][k] = entry
    _dirty = True
    print(f"  Pick #{pick_num:3d}: {entry['name']:<30} {entry['pos']:<4} {entry['team']}")
    post_server(entry)
    return True


# ── JSON response parser ──────────────────────────────

def _dig(obj, depth=0):
    added = 0
    if depth > 12 or not isinstance(obj, (dict, list)):
        return 0
    if isinstance(obj, list):
        for v in obj:
            added += _dig(v, depth+1)
        return added

    # Pattern: {pick: N, player_key: "...", team_key: "..."}
    if "pick" in obj and "player_key" in obj:
        pick_num = int(obj.get("pick") or 0)
        pk       = obj.get("player_key", "")
        team_key = obj.get("team_key", "")
        name     = (obj.get("player_name") or obj.get("full_name") or
                    (obj.get("name") or {}).get("full") or "")
        pos      = obj.get("position_type", obj.get("position", ""))
        team     = obj.get("editorial_team_abbr", obj.get("team", ""))
        if pick_num > 0:
            if name:
                if record(pick_num, name, team, pos, team_key or "Yahoo"):
                    added += 1
            elif pk:
                BY_KEY[pk] = {"pick": pick_num, "team_key": team_key}

    # Pattern: picks array
    for key in ("picks", "draft_picks", "draftResults", "draft_results"):
        val = obj.get(key)
        if isinstance(val, list):
            for pk in val:
                if not isinstance(pk, dict):
                    continue
                pn   = int(pk.get("pick_no", pk.get("pick", pk.get("pick_num", 0))) or 0)
                name = (pk.get("player_name") or pk.get("full_name") or pk.get("name") or
                        (pk.get("player") or {}).get("name", {}).get("full") or "")
                team = pk.get("nfl_team_abbr", pk.get("team", ""))
                pos  = pk.get("position_type", pk.get("position", pk.get("pos", "")))
                by   = str(pk.get("team_name", pk.get("team_key", "Yahoo")))
                if pn > 0 and name:
                    if record(pn, name, team, pos, by):
                        added += 1
        elif isinstance(val, dict):
            for k2, v2 in val.items():
                if str(k2).isdigit() and isinstance(v2, dict):
                    inner = v2.get("draft_result", v2)
                    pn  = int(inner.get("pick", 0) or 0)
                    pk2 = inner.get("player_key", "")
                    tk  = inner.get("team_key", "")
                    nm  = inner.get("player_name", "")
                    if pn > 0 and nm:
                        if record(pn, nm, "", "", tk or "Yahoo"):
                            added += 1
                    elif pn > 0 and pk2:
                        BY_KEY[pk2] = {"pick": pn, "team_key": tk}

    for v in obj.values():
        added += _dig(v, depth+1)
    return added


def parse_body(url: str, body: bytes) -> int:
    try:
        text = body.decode("utf-8", errors="ignore")
        if len(text) < 20:
            return 0
        stripped = text.lstrip()
        if not (stripped.startswith("{") or stripped.startswith("[")):
            return 0
        data = json.loads(stripped)
        return _dig(data)
    except Exception:
        return 0


def parse_ws_message(msg: str) -> int:
    """Parse a WebSocket frame — Yahoo draft rooms send pick data this way."""
    try:
        # Yahoo sometimes wraps in an array like [type, data]
        stripped = msg.strip()
        if stripped.startswith("["):
            obj = json.loads(stripped)
            if isinstance(obj, list) and len(obj) >= 2:
                return _dig(obj[1] if isinstance(obj[1], dict) else {"data": obj[1]})
        elif stripped.startswith("{"):
            return _dig(json.loads(stripped))
    except Exception:
        pass
    return 0


# ── DOM scraper: reads the visible pick list from the page ──

DOM_SCRIPT = """() => {
  const results = [];

  // Try various Yahoo draft board selectors
  const selectors = [
    '.pick-list .pick', '.drafted .pick', '[data-pick-number]',
    '.draft-results li', '.draft-results .pick-row',
    '.yfnc_tableout1 tr', '.draft-table tr',
    '[class*="pick"][class*="row"]', '[class*="draft"][class*="pick"]'
  ];

  let rows = [];
  for (const sel of selectors) {
    const found = document.querySelectorAll(sel);
    if (found.length > 0) { rows = Array.from(found); break; }
  }

  for (const row of rows) {
    const text = row.innerText || '';
    const pickMatch = text.match(/(?:pick\\s*#?|^)(\\d+)/i);
    const nameEl = row.querySelector('[class*="name"], [class*="player"], strong, b');
    const name = nameEl ? nameEl.innerText.trim() : '';
    const pickNum = pickMatch ? parseInt(pickMatch[1]) : 0;
    if (name && name.length > 2) results.push({pick: pickNum, name});
  }

  // Fallback: grab all text that looks like player names from pick table
  if (results.length === 0) {
    const tables = document.querySelectorAll('table');
    for (const t of tables) {
      if (t.innerText.toLowerCase().includes('pick') ||
          t.innerText.toLowerCase().includes('draft')) {
        const cells = t.querySelectorAll('td, th');
        let pickNum = 0;
        for (const cell of cells) {
          const t2 = cell.innerText.trim();
          if (/^\\d+$/.test(t2)) { pickNum = parseInt(t2); }
          else if (t2.length > 4 && t2.length < 35 && /[A-Z][a-z]/.test(t2)) {
            results.push({pick: pickNum, name: t2});
          }
        }
        if (results.length > 3) break;
      }
    }
  }
  return results;
}"""


async def dom_scan(page) -> int:
    added = 0
    try:
        items = await page.evaluate(DOM_SCRIPT)
        if not items:
            return 0
        next_pick = max((int(k) for k in state["drafted"]), default=0) + 1
        for item in items:
            name = item.get("name", "").strip()
            pn   = item.get("pick", 0) or next_pick
            if name and len(name) > 2:
                if record(pn, name):
                    added += 1
                    next_pick = pn + 1
    except Exception as e:
        pass
    return added


async def main():
    global state
    async with async_playwright() as pw:
        print("\n" + "="*60)
        print(f"  Yahoo FF Draft Sync — League #{LEAGUE_ID}")
        print(f"  {len(ALL_PLAYERS)} players | {len(state['drafted'])} picks already saved")
        print("="*60)
        print("  Log in, then navigate to your draft room.")
        print("  Ctrl+C to stop.\n")

        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # ── HTTP response intercept ──
        async def on_response(resp):
            url = resp.url
            if not any(x in url for x in [
                "fantasysports.yahoo", "fantasy/v2", "yfquery",
                "draftresult", "draft_status", "draft_picks"
            ]):
                return
            try:
                body = await resp.body()
                n = parse_body(url, body)
                if n > 0:
                    flush()
            except Exception:
                pass

        page.on("response", on_response)

        # ── WebSocket intercept ──
        def on_websocket(ws):
            def on_frame(payload):
                if isinstance(payload, str):
                    n = parse_ws_message(payload)
                    if n > 0:
                        flush()
            ws.on("framereceived", lambda f: on_frame(f.get("payload", "") if isinstance(f, dict) else str(f)))

        page.on("websocket", on_websocket)

        # Navigate
        await page.goto("https://football.fantasysports.yahoo.com", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Wait for login
        if await page.locator("a[href*='login']").count() > 0:
            print("Log in to Yahoo... (120s)")
            try:
                await page.wait_for_function(
                    "() => !document.querySelector('a[href*=\"login\"]')",
                    timeout=120_000
                )
            except Exception:
                pass

        # Try league URL
        for url in [
            f"https://football.fantasysports.yahoo.com/f1/{LEAGUE_ID}",
            f"https://football.fantasysports.yahoo.com/f1/{LEAGUE_ID}/draft",
        ]:
            try:
                r = await page.goto(url, timeout=8000)
                if r and r.status == 200 and "404" not in (await page.title()):
                    print(f"  League: {url}")
                    break
            except Exception:
                pass

        print("Watching for picks... navigate to your draft board in the browser.\n")

        tick = 0
        while True:
            tick += 1
            await asyncio.sleep(5)

            # DOM scan every 10s
            if tick % 2 == 0:
                n = await dom_scan(page)
                if n > 0:
                    flush()

            # Status every 30s
            if tick % 6 == 0:
                total = len(state["drafted"])
                print(f"  [{time.strftime('%H:%M:%S')}] {total} picks | {page.url[:55]}")

            # Reload every 15s to trigger fresh API responses
            if tick % 3 == 0:
                try:
                    cur = page.url
                    if "fantasysports.yahoo" in cur or "football.yahoo" in cur:
                        await page.reload(wait_until="domcontentloaded", timeout=8000)
                        await asyncio.sleep(1)
                        n = await dom_scan(page)
                        if n > 0:
                            flush()
                except Exception:
                    pass

            if _dirty:
                flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        flush()
        print(f"\nStopped. {len(state.get('drafted', {}))} picks saved.")
