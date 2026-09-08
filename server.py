"""
2026 Fantasy Football Draft Guide — Flask backend
Yahoo Fantasy Football League #728916

Usage:
  pip install -r requirements.txt
  python server.py
  Open http://localhost:5050
"""

import json, os, threading, time
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory, session
from flask_cors import CORS
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__, static_folder="public")
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET", "ff-draft-2026-secret")

LEAGUE_ID      = os.getenv("YAHOO_LEAGUE_ID", "728916")
CLIENT_ID      = os.getenv("YAHOO_CLIENT_ID", "")
CLIENT_SECRET  = os.getenv("YAHOO_CLIENT_SECRET", "")
REDIRECT_URI   = os.getenv("YAHOO_REDIRECT_URI", "http://localhost:5050/auth/yahoo/callback")
AUTH_URL       = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL      = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_API      = "https://fantasysports.yahooapis.com/fantasy/v2"

STATE_FILE = Path("draft_state.json")

# Build name→rank lookup from players.json
PLAYERS = {}
if Path("players.json").exists():
    for p in json.loads(Path("players.json").read_text()):
        PLAYERS[p["name"].lower()] = p

def name_to_rank(full_name: str):
    nl = full_name.lower().strip()
    if nl in PLAYERS:
        return PLAYERS[nl]["rank"]
    for k, p in PLAYERS.items():
        if nl in k or k in nl:
            return p["rank"]
    return None


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"drafted": {}, "lastSync": None, "yahooConnected": False}


def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2))


# In-memory state — merged with file on every /api/state request
draft_state = load_state()
token_data  = {}
_state_lock = threading.Lock()


# ─── STATIC ───────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("public", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("public", path)


# ─── DRAFT STATE API ──────────────────────────────────

@app.route("/api/state")
def get_state():
    # Read file fresh every time — scraper writes here, browser reads here
    try:
        data = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except Exception:
        data = {}
    # Also include any in-memory picks not yet flushed to file
    with _state_lock:
        for k, v in draft_state.get("drafted", {}).items():
            if k not in data.get("drafted", {}):
                data.setdefault("drafted", {})[k] = v
    return jsonify(data)


