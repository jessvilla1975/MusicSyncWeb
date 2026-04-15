import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request
from ytmusicapi import setup

from sync_playlist import (
    normalize_spotify_playlist_id,
    normalize_ytmusic_playlist_id,
    sync_spotify_to_ytmusic,
)

app = Flask(__name__)
SYNC_LOCK = threading.Lock()
SYNC_STATE = {
    "running": False,
    "done": False,
    "error": "",
    "message": "",
    "total": 0,
    "processed": 0,
    "added": 0,
    "not_found": 0,
    "logs": [],
}

PAGE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Music Sync Web</title>
  <style>
    :root {
      --bg: #0b1020;
      --card: #151b2f;
      --muted: #9aa5ce;
      --text: #edf1ff;
      --ok: #19c37d;
      --err: #ff5f7a;
      --accent: #5b8cff;
      --border: #253053;
    }
    body {
      margin: 0;
      background: radial-gradient(circle at top right, #1f2850, var(--bg));
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
    }
    .wrap { max-width: 1040px; margin: 22px auto; padding: 0 16px; }
    .title { margin: 0 0 4px; font-size: 28px; }
    .subtitle { margin: 0 0 18px; color: var(--muted); }
    .grid { display: grid; grid-template-columns: 1fr; gap: 14px; }
    .card {
      background: rgba(21, 27, 47, 0.95);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 10px 20px rgba(0, 0, 0, 0.25);
    }
    h2 { margin: 0 0 12px; font-size: 18px; }
    label { display: block; margin: 10px 0 6px; font-weight: 600; font-size: 14px; }
    input, textarea, select {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #0f1530;
      color: var(--text);
      padding: 10px 12px;
    }
    textarea { min-height: 130px; font-family: Consolas, monospace; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .btn {
      border: 0;
      border-radius: 10px;
      background: var(--accent);
      color: white;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
      margin-top: 12px;
    }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .alert {
      margin-top: 10px;
      border-radius: 10px;
      padding: 10px 12px;
      white-space: pre-wrap;
      display: none;
    }
    .alert.ok { background: rgba(25, 195, 125, 0.15); border: 1px solid rgba(25, 195, 125, 0.5); color: #b9ffe2; }
    .alert.err { background: rgba(255, 95, 122, 0.15); border: 1px solid rgba(255, 95, 122, 0.5); color: #ffd0d9; }
    .progress-wrap { background: #0f1530; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; margin-top: 8px; }
    .progress-bar { height: 14px; width: 0%; background: linear-gradient(90deg, #4ea8ff, #7c4dff); transition: width 0.2s ease; }
    .stats { margin-top: 8px; color: var(--muted); font-size: 14px; }
    .log {
      margin-top: 10px;
      max-height: 280px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #0f1530;
      padding: 8px;
      font-family: Consolas, monospace;
      font-size: 13px;
    }
    .log div { margin: 4px 0; }
    @media (max-width: 760px) { .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="title">Music Sync Web</h1>
    <p class="subtitle">Sincroniza playlist publica de Spotify a YouTube Music sin usar Spotify Premium API.</p>

    <div class="grid">
      <div class="card">
        <h2>1) Generar browser.json</h2>
        <label>Request headers de YouTube Music</label>
        <textarea id="headers_raw" placeholder="Pega aqui los headers de una request browse/next de music.youtube.com"></textarea>
        <button class="btn" id="saveHeadersBtn">Guardar browser.json</button>
        <div id="headersAlert" class="alert"></div>
      </div>

      <div class="card">
        <h2>2) Sincronizar playlist</h2>
        <div class="row">
          <div>
            <label>Fuente Spotify</label>
            <select id="spotify_source">
              <option value="web" selected>web (sin API)</option>
              <option value="api">api (requiere credenciales)</option>
            </select>
          </div>
          <div>
            <label>Archivo auth YT</label>
            <input id="yt_auth" value="browser.json">
          </div>
        </div>
        <label>URL/ID de playlist Spotify</label>
        <input id="spotify_playlist_id" placeholder="https://open.spotify.com/playlist/...">
        <div class="row">
          <div>
            <label>Nombre playlist YouTube Music</label>
            <input id="yt_playlist_name" placeholder="Mi playlist YT">
          </div>
          <div>
            <label>ID/URL playlist YT (opcional)</label>
            <input id="yt_playlist_id" placeholder="PL... o https://music.youtube.com/playlist?list=...">
          </div>
        </div>
        <button class="btn" id="syncBtn">Iniciar sincronizacion</button>
        <div id="syncAlert" class="alert"></div>

        <div class="progress-wrap"><div class="progress-bar" id="progressBar"></div></div>
        <div class="stats" id="stats">Esperando sincronizacion...</div>
        <div class="log" id="logs"></div>
      </div>
    </div>
  </div>

  <script>
    const headersBtn = document.getElementById("saveHeadersBtn");
    const syncBtn = document.getElementById("syncBtn");
    const headersAlert = document.getElementById("headersAlert");
    const syncAlert = document.getElementById("syncAlert");
    const progressBar = document.getElementById("progressBar");
    const stats = document.getElementById("stats");
    const logs = document.getElementById("logs");
    let pollTimer = null;

    function setAlert(el, ok, message) {
      el.style.display = "block";
      el.className = "alert " + (ok ? "ok" : "err");
      el.textContent = message;
    }

    function renderStatus(data) {
      const total = data.total || 0;
      const processed = data.processed || 0;
      const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
      progressBar.style.width = pct + "%";
      stats.textContent = `Progreso: ${processed}/${total} | Agregadas: ${data.added || 0} | No encontradas: ${data.not_found || 0}`;
      logs.innerHTML = (data.logs || []).map(line => `<div>${line}</div>`).join("");
      logs.scrollTop = logs.scrollHeight;
    }

    async function pollStatus() {
      const res = await fetch("/sync-status");
      const data = await res.json();
      renderStatus(data);
      if (data.error) setAlert(syncAlert, false, data.error);
      if (data.done && !data.error) setAlert(syncAlert, true, data.message || "Sincronizacion completada.");
      if (data.done) {
        syncBtn.disabled = false;
        if (pollTimer) clearInterval(pollTimer);
      }
    }

    headersBtn.addEventListener("click", async () => {
      const headers_raw = document.getElementById("headers_raw").value;
      const res = await fetch("/save-headers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ headers_raw })
      });
      const data = await res.json();
      setAlert(headersAlert, data.success, data.message);
    });

    syncBtn.addEventListener("click", async () => {
      syncBtn.disabled = true;
      syncAlert.style.display = "none";
      logs.innerHTML = "";
      progressBar.style.width = "0%";
      stats.textContent = "Iniciando...";

      const payload = {
        spotify_source: document.getElementById("spotify_source").value,
        spotify_playlist_id: document.getElementById("spotify_playlist_id").value,
        yt_playlist_name: document.getElementById("yt_playlist_name").value,
        yt_playlist_id: document.getElementById("yt_playlist_id").value,
        yt_auth: document.getElementById("yt_auth").value
      };

      const res = await fetch("/start-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!data.success) {
        syncBtn.disabled = false;
        setAlert(syncAlert, false, data.message);
        return;
      }
      pollTimer = setInterval(pollStatus, 900);
      pollStatus();
    });
  </script>
</body>
</html>
"""


def normalize_headers_text(headers_raw: str) -> str:
    lines = [line.strip() for line in headers_raw.splitlines() if line.strip()]
    if not lines:
        return ""
    if any(": " in line for line in lines):
        return "\n".join(lines)
    normalized = []
    i = 0
    while i < len(lines):
        key = lines[i]
        value = lines[i + 1] if i + 1 < len(lines) else ""
        normalized.append(f"{key}: {value}")
        i += 2
    return "\n".join(normalized)


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.post("/save-headers")
def save_headers():
    data = request.get_json(silent=True) or {}
    headers_raw = str(data.get("headers_raw", "")).strip()
    try:
        normalized = normalize_headers_text(headers_raw)
        if not normalized:
            raise ValueError("Debes pegar los headers de YouTube Music.")
        setup(filepath="browser.json", headers_raw=normalized)
        return jsonify({"success": True, "message": "Exito: browser.json se genero correctamente."})
    except Exception as exc:
        return jsonify({"success": False, "message": f"Error al generar browser.json: {exc}"})


def append_log(line: str) -> None:
    SYNC_STATE["logs"].append(line)
    if len(SYNC_STATE["logs"]) > 300:
        SYNC_STATE["logs"] = SYNC_STATE["logs"][-300:]


def run_sync_job(payload: dict) -> None:
    try:
        spotify_playlist_id = normalize_spotify_playlist_id(payload["spotify_playlist_id"])
        ytmusic_playlist_id = normalize_ytmusic_playlist_id(payload["yt_playlist_id"] or None)

        def progress(event: str, data: dict) -> None:
            if event == "start":
                SYNC_STATE["total"] = int(data.get("total", "0"))
                append_log(f"Iniciando: {SYNC_STATE['total']} canciones detectadas en Spotify.")
                return

            if event in {"added", "exists", "not_found"}:
                SYNC_STATE["processed"] += 1
                title = data.get("title", "")
                artist = data.get("artist", "")
                if event == "added":
                    SYNC_STATE["added"] += 1
                    append_log(f"Agregada: {title} - {artist}")
                elif event == "not_found":
                    SYNC_STATE["not_found"] += 1
                    append_log(f"No encontrada: {title} - {artist}")
                else:
                    append_log(f"Ya existe: {title} - {artist}")
                return

            if event == "done":
                SYNC_STATE["done"] = True
                SYNC_STATE["running"] = False
                SYNC_STATE["message"] = (
                    f"Sincronizacion completada. Agregadas: {SYNC_STATE['added']} | "
                    f"No encontradas: {SYNC_STATE['not_found']}"
                )
                append_log("Proceso finalizado.")

        sync_spotify_to_ytmusic(
            spotify_playlist_id=spotify_playlist_id,
            ytmusic_playlist_name=payload["yt_playlist_name"],
            ytmusic_playlist_id=ytmusic_playlist_id,
            ytmusic_auth_file=payload["yt_auth"],
            spotify_source=payload["spotify_source"],
            progress_callback=progress,
        )
    except Exception as exc:
        SYNC_STATE["error"] = str(exc)
        SYNC_STATE["done"] = True
        SYNC_STATE["running"] = False
        append_log(f"Error: {exc}")
    finally:
        SYNC_LOCK.release()


@app.post("/start-sync")
def start_sync():
    data = request.get_json(silent=True) or {}
    payload = {
        "spotify_source": str(data.get("spotify_source", "web")).strip() or "web",
        "spotify_playlist_id": str(data.get("spotify_playlist_id", "")).strip(),
        "yt_playlist_name": str(data.get("yt_playlist_name", "")).strip(),
        "yt_playlist_id": str(data.get("yt_playlist_id", "")).strip(),
        "yt_auth": str(data.get("yt_auth", "browser.json")).strip() or "browser.json",
    }

    if not payload["spotify_playlist_id"]:
        return jsonify({"success": False, "message": "Falta URL/ID de playlist de Spotify."})
    if not payload["yt_playlist_name"]:
        return jsonify({"success": False, "message": "Falta nombre de playlist de YouTube Music."})
    if not Path(payload["yt_auth"]).exists():
        return jsonify({"success": False, "message": f"No existe el archivo: {payload['yt_auth']}"})
    if not SYNC_LOCK.acquire(blocking=False):
        return jsonify({"success": False, "message": "Ya hay una sincronizacion en progreso."})

    SYNC_STATE.update(
        {
            "running": True,
            "done": False,
            "error": "",
            "message": "",
            "total": 0,
            "processed": 0,
            "added": 0,
            "not_found": 0,
            "logs": [],
        }
    )
    append_log("Preparando sincronizacion...")
    threading.Thread(target=run_sync_job, args=(payload,), daemon=True).start()
    return jsonify({"success": True, "message": "Sincronizacion iniciada."})


@app.get("/sync-status")
def sync_status():
    return jsonify(SYNC_STATE)


if __name__ == "__main__":
    threading.Timer(0.6, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
