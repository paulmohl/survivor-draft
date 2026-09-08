"""
Yahoo Fantasy Football Draft Scraper
Intercepts Yahoo's draft API responses in real time via Playwright.
No API keys needed — just log in in the browser.

Usage:
  python yahoo_scraper.py
"""

import asyncio, json, re, time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Run: pip install playwright && playwright install chromium")
    raise

LEAGUE_ID  = "728916"
STATE_FILE = Path("draft_state.json")

# Load player index
ALL_PLAYERS = []
BY_NAME     = {}   # lower name → player
BY_KEY      = {}   # yahoo player_key → player

if Path("players.json").exists():
    for p in json.loads(Path("players.json").read_text()):
        ALL_PLAYERS.append(p)
        BY_NAME[p["name"].lower()] = p
        # Index common name variations
        parts = p["name"].lower().split()
        if len(parts) >= 2:
            # "lastname" and "f. lastname"
            last = parts[-1].strip(".")
            if last not in BY_NAME:
                BY_NAME[last] = p


def find_player(name: str):
    if not name or len(name) < 3:
        return None
    nl = name.lower().strip()
    if nl in BY_NAME:
        return BY_NAME[nl]
    # Try without suffix (Jr., Sr., III)
    clean = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', nl).strip()
    if clean in BY_NAME:
        return BY_NAME[clean]
    # Partial match on full name
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


