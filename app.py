"""Forex signal web app. Educational decision support only; never places trades."""
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, Response, jsonify
import forex_signals as fs

PAIRS = [p.strip().upper() for p in os.environ.get("PAIRS", ",".join(fs.DEFAULT_PAIRS)).split(",") if p.strip()]
REFRESH_MIN = max(5, int(os.environ.get("REFRESH_MIN", "15")))
DEMO = os.environ.get("DEMO", "0") == "1"

app = Flask(__name__)
_lock = threading.Lock()
state = {"results": [], "updated": None, "error": None}


def refresh():
    results, errors = [], []
    for pair in PAIRS:
        try:
            results.append(fs.analyse(pair, demo=DEMO))
        except Exception as exc:
            errors.append(f"{pair}: {exc}")
    with _lock:
        if results:
            state["results"] = results
            state["updated"] = datetime.now(timezone.utc).isoformat()
        state["error"] = "; ".join(errors) or None


def loop():
    while True:
        try:
            refresh()
        except Exception as exc:
            with _lock:
                state["error"] = str(exc)
        time.sleep(REFRESH_MIN * 60)


# Avoid starting duplicate refresh loops when Flask's development reloader is active.
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    threading.Thread(target=loop, name="signal-refresh", daemon=True).start()


@app.route("/")
def home():
    with _lock:
        results, updated, error = list(state["results"]), state["updated"], state["error"]
    if not results:
        msg = error or "Loading first analysis; data providers may take a little while."
        return Response(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="10"><title>Forex Signals</title><body style="font-family:sans-serif;padding:24px"><h1>Forex Signals</h1><p>{fs.escape_text(msg)}</p><p>Signals are experimental and are not guaranteed.</p></body>', mimetype="text/html")
    return Response(fs.render_dashboard(results, updated), mimetype="text/html")


@app.route("/api/signals")
def api():
    keys = ("pair", "price", "signal", "score", "tech", "news", "sl", "tp", "why", "data_time", "news_count", "warning")
    with _lock:
        results, updated, error = list(state["results"]), state["updated"], state["error"]
    return jsonify(updated=updated, error=error,
                   disclaimer="Experimental decision support only. No signal is guaranteed; this is not financial advice.",
                   signals=[{k: r.get(k) for k in keys} for r in results])


@app.route("/health")
def health():
    return jsonify(status="ok", updated=state["updated"]), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
