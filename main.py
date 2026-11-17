import os
import re
import uuid
import shutil
import threading
import subprocess
import time
import wave
import math
import array
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

app = FastAPI(title="CLIPS.ONTHE", version="2.0.0")

BASE = Path("/tmp/clips-onthe")
BASE.mkdir(parents=True, exist_ok=True)
MAX_DOWNLOAD_BYTES = 650 * 1024 * 1024
MAX_VIDEO_SECONDS = 6 * 60 * 60
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
#result{margin-top:18px;line-height:1.55;overflow-wrap:anywhere}.muted{color:#aaa3bd;font-size:13px}.clip-card{padding:15px 0;border-top:1px solid #393249}.clip-card h3{margin:4px 0 10px;font-size:16px}.clip-card video{display:block;width:100%;max-height:520px;background:#000;border-radius:12px}.download{display:inline-block;margin-top:10px;color:#d6c4ff;font-weight:700;text-decoration:none}.error{color:#ffb4b4}.ok{color:#b7f7ca}
footer{color:#817b91;font-size:12px;text-align:center;margin-top:18px}
</style></head><body><main>
<h1 class="brand">CLIPS<span>.ONTHE</span></h1><p class="tag">Encuentra momentos destacados analizando la intensidad del audio y crea clips verticales.</p>
<section class="panel"><form id="form">
<label for="url">Enlace del vídeo de YouTube o Kick</label>
<input id="url" name="url" type="url" required placeholder="https://..." autocomplete="url">
<label for="count">¿Cuántos clips quieres?</label>
<select id="count" name="count"><option value="5" selected>5 clips</option><option value="10">10 clips</option><option value="20">20 clips</option></select>
<button id="btn" type="submit">GENERAR CLIPS</button>
</form><div id="result" aria-live="polite"></div>
</section><footer>Procesamiento sujeto a disponibilidad y restricciones de la plataforma de origen.</footer>
</main><script>
const form=document.querySelector("#form"),btn=document.querySelector("#btn"),result=document.querySelector("#result");
async function readJson(response){const raw=await response.text();if(!raw.trim())throw new Error("El servidor se reinició o cerró la conexión durante el proceso. Inicia un nuevo intento.");try{return JSON.parse(raw)}catch{throw new Error("El servidor devolvió una respuesta incompleta. Espera unos segundos e inténtalo de nuevo.")}}
let renderedClipCount=0;
function renderClips(state,done=false){
 const clips=state.clips||[];
 if(clips.length===renderedClipCount){
  const status=result.querySelector(".progress-message");
  if(status)status.textContent=done?"¡Listo! Todos tus clips están preparados.":(state.message||"Procesando…");
  return;
 }
 const cards=clips.map(clip=>"<article class='clip-card'><h3>"+clip.name+"</h3><video controls playsinline preload='metadata' src='"+clip.url+"'></video><a class='download' href='"+clip.url+"' download>Descargar clip ↓</a></article>").join("");
 renderedClipCount=clips.length;
 result.innerHTML="<p class='ok'>Ya puedes reproducir y descargar los clips que van saliendo.</p><p class='muted progress-message'>"+(done?"¡Listo! Todos tus clips están preparados.":(state.message||"Procesando…"))+"</p>"+cards;
}
form.addEventListener("submit",async e=>{
 e.preventDefault();btn.disabled=true;result.textContent="Enviando vídeo para procesar…";
 try{
  const res=await fetch("/api/clips",{method:"POST",body:new FormData(form)});
  const data=await readJson(res);if(!res.ok)throw new Error(data.detail||"No se pudo iniciar el trabajo.");
  result.textContent="Trabajo iniciado. Preparando tus clips…";
  let finished=false;
  while(!finished){
   await new Promise(r=>setTimeout(r,3000));
   const check=await fetch("/api/jobs/"+encodeURIComponent(data.job_id));
   const state=await readJson(check);if(!check.ok)throw new Error(state.detail||"No se pudo consultar el trabajo.");
   if(state.status==="failed")throw new Error(state.error||"No se pudo procesar el vídeo.");
   renderClips(state);
   if(state.status==="done"){
    finished=true;
    renderClips(state,true);
   }else if(!state.clips||state.clips.length===0){
    result.textContent=state.message||"Procesando vídeo…";
   }
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
    # Kick puede anunciar pistas HLS enormes. Si la estimación supera el
    # límite temporal, abortar el análisis completo y usar selección alternativa
    # antes de ocupar el almacenamiento o dejar la petición esperando horas.
    if estimated > MAX_DOWNLOAD_BYTES:
        raise yt_dlp.utils.DownloadError("audio-estimate-too-large")
    if downloaded > MAX_DOWNLOAD_BYTES:
        raise yt_dlp.utils.DownloadError("max-filesize")


def analyze_audio_highlights(audio_path, duration, count):
    """Rank 15-second windows by loudness and changes in audio energy."""
    wav_path = audio_path.with_suffix(".analysis.wav")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "8000",
        "-c:a", "pcm_s16le", str(wav_path)
    ], capture_output=True, check=True, timeout=900)
    try:
        levels = []
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            while True:
                raw = wav.readframes(sample_rate)
                if not raw:
                    break
                samples = array.array("h")
                samples.frombytes(raw)
                if not samples:
                    levels.append(0.0)
                    continue
                if os.sys.byteorder != "little":
                    samples.byteswap()
                square_mean = sum(int(v) * int(v) for v in samples) / len(samples)
                levels.append(math.sqrt(square_mean))
        if len(levels) < CLIP_SECONDS:
            raise RuntimeError("No se pudo analizar suficiente audio del vídeo.")
        step = 5
        candidates = []
        last_start = max(0, min(len(levels), int(duration)) - CLIP_SECONDS)
        for start in range(0, last_start + 1, step):
            window = levels[start:start + CLIP_SECONDS]
            if len(window) < CLIP_SECONDS:
                continue
            avg = statistics.fmean(window)
            peak = max(window)
            variation = statistics.pstdev(window)
            score = avg + 0.35 * peak + 0.25 * variation
            candidates.append((score, start))
        candidates.sort(reverse=True)
        chosen = []
        for score, start in candidates:
            if all(abs(start - prior) >= CLIP_SECONDS + 10 for prior in chosen):
                chosen.append(start)
                if len(chosen) >= count:
                    break
        if len(chosen) < count:
            for score, start in candidates:
                if start not in chosen:
                    chosen.append(start)
                    if len(chosen) >= count:
                        break
        return [
            {"start_time": float(start), "end_time": float(start + CLIP_SECONDS),
             "title": "Momento destacado %d" % (i + 1)}
            for i, start in enumerate(chosen)
        ]
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except OSError:
            pass


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
        return "El vídeo supera el límite de duración de 6 horas."
    return "No se pudo procesar el vídeo. Comprueba que el enlace sea público y vuelve a intentarlo."

def process_job(job_id, url, count):
    global ACTIVE_JOB
    folder = BASE / job_id
    source_dir = folder / "source"
    try:
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "processing", "message": "Analizando vídeo…", "clips": []}

        meta_options = {
            "format": "best[height<=480][ext=mp4]/best[height<=480]/worst[ext=mp4]/worst",
            "noplaylist": True, "quiet": True, "no_warnings": True,
            "socket_timeout": 20, "retries": 2, "extractor_retries": 2,
        }
        with yt_dlp.YoutubeDL(meta_options) as ydl:
            info = ydl.extract_info(url, download=False)

        duration = float(info.get("duration") or 0)
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            raise RuntimeError("No se pueden procesar directos que todavía están en emisión.")
        if duration <= CLIP_SECONDS:
            raise RuntimeError("El vídeo es demasiado corto para crear clips.")
        if duration > MAX_VIDEO_SECONDS:
            raise RuntimeError("duration")

        total = min(count, max(1, int(duration // CLIP_SECONDS)))
        source_dir.mkdir(parents=True, exist_ok=True)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "processing",
                "message": "Analizando el audio completo para encontrar momentos destacados…",
                "clips": []
            }
        audio_template = str(source_dir / "full_audio.%(ext)s")
        ranges = []
        audio_files = []
        try:
            audio_options = {
                # Preferir la pista de audio de menor tamaño para evitar bajar
                # una variante HLS enorme cuando Kick publica estimaciones erróneas.
                "format": "worstaudio[ext=m4a]/worstaudio/bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": audio_template,
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "socket_timeout": 30, "retries": 2, "fragment_retries": 2,
                "extractor_retries": 2, "concurrent_fragment_downloads": 1,
                "progress_hooks": [download_size_guard],
            }
            with yt_dlp.YoutubeDL(audio_options) as ydl:
                ydl.download([url])
            audio_files = [
                p for p in source_dir.glob("full_audio.*")
                if p.is_file() and not p.name.endswith(".analysis.wav")
            ]
            if not audio_files:
                raise RuntimeError("No se pudo descargar el audio para analizar los momentos.")
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Detectando picos de emoción y cambios de intensidad…",
                    "clips": []
                }
            ranges = analyze_audio_highlights(audio_files[0], duration, total)
        except Exception as audio_exc:
            print("CLIPS.ONTHE audio analysis unavailable for %s: %s: %s" % (
                job_id, type(audio_exc).__name__, audio_exc
            ), flush=True)
            # El fallo del análisis no debe impedir generar clips: usar puntos
            # repartidos por el vídeo como alternativa automática.
            available = max(0.0, duration - CLIP_SECONDS)
            ranges = []
            for i in range(total):
                start_time = available * (i + 1) / (total + 1)
                ranges.append({
                    "start_time": float(start_time),
                    "end_time": float(start_time + CLIP_SECONDS),
                    "title": "Momento del vídeo %d" % (i + 1)
                })
        finally:
            for audio_file in audio_files:
                try:
                    audio_file.unlink(missing_ok=True)
                except OSError:
                    pass
            for partial in source_dir.glob("full_audio.*"):
                try:
                    partial.unlink(missing_ok=True)
                except OSError:
                    pass

        progress = {i + 1: {"done": False, "percent": 0, "mb": 0, "speed": 0} for i in range(total)}

        def update_progress(index, data):
            status = data.get("status")
            downloaded = float(data.get("downloaded_bytes") or 0)
            total_bytes = float(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            speed = float(data.get("speed") or 0)
            with JOBS_LOCK:
                item = progress[index]
                item["mb"] = downloaded / (1024 * 1024)
                item["speed"] = speed
                if total_bytes > 0:
                    item["percent"] = min(100, int(downloaded * 100 / total_bytes))
                if status == "finished":
                    item["done"] = True
                    item["percent"] = 100
                completed = sum(1 for p in progress.values() if p["done"])
                active = next(
                    ((n, p) for n, p in progress.items() if not p["done"] and p["mb"] > 0),
                    (index, item)
                )
                active_index, active_item = active
                speed_text = (
                    " · %.0f KB/s" % (active_item["speed"] / 1024)
                    if active_item["speed"] > 0 else ""
                )
                if completed == total:
                    message = "Descargas completadas. Preparando los clips…"
                else:
                    message = (
                        "Descargando fragmentos uno por uno: %d/%d listos · "
                        "fragmento %d: %d%% (%.1f MB)%s"
                    ) % (
                        completed, total, active_index, active_item["percent"],
                        active_item["mb"], speed_text
                    )
                JOBS[job_id] = {"status": "processing", "message": message, "clips": []}

        def download_one(index, clip_range):
            output_template = str(source_dir / ("source_%02d.%%(ext)s" % index))
            options = {
                "format": "best[height<=480][ext=mp4]/best[height<=480]/worst[ext=mp4]/worst",
                "outtmpl": output_template,
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "socket_timeout": 20, "retries": 2, "fragment_retries": 2,
                "extractor_retries": 2, "concurrent_fragment_downloads": 1,
                "progress_hooks": [lambda data, clip_index=index: update_progress(clip_index, data)],
                "download_ranges": lambda video_info, ydl: [clip_range],
                "force_keyframes_at_cuts": True,
                "overwrites": True,
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
            matches = [
                p for p in source_dir.glob("source_%02d.*" % index)
                if p.is_file() and p.suffix.lower() in (".mp4", ".mkv", ".webm", ".ts")
            ]
            if not matches:
                raise RuntimeError("No se recibió el fragmento %d." % index)
            return index, matches[0]

        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "processing",
                "message": "Preparando %d fragmentos en calidad ligera…" % total,
                "clips": []
            }

        clips = []
        # Descarga y convierte cada fragmento antes de pasar al siguiente,
        # para que el usuario pueda reproducir el clip cuanto antes.
        for i, clip_range in enumerate(ranges, start=1):
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Descargando el fragmento %d/%d…" % (i, total),
                    "clips": list(clips)
                }

            _, source = download_one(i, clip_range)

            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Creando clip vertical %d/%d…" % (i, total),
                    "clips": list(clips)
                }

            filename = "clip_%02d.mp4" % i
            output = folder / filename
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-t", str(CLIP_SECONDS),
                "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "21",
                "-threads", "1", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(output)
            ], capture_output=True, check=True, timeout=180)

            clips.append({"name": "Clip %d" % i, "url": "/download/%s/%s" % (job_id, filename)})
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Clip %d/%d listo. Puedes reproducirlo mientras se prepara el siguiente." % (i, total),
                    "clips": list(clips)
                }
            try:
                source.unlink(missing_ok=True)
            except OSError:
                pass
            if folder_size(BASE) > MAX_STORAGE_BYTES:
                raise RuntimeError("Se alcanzó el límite temporal de almacenamiento. Inténtalo con menos clips.")

        shutil.rmtree(source_dir, ignore_errors=True)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "done",
                "message": "Clips verticales listos.",
                "clips": clips
            }
    except Exception as exc:
        print("CLIPS.ONTHE job %s failed: %s: %s" % (job_id, type(exc).__name__, exc), flush=True)
        shutil.rmtree(folder, ignore_errors=True)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "failed",
                "message": "No se pudo procesar el vídeo.",
                "error": safe_error(exc),
                "clips": []
            }
    finally:
        with JOBS_LOCK:
            ACTIVE_JOB = False

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.get("/healthz")
def health():
    return {"status": "ok", "service": "CLIPS.ONTHE"}

@app.post("/api/clips")
def create_clips(background_tasks: BackgroundTasks, url: str = Form(...), count: int = Form(5)):
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
    try:
        (BASE / job_id).mkdir(parents=True, exist_ok=False)
    except OSError:
        with JOBS_LOCK:
            ACTIVE_JOB = False
        raise HTTPException(503, "No se pudo reservar espacio temporal. Inténtalo de nuevo.")
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
