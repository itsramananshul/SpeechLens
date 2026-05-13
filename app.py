import os, sys, time, json, threading, uuid
from pathlib import Path

# Flask only — whisper is imported lazily inside the worker thread
# so startup is instant and doesn't block
try:
    from flask import Flask, request, jsonify, send_from_directory, Response
except ImportError:
    import subprocess
    print("[SpeechLens] Installing flask...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "-q"])
    from flask import Flask, request, jsonify, send_from_directory, Response

app = Flask(__name__, static_folder="static")

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".mp4", ".flac", ".ogg", ".webm", ".aac", ".wma", ".opus"}
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

jobs = {}
job_lock = threading.Lock()

worker_event = threading.Event()
run_config = {"model": "large-v3", "language": None, "task": "transcribe"}
loaded_model = {"name": None, "model": None}
model_lock = threading.Lock()

def get_model(name):
    with model_lock:
        if loaded_model["name"] != name:
            print(f"[SpeechLens] Loading model '{name}'...", flush=True)
            import whisper
            loaded_model["model"] = whisper.load_model(name)
            loaded_model["name"] = name
            print(f"[SpeechLens] Model ready.", flush=True)
        return loaded_model["model"]

def pick_next():
    with job_lock:
        pending = [j for j in jobs.values() if j["status"] == "pending"]
        if not pending:
            return None
        return min(pending, key=lambda j: j["order"])

def worker():
    while True:
        worker_event.wait()
        worker_event.clear()
        while True:
            job = pick_next()
            if not job:
                break
            _run(job["id"], job["path"], run_config["model"], run_config["language"], run_config["task"])

def _run(job_id, file_path, model_name, language, task):
    with job_lock:
        jobs[job_id]["status"] = "loading"
        jobs[job_id]["message"] = f"Loading model '{model_name}'..."
    try:
        model = get_model(model_name)
        with job_lock:
            jobs[job_id]["status"] = "transcribing"
            jobs[job_id]["message"] = "Transcribing..."
        start = time.time()
        import torch
        opts = {"verbose": False, "task": task, "fp16": torch.cuda.is_available()}
        if language:
            opts["language"] = language
        result = model.transcribe(str(file_path), **opts)
        elapsed = round(time.time() - start, 1)
        text = result["text"].strip()
        segments = [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result.get("segments", [])
        ]
        with job_lock:
            jobs[job_id].update({
                "status": "done", "message": f"Done in {elapsed}s",
                "text": text, "segments": segments,
                "language": result.get("language", "unknown"),
                "elapsed": elapsed, "words": len(text.split()), "chars": len(text),
            })
        print(f"[SpeechLens] Done: {jobs[job_id]['name']} in {elapsed}s", flush=True)
    except Exception as e:
        print(f"[SpeechLens] Error: {e}", flush=True)
        with job_lock:
            jobs[job_id].update({"status": "error", "message": str(e)})

threading.Thread(target=worker, daemon=True).start()