@app.route("/api/draft_pick", methods=["POST"])
def draft_pick_from_scraper():
    """Called directly by yahoo_scraper.py — updates in-memory state instantly."""
    data = request.json or {}
    pick_num = str(data.get("pick", ""))
    if not pick_num:
        return jsonify({"error": "pick required"}), 400
    with _state_lock:
        draft_state["drafted"][pick_num] = {
            "rank": data.get("rank"),
            "name": data.get("name", ""),
            "team": data.get("team", ""),
            "pos":  data.get("pos", ""),
            "by":   data.get("by", "Yahoo"),
            "yahoo": True,
            "at":   data.get("at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        }
        draft_state["lastSync"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        draft_state["yahooConnected"] = True
        save_state(draft_state)
    print(f"[Pick] #{pick_num}: {data.get('name','')} ({data.get('pos','')})")
    return jsonify({"ok": True, "total": len(draft_state["drafted"])})

@app.route("/api/draft", methods=["POST"])
def mark_drafted():
    data = request.json or {}
    pick_num = str(data.get("pick", ""))
    rank     = data.get("rank")
    by       = data.get("by", "Manual")
    if not pick_num or not rank:
        return jsonify({"error": "pick and rank required"}), 400
    p = PLAYERS.get(str(rank), {})
    draft_state["drafted"][pick_num] = {
        "rank": rank, "name": p.get("name",""), "team": p.get("team",""),
        "pos": p.get("pos",""), "by": by,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_state(draft_state)
    return jsonify({"ok": True})

@app.route("/api/undraft", methods=["POST"])
def undraft():
    data = request.json or {}
    pick_num = str(data.get("pick", ""))
    if pick_num in draft_state["drafted"]:
        del draft_state["drafted"][pick_num]
        save_state(draft_state)
    return jsonify({"ok": True, "state": draft_state})

@app.route("/api/reset", methods=["POST"])
def reset_draft():
    draft_state["drafted"] = {}
    draft_state["lastSync"] = None
    save_state(draft_state)
    return jsonify({"ok": True})


# ─── YAHOO OAUTH ──────────────────────────────────────

@app.route("/auth/yahoo")
def yahoo_auth():
    if not CLIENT_ID:
        return """<html><body style="font-family:sans-serif;background:#0d1117;color:#e2e8f0;padding:40px">
        <h2>Yahoo credentials not configured</h2>
        <p>Add <code>YAHOO_CLIENT_ID</code> and <code>YAHOO_CLIENT_SECRET</code> to <code>.env</code></p>
        <p>Get them at <a href="https://developer.yahoo.com/apps/create/" style="color:#58a6ff">Yahoo Developer Console</a></p>
        <p>OR use the <strong>yahoo_scraper.py</strong> browser-based sync (no credentials needed).</p>
        <a href="/" style="color:#58a6ff">← Back</a></body></html>""", 400
    params = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code"}
    return redirect(AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items()))

@app.route("/auth/yahoo/callback")
def yahoo_callback():
    code = request.args.get("code")
    if not code:
        return "No auth code", 400
    import base64
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    resp = requests.post(TOKEN_URL,
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "authorization_code", "redirect_uri": REDIRECT_URI, "code": code})
    if not resp.ok:
        return f"Token exchange failed: {resp.text}", 400
    token_data.update(resp.json())
    draft_state["yahooConnected"] = True
    save_state(draft_state)
    sync_yahoo()
    return redirect("/")

def yahoo_get(path):
    if not token_data.get("access_token"):
        return None
    headers = {"Authorization": f"Bearer {token_data['access_token']}", "Accept": "application/json"}
    r = requests.get(f"{YAHOO_API}{path}", headers=headers)
    if r.status_code == 401:
        _refresh()
        headers["Authorization"] = f"Bearer {token_data.get('access_token','')}"
        r = requests.get(f"{YAHOO_API}{path}", headers=headers)
    return r.json() if r.ok else None

def _refresh():
    if not token_data.get("refresh_token"): return
    import base64
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    r = requests.post(TOKEN_URL, headers={"Authorization": f"Basic {creds}"},
        data={"grant_type": "refresh_token", "redirect_uri": REDIRECT_URI,
              "refresh_token": token_data["refresh_token"]})
    if r.ok: token_data.update(r.json())


def sync_yahoo():
    """Pull Yahoo Fantasy NFL draft results and map to our player ranks."""
    # Find football game key
    games = yahoo_get("/users;use_login=1/games;game_codes=nfl")
    game_key = None
    if games:
        try:
            g = games["fantasy_content"]["users"]["0"]["user"][1]["games"]
            for k, v in g.items():
                if k == "count": continue
                ginfo = v.get("game", [{}])
                if isinstance(ginfo, list) and ginfo:
                    game_key = ginfo[0].get("game_key")
                    break
        except Exception as e:
            print(f"[Yahoo] game key parse error: {e}")

    if not game_key:
        print("[Yahoo] Could not determine game key")
        return

    league_key = f"{game_key}.l.{LEAGUE_ID}"
    print(f"[Yahoo] League key: {league_key}")

    draft_data = yahoo_get(f"/league/{league_key}/draftresults")
    if not draft_data:
        print("[Yahoo] No draft data")
        return

    try:
        content = draft_data["fantasy_content"]
        dr = content["league"][1]["draft_results"]
        new = {}
        for k, v in dr.items():
            if not k.isdigit(): continue
            pick = v.get("draft_result", {})
            pick_num = str(pick.get("pick", ""))
            player_key = pick.get("player_key", "")
            team_key = pick.get("team_key", "")
            if not player_key: continue

            pdata = yahoo_get(f"/player/{player_key}")
            if pdata:
                try:
                    pinfo = pdata["fantasy_content"]["player"][0]
                    full_name = ""
                    for item in (pinfo if isinstance(pinfo, list) else []):
                        if isinstance(item, dict):
                            full_name = item.get("name", {}).get("full", "")
                            if full_name: break
                    if full_name:
                        rank = name_to_rank(full_name)
                        p = PLAYERS.get(full_name.lower(), {})
                        new[pick_num] = {
                            "rank": rank, "name": full_name,
                            "team": p.get("team",""), "pos": p.get("pos",""),
                            "by": team_key, "yahoo": True,
                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                except Exception as e:
                    print(f"[Yahoo] player parse error: {e}")

        if new:
            draft_state["drafted"].update(new)
            draft_state["lastSync"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            save_state(draft_state)
            print(f"[Yahoo] Synced {len(new)} picks")
        else:
            print("[Yahoo] No picks yet")
    except Exception as e:
        print(f"[Yahoo] sync error: {e}")

@app.route("/api/yahoo/sync", methods=["POST"])
def manual_sync():
    if not token_data.get("access_token"):
        return jsonify({"error": "Not authenticated. Visit /auth/yahoo"}), 401
    sync_yahoo()
    return jsonify({"ok": True, "state": draft_state})

@app.route("/api/yahoo/status")
def yahoo_status():
    return jsonify({
        "connected": bool(token_data.get("access_token")),
        "lastSync": draft_state.get("lastSync"),
        "picks": len(draft_state.get("drafted", {})),
        "leagueId": LEAGUE_ID,
    })


def _bg_sync():
    while True:
        time.sleep(60)
        if token_data.get("access_token"):
            print("[Auto-sync] Polling Yahoo...")
            sync_yahoo()

if __name__ == "__main__":
    print("=" * 60)
    print("  2026 Fantasy Football Draft Guide")
    print(f"  League #728916  |  Open: http://localhost:5050")
    if CLIENT_ID:
        print(f"  Yahoo Auth: http://localhost:5050/auth/yahoo")
    else:
        print("  Yahoo API: Set YAHOO_CLIENT_ID + YAHOO_CLIENT_SECRET in .env")
        print("  OR run: python yahoo_scraper.py (no credentials needed)")
    print("=" * 60)

    threading.Thread(target=_bg_sync, daemon=True).start()
    app.run(host="0.0.0.0", port=5050, debug=False)
