
import os
import uuid
import shutil
import subprocess
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse

app = FastAPI(title="CLIPS.ONTHE")

BASE = Path("/tmp/clips-onthe")
BASE.mkdir(exist_ok=True)

HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CLIPS.ONTHE</title>
<style>
body{background:#090910;color:white;font-family:Arial;padding:22px}
main{max-width:600px;margin:auto}
h1{font-size:35px}span{color:#a78bfa}
section{background:#191827;padding:22px;border-radius:18px}
input,select,button{width:100%;padding:15px;margin:10px 0;
border-radius:10px;box-sizing:border-box}
input,select{background:#292638;color:white;border:1px solid #555}
button{background:#8b5cf6;color:white;border:0;font-weight:bold}
#result{overflow-wrap:anywhere}
a{color:#c4b5fd}
</style>
</head>
<body>
<main>
<h1>CLIPS<span>.ONTHE</span></h1>
<p>Tu generador automático de clips</p>
<section>
<form id="form">
<label>Enlace de YouTube o Kick</label>
<input name="url" type="url" required placeholder="Pega tu enlace aquí">
<label>Cantidad de clips</label>
<select name="count">
<option value="20">20 clips</option>
<option value="10">10 clips</option>
<option value="5">5 clips</option>
</select>
<button id="btn">GENERAR CLIPS</button>
</form>
<div id="result"></div>
</section>
</main>
<script>
document.querySelector("#form").onsubmit=async e=>{
e.preventDefault();
let b=document.querySelector("#btn");
let r=document.querySelector("#result");
b.disabled=true;
r.textContent="Procesando video. Espera...";
try{
let response=await fetch("/api/clips",{
method:"POST",body:new FormData(e.target)
});
let data=await response.json();
if(!response.ok)throw Error(data.detail);
r.innerHTML=data.clips.map(c=>
'<p><a href="'+c.url+'">Descargar '+c.name+'</a></p>'
).join("");
}catch(err){r.textContent="Error: "+err.message}
b.disabled=false;
};
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.post("/api/clips")
def create_clips(url: str = Form(...), count: int = Form(20)):
    if count not in [5, 10, 20]:
        raise HTTPException(400, "Cantidad inválida")

    if not url.startswith(("https://", "http://")):
        raise HTTPException(400, "Enlace inválido")

    job = uuid.uuid4().hex
    folder = BASE / job
    folder.mkdir()

    try:
        options = {
            "format": "best[height<=720]/best",
            "outtmpl": str(folder / "video.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "socket_timeout": 30,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        video = next(folder.glob("video.*"))

        probe = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video)
        ], capture_output=True, text=True, check=True)

        duration = float(probe.stdout.strip())

        if duration < 10:
            raise ValueError("El video es demasiado corto")

        total = min(count, int(duration // 10))
        clips = []

        for i in range(total):
            start = (duration - 10) * i / max(1, total - 1)
            filename = f"clip_{i+1}.mp4"
            output = folder / filename

            subprocess.run([
                "ffmpeg", "-y", "-ss", str(start),
                "-i", str(video), "-t", "10",
                "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-crf", "28", "-c:a", "aac",
                str(output)
            ], capture_output=True, check=True, timeout=120)

            clips.append({
                "name": f"Clip {i+1}",
                "url": f"/download/{job}/{filename}"
            })

        return {"clips": clips}

    except Exception as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(500, str(error)[:300])

@app.get("/download/{job}/{filename}")
def download(job: str, filename: str):
    path = BASE / job / filename
    if not path.is_file() or path.parent.parent != BASE:
        raise HTTPException(404, "Clip no encontrado")
    return FileResponse(path, filename=filename)