def fmt_srt(t):
    h=int(t//3600); m=int((t%3600)//60); s=int(t%60); ms=int((t-int(t))*1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def fmt_vtt(t):
    h=int(t//3600); m=int((t%3600)//60); s=int(t%60); ms=int((t-int(t))*1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"

def build_srt(segs):
    return "\n".join(f"{i}\n{fmt_srt(s['start'])} --> {fmt_srt(s['end'])}\n{s['text']}\n" for i,s in enumerate(segs,1))

def build_vtt(segs):
    return "WEBVTT\n\n" + "\n".join(f"{fmt_vtt(s['start'])} --> {fmt_vtt(s['end'])}\n{s['text']}\n" for s in segs)

def build_tsv(segs):
    return "start\tend\ttext\n" + "\n".join(f"{s['start']:.3f}\t{s['end']:.3f}\t{s['text']}" for s in segs)

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    result = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in AUDIO_EXTS:
            result.append({"name": f.filename, "error": f"Unsupported: {ext}"}); continue
        job_id = str(uuid.uuid4())
        save_path = UPLOAD_DIR / f"{job_id}{ext}"
        f.save(save_path)
        size_mb = round(save_path.stat().st_size / 1024 / 1024, 2)
        with job_lock:
            jobs[job_id] = {
                "id": job_id, "name": f.filename, "status": "queued",
                "message": "Queued", "text": "", "segments": [],
                "language": "", "elapsed": 0, "words": 0, "chars": 0,
                "path": str(save_path), "size_mb": size_mb, "order": len(jobs),
            }
        result.append({"id": job_id, "name": f.filename, "size_mb": size_mb})
    return jsonify(result)

@app.route("/transcribe", methods=["POST"])
def transcribe_route():
    data = request.json
    job_ids = data.get("ids", [])
    run_config["model"] = data.get("model", "large-v3")
    run_config["language"] = data.get("language", "").strip() or None
    run_config["task"] = data.get("task", "transcribe")
    for job_id in job_ids:
        if job_id not in jobs: continue
        if jobs[job_id]["status"] in ("loading", "transcribing"): continue
        with job_lock:
            jobs[job_id]["status"] = "pending"
            jobs[job_id]["message"] = "In queue..."
    worker_event.set()
    return jsonify({"ok": True})

@app.route("/status")
def status():
    ids = request.args.get("ids", "").split(",")
    out = {}
    for job_id in ids:
        if job_id in jobs:
            j = jobs[job_id]
            out[job_id] = {k: j[k] for k in ("status","message","language","elapsed","words","chars","name","size_mb")}
    return jsonify(out)

@app.route("/result/<job_id>")
def result(job_id):
    if job_id not in jobs: return jsonify({"error": "Not found"}), 404
    j = jobs[job_id]
    return jsonify({"text": j.get("text",""), "segments": j.get("segments",[])})

@app.route("/reorder", methods=["POST"])
def reorder():
    order = request.json.get("order", [])
    for i, job_id in enumerate(order):
        if job_id in jobs:
            jobs[job_id]["order"] = i
    return jsonify({"ok": True})

@app.route("/delete/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    if job_id in jobs:
        try: Path(jobs[job_id]["path"]).unlink(missing_ok=True)
        except: pass
        del jobs[job_id]
    return jsonify({"ok": True})

@app.route("/download/<job_id>/<fmt>")
def download(job_id, fmt):
    if job_id not in jobs: return "Not found", 404
    j = jobs[job_id]
    stem = Path(j["name"]).stem
    segs = j.get("segments", [])
    if fmt == "txt":
        return Response(j.get("text",""), mimetype="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{stem}_transcript.txt"'})
    elif fmt == "srt":
        return Response(build_srt(segs), mimetype="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{stem}_transcript.srt"'})
    elif fmt == "vtt":
        return Response(build_vtt(segs), mimetype="text/vtt",
            headers={"Content-Disposition": f'attachment; filename="{stem}_transcript.vtt"'})
    elif fmt == "tsv":
        return Response(build_tsv(segs), mimetype="text/tab-separated-values",
            headers={"Content-Disposition": f'attachment; filename="{stem}_transcript.tsv"'})
    elif fmt == "json":
        payload = json.dumps({"text": j.get("text",""), "segments": segs, "language": j.get("language","")}, indent=2)
        return Response(payload, mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{stem}_transcript.json"'})
    return "Bad format", 400

@app.route("/download_merged", methods=["POST"])
def download_merged():
    data = request.json
    ids = data.get("ids", [])
    fmt = data.get("fmt", "txt")
    sep = data.get("separator", "\n\n---\n\n")
    parts = []
    for job_id in ids:
        if job_id not in jobs: continue
        j = jobs[job_id]
        if j["status"] != "done": continue
        header = f"# {j['name']}\n\n"
        parts.append(header + (j.get("text","") if fmt=="txt" else build_srt(j.get("segments",[]))))
    return Response(sep.join(parts), mimetype="text/plain",
        headers={"Content-Disposition": f'attachment; filename="merged_transcript.{fmt}"'})

if __name__ == "__main__":
    import webbrowser
    print("\n  SpeechLens  →  http://localhost:7331\n", flush=True)
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:7331")).start()
    app.run(port=7331, debug=False, threaded=True)
