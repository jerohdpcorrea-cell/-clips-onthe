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
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

app = FastAPI(title="CLIPS.ONTHE", version="2.0.0")

BASE = Path("/tmp/clips-onthe")
BASE.mkdir(parents=True, exist_ok=True)
MAX_DOWNLOAD_BYTES = 160 * 1024 * 1024
MAX_AUDIO_ANALYSIS_SECONDS = 20 * 60
MAX_VIDEO_SECONDS = 6 * 60 * 60
MIN_CLIP_SECONDS = 20
MAX_CLIP_SECONDS = 60
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
<h1 class="brand">CLIPS<span>.ONTHE</span></h1><p class="tag">Clips inteligentes para TikTok: momentos de 20 a 60 segundos y encuadre vertical sin perder la escena.</p>
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
 const finalMessage=state.status==="partial"?(state.message||"Se generaron clips parciales."):"¡Listo! Todos tus clips están preparados.";
 if(clips.length===renderedClipCount){
  const status=result.querySelector(".progress-message");
  if(status)status.textContent=done?finalMessage:(state.message||"Procesando…");
  return;
 }
 const cards=clips.map(clip=>"<article class='clip-card'><h3>"+clip.name+"</h3><video controls playsinline preload='metadata' src='"+clip.url+"'></video><a class='download' href='"+clip.url+"' download>Descargar clip ↓</a></article>").join("");
 renderedClipCount=clips.length;
 result.innerHTML="<p class='ok'>Ya puedes reproducir y descargar los clips que van saliendo.</p><p class='muted progress-message'>"+(done?finalMessage:(state.message||"Procesando…"))+"</p>"+cards;
}
form.addEventListener("submit",async e=>{
 e.preventDefault();btn.disabled=true;renderedClipCount=0;result.textContent="Enviando vídeo para procesar…";
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
   if(state.status==="partial"){
    renderClips(state,true);
    finished=true;
   }else{
    renderClips(state);
   }
   if(state.status==="done"){
    finished=true;
    renderClips(state,true);
   }else if(state.status!=="partial"&&renderedClipCount===0&&(!state.clips||state.clips.length===0)){
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
    """Select non-overlapping 20-60s windows using audio activity as a free heuristic."""
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
        if len(levels) < MIN_CLIP_SECONDS:
            raise RuntimeError("No se pudo analizar suficiente audio del vídeo.")
        candidates = []
        step = 5
        available = min(len(levels), int(duration))
        # Normalizar contra el propio vídeo evita que un volumen general alto
        # (por ejemplo, música constante) domine toda la selección.
        ordered_levels = sorted(levels[:available])
        p20 = ordered_levels[int((len(ordered_levels) - 1) * 0.20)] if ordered_levels else 0
        p80 = ordered_levels[int((len(ordered_levels) - 1) * 0.80)] if ordered_levels else 0
        noise_floor = max(80.0, p20 * 1.6)
        reference = max(1.0, p80)
        for length in (20, 30, 45, 60):
            if available < length:
                continue
            for start in range(0, available - length + 1, step):
                window = levels[start:start + length]
                if len(window) != length:
                    continue
                avg = statistics.fmean(window)
                peak = max(window)
                variation = statistics.pstdev(window)
                active_ratio = sum(1 for v in window if v > noise_floor) / length
                # Energía + picos + actividad sostenida; es una heurística de
                # audio, no una comprensión semántica de lo que se dice.
                energy_score = min(1.5, avg / reference)
                peak_score = min(2.0, peak / reference)
                variation_score = min(1.0, variation / reference)
                silence_penalty = max(0.0, 0.35 - active_ratio)
                length_bonus = 0.04 if length in (30, 45) else 0.0
                score = (0.42 * energy_score + 0.18 * peak_score +
                         0.28 * active_ratio + 0.12 * variation_score +
                         length_bonus - silence_penalty)
                candidates.append((score, start, length))
        candidates.sort(reverse=True)
        chosen = []
        # Dejar un pequeño margen entre clips reduce repeticiones de la misma
        # conversación y evita cortes pegados unos a otros.
        min_gap = 10
        for score, start, length in candidates:
            end = start + length
            if all(end + min_gap <= prior_start or start >= prior_end + min_gap
                   for prior_start, prior_end in chosen):
                chosen.append((start, end))
                if len(chosen) >= count:
                    break
        if len(chosen) < count:
            for score, start, length in candidates:
                end = start + length
                if (start, end) not in chosen and all(
                    end <= prior_start or start >= prior_end
                    for prior_start, prior_end in chosen
                ):
                    chosen.append((start, end))
                    if len(chosen) >= count:
                        break
        chosen.sort()
        return [
            {"start_time": float(start), "end_time": float(end),
             "title": "Momento destacado %d (%ds)" % (i + 1, end - start)}
            for i, (start, end) in enumerate(chosen)
        ]
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except OSError:
            pass



def parse_vtt_timestamp(value):
    match = re.match(r"(?:(\\d+):)?(\\d{2}):(\\d{2})[.,](\\d{3})", value.strip())
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int(match.group(4))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def download_source_captions(url, source_dir):
    """Fetch only platform-provided Spanish/English captions; never downloads video."""
    options = {
        "skip_download": True, "writesubtitles": True, "writeautomaticsub": True,
        "subtitleslangs": ["es", "es-419", "es-ES", "en"],
        "subtitlesformat": "vtt/best", "outtmpl": str(source_dir / "captions.%(ext)s"),
        "noplaylist": True, "quiet": True, "no_warnings": True,
        "ignoreerrors": True, "socket_timeout": 15, "retries": 1,
        "extractor_retries": 1,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])
    files = sorted(source_dir.glob("captions*.vtt"),
                   key=lambda path: (0 if re.search(r"\\.es(?:[-.]|\\.)", path.name, re.I) else 1, path.name))
    return files[0] if files else None


def write_clip_srt(vtt_path, clip_start, clip_end, output_path):
    """Convert available VTT cues to a clip-relative SRT file."""
    if not vtt_path or not vtt_path.is_file():
        return False
    try:
        lines = vtt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    cues = []
    i = 0
    while i < len(lines):
        match = re.match(r"^\\s*((?:\\d{2}:)?\\d{2}:\\d{2}[.,]\\d{3})\\s+-->\\s+((?:\\d{2}:)?\\d{2}:\\d{2}[.,]\\d{3})", lines[i])
        if not match:
            i += 1
            continue
        start = parse_vtt_timestamp(match.group(1))
        end = parse_vtt_timestamp(match.group(2))
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i])
            i += 1
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = re.sub(r"\\s+", " ", text).strip()
        if start is not None and end is not None and end > clip_start and start < clip_end and text:
            left = max(0.0, start - clip_start)
            right = min(clip_end - clip_start, end - clip_start)
            if right > left:
                cues.append((left, right, text))
        i += 1
    if not cues:
        return False

    def stamp(seconds):
        milliseconds = max(0, int(round(seconds * 1000)))
        hours, remainder = divmod(milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds_part, millis = divmod(remainder, 1000)
        return "%02d:%02d:%02d,%03d" % (hours, minutes, seconds_part, millis)

    try:
        with output_path.open("w", encoding="utf-8") as output:
            for index, (start, end, text) in enumerate(cues, 1):
                output.write("%d\\n%s --> %s\\n%s\\n\\n" % (index, stamp(start), stamp(end), text))
        return True
    except OSError:
        return False


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
    clips = []
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
        if duration < MIN_CLIP_SECONDS:
            raise RuntimeError("El vídeo es demasiado corto para crear clips.")
        if duration > MAX_VIDEO_SECONDS:
            raise RuntimeError("duration")

        total = min(count, max(1, int(duration // MIN_CLIP_SECONDS)))
        source_dir.mkdir(parents=True, exist_ok=True)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "processing",
                "message": ("Analizando audio para elegir momentos de 20 a 60 segundos…"
                            if duration <= MAX_AUDIO_ANALYSIS_SECONDS else
                            "Vídeo largo: preparando selección distribuida para evitar una descarga de audio interminable…"),
                "clips": []
            }
        audio_template = str(source_dir / "full_audio.%(ext)s")
        ranges = []
        audio_files = []
        try:
            if duration > MAX_AUDIO_ANALYSIS_SECONDS:
                raise RuntimeError("audio-analysis-too-long")
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
                    "message": "Detectando momentos activos y su duración ideal…",
                    "clips": []
                }
            ranges = analyze_audio_highlights(audio_files[0], duration, total)
        except Exception as audio_exc:
            print("CLIPS.ONTHE audio analysis unavailable for %s: %s: %s" % (
                job_id, type(audio_exc).__name__, audio_exc
            ), flush=True)
            # El fallo o el límite de duración del análisis no debe impedir
            # generar clips: usar puntos repartidos por todo el vídeo.
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Análisis de audio omitido o no disponible. Seleccionando momentos repartidos por el vídeo…",
                    "clips": []
                }
            fallback_length = min(30, max(MIN_CLIP_SECONDS, int(duration / max(1, total))))
            available = max(0.0, duration - fallback_length)
            ranges = []
            for i in range(total):
                start_time = available * (i + 1) / (total + 1)
                ranges.append({
                    "start_time": float(start_time),
                    "end_time": float(start_time + fallback_length),
                    "title": "Momento del vídeo %d (%ds)" % (i + 1, fallback_length)
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

        caption_file = None
        try:
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "processing", "message": "Buscando subtítulos disponibles en el vídeo…", "clips": []}
            caption_file = download_source_captions(url, source_dir)
            if caption_file:
                print("CLIPS.ONTHE captions found for %s: %s" % (job_id, caption_file.name), flush=True)
            else:
                print("CLIPS.ONTHE no platform captions available for %s" % job_id, flush=True)
        except Exception as caption_exc:
            print("CLIPS.ONTHE captions unavailable for %s: %s" % (job_id, caption_exc), flush=True)

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
                current = JOBS.get(job_id, {})
                JOBS[job_id] = {
                    "status": "processing",
                    "message": message,
                    "clips": list(current.get("clips") or [])
                }

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
            srt_path = source_dir / ("clip_%02d.srt" % i)
            has_subtitles = write_clip_srt(
                caption_file, clip_range["start_time"], clip_range["end_time"], srt_path
            )
            video_filter = (
                "[0:v]split=2[bg][fg];"
                "[bg]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=24:8[bg];"
                "[fg]scale=720:1280:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
            )
            if has_subtitles:
                video_filter += ",subtitles='%s':force_style='FontName=Arial,FontSize=18,Outline=2,Shadow=1,MarginV=70'" % str(srt_path)
            video_filter += "[v]"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-t", str(max(1, clip_range["end_time"] - clip_range["start_time"])),
                "-filter_complex", video_filter,
                "-map", "[v]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "21",
                "-threads", "1", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(output)
            ], capture_output=True, check=True, timeout=180)

            clips.append({"name": "Clip %d%s" % (i, " · subtítulos" if has_subtitles else ""), "url": "/download/%s/%s" % (job_id, filename)})
            try:
                srt_path.unlink(missing_ok=True)
            except OSError:
                pass
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
        shutil.rmtree(source_dir, ignore_errors=True)
        has_partial_clips = bool(clips)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "partial" if has_partial_clips else "failed",
                "message": ("Se generaron %d clips antes de un problema. Puedes descargarlos; no se borraron." % len(clips)
                            if has_partial_clips else "No se pudo procesar el vídeo."),
                "error": safe_error(exc),
                "clips": list(clips)
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
