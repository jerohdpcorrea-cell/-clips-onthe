import os
import re
import uuid
import shutil
import threading
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

app = FastAPI(title="CLIPS.ONTHE", version="2.0.0")

BASE = Path("/tmp/clips-onthe")
BASE.mkdir(parents=True, exist_ok=True)
MAX_DOWNLOAD_BYTES = 650 * 1024 * 1024
MAX_VIDEO_SECONDS = 2 * 60 * 60
CLIP_SECONDS = 15
MAX_STORAGE_BYTES = 1500 * 1024 * 1024
JOB_TTL_SECONDS = 8 * 60 * 60
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "kick.com", "www.kick.com"}
JOBS = {}
JOBS_LOCK = threading.Lock()
ACTIVE_JOB = False

HTML = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#090910"><title>CLIPS.ONTHE</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at top,#21163c 0,#090910 58%);color:#f8f7ff;font-family:Inter,Arial,sans-serif;padding:32px 18px}
main{max-width:680px;margin:5vh auto}.brand{font-size:clamp(34px,8vw,54px);font-weight:900;letter-spacing:-2px;margin:0}.brand span{color:#a78bfa}
.tag{color:#b9b4ca;margin:8px 0 28px}.panel{background:#171525;border:1px solid #302943;border-radius:22px;padding:24px;box-shadow:0 18px 60px #0007}
label{display:block;font-size:14px;color:#d8d3e8;margin:14px 0 8px}input,select,button{width:100%;border-radius:12px;padding:15px;font-size:16px}
input,select{background:#0e0d17;color:white;border:1px solid #49405e;outline:none}input:focus,select:focus{border-color:#a78bfa}
button{margin-top:18px;background:linear-gradient(100deg,#7c3aed,#a855f7);color:white;border:0;font-weight:800;cursor:pointer}button:disabled{opacity:.55;cursor:wait}
#result{margin-top:18px;line-height:1.55;overflow-wrap:anywhere}.muted{color:#aaa3bd;font-size:13px}.clip{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 0;border-top:1px solid #393249}.clip a{color:#d6c4ff;font-weight:700}.error{color:#ffb4b4}.ok{color:#b7f7ca}
footer{color:#817b91;font-size:12px;text-align:center;margin-top:18px}
</style></head><body><main>
<h1 class="brand">CLIPS<span>.ONTHE</span></h1><p class="tag">Convierte vídeos en clips verticales listos para compartir.</p>
<section class="panel"><form id="form">
<label for="url">Enlace del vídeo de YouTube o Kick</label>
<input id="url" name="url" type="url" required placeholder="https://..." autocomplete="url">
<label for="count">¿Cuántos clips quieres?</label>
<select id="count" name="count"><option value="5">5 clips</option><option value="10">10 clips</option><option value="20" selected>20 clips</option></select>
<button id="btn" type="submit">GENERAR CLIPS</button>
</form><div id="result" aria-live="polite"></div>
</section><footer>Procesamiento sujeto a disponibilidad y restricciones de la plataforma de origen.</footer>
</main><script>
const form=document.querySelector("#form"),btn=document.querySelector("#btn"),result=document.querySelector("#result");
form.addEventListener("submit",async e=>{
 e.preventDefault();btn.disabled=true;result.textContent="Enviando vídeo para procesar…";
 try{
  const res=await fetch("/api/clips",{method:"POST",body:new FormData(form)});
  const data=await res.json();if(!res.ok)throw new Error(data.detail||"No se pudo iniciar el trabajo.");
  result.textContent="Trabajo iniciado. Preparando tus clips…";
  let finished=false;
  while(!finished){
   await new Promise(r=>setTimeout(r,3000));
   const check=await fetch("/api/jobs/"+encodeURIComponent(data.job_id));
   const state=await check.json();if(!check.ok)throw new Error(state.detail||"No se pudo consultar el trabajo.");
   if(state.status==="failed")throw new Error(state.error||"No se pudo procesar el vídeo.");
   if(state.status==="done"){
    finished=true;result.innerHTML="<p class='ok'>¡Listo! Tus clips están preparados:</p>"+state.clips.map(c=>"<div class='clip'><span>"+c.name+"</span><a href='"+c.url+"' download>Descargar ↓</a></div>").join("");
   }else{result.textContent=state.message||"Procesando vídeo…";}
  }
 }catch(err){result.innerHTML="<p class='error'>"+String(err.message).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))+"</p>";}
 finally{btn.disabled=false;}
});
</script></body></html>"""

def cleanup_old_jobs():
    now = time.time()
    for folder in BASE.iterdir():
        try:
            if folder.is_dir() and now - folder.stat().st_mtime > JOB_TTL_SECONDS:
                shutil.rmtree(folder, ignore_errors=True)
                with JOBS_LOCK:
                    JOBS.pop(folder.name, None)
        except OSError:
            pass

def folder_size(path):
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total

def valid_source_url(raw):
    try:
        parsed = urlparse(raw.strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and host in ALLOWED_HOSTS and not parsed.username and not parsed.password
    except Exception:
        return False

def download_size_guard(data):
    if data.get("status") != "downloading":
        return
    downloaded = data.get("downloaded_bytes") or 0
    estimated = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
    if downloaded > MAX_DOWNLOAD_BYTES or estimated > MAX_DOWNLOAD_BYTES:
        raise yt_dlp.utils.DownloadError("max-filesize")


def safe_error(exc):
    msg = str(exc).lower()
    if "not a bot" in msg or "sign in to confirm" in msg:
        return "YouTube bloqueó la descarga automática desde el servidor. Prueba más tarde o usa un vídeo público de Kick; algunos vídeos de YouTube requieren una sesión verificada."
    if "429" in msg or "too many requests" in msg:
        return "La plataforma limitó las descargas (HTTP 429). Espera un rato e inténtalo más tarde."
    if "403" in msg or "forbidden" in msg or "player response" in msg:
        return "La plataforma bloqueó esta descarga (HTTP 403). Prueba otro vídeo público; algunos vídeos no permiten extracción desde servidores."
    if "private" in msg or "login" in msg or "members-only" in msg:
        return "El vídeo es privado o requiere iniciar sesión. Usa un vídeo público."
    if "max-filesize" in msg or "file is larger" in msg:
        return "El vídeo supera el límite de tamaño de 650 MB."
    if "duration" in msg or "demasiado largo" in msg:
        return "El vídeo supera el límite de duración de 2 horas."
    return "No se pudo procesar el vídeo. Comprueba que el enlace sea público y vuelve a intentarlo."

def process_job(job_id, url, count):
    global ACTIVE_JOB
    folder = BASE / job_id
    try:
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "processing", "message": "Descargando vídeo…", "clips": []}
        options = {
            "format": "best[height<=360][ext=mp4]/best[height<=360]",
            "outtmpl": str(folder / "source.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 25,
            "retries": 2,
            "fragment_retries": 2,
            "extractor_retries": 2,
            "max_filesize": MAX_DOWNLOAD_BYTES,
            "progress_hooks": [download_size_guard],
            "match_filter": yt_dlp.utils.match_filter_func("!is_live & duration <= 7200"),
            "overwrites": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
        videos = list(folder.glob("source.*"))
        if not videos:
            raise RuntimeError("No se encontró el archivo descargado.")
        video = videos[0]
        if video.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise RuntimeError("max-filesize")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True, timeout=30
        )
        duration = float(probe.stdout.strip())
        if duration <= CLIP_SECONDS:
            raise RuntimeError("El vídeo es demasiado corto para crear clips.")
        if duration > MAX_VIDEO_SECONDS:
            raise RuntimeError("duration")
        total = min(count, max(1, int(duration // CLIP_SECONDS)))
        clips = []
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "processing", "message": "Creando clips verticales…", "clips": []}
        for i in range(total):
            start = max(0, (duration - CLIP_SECONDS) * i / max(1, total - 1))
            filename = f"clip_{i+1:02d}.mp4"
            output = folder / filename
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(start), "-i", str(video), "-t", str(CLIP_SECONDS),
                "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output)
            ], capture_output=True, check=True, timeout=180)
            clips.append({"name": f"Clip {i+1}", "url": f"/download/{job_id}/{filename}"})
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "processing", "message": f"Creando clips… {i+1}/{total}", "clips": []}
            if folder_size(BASE) > MAX_STORAGE_BYTES:
                raise RuntimeError("Se alcanzó el límite temporal de almacenamiento. Inténtalo con menos clips.")
        video.unlink(missing_ok=True)
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "done", "message": "Clips listos.", "clips": clips}
    except Exception as exc:
        print(f"CLIPS.ONTHE job {job_id} failed: {type(exc).__name__}: {exc}", flush=True)
        shutil.rmtree(folder, ignore_errors=True)
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "failed", "message": "No se pudo procesar el vídeo.", "error": safe_error(exc), "clips": []}
    finally:
        ACTIVE_JOB = False

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.get("/healthz")
def health():
    return {"status": "ok", "service": "CLIPS.ONTHE"}

@app.post("/api/clips")
def create_clips(background_tasks: BackgroundTasks, url: str = Form(...), count: int = Form(20)):
    global ACTIVE_JOB
    cleanup_old_jobs()
    if count not in (5, 10, 20):
        raise HTTPException(400, "Selecciona 5, 10 o 20 clips.")
    if not valid_source_url(url):
        raise HTTPException(400, "Pega un enlace HTTPS válido de YouTube o Kick.")
    if folder_size(BASE) > MAX_STORAGE_BYTES:
        raise HTTPException(503, "El espacio temporal está ocupado. Inténtalo de nuevo más tarde.")
    with JOBS_LOCK:
        if ACTIVE_JOB:
            raise HTTPException(429, "Ya hay un vídeo procesándose. Espera a que termine.")
        ACTIVE_JOB = True
    job_id = uuid.uuid4().hex
    (BASE / job_id).mkdir(parents=True, exist_ok=False)
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "message": "Trabajo en cola…", "clips": []}
    background_tasks.add_task(process_job, job_id, url, count)
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "Trabajo no encontrado.")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "El trabajo expiró o el servidor se reinició. Inicia uno nuevo.")
    return job

@app.get("/download/{job_id}/{filename}")
def download(job_id: str, filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id) or not re.fullmatch(r"clip_[0-9]{2}\.mp4", filename):
        raise HTTPException(404, "Clip no encontrado.")
    path = BASE / job_id / filename
    if not path.is_file() or path.parent.parent != BASE:
        raise HTTPException(404, "Clip no encontrado.")
    return FileResponse(path, filename=filename, media_type="video/mp4")
