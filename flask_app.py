from flask import Flask, render_template, jsonify, request
import sqlite3
import requests
import time
import os
import atexit
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DONNÉES SQLite
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'test_results.db')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS test_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT    NOT NULL,
            test_name     TEXT    NOT NULL,
            status        TEXT    NOT NULL,
            response_time REAL,
            status_code   INTEGER,
            message       TEXT
        )
    ''')
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION API  —  Open-Meteo (aucune clé requise)
# ─────────────────────────────────────────────────────────────────────────────
FORECAST_URL  = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
PARIS_PARAMS  = {
    "latitude": 48.8566,
    "longitude": 2.3522,
    "current_weather": "true"
}


# ─────────────────────────────────────────────────────────────────────────────
# MOTEUR DE TESTS
# ─────────────────────────────────────────────────────────────────────────────
def _store_result(test_name, status, rt, code, msg):
    """Persiste un résultat de test dans la base de données."""
    conn = get_db()
    conn.execute(
        "INSERT INTO test_results "
        "(timestamp, test_name, status, response_time, status_code, message) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
         test_name, status, rt, code, msg)
    )
    conn.commit()
    conn.close()


def _execute_test(name, fn):
    """Exécute un test, mesure le temps, stocke le résultat."""
    t0 = time.time()
    try:
        result = fn()
        rt     = round((time.time() - t0) * 1000, 2)
        status = "PASS" if result["ok"] else "FAIL"
        _store_result(name, status, rt,
                      result.get("status_code"),
                      result.get("message", ""))
    except Exception as exc:
        rt = round((time.time() - t0) * 1000, 2)
        _store_result(name, "ERROR", rt, None, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# CAS DE TEST
# ─────────────────────────────────────────────────────────────────────────────
def t_status_200():
    """Vérifie que l'API répond avec HTTP 200."""
    r = requests.get(FORECAST_URL, params=PARIS_PARAMS, timeout=10)
    return {
        "ok": r.status_code == 200,
        "status_code": r.status_code,
        "message": f"HTTP {r.status_code}"
    }


def t_response_time():
    """Vérifie que le temps de réponse est inférieur à 2 000 ms."""
    t0 = time.time()
    r  = requests.get(FORECAST_URL, params=PARIS_PARAMS, timeout=10)
    ms = (time.time() - t0) * 1000
    return {
        "ok": ms < 2000,
        "status_code": r.status_code,
        "message": f"{round(ms, 1)} ms (seuil : 2 000 ms)"
    }


def t_champs_requis():
    """Vérifie la présence des champs JSON obligatoires dans la réponse."""
    r       = requests.get(FORECAST_URL, params=PARIS_PARAMS, timeout=10)
    data    = r.json()
    missing = [f for f in ["current_weather", "latitude", "longitude"]
               if f not in data]
    return {
        "ok": not missing,
        "status_code": r.status_code,
        "message": "Tous les champs présents" if not missing
                   else f"Champs manquants : {missing}"
    }


def t_temperature():
    """Vérifie que la température retournée est dans une plage réaliste."""
    r    = requests.get(FORECAST_URL, params=PARIS_PARAMS, timeout=10)
    temp = r.json()["current_weather"]["temperature"]
    ok   = -90 <= temp <= 60
    return {
        "ok": ok,
        "status_code": r.status_code,
        "message": f"Température : {temp} °C  (plage acceptée : -90 à 60)"
    }


def t_geocoding():
    """Vérifie que l'endpoint de géocodage répond correctement."""
    r  = requests.get(GEOCODING_URL,
                      params={"name": "Paris", "count": 1, "language": "fr"},
                      timeout=10)
    ok = r.status_code == 200 and "results" in r.json()
    return {
        "ok": ok,
        "status_code": r.status_code,
        "message": f"Geocoding HTTP {r.status_code}"
    }


def t_content_type():
    """Vérifie que le Content-Type de la réponse est application/json."""
    r  = requests.get(FORECAST_URL, params=PARIS_PARAMS, timeout=10)
    ct = r.headers.get("Content-Type", "")
    ok = "application/json" in ct
    return {
        "ok": ok,
        "status_code": r.status_code,
        "message": f"Content-Type : {ct}"
    }


# Registre de tous les tests
ALL_TESTS = [
    ("Statut HTTP 200",                t_status_200),
    ("Temps réponse < 2 000 ms",       t_response_time),
    ("Champs JSON requis présents",     t_champs_requis),
    ("Température dans plage réelle",  t_temperature),
    ("Endpoint Géocodage",             t_geocoding),
    ("Content-Type application/json",  t_content_type),
]


def run_all_tests():
    """Lance l'ensemble des tests et stocke les résultats."""
    for name, fn in ALL_TESTS:
        _execute_test(name, fn)


# ─────────────────────────────────────────────────────────────────────────────
# PLANIFICATEUR  (toutes les 5 minutes)
# ─────────────────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(
    func=run_all_tests,
    trigger="interval",
    minutes=5,
    id="api_monitor",
    next_run_time=datetime.now() + timedelta(seconds=10)   # 1er run 10 s après démarrage
)
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES FLASK
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("consignes.html")


@app.get("/monitoring")
def monitoring():
    return render_template("dashboard.html")


@app.post("/run-tests")
def run_tests_now():
    """Déclenche manuellement l'exécution des tests."""
    run_all_tests()
    return jsonify({"status": "ok", "message": f"{len(ALL_TESTS)} tests exécutés avec succès"})


@app.get("/api/results")
def api_results():
    """Retourne les N derniers résultats au format JSON."""
    limit = int(request.args.get("limit", 60))
    conn  = get_db()
    rows  = conn.execute(
        "SELECT * FROM test_results ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/metrics")
def api_metrics():
    """Retourne les métriques QoS agrégées."""
    conn = get_db()
    total   = conn.execute("SELECT COUNT(*) FROM test_results").fetchone()[0]
    passed  = conn.execute("SELECT COUNT(*) FROM test_results WHERE status='PASS'").fetchone()[0]
    failed  = conn.execute("SELECT COUNT(*) FROM test_results WHERE status='FAIL'").fetchone()[0]
    errors  = conn.execute("SELECT COUNT(*) FROM test_results WHERE status='ERROR'").fetchone()[0]
    avg_rt  = conn.execute("SELECT AVG(response_time) FROM test_results").fetchone()[0]
    min_rt  = conn.execute("SELECT MIN(response_time) FROM test_results WHERE status='PASS'").fetchone()[0]
    max_rt  = conn.execute("SELECT MAX(response_time) FROM test_results WHERE status='PASS'").fetchone()[0]
    last_ts = conn.execute(
        "SELECT timestamp FROM test_results ORDER BY id DESC LIMIT 1"
    ).fetchone()
    per_test = conn.execute("""
        SELECT t1.test_name,
               COUNT(*)  AS total,
               SUM(CASE WHEN t1.status = 'PASS' THEN 1 ELSE 0 END) AS passed,
               AVG(t1.response_time) AS avg_rt,
               (SELECT t2.status FROM test_results t2
                WHERE t2.test_name = t1.test_name
                ORDER BY t2.id DESC LIMIT 1) AS last_status
        FROM test_results t1
        GROUP BY t1.test_name
    """).fetchall()
    conn.close()

    avail = round(passed / total * 100, 1) if total else 0
    return jsonify({
        "total":        total,
        "passed":       passed,
        "failed":       failed,
        "errors":       errors,
        "availability": avail,
        "avg_rt":       round(avg_rt, 1) if avg_rt else None,
        "min_rt":       round(min_rt, 1) if min_rt else None,
        "max_rt":       round(max_rt, 1) if max_rt else None,
        "last_run":     last_ts[0] if last_ts else None,
        "per_test":     [dict(r) for r in per_test],
    })


# ─────────────────────────────────────────────────────────────────────────────
# INITIALISATION
# ─────────────────────────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
