from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from adsb_analysis import fetch_planes_near_airport, check_proximity_alerts
from airport_config import AIRPORTS
from threshold_config import THRESHOLDS
import os
import time
import threading

app = Flask(__name__)
app.secret_key = "anicca-demo-key"  # For session handling

# -------------------------------------------------------
# Caching / rate limiting: refresh at most once per hour
# -------------------------------------------------------
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "3600"))  # seconds
_cache = {}               # { "SEA": {"ts": float, "planes": [...] } }
_cache_lock = threading.Lock()

# ---------------- Login Routes ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == "admin" and password == "Anicca":
            session["user"] = username
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ---------------- Main Dashboard --------------
@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))

    airport_coords = {
        code: {"lat": data["lat"], "lon": data["lon"]}
        for code, data in AIRPORTS.items()
    }
    return render_template(
        "index.html",
        airports=AIRPORTS,
        thresholds=THRESHOLDS,
        airport_coords=airport_coords
    )

# ---------------- API -------------------------
@app.route("/api/planes")
def get_planes():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    airport_code = request.args.get("airport", "SEA").upper()
    # optional: ?force=1 to bypass cache (handy for testing)
    force_refresh = request.args.get("force", "0").lower() in ("1", "true", "yes")

    now = time.time()

    # Quick path: serve fresh cache (if present and not forced)
    with _cache_lock:
        cached = _cache.get(airport_code)
        if cached and (not force_refresh) and (now - cached["ts"] < REFRESH_INTERVAL):
            return jsonify(cached["planes"])

    # Refresh path (single-threaded via lock)
    with _cache_lock:
        # Recheck inside lock so multiple concurrent requests don't all fetch
        cached = _cache.get(airport_code)
        if cached and (not force_refresh) and (now - cached["ts"] < REFRESH_INTERVAL):
            return jsonify(cached["planes"])

        try:
            planes = fetch_planes_near_airport(airport_code)
            check_proximity_alerts(planes)
            _cache[airport_code] = {"ts": now, "planes": planes}
            return jsonify(planes)
        except Exception as e:
            # On failure, serve last good cache if available
            if cached:
                return jsonify(cached["planes"])
            return jsonify({"error": f"data fetch failed: {str(e)}"}), 502

# Optional health check for hosting platforms
@app.route("/health")
def health():
    return "ok", 200


if __name__ == "__main__":
    # Bind to the host/port expected by hosting providers
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
