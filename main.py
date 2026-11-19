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
import json
import sys
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
JOB_TTL_SECONDS = 48 * 60 * 60
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "kick.com", "www.kick.com"}
JOBS = {}
JOB_CREATED_AT = {}
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

/* CLIPS.ONTHE refreshed interface */
body{padding:28px 16px;background:radial-gradient(900px 520px at 50% -10%,#39216d 0%,transparent 65%),radial-gradient(600px 420px at 100% 35%,#1a3150 0%,transparent 70%),#080811;color:#f7f5ff}
main{max-width:760px;margin:4vh auto}
.topline{display:flex;align-items:center;gap:9px;color:#c9b7ff;font-size:11px;font-weight:900;letter-spacing:2px;margin:0 0 16px}
.status-dot{width:8px;height:8px;border-radius:50%;background:#8b5cf6;box-shadow:0 0 14px #a78bfa}
.topline-pill{border:1px solid #554278;border-radius:99px;padding:4px 8px;font-size:9px;letter-spacing:1px;color:#d9ccff}
.brand{font-size:clamp(38px,8vw,62px);letter-spacing:-2.8px;line-height:1;margin:0}
.tag{color:#c4bdd8;max-width:600px;line-height:1.65;margin:13px 0 20px;font-size:15px}
.feature-row{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.feature-chip{border:1px solid #39304f;background:#171326;border-radius:99px;padding:7px 11px;color:#d8d0eb;font-size:11px;font-weight:700}
.panel{background:linear-gradient(145deg,#1b1830f5,#11111df5);border:1px solid #40345d;border-radius:24px;padding:clamp(19px,4vw,32px);box-shadow:0 24px 80px #0009,0 0 45px #6d28d91a}
label{font-size:13px;font-weight:800;color:#e5def5;margin:17px 0 9px}
input,select{background:#0b0a14;border:1px solid #49405e;border-radius:14px;padding:16px;color:#fff}
input::placeholder{color:#777187}
input:focus,select:focus{border-color:#a78bfa;box-shadow:0 0 0 3px #8b5cf622}
button{border-radius:14px;padding:17px;background:linear-gradient(100deg,#6d28d9,#9333ea 55%,#c026d3);box-shadow:0 10px 28px #7c3aed38;letter-spacing:.5px;transition:transform .18s,filter .18s}
button:not(:disabled):hover{transform:translateY(-2px);filter:brightness(1.12)}
button:disabled{opacity:.62}
.form-hint{margin:9px 0 0;color:#9e96b4;font-size:12px;line-height:1.5}
#result{margin-top:22px;padding-top:2px}
.progress-message{color:#c9c1dc;font-size:13px;line-height:1.5}
.progress-track{height:7px;background:#302943;border-radius:99px;overflow:hidden;margin:12px 0 18px}
.progress-track span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#8b5cf6,#d946ef);transition:width .3s}
.clip-card{padding:19px 0;border-top:1px solid #3a324d}
.clip-card h3{font-size:15px;font-weight:800}
.clip-card video{max-height:620px;border:1px solid #403750}
.download{display:inline-flex;align-items:center;gap:7px;background:#251b3a;border:1px solid #594276;border-radius:10px;padding:9px 13px;color:#e5d8ff;font-size:13px}
footer{color:#777188;line-height:1.6;margin:22px auto 0;max-width:560px}
@media(max-width:520px){body{padding:20px 13px}main{margin:3vh auto}.panel{border-radius:19px}.tag{font-size:14px}.clip-card video{max-height:460px}}

/* CLIPS STUDIO — redesigned creator workspace */
:root{color-scheme:dark}
body{padding:0;background:#08090f;color:#f4f3fa;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(ellipse at 14% 0%,#5b21b633,transparent 36%),radial-gradient(ellipse at 95% 24%,#0e749033,transparent 30%);z-index:-1}
main{width:min(1180px,calc(100% - 40px));max-width:none;margin:0 auto;padding:34px 0 56px}
.topline{height:46px;margin:0 0 44px;display:flex;align-items:center;gap:12px;color:#c9c5d6;font-size:11px;letter-spacing:2.1px}
.status-dot{width:9px;height:9px;background:#a3e635;box-shadow:0 0 15px #a3e655;border-radius:50%}
.topline-pill{margin-left:auto;border:1px solid #353448;background:#151522;border-radius:99px;padding:7px 12px;color:#b7a6ff;font-size:10px}
.brand{font-size:clamp(42px,7vw,76px);letter-spacing:-4px;line-height:.98;font-weight:950;margin:0}
.brand span{background:linear-gradient(100deg,#b9a3ff,#7c5cff 55%,#4dd7c4);-webkit-background-clip:text;background-clip:text;color:transparent}
.tag{font-size:16px;color:#a8a6b8;line-height:1.7;max-width:660px;margin:18px 0 24px}
.feature-row{display:flex;flex-wrap:wrap;gap:9px;margin:0 0 32px}
.feature-chip{display:inline-flex;align-items:center;gap:7px;border:1px solid #29283b;background:#11121d;border-radius:9px;padding:9px 12px;color:#c8c4d8;font-size:11px;letter-spacing:.2px}
.panel{position:relative;background:linear-gradient(145deg,#171827,#10111b 75%);border:1px solid #343348;border-radius:24px;padding:clamp(22px,4vw,38px);box-shadow:0 28px 90px #0008}
.panel:before{content:"";position:absolute;left:34px;top:-1px;width:110px;height:2px;background:linear-gradient(90deg,#a78bfa,#43d7c5);border-radius:9px}
#form{display:grid;grid-template-columns:minmax(0,1fr) 190px;gap:0 16px;align-items:end}
label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:1.3px;font-weight:850;color:#b9b5ca;margin:15px 0 10px}
#form label[for=url],#url{grid-column:1/-1}
input,select{width:100%;min-width:0;background:#0a0b13;border:1px solid #37364b;border-radius:12px;padding:17px 16px;color:#fff;font-size:15px;outline:none;transition:border .18s,box-shadow .18s}
input:focus,select:focus{border-color:#9a82ff;box-shadow:0 0 0 3px #9a82ff20}
input::placeholder{color:#68677a}
#form label[for=count],#count{grid-column:1}
#count{min-height:54px}
.form-hint{grid-column:1/-1;margin:12px 0 0;color:#89879d;font-size:12px;line-height:1.55}
button{grid-column:2;grid-row:3;width:100%;margin:0;min-height:54px;border:0;border-radius:12px;background:linear-gradient(105deg,#7655ed,#9874ff 58%,#43c9bd);color:#090912;font-weight:950;font-size:12px;letter-spacing:1px;box-shadow:0 12px 32px #7255ed33;transition:transform .18s,filter .18s}
button:not(:disabled):hover{transform:translateY(-2px);filter:brightness(1.08)}
button:disabled{opacity:.55;cursor:wait}
#result{margin-top:25px;line-height:1.6;overflow-wrap:anywhere}
#result:empty{display:none}
#result:not(:empty){padding-top:22px;border-top:1px solid #302f42}
.ok{color:#a6f0ce;font-size:13px;font-weight:750}
.muted,.progress-message{color:#aaa7bc;font-size:13px;line-height:1.6}
.progress-track{height:8px;background:#29283a;border-radius:99px;overflow:hidden;margin:14px 0 22px}
.progress-track span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#8b6bff,#43d7c4);box-shadow:0 0 16px #8b6bff66;transition:width .35s}
.clip-card{display:grid;grid-template-columns:minmax(0,1fr) minmax(150px,220px);gap:8px 22px;align-items:center;padding:22px 0;border-top:1px solid #302f42}
.clip-card h3{grid-column:1;margin:0;font-size:15px;color:#f0eef8}
.clip-card video{grid-column:2;grid-row:1/3;width:100%;max-height:390px;aspect-ratio:9/16;object-fit:contain;background:#050508;border:1px solid #343348;border-radius:13px}
.download{grid-column:1;grid-row:2;justify-self:start;display:inline-flex;align-items:center;margin:0;background:#211e35;border:1px solid #514477;border-radius:9px;padding:10px 14px;color:#d8ccff;font-size:12px;font-weight:800;text-decoration:none}
.error{color:#ffaaaa;background:#351c26;border:1px solid #633442;border-radius:10px;padding:13px}
footer{color:#68677c;font-size:11px;text-align:left;margin:22px 0 0;line-height:1.7}
@media(max-width:680px){main{width:calc(100% - 28px);padding:22px 0 38px}.topline{margin-bottom:32px}.brand{letter-spacing:-2.5px}.tag{font-size:14px}.panel{border-radius:18px;padding:20px 16px}#form{grid-template-columns:1fr}#form label[for=count],#count,.form-hint,button{grid-column:1;grid-row:auto}button{margin-top:12px}.clip-card{grid-template-columns:1fr 112px;gap:8px 14px}.clip-card video{grid-column:2;grid-row:1/3;max-height:210px}.download{grid-column:1;grid-row:2}.feature-chip{font-size:10px;padding:8px 9px}}
/* Creator Studio dashboard refresh */
body{padding:0;background:#080a10;color:#f4f5fb;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
body:before{background:radial-gradient(ellipse at 12% 4%,#6042d52b,transparent 34%),radial-gradient(ellipse at 90% 25%,#16a69a18,transparent 30%),linear-gradient(180deg,#0b0d16,#080a10 70%)}
main{width:min(1240px,calc(100% - 48px));padding:24px 0 48px}
.topline{height:56px;margin:0 0 44px;display:flex;gap:13px;align-items:center;border-bottom:1px solid #222637;letter-spacing:0}
.brand-mark{width:37px;height:37px;display:grid;place-items:center;border-radius:11px;background:linear-gradient(135deg,#9277ff,#4bd4c2);color:#080a10;font-size:14px;font-weight:1000;letter-spacing:-1px}.brand-mark span{color:white}
.nav-brand{font-size:12px;font-weight:950;letter-spacing:1.2px;color:#f6f5fc}.nav-brand small{display:block;margin-top:3px;font-size:8px;letter-spacing:2px;color:#777d91}
.topline-pill{margin-left:auto;border:1px solid #30384a;background:#121722;border-radius:99px;padding:8px 12px;color:#c5c9d6;font-size:9px;letter-spacing:1px}.topline-pill i{display:inline-block;width:6px;height:6px;margin-right:6px;border-radius:50%;background:#56d7ad;box-shadow:0 0 10px #56d7ad}
.hero{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(260px,.75fr);gap:36px;align-items:center;margin:0 0 36px}
.eyebrow{font-size:9px;letter-spacing:2px;font-weight:900;color:#9e8bff;margin:0 0 12px}
.hero .brand{font-size:clamp(48px,6.7vw,78px);line-height:.98;letter-spacing:-4.5px;margin:0;font-weight:950}.hero .brand span{background:linear-gradient(100deg,#a994ff,#64d7ca);-webkit-background-clip:text;background-clip:text;color:transparent}
.tag{font-size:15px;line-height:1.75;color:#a7acbd;max-width:590px;margin:17px 0 20px}
.hero-tags{display:flex;flex-wrap:wrap;gap:8px}.hero-tags span{border:1px solid #292e40;background:#111620;color:#c4c8d5;border-radius:7px;padding:7px 10px;font-size:10px;font-weight:750}
.hero-visual{border:1px solid #303449;border-radius:20px;background:linear-gradient(145deg,#171a2b,#10131c);padding:16px;box-shadow:0 20px 65px #0006;transform:rotate(1deg)}
.visual-top,.visual-bottom{display:flex;justify-content:space-between;align-items:center;color:#8e93a7;font-size:8px;font-weight:900;letter-spacing:1.7px}.live-indicator{color:#67d9b2}
.visual-screen{position:relative;overflow:hidden;display:grid;place-items:center;aspect-ratio:16/9;margin:14px 0;border-radius:12px;background:radial-gradient(circle at 50% 35%,#4a347f,#17182b 48%,#0a1018 100%);border:1px solid #3d355f}
.screen-glow{position:absolute;width:190px;height:120px;border-radius:50%;background:#9a75ff44;filter:blur(35px)}.play-icon{position:relative;z-index:1;width:48px;height:48px;border:1px solid #ffffff55;border-radius:50%;display:grid;place-items:center;color:#fff;background:#ffffff14;padding-left:3px}
.screen-caption{position:absolute;left:17px;bottom:22px;font-size:8px;line-height:1.7;letter-spacing:2px;color:#c5c4d4}.screen-caption b{font-size:14px;color:white}
.screen-bars{position:absolute;right:16px;bottom:18px;height:42px;display:flex;align-items:center;gap:3px}.screen-bars i{width:3px;border-radius:4px;background:linear-gradient(#a88bff,#49d6c2);height:50%}.screen-bars i:nth-child(3n){height:90%}.screen-bars i:nth-child(3n+1){height:35%}.screen-bars i:nth-child(3n+2){height:65%}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px;align-items:start}
.panel{background:linear-gradient(145deg,#171b29,#11151f);border:1px solid #30364a;border-radius:20px;padding:clamp(20px,3vw,30px);box-shadow:0 24px 70px #0005}.panel:before{display:none}
.panel-heading{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}.panel-heading h2{font-size:25px;letter-spacing:-.8px;margin:0 0 6px}.panel-heading p:not(.eyebrow){font-size:12px;color:#8f96a9;margin:0;line-height:1.6}.panel-icon{width:36px;height:36px;display:grid;place-items:center;border:1px solid #393e54;border-radius:10px;color:#a996ff;background:#1c2030}
#form{display:grid;grid-template-columns:1fr 1fr;gap:0 14px;align-items:end}#form>label[for=url],#url,#form>.form-hint,#form>button{grid-column:1/-1}
#form label{font-size:9px;letter-spacing:1.35px;color:#aeb4c5;margin:12px 0 8px}#form input[type=url],#form select{width:100%;background:#0c1019;border:1px solid #343b50;border-radius:10px;padding:14px 13px;font-size:13px;color:#f5f5fa;min-height:48px}#form input:focus,#form select:focus{border-color:#9b87ff;box-shadow:0 0 0 3px #9b87ff1c}#form input::placeholder{color:#626b80}
.form-grid{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr;gap:14px}.form-grid>div{min-width:0}
.tracking-toggle{grid-column:1/-1;display:flex!important;align-items:flex-start;gap:10px;margin:17px 0 4px!important;padding:12px;border:1px solid #2d3547;border-radius:10px;background:#111722;cursor:pointer}.tracking-toggle input{width:16px;height:16px;margin:2px 0 0;accent-color:#8c79ff}.tracking-toggle b{display:block;color:#e0e3ed;font-size:11px;letter-spacing:0;text-transform:none}.tracking-toggle small{display:block;margin-top:4px;color:#858da1;font-size:10px;line-height:1.5;font-weight:500}
.form-hint{font-size:10px;color:#858da0;line-height:1.65;margin:10px 0 14px}#form button{min-height:49px;border:0;border-radius:10px;background:linear-gradient(100deg,#8d75ff,#59d2c4);color:#0a0d14;font-size:10px;font-weight:1000;letter-spacing:1px;box-shadow:0 10px 28px #7866ef2b}#form button span{font-size:16px;margin-left:8px}
.side-panel{background:#11151f;border:1px solid #2c3345;border-radius:20px;padding:22px 20px}.side-panel h3{font-size:17px;margin:0 0 20px;letter-spacing:-.4px}
.side-feature{display:flex;gap:12px;align-items:center;padding:13px 0;border-top:1px solid #272e3d}.side-icon{width:34px;height:34px;flex:0 0 34px;display:grid;place-items:center;border-radius:9px;background:#211e35;color:#b8a7ff;font-size:11px;font-weight:900}.side-feature b{display:block;font-size:11px;color:#e5e7ef}.side-feature small{display:block;margin-top:4px;font-size:10px;color:#858da0;line-height:1.45}
.side-note{margin-top:16px;padding:13px;border:1px solid #34334b;border-radius:10px;background:linear-gradient(135deg,#201b36,#141b25)}.side-note b{font-size:10px;color:#c4b7ff}.side-note p{font-size:10px;line-height:1.6;color:#9299aa;margin:6px 0 0}
#result{margin-top:20px;line-height:1.6;overflow-wrap:anywhere}.clip-card{grid-template-columns:minmax(0,1fr) minmax(130px,190px);gap:9px 18px}.clip-meta{grid-column:1;grid-row:2;display:flex;gap:7px;flex-wrap:wrap;align-items:center}.clip-score,.clip-duration{border:1px solid #3a4054;background:#191e2c;border-radius:6px;padding:5px 8px;font-size:9px;color:#c7c2ff;font-weight:800}.clip-duration{color:#9ca5b6}.clip-card .download{grid-column:1;grid-row:3}
footer{color:#626b7e;font-size:10px;margin:24px 0 0;max-width:760px}
@media(max-width:850px){.hero{grid-template-columns:1fr .75fr;gap:18px}.workspace{grid-template-columns:1fr 250px}}
@media(max-width:680px){main{width:calc(100% - 26px);padding:14px 0 32px}.topline{margin-bottom:28px}.hero{grid-template-columns:1fr;margin-bottom:24px}.hero-visual{display:none}.hero .brand{font-size:52px;letter-spacing:-3px}.tag{font-size:13px}.workspace{grid-template-columns:1fr}.side-panel{display:none}.panel{padding:19px 15px;border-radius:16px}.panel-heading h2{font-size:22px}#form{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr 1fr;gap:9px}.tracking-toggle,#form>.form-hint,#form>button{grid-column:1}.clip-card{grid-template-columns:1fr 100px;gap:8px 12px}.clip-card video{grid-column:2;grid-row:1/4;max-height:190px}.clip-meta{grid-column:1;grid-row:2}.clip-card .download{grid-column:1;grid-row:3}}
.history-toolbar{display:flex;justify-content:flex-end;margin:-12px 0 18px}
#history-toggle{width:auto;min-height:42px;margin:0;padding:0 16px;border:1px solid #3b4054;border-radius:10px;background:#151a27;color:#dcd9ec;font-size:11px;letter-spacing:.5px;box-shadow:none}
#history-toggle:hover{border-color:#8c79ff}
#history-panel{display:none;margin:0 0 22px;padding:20px;background:#111620;border:1px solid #30364a;border-radius:16px}
#history-panel.open{display:block}
.history-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}
.history-head h2{font-size:17px;margin:0}
.history-note{font-size:10px;color:#858da0;margin:5px 0 14px}
.history-job{border-top:1px solid #2b3242;padding:14px 0}
.history-job h3{font-size:12px;margin:0 0 5px;overflow-wrap:anywhere}
.history-job p{font-size:10px;color:#9299aa;margin:4px 0;line-height:1.5}
.history-status{display:inline-block;border:1px solid #41445a;border-radius:6px;padding:4px 7px;font-size:9px;color:#c9c2ff;margin:3px 0 7px}
.history-empty{font-size:12px;color:#8f96a9;padding:14px 0}
.history-clips{margin-top:8px}
.history-clips .clip-card{grid-template-columns:minmax(0,1fr) 100px;gap:8px 12px;padding:12px 0}
.history-clips .clip-card video{grid-column:2;grid-row:1/3;max-height:170px}
.history-clips .clip-card .download{grid-column:1;grid-row:2}
@media(max-width:680px){.history-toolbar{margin:-5px 0 15px}#history-panel{padding:15px}.history-clips .clip-card{grid-template-columns:minmax(0,1fr) 88px}}
</style></head><body><main>
<header class="topline"><div class="brand-mark">C<span>.</span>O</div><div class="nav-brand">CLIPS.ONTHE<small>CREATOR STUDIO</small></div><span class="topline-pill"><i></i> MOTOR DE CLIPS ACTIVO</span></header>
<section class="hero"><div class="hero-copy"><p class="eyebrow">TU CONTENIDO, MULTIPLICADO</p><h1 class="brand">De directo a<br><span>clip listo.</span></h1><p class="tag">Encuentra momentos con energía, conviértelos en vertical y descárgalos para TikTok, Reels y Shorts.</p><div class="hero-tags"><span>720 × 1280</span><span>9:16 vertical</span><span>Subtítulos disponibles</span></div></div><aside class="hero-visual"><div class="visual-top"><span>CLIP ENGINE</span><span class="live-indicator">● READY</span></div><div class="visual-screen"><div class="screen-glow"></div><div class="play-icon">▶</div><div class="screen-caption">TU PRÓXIMO CLIP<br><b>EMPIEZA AQUÍ</b></div><div class="screen-bars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div></div><div class="visual-bottom"><span>ANÁLISIS DE AUDIO</span><b>01 — 03</b></div></aside></section>
<section class="workspace"><section class="panel"><div class="panel-heading"><div><p class="eyebrow">01 / NUEVO PROYECTO</p><h2>Crear clips</h2><p>Pega el enlace y configura cómo quieres encontrar los mejores momentos.</p></div><span class="panel-icon">↗</span></div><form id="form">
<label for="url">Enlace del vídeo</label><input id="url" name="url" type="url" required placeholder="Pega aquí tu enlace de Kick o YouTube" autocomplete="url">
<div class="form-grid"><div><label for="count">Cantidad de clips</label><select id="count" name="count"><option value="1" selected>1 clip · prueba rápida</option><option value="5">5 clips</option><option value="10">10 clips</option><option value="20">20 clips</option></select></div><div><label for="mode">Estilo de selección</label><select id="mode" name="mode"><option value="balanced" selected>Equilibrado</option><option value="reactions">Reacciones y picos</option><option value="conversation">Conversación</option><option value="gameplay">Acción y gameplay</option></select></div></div>
<label class="tracking-toggle"><input id="follow_face" name="follow_face" type="checkbox" value="on"><span><b>Seguimiento de rostro opcional</b><small>Si detecta una cámara clara, centra el rostro. Si no, conserva la imagen completa.</small></span></label>
<p class="form-hint">La selección analiza actividad, picos y variación del audio. El modo cambia el peso de esas señales; no promete viralidad ni sustituye una revisión humana.</p>
<button id="btn" type="submit">ANALIZAR Y GENERAR CLIPS <span>→</span></button>
</form><div id="result" aria-live="polite"></div></section>
<aside class="side-panel"><p class="eyebrow">02 / QUÉ RECIBES</p><h3>Listos para publicar</h3><div class="side-feature"><span class="side-icon">▣</span><div><b>Vertical 9:16</b><small>720 × 1280 con imagen completa.</small></div></div><div class="side-feature"><span class="side-icon">CC</span><div><b>Subtítulos</b><small>Usa los subtítulos disponibles en la fuente.</small></div></div><div class="side-feature"><span class="side-icon">◉</span><div><b>Encuadre opcional</b><small>Seguimiento facial ligero si se activa.</small></div></div><div class="side-note"><b>Flujo sencillo</b><p>Analiza · genera · reproduce · descarga. Los clips van apareciendo a medida que se terminan.</p></div></aside></section>
<footer>CLIPS.ONTHE · Herramienta independiente. El procesamiento depende de que el vídeo sea público y la plataforma permita descargarlo.</footer>
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
 const cards=clips.map(clip=>"<article class='clip-card'><h3>"+clip.name+"</h3><div class='clip-meta'>"+(clip.score?"<span class='clip-score'>Fuerza del momento "+clip.score+"/100</span>":"<span class='clip-score'>Selección distribuida</span>")+"<span class='clip-duration'>"+(clip.duration||30)+" s</span></div><video controls playsinline preload='metadata' src='"+clip.url+"'></video><a class='download' href='"+clip.url+"' download>Descargar clip ↓</a></article>").join("");
 renderedClipCount=clips.length;
 const pct=Math.min(100,Math.round(clips.length/Math.max(1,Number(form.count.value))*100));
 result.innerHTML="<p class='ok'>Ya puedes reproducir y descargar los clips que van saliendo.</p><p class='muted progress-message'>"+(done?finalMessage:(state.message||"Procesando…"))+"</p><div class='progress-track'><span style='width:"+pct+"%'></span></div>"+cards;
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
/* Historial desplegable de trabajos enviados */
(function(){
 const workspace=document.querySelector(".workspace");
 if(!workspace)return;
 const toolbar=document.createElement("div");
 toolbar.className="history-toolbar";
 toolbar.innerHTML='<button type="button" id="history-toggle" aria-expanded="false">▤ &nbsp; MIS CLIPS</button>';
 const panel=document.createElement("section");
 panel.id="history-panel";
 panel.setAttribute("aria-live","polite");
 panel.innerHTML='<div class="history-head"><h2>Historial de clips</h2><span class="history-status">48 HORAS</span></div><p class="history-note">Tus trabajos y clips estarán disponibles durante 48 horas desde que los enviaste.</p><div id="history-list" class="history-empty">Pulsa actualizar para consultar tus trabajos.</div>';
 workspace.parentNode.insertBefore(toolbar,workspace);
 workspace.parentNode.insertBefore(panel,workspace);
 const toggle=toolbar.querySelector("button");
 const list=panel.querySelector("#history-list");
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const labels={queued:"En cola",processing:"Procesando",done:"Terminado",partial:"Parcial",failed:"Fallido"};
 async function loadHistory(){
  list.className="history-empty";list.textContent="Cargando historial…";
  try{
   const response=await fetch("/api/jobs",{cache:"no-store"});
   const data=await readJson(response);
   if(!response.ok)throw new Error(data.detail||"No se pudo cargar el historial.");
   const jobs=data.jobs||[];
   if(!jobs.length){list.className="history-empty";list.textContent="Todavía no has enviado ningún vídeo.";return;}
   list.className="";
   list.innerHTML=jobs.map(job=>{
    const created=new Date(job.created_at*1000).toLocaleString("es");
    const expires=new Date(job.expires_at*1000).toLocaleString("es");
    const clips=(job.clips||[]).map(clip=>'<article class="clip-card"><h3>'+esc(clip.name)+'</h3><div class="clip-meta"><span class="clip-duration">'+esc(clip.duration||30)+' s</span></div><video controls playsinline preload="metadata" src="'+esc(clip.url)+'"></video><a class="download" href="'+esc(clip.url)+'" download>Descargar ↓</a></article>').join("");
    return '<article class="history-job"><h3>Trabajo · '+esc(job.job_id.slice(0,8))+'</h3><span class="history-status">'+esc(labels[job.status]||job.status)+'</span><p>Enviado: '+esc(created)+'</p><p>Eliminación automática: '+esc(expires)+'</p><p>'+esc(job.message||"")+'</p>'+(clips?'<div class="history-clips">'+clips+'</div>':"")+'</article>';
   }).join("");
  }catch(error){list.className="history-empty";list.textContent=error.message||"No se pudo cargar el historial.";}
 }
 toggle.addEventListener("click",()=>{
  const open=panel.classList.toggle("open");
  toggle.setAttribute("aria-expanded",String(open));
  toggle.textContent=open?"▤  OCULTAR MIS CLIPS":"▤  MIS CLIPS";
  if(open)loadHistory();
 });
 window.addEventListener("focus",()=>{if(panel.classList.contains("open"))loadHistory();});
})();
</script></body></html>"""

def cleanup_old_jobs():
    now = time.time()
    for folder in BASE.iterdir():
        try:
            if folder.is_dir():
                created_at = JOB_CREATED_AT.get(folder.name, folder.stat().st_mtime)
                if now - created_at > JOB_TTL_SECONDS:
                    shutil.rmtree(folder, ignore_errors=True)
                    with JOBS_LOCK:
                        JOBS.pop(folder.name, None)
                        JOB_CREATED_AT.pop(folder.name, None)
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


def analyze_audio_highlights(audio_path, duration, count, mode="balanced"):
    """Rank non-overlapping moments with lightweight audio cues; no external AI service."""
    wav_path = audio_path.with_suffix(".analysis.wav")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(wav_path)], capture_output=True, check=True, timeout=900)
    try:
        levels = []
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            while True:
                raw = wav.readframes(sample_rate)
                if not raw: break
                samples = array.array("h")
                samples.frombytes(raw)
                if not samples:
                    levels.append(0.0)
                    continue
                if os.sys.byteorder != "little": samples.byteswap()
                square_mean = sum(int(v) * int(v) for v in samples) / len(samples)
                levels.append(math.sqrt(square_mean))
        if len(levels) < MIN_CLIP_SECONDS: raise RuntimeError("No se pudo analizar suficiente audio del vídeo.")
        candidates = []
        available = min(len(levels), int(duration))
        ordered = sorted(levels[:available])
        p20 = ordered[int((len(ordered)-1)*0.20)] if ordered else 0
        p80 = ordered[int((len(ordered)-1)*0.80)] if ordered else 0
        if p80 < 120: raise RuntimeError("No se detectó suficiente actividad de audio.")
        noise_floor = max(80.0, p20 * 1.6)
        reference = max(1.0, p80)
        weights = {"balanced": (0.42,0.18,0.28,0.12), "reactions": (0.25,0.35,0.15,0.25), "conversation": (0.28,0.10,0.48,0.14), "gameplay": (0.30,0.30,0.15,0.25)}.get(mode, (0.42,0.18,0.28,0.12))
        for length in (20,30,45,60):
            if available < length: continue
            for start in range(0, available-length+1, 5):
                window = levels[start:start+length]
                avg = statistics.fmean(window)
                peak = max(window)
                variation = statistics.pstdev(window)
                active = sum(1 for v in window if v > noise_floor) / length
                energy_score = min(1.5, avg/reference)
                peak_score = min(2.0, peak/reference)
                variation_score = min(1.0, variation/reference)
                silence_penalty = max(0.0, 0.35-active)
                length_bonus = 0.04 if length in (30,45) else 0.0
                score = weights[0]*energy_score + weights[1]*peak_score + weights[2]*active + weights[3]*variation_score + length_bonus - silence_penalty
                candidates.append((score,start,length))
        candidates.sort(reverse=True)
        chosen = []
        for score,start,length in candidates:
            end = start+length
            if all(end+10 <= ps or start >= pe+10 for ps,pe,_ in chosen):
                chosen.append((start,end,score))
                if len(chosen) >= count: break
        if len(chosen) < count:
            for score,start,length in candidates:
                end = start+length
                if all(end <= ps or start >= pe for ps,pe,_ in chosen):
                    chosen.append((start,end,score))
                    if len(chosen) >= count: break
        chosen.sort(key=lambda item:item[0])
        best = max((item[2] for item in chosen), default=1.0)
        return [{"start_time":float(st),"end_time":float(en),"title":"Momento destacado %d (%ds)"%(i+1,en-st),"score":max(1,min(99,int(round(100*score/max(0.01,best)))))} for i,(st,en,score) in enumerate(chosen)]
    finally:
        try: wav_path.unlink(missing_ok=True)
        except OSError: pass
def parse_vtt_timestamp(value):
    match = re.match(r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})", value.strip())
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
                   key=lambda path: (0 if re.search(r"\.es(?:[-.]|\.)", path.name, re.I) else 1, path.name))
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
        match = re.match(r"^\s*((?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})\s+-->\s+((?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})", lines[i])
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
        text = re.sub(r"\s+", " ", text).strip()
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
                output.write("%d\n%s --> %s\n%s\n\n" % (index, stamp(start), stamp(end), text))
        return True
    except OSError:
        return False



def build_face_crop_filter(source_path):
    """Build a smoothed, low-resolution face-follow crop; return empty on uncertainty."""
    try:
        tracker = Path(__file__).with_name("face_tracker.py")
        result = subprocess.run(
            [sys.executable, str(tracker), str(source_path)],
            capture_output=True, text=True, timeout=50
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""
        data = json.loads(result.stdout)
        width = int(data.get("width") or 0)
        height = int(data.get("height") or 0)
        centers = data.get("centers") or []
        face_sizes = [float(item.get("size") or 0) for item in centers]
        if width < 2 or height < 2 or len(centers) < 3:
            return ""
        # No acercar una cámara facial pequeña dentro de una transmisión:
        # se conserva la escena completa para no ocultar el juego o contexto.
        if not face_sizes or statistics.median(face_sizes) < 0.08:
            return ""
        crop_height = height - (height % 2)
        crop_width = int(crop_height * 9 / 16)
        crop_width -= crop_width % 2
        if crop_width < 2 or width <= crop_width + 4:
            return ""
        raw_x = [
            max(0.0, min(float(width - crop_width), float(item["x"]) - crop_width / 2))
            for item in centers
        ]
        smooth_x = []
        for index in range(len(raw_x)):
            nearby = raw_x[max(0, index - 1):min(len(raw_x), index + 2)]
            smooth_x.append(sum(nearby) / len(nearby))
        expression = "%.2f" % smooth_x[-1]
        for index in range(len(smooth_x) - 2, -1, -1):
            t0 = float(centers[index]["t"])
            t1 = float(centers[index + 1]["t"])
            span = max(0.01, t1 - t0)
            x0, x1 = smooth_x[index], smooth_x[index + 1]
            interpolation = "(%.2f+(%.2f)*(t-%.3f)/%.3f)" % (
                x0, x1 - x0, t0, span
            )
            expression = "if(lt(t\\,%.3f)\\,%s\\,%s)" % (t1, interpolation, expression)
        first_time = float(centers[0]["t"])
        expression = "if(lt(t\\,%.3f)\\,%.2f\\,%s)" % (
            first_time, smooth_x[0], expression
        )
        return "crop=%d:%d:'%s':0," % (
            crop_width, crop_height, expression
        )
    except Exception as face_exc:
        print("CLIPS.ONTHE face tracking unavailable: %s" % face_exc, flush=True)
        return ""


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
        return "Un fragmento supera el límite temporal de 160 MB. Prueba con otro vídeo o una resolución más baja."
    if "duration" in msg or "demasiado largo" in msg:
        return "El vídeo supera el límite de duración de 6 horas."
    return "No se pudo procesar el vídeo. Comprueba que el enlace sea público y vuelve a intentarlo."

def process_job(job_id, url, count, mode="balanced", follow_face=False):
    global ACTIVE_JOB
    folder = BASE / job_id
    source_dir = folder / "source"
    clips = []
    try:
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "processing", "message": "Analizando vídeo…", "clips": []}

        meta_options = {
            "format": "best[height<=720][ext=mp4]/best[height<=720]/worst[ext=mp4]/worst",
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
            ranges = analyze_audio_highlights(audio_files[0], duration, total, mode)
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
            segment_span = duration / max(1, total)
            fallback_length = min(30, max(MIN_CLIP_SECONDS, int(segment_span)))
            ranges = []
            for i in range(total):
                # Un clip por tramo: repartirlos por todo el vídeo sin solaparlos.
                start_time = i * segment_span + max(0.0, (segment_span - fallback_length) / 2)
                ranges.append({
                    "start_time": float(start_time),
                    "end_time": float(start_time + fallback_length),
                    "title": "Momento del vídeo %d (%ds)" % (i + 1, fallback_length),
                    "score": None
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

        def clip_download_progress(index, data):
            # Limitar bytes reales descargados por fragmento. No usar la
            # estimación del vídeo completo: algunos HLS de Kick la inflan.
            if data.get("status") == "downloading":
                downloaded = data.get("downloaded_bytes") or 0
                if downloaded > MAX_DOWNLOAD_BYTES:
                    raise yt_dlp.utils.DownloadError("max-filesize")
            update_progress(index, data)

        def download_one(index, clip_range):
            output_template = str(source_dir / ("source_%02d.%%(ext)s" % index))
            options = {
                "format": "best[height<=720][ext=mp4]/best[height<=720]/worst[ext=mp4]/worst",
                "outtmpl": output_template,
                "noplaylist": True, "quiet": True, "no_warnings": True,
                "socket_timeout": 20, "retries": 2, "fragment_retries": 2,
                "extractor_retries": 2, "concurrent_fragment_downloads": 1,
                "progress_hooks": [lambda data, clip_index=index: clip_download_progress(clip_index, data)],
                "download_ranges": lambda video_info, ydl: [clip_range],
                "force_keyframes_at_cuts": False,
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
            face_crop_filter = build_face_crop_filter(source) if follow_face else ""
            srt_path = source_dir / ("clip_%02d.srt" % i)
            has_subtitles = write_clip_srt(
                caption_file, clip_range["start_time"], clip_range["end_time"], srt_path
            )
            # Ajustar la imagen completa dentro del lienzo vertical sin recortar
            # bordes; rellenar el espacio sobrante con negro en una sola pasada.
            if face_crop_filter:
                video_filter = face_crop_filter + "scale=720:1280,setsar=1"
            else:
                video_filter = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
            if has_subtitles:
                video_filter += ",subtitles='%s':force_style='FontName=Arial,FontSize=18,Outline=2,Shadow=1,MarginV=70'" % str(srt_path)
            video_filter += "[v]"
            ffmpeg_command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-t", str(max(1, clip_range["end_time"] - clip_range["start_time"])),
                "-filter_complex", video_filter,
                "-map", "[v]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-threads", "1", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(output)
            ]
            try:
                subprocess.run(ffmpeg_command, capture_output=True, check=True, timeout=180)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                # Si el seguimiento facial falla o tarda demasiado, conservar
                # el clip con el encuadre completo antes que perder el resultado.
                if face_crop_filter:
                    print("CLIPS.ONTHE face reframe failed for %s clip %d; retrying full frame" % (job_id, i), flush=True)
                    face_crop_filter = ""
                    video_filter = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
                    if has_subtitles:
                        video_filter += ",subtitles='%s':force_style='FontName=Arial,FontSize=18,Outline=2,Shadow=1,MarginV=70'" % str(srt_path)
                    video_filter += "[v]"
                    ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1] = video_filter
                    try:
                        subprocess.run(ffmpeg_command, capture_output=True, check=True, timeout=180)
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        if not has_subtitles:
                            raise
                        has_subtitles = False
                        srt_path.unlink(missing_ok=True)
                        video_filter = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[v]"
                        ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1] = video_filter
                        subprocess.run(ffmpeg_command, capture_output=True, check=True, timeout=180)
                elif has_subtitles:
                    # Si los subtítulos VTT son incompatibles, producir el clip
                    # sin texto antes que perder el vídeo.
                    print("CLIPS.ONTHE subtitle rendering failed for %s clip %d; retrying without captions" % (job_id, i), flush=True)
                    has_subtitles = False
                    srt_path.unlink(missing_ok=True)
                    video_filter = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[v]"
                    ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1] = video_filter
                    subprocess.run(ffmpeg_command, capture_output=True, check=True, timeout=180)
                else:
                    raise

            clips.append({"name": "Clip %d%s" % (i, " · subtítulos" if has_subtitles else ""), "url": "/download/%s/%s" % (job_id, filename), "score": clip_range.get("score"), "duration": int(clip_range["end_time"] - clip_range["start_time"])})
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


@app.head("/", response_class=HTMLResponse)
def home_head():
    # Render y algunos proxies validan la portada mediante HEAD.
    return HTMLResponse(content="")


@app.get("/healthz")
def health():
    return {"status": "ok", "service": "CLIPS.ONTHE"}

@app.post("/api/clips")
def create_clips(background_tasks: BackgroundTasks, url: str = Form(...), count: int = Form(5), mode: str = Form("balanced"), follow_face: bool = Form(False)):
    global ACTIVE_JOB
    cleanup_old_jobs()
    if count not in (1, 5, 10, 20):
        raise HTTPException(400, "Selecciona 1, 5, 10 o 20 clips.")
    if mode not in ("balanced", "reactions", "conversation", "gameplay"):
        raise HTTPException(400, "Selecciona un modo de análisis válido.")
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
        JOB_CREATED_AT[job_id] = time.time()
        JOBS[job_id] = {"status": "queued", "message": "Trabajo en cola…", "clips": []}
    background_tasks.add_task(process_job, job_id, url, count, mode, follow_face)
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/jobs")
def list_jobs():
    cleanup_old_jobs()
    now = time.time()
    with JOBS_LOCK:
        items = []
        for job_id, job in JOBS.items():
            created_at = JOB_CREATED_AT.get(job_id)
            if created_at is None:
                continue
            items.append({
                "job_id": job_id,
                "status": job.get("status", "processing"),
                "message": job.get("message", ""),
                "clips": list(job.get("clips") or []),
                "created_at": created_at,
                "expires_at": created_at + JOB_TTL_SECONDS,
                "remaining_seconds": max(0, int(created_at + JOB_TTL_SECONDS - now))
            })
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"jobs": items, "retention_hours": 48}

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    cleanup_old_jobs()
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "Trabajo no encontrado.")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "El trabajo expiró o el servidor se reinició. Inicia uno nuevo.")
    return job

@app.get("/download/{job_id}/{filename}")
def download(job_id: str, filename: str):
    cleanup_old_jobs()
    if not re.fullmatch(r"[a-f0-9]{32}", job_id) or not re.fullmatch(r"clip_[0-9]{2}\.mp4", filename):
        raise HTTPException(404, "Clip no encontrado.")
    path = BASE / job_id / filename
    if not path.is_file() or path.parent.parent != BASE:
        raise HTTPException(404, "Clip no encontrado.")
    return FileResponse(path, filename=filename, media_type="video/mp4")
