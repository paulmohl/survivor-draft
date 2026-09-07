"""
Yahoo Fantasy Football Draft Board Scraper
Uses Playwright (browser automation) — no API keys needed.

Usage:
  pip install playwright
  playwright install chromium
  python yahoo_scraper.py

A browser window opens. Log in to Yahoo, then the script auto-navigates
to League #728916 and syncs the draft board every 15s → draft_state.json
(picked up automatically by server.py if running).
"""

import asyncio, json, re, time
from pathlib import Path

try:
    from playwright.async_api import async_playwright, TimeoutError as PWT
except ImportError:
    print("Install playwright: pip install playwright && playwright install chromium")
    raise

LEAGUE_ID  = "728916"
STATE_FILE = Path("draft_state.json")
PLAYERS    = {}

if Path("players.json").exists():
    for p in json.loads(Path("players.json").read_text()):
        PLAYERS[p["name"].lower()] = p
        # Also index by last name for fuzzy matching
        parts = p["name"].lower().split()
        if len(parts) >= 2:
            PLAYERS[parts[-1]] = p  # last name only


def load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except Exception: pass
    return {"drafted": {}, "lastSync": None, "yahooConnected": False}


def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2))
    print(f"[Saved] {len(s['drafted'])} picks → draft_state.json")


def find_player(name: str):
    nl = name.lower().strip()
    if nl in PLAYERS:
        return PLAYERS[nl]
    for k, p in PLAYERS.items():
        if nl in k or k in nl:
            return p
    return None


async def main():
    state = load_state()

    async with async_playwright() as pw:
        print("\n" + "="*60)
        print("  2026 Fantasy Football — Yahoo Draft Scraper")
        print("="*60)
        print("  A browser window will open.")
        print("  1. Log in to Yahoo when prompted")
        print("  2. Script auto-navigates to League #728916")
        print("  3. Draft picks sync every 15 seconds")
        print("  4. Ctrl+C to stop")
        print("="*60 + "\n")

        browser = await pw.chromium.launch(headless=False, slow_mo=150)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        print("[1/3] Opening Yahoo Fantasy Football...")
        await page.goto("https://football.fantasysports.yahoo.com", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Wait for login if needed
        if await page.locator("a[href*='login.yahoo.com']").count() > 0:
            print("[2/3] Please log in to Yahoo... (120s timeout)")
            try:
                await page.wait_for_url(lambda u: "login.yahoo.com" not in u, timeout=120_000)
            except PWT:
                print("[!] Login timeout.")
                await browser.close(); return
        else:
            print("[2/3] Already logged in ✓")

        # Find the league
        league_urls = [
            f"https://football.fantasysports.yahoo.com/f1/league/{LEAGUE_ID}",
            f"https://football.fantasysports.yahoo.com/f1/{LEAGUE_ID}",
            f"https://football.fantasysports.yahoo.com/league/{LEAGUE_ID}",
        ]
        league_url = None
        for url in league_urls:
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=8000)
                if resp and resp.status == 200:
                    title = await page.title()
                    if any(x in title.lower() for x in ["fantasy","league","survivor","football"]):
                        print(f"[3/3] Found league: {url}")
                        league_url = url
                        break
            except Exception as e:
                print(f"  Tried {url}: {e}")

        if not league_url:
            print("\n[!] Could not auto-navigate. Navigate to your draft page manually.")
            input("    Press Enter when you're on the draft board...")

        # Draft pick sync loop
        loop_n = 0
        while True:
            loop_n += 1
            url_now = page.url
            print(f"\n[Sync #{loop_n}] {url_now[:70]}...")

            try:
                body = await page.evaluate("document.body.innerText")
                lines = [l.strip() for l in body.split("\n") if l.strip()]

                # Look for player names in page text
                found = 0
                for line in lines:
                    p = find_player(line)
                    if p:
                        rank = str(p["rank"])
                        # Check if already recorded
                        already = any(v.get("rank") == p["rank"] for v in state["drafted"].values())
                        if not already:
                            # Determine pick number (next available)
                            picks_used = set(int(k) for k in state["drafted"].keys() if k.isdigit())
                            next_pick = 1
                            while next_pick in picks_used: next_pick += 1
                            state["drafted"][str(next_pick)] = {
                                "rank": p["rank"], "name": p["name"],
                                "team": p.get("team",""), "pos": p.get("pos",""),
                                "by": "Yahoo", "yahoo": True,
                                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            }
                            print(f"  ✓ #{p['rank']} {p['name']} ({p.get('pos','')})")
                            found += 1

                # Also scan structured draft rows
                rows = await page.query_selector_all(
                    "tr, .pick-row, .draft-result, [class*='pick'], [class*='draft-pick']"
                )
                for row in rows:
                    try:
                        text = (await row.inner_text()).strip()
                        player = find_player(text)
                        if player:
                            already = any(v.get("rank")==player["rank"] for v in state["drafted"].values())
                            if not already:
                                picks_used = set(int(k) for k in state["drafted"].keys() if k.isdigit())
                                next_pick = 1
                                while next_pick in picks_used: next_pick += 1
                                state["drafted"][str(next_pick)] = {
                                    "rank": player["rank"], "name": player["name"],
                                    "team": player.get("team",""), "pos": player.get("pos",""),
                                    "by": "Yahoo", "yahoo": True,
                                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                }
                                print(f"  ✓ #{player['rank']} {player['name']} (row scan)")
                                found += 1
                    except Exception:
                        pass

                if state["drafted"]:
                    state["lastSync"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    state["yahooConnected"] = True
                    save_state(state)

                # Navigate toward draft page
                if "draft" not in url_now.lower():
                    try:
                        link = page.locator("a[href*='draft']").first
                        if await link.count() > 0:
                            href = await link.get_attribute("href")
                            if href:
                                await page.goto(href, wait_until="domcontentloaded", timeout=8000)
                    except Exception:
                        pass

            except Exception as e:
                print(f"  [Scan error] {e}")

            print(f"  Sleeping 15s... ({len(state['drafted'])} picks total)")
            await asyncio.sleep(15)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped. Draft state saved to draft_state.json")
