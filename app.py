import os, time, requests
from flask import Flask, request, jsonify
from ytmusicapi import YTMusic

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
DEFAULT_MARKET = os.getenv("DEFAULT_MARKET", "MX")  # MX o US

ytm = YTMusic()
_sp_token = {"value": None, "exp": 0}

def _spotify_token():
    if _sp_token["value"] and _sp_token["exp"] > time.time() + 30:
        return _sp_token["value"]
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    _sp_token["value"] = data["access_token"]
    _sp_token["exp"] = time.time() + data.get("expires_in", 3600)
    return _sp_token["value"]

def _spotify_album_by_upc(upc, market):
    tok = _spotify_token()
    r = requests.get(
        "https://api.spotify.com/v1/search",
        params={"q": f"upc:{upc}", "type": "album", "limit": 1, "market": market},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15
    )
    r.raise_for_status()
    items = r.json().get("albums", {}).get("items", [])
    return items[0] if items else None

def _spotify_album_tracks(album_id, market):
    tok = _spotify_token()
    tracks = []
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
    params = {"limit": 50, "market": market}
    while True:
        r = requests.get(url, params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        r.raise_for_status()
        j = r.json()
        tracks.extend(j.get("items", []))
        if j.get("next"):
            url = j["next"]; params = None
        else:
            break
    return tracks

def _ytmusic_best_link(query):
    res = ytm.search(query, filter="albums")
    if res:
        bid = res[0].get("browseId")
        if bid:
            return f"https://music.youtube.com/browse/{bid}"
    res = ytm.search(query, filter="songs")
    if res and res[0].get("videoId"):
        return f"https://music.youtube.com/watch?v={res[0]['videoId']}"
    res = ytm.search(query)
    if res and res[0].get("videoId"):
        return f"https://music.youtube.com/watch?v={res[0]['videoId']}"
    return None

app = Flask(__name__)

@app.get("/ytmusic")
def by_upc():
    upc = (request.args.get("upc") or "").strip()
    market = (request.args.get("market") or DEFAULT_MARKET).strip().upper()
    mode = (request.args.get("mode") or "auto").strip().lower()

    if not upc:
        return jsonify({"ok": False, "error": "missing upc"}), 400

    album = _spotify_album_by_upc(upc, market)
    if not album:
        return jsonify({"ok": False, "upc": upc, "link": None, "error": "spotify_album_not_found"}), 404

    artist = (album["artists"][0]["name"] if album.get("artists") else "").strip()
    album_name = album.get("name", "").strip()
    tried = []

    if mode in ("auto", "album"):
        tried.append("album")
        q_album = f"{artist} {album_name}"
        link = _ytmusic_best_link(q_album)
        if link and "browse/" in link:
            return jsonify({"ok": True, "upc": upc, "query_used": q_album, "link": link, "fallbacks_tried": tried})

    if mode in ("auto", "track"):
        tracks = _spotify_album_tracks(album["id"], market)
        for t in tracks[:10]:
            tried.append("track")
            q_track = f"{artist} {t['name']}"
            link = _ytmusic_best_link(q_track)
            if link:
                return jsonify({"ok": True, "upc": upc, "query_used": q_track, "link": link, "fallbacks_tried": tried})

    tried.append("generic")
    q_generic = f"{artist} {album_name}"
    link = _ytmusic_best_link(q_generic)
    return jsonify({"ok": bool(link), "upc": upc, "query_used": q_generic, "link": link, "fallbacks_tried": tried})

@app.get("/")
def health():
    return jsonify({"status": "ok"})
