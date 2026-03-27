"""
GNC Anime — Flask Backend
Proxies Jikan API (MyAnimeList), adds CORS, caching, and ML recommendations.
Run: python app.py
"""
import os, json, time, pickle, math
from flask import Flask, request, jsonify
from urllib.request import urlopen, Request
from urllib.error import URLError
from functools import lru_cache

BASE   = os.path.dirname(__file__)
JIKAN  = "https://api.jikan.moe/v4"

app = Flask(__name__)

# ── CORS ────────────────────────────────────────────────
@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def preflight(_path=None): return jsonify({}), 200

# ── IN-MEMORY CACHE ─────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 3600  # 1 hour

def cache_get(key):
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None

def cache_set(key, val):
    _cache[key] = (val, time.time())
    return val

# ── JIKAN PROXY ─────────────────────────────────────────
_last_jikan = 0.0

def jikan(path: str):
    """Proxies Jikan API with rate limiting (3 req/s)"""
    global _last_jikan
    cached = cache_get(path)
    if cached: return cached

    # Rate limiting
    wait = max(0, 0.34 - (time.time() - _last_jikan))
    if wait > 0: time.sleep(wait)
    _last_jikan = time.time()

    try:
        url = JIKAN + path
        req = Request(url, headers={"User-Agent": "GNCAnime/1.0"})
        with urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            return cache_set(path, data)
    except Exception as e:
        print(f"Jikan error {path}: {e}")
        return None

# ── ROUTES ──────────────────────────────────────────────
@app.route("/health")
def health(): return jsonify({"status": "ok", "source": "Jikan MAL API"})

@app.route("/login", methods=["POST"])
def login():
    d = request.get_json(force=True, silent=True) or {}
    name  = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip()
    if not name or not email: return jsonify({"error": "Name and email required"}), 400
    return jsonify({"success": True, "user": {"name": name, "email": email}})

@app.route("/anime/top")
def top_anime():
    page   = int(request.args.get("page", 1))
    sort   = request.args.get("sort", "score")
    genre  = request.args.get("genre", "")
    year   = request.args.get("year", "")

    if sort == "airing":
        path = f"/top/anime?type=tv&filter=airing&page={page}&limit=24"
    elif sort == "upcoming":
        path = f"/top/anime?filter=upcoming&page={page}&limit=24"
    elif sort == "popularity":
        path = f"/top/anime?filter=bypopularity&page={page}&limit=24"
        if genre: path += f"&genres={genre}"
    else:
        if genre or year:
            path = f"/anime?order_by=score&sort=desc&page={page}&limit=24"
            if genre: path += f"&genres={genre}"
            if year:  path += f"&start_date={year}-01-01&end_date={year}-12-31"
        else:
            path = f"/top/anime?page={page}&limit=24"

    data = jikan(path)
    if not data: return jsonify({"error": "Could not fetch from MAL"}), 502
    return jsonify(data)

@app.route("/anime/search")
def search():
    q    = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    if not q: return jsonify({"error": "Query required"}), 400
    data = jikan(f"/anime?q={q}&page={page}&limit=24&sfw=true")
    if not data: return jsonify({"error": "Search failed"}), 502
    return jsonify(data)

@app.route("/anime/<int:mal_id>")
def get_anime(mal_id):
    data = jikan(f"/anime/{mal_id}/full")
    if not data: return jsonify({"error": "Not found"}), 404
    return jsonify(data)

@app.route("/recommend/<int:mal_id>")
def recommend(mal_id):
    data = jikan(f"/anime/{mal_id}/recommendations")
    if not data: return jsonify({"recommendations": []}), 200
    recs = [r["entry"] for r in (data.get("data") or [])[:8]]
    return jsonify({"recommendations": recs})

@app.route("/genres")
def genres():
    data = jikan("/genres/anime")
    if not data: return jsonify([])
    return jsonify(data.get("data", []))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀  GNC Anime API → http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