def record(pick_num: int, name: str, team: str = "", pos: str = "", by: str = "Yahoo"):
    k = str(pick_num)
    if k in state["drafted"] and state["drafted"][k].get("name"):
        return False
    p = find_player(name)
    state["drafted"][k] = {
        "rank":  p["rank"] if p else None,
        "name":  p["name"] if p else name,
        "team":  p.get("team", team) if p else team,
        "pos":   p.get("pos", pos) if p else pos,
        "by":    by,
        "yahoo": True,
        "at":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    entry = state["drafted"][k]
    print(f"  Pick #{pick_num:3d}: {entry['name']:<28} {entry['pos']:<4} {entry['team']}")
    return True


def parse_body(url: str, body: bytes) -> int:
    """Try to extract pick data from any Yahoo response body."""
    added = 0
    try:
        text = body.decode("utf-8", errors="ignore")
        if len(text) < 10:
            return 0

        # Only bother with JSON
        stripped = text.lstrip()
        if not (stripped.startswith("{") or stripped.startswith("[")):
            return 0

        data = json.loads(stripped)
    except Exception:
        return 0

    def dig(obj, path=()):
        nonlocal added
        if not isinstance(obj, (dict, list)):
            return
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                dig(v, path+(i,))
            return

        # ── Yahoo draft_result row ──
        if "pick" in obj and ("player_key" in obj or "player" in obj):
            pick_num = int(obj.get("pick") or 0)
            team_key = obj.get("team_key", "")

            # player_key → need separate lookup (cache for later)
            pk = obj.get("player_key", "")
            if pk and pick_num > 0:
                BY_KEY[pk] = {"pick": pick_num, "team_key": team_key}

            # If player name is inline
            name = (obj.get("player_name") or obj.get("full_name") or
                    (obj.get("name") or {}).get("full") or "")
            pos  = obj.get("position_type", obj.get("pos", obj.get("position", "")))
            team = obj.get("editorial_team_abbr", obj.get("team", ""))
            if pick_num > 0 and name:
                if record(pick_num, name, team, pos, team_key):
                    added += 1

        # ── Generic picks array ──
        for key in ("picks", "draft_picks", "draftResults", "draft_results"):
            val = obj.get(key)
            if isinstance(val, list):
                for pk in val:
                    if not isinstance(pk, dict): continue
                    pn = int(pk.get("pick_no", pk.get("pick", pk.get("pick_num", 0))) or 0)
                    name = (pk.get("player_name") or pk.get("full_name") or
                            pk.get("name") or
                            (pk.get("player") or {}).get("name", {}).get("full") or "")
                    team = pk.get("nfl_team_abbr", pk.get("team", ""))
                    pos  = pk.get("position_type", pk.get("position", pk.get("pos", "")))
                    by   = str(pk.get("team_name", pk.get("team_key", "Yahoo")))
                    if pn > 0 and name:
                        if record(pn, name, team, pos, by):
                            added += 1
            elif isinstance(val, dict):
                for k2, v2 in val.items():
                    if k2.isdigit() and isinstance(v2, dict):
                        inner = v2.get("draft_result", v2)
                        pn = int(inner.get("pick", 0) or 0)
                        pk = inner.get("player_key", "")
                        team_key = inner.get("team_key", "")
                        if pn > 0 and pk:
                            BY_KEY[pk] = {"pick": pn, "team_key": team_key}

        for v in obj.values():
            dig(v, path)

    dig(data)
    return added


async def resolve_player_keys(page):
    """Fetch player names for any queued player_keys we couldn't resolve inline."""
    unresolved = [pk for pk, info in BY_KEY.items()
                  if info.get("pick") and not state["drafted"].get(str(info["pick"]))]
    if not unresolved:
        return 0

    added = 0
    print(f"  Resolving {len(unresolved)} player keys via page...")
    for pk in unresolved[:20]:  # limit per cycle
        info = BY_KEY[pk]
        pick_num = info["pick"]
        try:
            result = await page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('https://fantasysports.yahooapis.com/fantasy/v2/player/{pk}?format=json');
                    if (!r.ok) return null;
                    return await r.text();
                }} catch(e) {{ return null; }}
            }}""")
            if result:
                body = result.encode("utf-8")
                n = parse_body(f"/player/{pk}", body)
                added += n
                if n == 0:
                    # Try to extract name from JSON directly
                    try:
                        d = json.loads(result)
                        def find_full(o):
                            if isinstance(o, dict):
                                if "full" in o and isinstance(o["full"], str) and len(o["full"]) > 3:
                                    return o["full"]
                                for v in o.values():
                                    r = find_full(v)
                                    if r: return r
                            elif isinstance(o, list):
                                for v in o:
                                    r = find_full(v)
                                    if r: return r
                        name = find_full(d)
                        if name and pick_num > 0:
                            if record(pick_num, name, "", "", info.get("team_key", "Yahoo")):
                                added += 1
                    except Exception:
                        pass
        except Exception:
            pass
    return added


async def main():
    global state
    async with async_playwright() as pw:
        print("\n" + "="*60)
        print(f"  Yahoo Fantasy Football Draft Sync — League #{LEAGUE_ID}")
        print(f"  {len(ALL_PLAYERS)} players loaded")
        print("="*60)
        print("  Browser will open → log in → go to draft room")
        print("  Ctrl+C to stop\n")

        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # Intercept all responses
        async def on_response(resp):
            url = resp.url
            if not any(x in url for x in [
                "fantasysports.yahoo", "fantasy/v2", "/draft", "/pick",
                "yfquery", "draft_status", "draftresult"
            ]):
                return
            try:
                body = await resp.body()
                n = parse_body(url, body)
                if n > 0:
                    state["lastSync"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    state["yahooConnected"] = True
                    STATE_FILE.write_text(json.dumps(state, indent=2))
                    print(f"  → Saved {len(state['drafted'])} total picks")
            except Exception:
                pass

        page.on("response", on_response)

        # Navigate
        await page.goto("https://football.fantasysports.yahoo.com", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if await page.locator("a[href*='login']").count() > 0:
            print("Please log in to Yahoo in the browser... (120s)")
            try:
                await page.wait_for_function(
                    "() => !document.querySelector('a[href*=\"login\"]')",
                    timeout=120_000
                )
            except Exception:
                pass

        # Try to find your league
        for url in [
            f"https://football.fantasysports.yahoo.com/f1/{LEAGUE_ID}",
            f"https://football.fantasysports.yahoo.com/f1/league/{LEAGUE_ID}",
            f"https://football.fantasysports.yahoo.com/f1/{LEAGUE_ID}/draft",
        ]:
            try:
                r = await page.goto(url, timeout=8000)
                if r and r.status == 200:
                    if "404" not in (await page.title()):
                        print(f"  League page: {url}")
                        # Try to navigate directly to draft
                        try:
                            await page.locator("a[href*='draft']").first.click(timeout=3000)
                        except Exception:
                            pass
                        break
            except Exception:
                pass

        print("\nWaiting for draft picks... (picks detected via network intercept)")
        print("If not auto-navigating, open your draft board manually in the browser.\n")

        tick = 0
        while True:
            tick += 1
            await asyncio.sleep(5)

            # Every 30s: resolve any pending player keys + print status
            if tick % 6 == 0:
                n = await resolve_player_keys(page)
                if n > 0:
                    state["lastSync"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    STATE_FILE.write_text(json.dumps(state, indent=2))
                total = len(state["drafted"])
                url_now = page.url[:60]
                print(f"  [{time.strftime('%H:%M:%S')}] {total} picks | {url_now}")

            # Every 60s: try to reload draft board to trigger fresh API calls
            if tick % 12 == 0:
                try:
                    cur = page.url
                    if "fantasysports.yahoo" in cur or "football.yahoo" in cur:
                        await page.reload(wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        total = len(state.get("drafted", {}))
        print(f"\nStopped. {total} picks saved to draft_state.json")
