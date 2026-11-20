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
import json
import sys
import hashlib
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
<meta name="theme-color" content="#090910"><link rel="icon" href="data:,"><title>CLIPS.ONTHE</title>
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

/* OBSIDIAN / INFERNO — identidad visual épica */
:root{color-scheme:dark;--bg:#090909;--panel:#141414;--line:#34302b;--muted:#aaa39a;--text:#f7f1e8;--hot:#ff6a24;--gold:#ffc15a;--red:#d93622}
html{background:var(--bg);scroll-behavior:smooth}
body{background:radial-gradient(ellipse at 50% -18%,#6d2b12 0%,transparent 43%),radial-gradient(ellipse at 100% 52%,#39170d55 0%,transparent 34%),linear-gradient(180deg,#0d0c0b,#080808 72%);color:var(--text)}
body:before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.18;background-image:linear-gradient(#ffffff08 1px,transparent 1px),linear-gradient(90deg,#ffffff08 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(to bottom,black,transparent 78%)}
main{width:min(1280px,calc(100% - 56px));padding:25px 0 58px}
.topline{border-bottom:1px solid #30251e;margin-bottom:54px;padding-bottom:17px}
.brand-mark{border-radius:10px;background:linear-gradient(145deg,#ff9a3d,#e33b1f 75%);color:#160b06;box-shadow:0 0 28px #ff632b35;font-size:13px}
.brand-mark span{color:#fff0d6}
.nav-brand{color:#fff8ef;letter-spacing:1.8px}
.nav-brand small{color:#9e7560;letter-spacing:2.6px}
.topline-pill{background:#17110e;border-color:#55301f;color:#f5b27b}
.topline-pill i{background:#ff7b32;box-shadow:0 0 12px #ff6a24}
.hero{gap:52px;margin-bottom:42px}
.eyebrow{color:#ff9651;letter-spacing:2.5px}
.hero .brand{font-size:clamp(54px,7.2vw,88px);letter-spacing:-5px;line-height:.93;text-shadow:0 12px 55px #ff5b1b22}
.hero .brand span{background:linear-gradient(100deg,#fff0cf 0%,#ffb34f 38%,#ff5428 78%,#d92e1d);-webkit-background-clip:text;background-clip:text;color:transparent}
.tag{color:#b8ada2;font-size:15px;max-width:610px}
.hero-tags span{background:#17120f;border-color:#493020;color:#e7c5a7}
.hero-visual{position:relative;overflow:hidden;transform:rotate(0);border-radius:17px;border-color:#5a3825;background:linear-gradient(145deg,#21150f,#11100f 70%);box-shadow:0 28px 90px #000a,0 0 55px #e84b1c18}
.hero-visual:after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(115deg,transparent 20%,#ff9d3b0c 48%,transparent 72%)}
.visual-top,.visual-bottom{color:#a99482}
.live-indicator{color:#ff9951}
.visual-screen{background:radial-gradient(circle at 50% 38%,#7d3219,#2b1710 48%,#0b0b0b 100%);border-color:#704027}
.screen-glow{background:#ff6a244d}
.play-icon{border-color:#ffca9a77;background:#ff8b321c}

.screen-bars i{background:linear-gradient(#ffc15a,#ed4724)}
.workspace{grid-template-columns:minmax(0,1fr) 310px;gap:20px}
.panel{background:linear-gradient(145deg,#191715,#11100f 76%);border:1px solid #49372b;border-radius:18px;box-shadow:0 30px 90px #0009,0 0 0 1px #ff8a2b08 inset}
.panel-heading h2{color:#fff7ed;font-size:27px;letter-spacing:-1px}
.panel-heading p:not(.eyebrow){color:#a99d91}
.panel-icon{border-color:#5a3825;background:#26170f;color:#ff9b54}
#form label{color:#d3bca8}
#form input[type=url],#form select{background:#0b0a09;border-color:#46372e;color:#fff6ed;border-radius:9px}
#form input:focus,#form select:focus{border-color:#ff8740;box-shadow:0 0 0 3px #ff70221f}
#form input::placeholder{color:#76675d}
.form-hint{color:#918477}
#form button{background:linear-gradient(105deg,#e84920 0%,#ff762d 54%,#ffb64c 100%);color:#1a0c06;box-shadow:0 12px 32px #f05a242d;letter-spacing:1.25px}
#form button:hover{filter:brightness(1.12)}
.side-panel{background:linear-gradient(160deg,#191512,#100f0e);border-color:#49372b;border-radius:18px}
.side-panel h3{color:#fff3e7}
.side-feature{border-color:#35271f}
.side-icon{background:#2b190f;color:#ff9b54;border:1px solid #57321e}
.side-feature b{color:#f0e2d5}
.side-feature small,.side-note p{color:#a29488}
.side-note{background:linear-gradient(135deg,#2b1a11,#17110e);border-color:#664026}
.side-note b{color:#ffb16d}
#result:not(:empty){border-color:#453329}
.progress-track{background:#33251d}
.progress-track span{background:linear-gradient(90deg,#e84920,#ff9a35,#ffd06b);box-shadow:0 0 16px #ff762b55}
.ok{color:#ffc18a}
.progress-message,.muted{color:#b2a498}
.clip-card{border-color:#3b2b21}
.clip-card h3{color:#fff0e2}
.clip-score,.clip-duration{background:#211710;border-color:#5b3824;color:#ffbd80}
.clip-duration{color:#c4aa96}
.clip-card video{border-color:#513625;background:#050505}
.download{background:linear-gradient(110deg,#32190f,#24150f);border-color:#754326;color:#ffc18a}
.download:hover{background:#482313}
#history-toggle{background:#1b1511;border-color:#553724;color:#f2d2b8}
#history-toggle:hover{border-color:#ff8740}
#history-panel{background:#15110e;border-color:#49372b}
.history-job{border-color:#3b2b21}
.history-job p,.history-note{color:#a29488}
.history-status{border-color:#71452c;color:#ffbd80}
footer{color:#887b70}
.error{background:#30130f;border-color:#7c3023;color:#ffb4a1}
@media(max-width:850px){.workspace{grid-template-columns:minmax(0,1fr) 270px}.hero{gap:24px}}
@media(max-width:680px){main{width:calc(100% - 28px);padding-top:16px}.topline{margin-bottom:34px}.hero .brand{font-size:56px;letter-spacing:-3.5px}.hero{gap:12px}.workspace{grid-template-columns:1fr}.panel{background:linear-gradient(145deg,#191715,#11100f)}.side-panel{display:none}}

/* NEXUS CREATOR — nueva composición visual */
:root{--acid:#d6ff45;--violet:#8b5cf6;--cyan:#4de8dc;--ink:#080910;--glass:#111421;--edge:#292d42}
body{background:#080910;color:#f5f5ff;overflow-x:hidden}
body:before{opacity:.23;background-image:linear-gradient(#a9a2ff0b 1px,transparent 1px),linear-gradient(90deg,#a9a2ff0b 1px,transparent 1px);background-size:34px 34px;mask-image:linear-gradient(90deg,black,transparent 95%)}
.rail{position:fixed;z-index:5;inset:0 auto 0 0;width:82px;background:#0c0e17;border-right:1px solid #25283a;display:flex;flex-direction:column;align-items:center;padding:22px 10px;gap:23px}
.rail-logo{width:45px;height:45px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(145deg,var(--acid),#8dffb3);color:#10120b;font-size:14px;font-weight:1000;box-shadow:0 0 35px #cfff4530}
.rail-line{width:30px;height:1px;background:#303247}
.rail-link{width:44px;height:44px;display:grid;place-items:center;border:1px solid transparent;border-radius:13px;color:#7f849b;text-decoration:none;font-size:17px;transition:.2s}
.rail-link:hover,.rail-link.active{background:#1c2030;border-color:#41465e;color:var(--acid);box-shadow:0 0 24px #cfff4512}
.rail-bottom{margin-top:auto;color:#777d91;font-size:9px;letter-spacing:1px;writing-mode:vertical-rl}
main{width:min(1440px,calc(100% - 130px));margin:0 28px 0 108px;padding:22px 0 60px}
.topline{height:54px;margin:0 0 34px;padding:0 0 14px;border-bottom:1px solid #24283a}
.brand-mark{background:linear-gradient(145deg,var(--acid),#7dffb8);color:#0b0d0c;box-shadow:0 0 30px #d6ff452b}
.brand-mark span{color:#10130d}.nav-brand{letter-spacing:2px}.nav-brand small{color:#8f94a9}
.topline-pill{background:#121725;border-color:#384054;color:#d6ff45}.topline-pill i{background:#d6ff45;box-shadow:0 0 12px #d6ff45}
.hero{position:relative;isolation:isolate;min-height:310px;grid-template-columns:minmax(0,1.05fr) minmax(300px,.95fr);gap:30px;margin-bottom:24px;padding:36px 40px;border:1px solid #33364d;border-radius:26px;background:linear-gradient(115deg,#171a2a 0%,#111421 55%,#211737 100%);box-shadow:0 35px 100px #0008;overflow:hidden}
.hero:before{content:"";position:absolute;z-index:-1;width:440px;height:440px;right:6%;top:-52%;border-radius:50%;border:1px solid #d6ff452b;box-shadow:0 0 0 35px #d6ff4508,0 0 0 75px #8b5cf60b,0 0 100px #8b5cf633}
.hero:after{content:"";position:absolute;z-index:-1;inset:0;background:linear-gradient(110deg,transparent 25%,#d6ff4507 55%,transparent 80%);pointer-events:none}
.eyebrow{color:var(--acid);letter-spacing:2.8px}
.hero .brand{font-size:clamp(58px,7vw,96px);letter-spacing:-6px;line-height:.88}
.hero .brand span{background:linear-gradient(100deg,#e7ff9a,var(--acid) 40%,#55e9d7 85%);-webkit-background-clip:text;background-clip:text;color:transparent}
.tag{color:#b5b8ca;font-size:15px;max-width:560px}
.hero-tags span{border:1px solid #45465c;background:#171c2b;color:#e1e4f0;border-radius:99px;padding:8px 12px}
.hero-visual{align-self:stretch;display:flex;flex-direction:column;justify-content:space-between;border-radius:19px;border-color:#4b4863;background:radial-gradient(ellipse at 52% 40%,#4b367b 0%,#202039 36%,#111421 78%);box-shadow:inset 0 0 55px #a68aff18,0 20px 65px #0007;padding:19px}
.visual-screen{flex:1;min-height:150px;margin:14px 0;background:radial-gradient(circle at 50% 50%,#d6ff4522,transparent 45%),linear-gradient(135deg,#1c2440,#111421);border:1px solid #74709a}
.screen-glow{width:230px;height:150px;background:#b7ff4550;filter:blur(50px)}
.play-icon{width:58px;height:58px;border-color:#d6ff4588;background:#d6ff451c;color:var(--acid);font-size:18px;box-shadow:0 0 30px #d6ff4533}

.screen-bars i{background:linear-gradient(var(--acid),var(--cyan))}
.workspace{grid-template-columns:minmax(0,1fr) 320px;gap:22px}
.panel{background:linear-gradient(145deg,#151929,#10131e);border:1px solid #353b52;border-radius:22px;padding:30px;box-shadow:0 24px 75px #0007,inset 0 1px #ffffff08}
.panel-heading{margin-bottom:26px}.panel-heading h2{font-size:31px;letter-spacing:-1.4px}.panel-heading p:not(.eyebrow){font-size:13px}
.panel-icon{width:44px;height:44px;background:#25263a;border:1px solid #565071;color:var(--acid);font-size:19px}
#form label{color:#c5c8d8;font-size:10px}
#form input[type=url],#form select{background:#090c15;border:1px solid #353b52;border-radius:12px;min-height:54px;padding:16px;font-size:14px}
#form input:focus,#form select:focus{border-color:var(--acid);box-shadow:0 0 0 3px #d6ff4518}
.form-grid{gap:16px}
#form button{min-height:58px;border-radius:12px;background:linear-gradient(100deg,var(--acid),#9aff8c 48%,var(--cyan));color:#10130b;font-size:11px;letter-spacing:1.4px;box-shadow:0 12px 35px #baff4530}
#form button:hover{filter:brightness(1.08);box-shadow:0 14px 40px #baff4540}
.form-hint{font-size:11px;color:#969cb1;margin:14px 0 18px}
.side-panel{position:relative;overflow:hidden;background:linear-gradient(155deg,#17172b,#11141e);border:1px solid #403b60;border-radius:22px;padding:25px}
.side-panel:after{content:"";position:absolute;width:180px;height:180px;right:-100px;top:-90px;border-radius:50%;background:#8b5cf633;filter:blur(25px);pointer-events:none}
.side-panel h3{font-size:21px;letter-spacing:-.6px}
.side-icon{background:#24243b;border:1px solid #4a4567;color:var(--acid);width:40px;height:40px;flex-basis:40px}
.side-feature{padding:16px 0;border-color:#303349}.side-feature b{font-size:12px}.side-feature small{font-size:11px}
.side-note{background:linear-gradient(130deg,#26213e,#17212c);border:1px solid #555071;border-radius:13px;padding:16px}.side-note b{color:var(--acid)}.side-note p{font-size:11px}
#result:not(:empty){margin-top:25px;padding:24px 0 0;border-top:1px solid #33384c}
.progress-track{height:9px;background:#2c3041}.progress-track span{background:linear-gradient(90deg,var(--violet),var(--acid),var(--cyan));box-shadow:0 0 18px #d6ff4540}
.clip-card{padding:25px 0;border-color:#30354a}.clip-card h3{font-size:17px}.clip-score{background:#252a20;border-color:#65743b;color:var(--acid)}.clip-duration{background:#1b2030;border-color:#3c4660;color:#b7c4e1}
.clip-card video{border:1px solid #48516b;border-radius:15px;box-shadow:0 12px 35px #0008}
.download{background:linear-gradient(100deg,#27233f,#1c3034);border:1px solid #555071;color:#e4ff9a;border-radius:10px;padding:12px 16px}
#history-toggle{background:#171b29;border-color:#3b4259;color:#e0e2ee;border-radius:11px}
#history-toggle:hover{border-color:var(--acid);color:var(--acid)}
#history-panel{background:#111522;border-color:#363d54;border-radius:18px}
.history-job{border-color:#30364a}
.history-status{border-color:#64733c;color:var(--acid)}
footer{color:#737b91}
@media(max-width:900px){.rail{width:62px}.rail-logo{width:39px;height:39px}main{width:calc(100% - 92px);margin-left:78px;margin-right:14px}.hero{padding:26px;gap:18px}.workspace{grid-template-columns:minmax(0,1fr) 270px}}
@media(max-width:680px){.rail{position:sticky;top:0;inset:auto;width:100%;height:58px;flex-direction:row;justify-content:flex-start;padding:7px 14px;gap:12px;border-right:0;border-bottom:1px solid #25283a}.rail-logo{width:36px;height:36px}.rail-line,.rail-bottom{display:none}.rail-link{width:38px;height:38px}.rail-link:last-of-type{margin-left:auto}main{width:calc(100% - 26px);margin:0 auto;padding:16px 0 35px}.topline{margin-bottom:22px}.hero{grid-template-columns:1fr;padding:25px 20px;min-height:0;border-radius:19px;margin-bottom:18px}.hero .brand{font-size:58px;letter-spacing:-3.5px}.hero-visual{min-height:200px}.workspace{grid-template-columns:1fr}.panel{padding:20px 15px;border-radius:18px}.panel-heading h2{font-size:26px}.side-panel{display:block}.form-grid{gap:9px}.clip-card{grid-template-columns:1fr 100px}.clip-card video{grid-column:2;grid-row:1/4;max-height:190px}}

/* Resultados: tarjetas de clips en formato estudio */
#result:not(:empty){padding-top:25px}
.results-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:0 0 15px}
.results-kicker{display:block;color:var(--acid);font-size:9px;font-weight:900;letter-spacing:2px;margin-bottom:7px}
.results-heading h3{margin:0;color:#f4f6fb;font-size:25px;letter-spacing:-.8px}
.results-heading .ok{margin:6px 0 0;color:#aeb8c8;font-size:12px;font-weight:500}
.results-count{flex:0 0 auto;border:1px solid #4c5b38;background:#20291d;color:var(--acid);border-radius:12px;padding:9px 12px;font-size:13px;font-weight:900;font-variant-numeric:tabular-nums}
.clips-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:17px;margin-top:18px}
.clip-card{display:flex;flex-direction:column;min-width:0;padding:16px;background:linear-gradient(155deg,#171d2b,#111621);border:1px solid #30394d;border-radius:17px;overflow:hidden;gap:9px;transition:border-color .2s,transform .2s}
.clip-card:hover{border-color:#71804b;transform:translateY(-2px)}
.clip-card-top{display:flex;justify-content:space-between;align-items:center}
.clip-number{font-size:9px;font-weight:900;letter-spacing:1.6px;color:#aeb8ca}
.clip-ready{font-size:8px;font-weight:900;letter-spacing:1px;color:var(--acid);background:#26311d;border:1px solid #53663a;border-radius:99px;padding:5px 8px}
.clip-card h3{margin:0;font-size:17px;line-height:1.25;color:#f4f6fb}
.clip-meta{display:flex;flex-wrap:wrap;gap:6px}
.clip-score,.clip-duration{font-size:10px;padding:5px 8px;border-radius:7px}
.clip-preview{display:flex;justify-content:center;align-items:center;width:100%;padding:12px;background:radial-gradient(ellipse at center,#222b3c,#090d15 72%);border:1px solid #293246;border-radius:12px;min-height:170px}
.clip-card .clip-preview video{display:block;width:auto;max-width:100%;height:clamp(230px,32vw,390px);max-height:none;aspect-ratio:9/16;object-fit:contain;background:#000;border:1px solid #3b465d;border-radius:8px}
.clip-card .download{display:flex;justify-content:center;align-items:center;gap:9px;width:100%;box-sizing:border-box;margin-top:2px;padding:12px 14px;border-radius:10px;font-size:12px}
.clip-card .download>span{font-size:18px;line-height:1}
.clip-card .download small{margin-left:auto;color:#aeb9a0;font-size:8px;letter-spacing:1px}
@media(max-width:680px){.clips-grid{grid-template-columns:1fr;gap:13px}.clip-card{padding:13px}.clip-card .clip-preview video{height:min(105vw,420px)}.results-heading h3{font-size:21px}}
.tracking-toggle{display:flex!important;align-items:flex-start;gap:11px;margin:17px 0 5px!important;padding:14px;border:1px solid #3b4050;border-radius:12px;background:#111722;cursor:pointer}.tracking-toggle input{width:17px;height:17px;flex:0 0 17px;margin:1px 0 0;accent-color:var(--acid)}.tracking-toggle b{display:block;color:#f0f2f8;font-size:11px;letter-spacing:.4px;text-transform:none}.tracking-toggle small{display:block;margin-top:5px;color:#969eb0;font-size:10px;line-height:1.55;font-weight:500}.clip-time{color:#929bb0;font-size:10px;font-variant-numeric:tabular-nums}

/* QUALITY PASS — interfaz consistente, accesible y adaptable */
:root{color-scheme:dark;--focus-ring:0 0 0 3px #d6ff4530}
html{scroll-padding-top:24px}
button,a,select,input{ -webkit-tap-highlight-color:transparent }
:focus-visible{outline:2px solid var(--acid,#d6ff45);outline-offset:3px}
.rail-link{position:relative}
.rail-link.active{background:#202638;border-color:#536044;color:var(--acid,#d6ff45)}
.rail-link.active:after{content:"";position:absolute;left:-11px;top:10px;bottom:10px;width:3px;border-radius:4px;background:var(--acid,#d6ff45)}
.hero{isolation:isolate}
.hero-visual{min-width:0}
.workspace{align-items:start}
.panel,.side-panel{min-width:0}
#form button{min-height:56px}
#form button:focus-visible,#history-toggle:focus-visible,.download:focus-visible{outline-color:var(--acid,#d6ff45)}
#result{scroll-margin-top:24px}
.results-heading{align-items:flex-end}
.clips-grid{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
.clip-card{height:100%;min-width:0}
.clip-card .clip-preview{min-width:0}
.clip-card .clip-preview video{max-width:100%;height:clamp(250px,30vw,390px)}
.clip-card .download{min-height:44px}
.history-toolbar{margin-top:4px}
#history-toggle{min-height:44px;font-weight:850;cursor:pointer}
.history-job{overflow-wrap:anywhere}
@media(max-width:900px){.hero{grid-template-columns:minmax(0,1fr) minmax(220px,.8fr)}.workspace{grid-template-columns:minmax(0,1fr) 260px}.clips-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:680px){.hero{grid-template-columns:1fr}.hero-visual{min-height:180px}.workspace{grid-template-columns:1fr}.clips-grid{grid-template-columns:1fr}.clip-card .clip-preview video{height:min(112vw,440px)}.results-heading{align-items:flex-start}.results-heading h3{font-size:21px}.rail-link.active:after{left:4px;right:4px;top:auto;bottom:-7px;width:auto;height:3px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
/* VISTA INDEPENDIENTE: MIS CLIPS */
#clips-view{display:none;min-height:calc(100vh - 80px);padding:28px 0 60px}
body.clips-view-mode main>:not(#clips-view){display:none!important}
body.clips-view-mode #clips-view{display:block}
.clips-view-head{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 0 26px;padding:8px 0 22px;border-bottom:1px solid #34394d}
.clips-view-title .eyebrow{margin:0 0 8px}
.clips-view-title h1{margin:0;font-size:clamp(30px,5vw,48px);letter-spacing:-1.8px;color:#f4f6fb}
.clips-view-title p{margin:8px 0 0;color:#9ca5b6;font-size:13px}
#clips-back{border:1px solid #41485d;border-radius:11px;background:#171c29;color:#edf0f8;padding:12px 17px;font-weight:800;cursor:pointer;white-space:nowrap}
#clips-back:hover{border-color:var(--acid,#d6ff45);color:var(--acid,#d6ff45)}
body.clips-view-mode #result{margin:0;padding:0;border:0}
body.clips-view-mode #result:empty:after{content:"Todavía no has generado clips. Vuelve a Crear clips para iniciar un proyecto.";display:block;padding:28px;border:1px dashed #41485d;border-radius:16px;color:#9ca5b6;text-align:center}
body.clips-view-mode .clips-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}
@media(max-width:680px){#clips-view{padding:18px 0 40px}.clips-view-head{align-items:flex-start;flex-direction:column}.clips-view-title h1{font-size:34px}#clips-back{width:100%}body.clips-view-mode .clips-grid{grid-template-columns:1fr}}
</style></head><body><aside class="rail"><div class="rail-logo">C/O</div><div class="rail-line"></div><a class="rail-link active" href="#top" data-nav="home" aria-label="Inicio" title="Inicio">⌂</a><a class="rail-link" href="#form" data-nav="create" aria-label="Crear clips" title="Crear clips">✦</a><a class="rail-link" href="#result" data-nav="results" aria-label="Resultados" title="Resultados">▣</a><a class="rail-link" href="#history-panel" data-nav="history" aria-label="Historial" title="Historial">◷</a><div class="rail-bottom">CREATOR MODE</div></aside><main id="top">
<header class="topline"><div class="brand-mark">C<span>.</span>O</div><div class="nav-brand">CLIPS.ONTHE<small>CREATOR STUDIO</small></div><span class="topline-pill"><i></i> MOTOR DE CLIPS ACTIVO</span></header>
<section class="hero"><div class="hero-copy"><p class="eyebrow">TU CONTENIDO, MULTIPLICADO</p><h1 class="brand">De directo a<br><span>clip listo.</span></h1><p class="tag">Encuentra momentos con energía, conviértelos en vertical y descárgalos para TikTok, Reels y Shorts.</p><div class="hero-tags"><span>720 × 1280</span><span>9:16 vertical</span></div></div><aside class="hero-visual"><div class="visual-top"><span>CLIP ENGINE</span><span class="live-indicator">● READY</span></div><div class="visual-screen"><div class="screen-glow"></div><div class="play-icon">▶</div><div class="screen-bars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div></div><div class="visual-bottom"><span>ANÁLISIS DE AUDIO</span><b>01 — 03</b></div></aside></section>
<section class="workspace"><section class="panel"><div class="panel-heading"><div><p class="eyebrow">01 / NUEVO PROYECTO</p><h2>Crear clips</h2><p>Pega el enlace y elige cuántos clips quieres generar.</p></div><span class="panel-icon">↗</span></div><form id="form">
<label for="url">Enlace del vídeo</label><input id="url" name="url" type="url" required placeholder="Pega aquí tu enlace de Kick o YouTube" autocomplete="url">
<div class="form-grid"><div><label for="count">Cantidad de clips</label><select id="count" name="count"><option value="1" selected>1 clip · prueba rápida</option><option value="5">5 clips</option><option value="10">10 clips</option><option value="20">20 clips</option></select></div></div><input type="hidden" name="mode" value="balanced"><input type="hidden" name="follow_face" value="false"><label class="tracking-toggle" for="follow_face"><input id="follow_face" type="checkbox" name="follow_face" value="true" checked><span><b>ENCUADRE INTELIGENTE</b><small>Si aparece una sola persona, la sigue suavemente. Si detecta un grupo o no está seguro, conserva la imagen completa.</small></span></label>
<button id="btn" type="submit">ANALIZAR Y GENERAR CLIPS <span>→</span></button>
</form><div id="result" aria-live="polite"></div></section>
<aside class="side-panel"><p class="eyebrow">02 / QUÉ RECIBES</p><h3>Listos para publicar</h3><div class="side-feature"><span class="side-icon">▣</span><div><b>Vertical 9:16</b><small>720 × 1280 con imagen completa.</small></div></div><div class="side-feature"><span class="side-icon">◉</span><div><b>Encuadre opcional</b><small>Encuadre automático: grupo completo o seguimiento individual.</small></div></div><div class="side-note"><b>Flujo sencillo</b><p>Analiza · genera · reproduce · descarga. Los clips van apareciendo a medida que se terminan.</p></div></aside></section>
<footer>CLIPS.ONTHE · Herramienta independiente. El procesamiento depende de que el vídeo sea público y la plataforma permita descargarlo.</footer>
</main><script>
const form=document.querySelector("#form"),btn=document.querySelector("#btn"),result=document.querySelector("#result");
const clipsView=document.createElement("section");
clipsView.id="clips-view";
clipsView.innerHTML='<div class="clips-view-head"><div class="clips-view-title"><p class="eyebrow">TU BIBLIOTECA PERSONAL</p><h1>Mis clips</h1><p>Solo tus clips generados, sin el resto del panel de creación.</p></div><button type="button" id="clips-back">← Volver a crear clips</button></div>';
document.querySelector("main").appendChild(clipsView);
clipsView.appendChild(result);
document.querySelector("#clips-back").addEventListener("click",()=>{
 document.body.classList.remove("clips-view-mode");
 document.querySelectorAll(".rail-link[data-nav]").forEach(link=>link.classList.toggle("active",link.dataset.nav==="create"));
 document.querySelector("#form")?.scrollIntoView({behavior:"smooth",block:"start"});
});
async function readJson(response){const raw=await response.text();if(!raw.trim())throw new Error("El servidor se reinició o cerró la conexión durante el proceso. Inicia un nuevo intento.");try{return JSON.parse(raw)}catch{throw new Error("El servidor devolvió una respuesta incompleta. Espera unos segundos e inténtalo de nuevo.")}}
let renderedClipCount=0;
const escapeHtml=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clipUrl=value=>/^\/download\/[a-f0-9]{32}\/clip_\d{2}\.mp4$/.test(String(value||""))?String(value):"#";
function renderClips(state,done=false){
 const clips=state.clips||[];
 const finalMessage=state.status==="partial"?(state.message||"Se generaron clips parciales."):"¡Listo! Todos tus clips están preparados.";
 const targetCount=done?Math.max(1,clips.length):Math.max(1,Number(form.count.value));
 const pct=done?100:Math.max(0,Math.min(99,Number(state.progress_percent??Math.round(clips.length/targetCount*100))));
 if(clips.length===renderedClipCount){
  const status=result.querySelector(".progress-message");
  const bar=result.querySelector(".progress-track span");
  const count=result.querySelector(".results-count");
  if(status)status.textContent=done?finalMessage:(state.message||"Procesando…");
  if(bar)bar.style.width=pct+"%";
  if(count)count.textContent=clips.length+" / "+targetCount;
  return;
 }
 const cards=clips.map((clip,index)=>{
  const url=clipUrl(clip.url),start=Number(clip.start_time||0),end=Number(clip.end_time||0);
  const time=start||end?'<span class="clip-time">'+Math.floor(start/60).toString().padStart(2,"0")+':'+Math.floor(start%60).toString().padStart(2,"0")+' – '+Math.floor(end/60).toString().padStart(2,"0")+':'+Math.floor(end%60).toString().padStart(2,"0")+'</span>':"";
  return "<article class='clip-card'><div class='clip-card-top'><span class='clip-number'>CLIP "+String(index+1).padStart(2,'0')+"</span><span class='clip-ready'>LISTO</span></div><h3>"+escapeHtml(clip.name||("Clip "+(index+1)))+"</h3><div class='clip-meta'>"+(clip.score?"<span class='clip-score' title='Índice comparativo de actividad; no predice viralidad'>Actividad "+escapeHtml(clip.score)+"/100</span>":"<span class='clip-score'>Momento seleccionado</span>")+"<span class='clip-duration'>"+escapeHtml(clip.duration||30)+" segundos</span>"+time+"</div><div class='clip-preview'><video controls playsinline preload='metadata' src='"+url+"'></video></div><a class='download' href='"+url+"' download><span>↓</span> Descargar clip <small>MP4 · VERTICAL 9:16</small></a></article>";
 }).join("");
 renderedClipCount=clips.length;
 result.innerHTML="<section class='results-heading'><div><span class='results-kicker'>TU CONTENIDO ESTÁ AQUÍ</span><h3>Clips generados</h3><p class='ok'>Puedes reproducirlos y descargarlos.</p></div><span class='results-count'>"+clips.length+" / "+targetCount+"</span></section><p class='muted progress-message'>"+escapeHtml(done?finalMessage:(state.message||"Procesando…"))+"</p><div class='progress-track'><span style='width:"+pct+"%'></span></div><div class='clips-grid'>"+cards+"</div>";
}
form.addEventListener("submit",async e=>{
 e.preventDefault();btn.disabled=true;renderedClipCount=0;result.innerHTML="<p class='progress-message'>Conectando con el motor de clips…</p><div class='progress-track'><span style='width:2%'></span></div>";
 try{
  const res=await fetch("/api/clips",{method:"POST",body:new FormData(form)});
  const data=await readJson(res);if(!res.ok)throw new Error(data.detail||"No se pudo iniciar el trabajo.");
  result.innerHTML="<p class='progress-message'>Trabajo iniciado. Preparando tus clips…</p><div class='progress-track'><span style='width:2%'></span></div>";
  let finished=false;
  while(!finished){
   await new Promise(r=>setTimeout(r,3000));
   let check,state,lastError;
   for(let attempt=0;attempt<4;attempt++){try{check=await fetch("/api/jobs/"+encodeURIComponent(data.job_id),{cache:"no-store"});state=await readJson(check);if(!check.ok)throw new Error(state.detail||"No se pudo consultar el trabajo.");lastError=null;break;}catch(error){lastError=error;if(attempt<3)await new Promise(r=>setTimeout(r,1500*(attempt+1)));}}
   if(lastError)throw lastError;
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
    const clips=(job.clips||[]).map(clip=>'<article class="clip-card"><h3>'+esc(clip.name)+'</h3><div class="clip-meta"><span class="clip-duration">'+esc(clip.duration||30)+' s</span>'+(clip.score?'<span class="clip-score">Actividad '+esc(clip.score)+'/100</span>':"")+'</div><video controls playsinline preload="metadata" src="'+esc(clip.url)+'"></video><a class="download" href="'+esc(clip.url)+'" download>Descargar ↓</a></article>').join("");
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
 /* Navegación funcional del rail lateral */
 const navLinks=[...document.querySelectorAll(".rail-link[data-nav]")];
 const goTo=(target)=>target?.scrollIntoView({behavior:"smooth",block:"start"});
 navLinks.forEach(link=>link.addEventListener("click",event=>{
  event.preventDefault();
  navLinks.forEach(item=>item.classList.toggle("active",item===link));
  const action=link.dataset.nav;
  if(action==="home"){document.body.classList.remove("clips-view-mode");goTo(document.querySelector("#top"));return;}
  if(action==="create"){document.body.classList.remove("clips-view-mode");goTo(form);setTimeout(()=>document.querySelector("#url")?.focus({preventScroll:true}),450);return;}
  if(action==="results"){
   document.body.classList.add("clips-view-mode");
   return;
  }
  if(action==="history"){
   document.body.classList.remove("clips-view-mode");
   if(!panel.classList.contains("open"))toggle.click();
   goTo(panel);
  }
 }));
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
            elif folder.is_file() and folder.name.startswith("seen_"):
                # La memoria de momentos usados también es temporal: no dejar
                # un JSON por cada vídeo acumulándose indefinidamente en /tmp.
                if now - folder.stat().st_mtime > JOB_TTL_SECONDS:
                    folder.unlink(missing_ok=True)
        except OSError:
            pass

def cleanup_worker():
    # Limpieza ligera cada 15 minutos para que los trabajos caduquen
    # aunque el usuario no vuelva a abrir el historial.
    while True:
        time.sleep(15 * 60)
        cleanup_old_jobs()


@app.on_event("startup")
def start_cleanup_worker():
    threading.Thread(target=cleanup_worker, name="clip-history-cleanup", daemon=True).start()


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


def select_diverse_candidates(candidates, count, duration, exclude_ranges=None):
    """Greedy highlight selection balancing quality, timeline coverage and clip length."""
    exclude_ranges = exclude_ranges or []
    selected = []
    remaining = list(candidates)

    def allowed(start, end, gap):
        if any(not (end + gap <= prev_start or start >= prev_end + gap)
               for prev_start, prev_end, _ in selected):
            return False
        return not any(
            not (end + gap <= float(item[0]) or start >= float(item[1]) + gap)
            for item in exclude_ranges
        )

    while remaining and len(selected) < count:
        best_index = None
        best_rank = None
        for index, (score, start, length) in enumerate(remaining):
            end = start + length
            if not allowed(start, end, 10):
                continue
            same_length = sum(1 for _, _, chosen_length in selected if chosen_length == length)
            region = min(3, int((start / max(1.0, duration)) * 4))
            same_region = sum(
                1 for chosen_start, _, _ in selected
                if min(3, int((chosen_start / max(1.0, duration)) * 4)) == region
            )
            # Small penalties keep strong moments while avoiding a batch of
            # nearly identical durations or clips concentrated in one section.
            rank = score - (0.12 * same_length) - (0.055 * same_region)
            key = (rank, score, -start, -length)
            if best_rank is None or key > best_rank:
                best_rank = key
                best_index = index
        if best_index is None:
            break
        score, start, length = remaining.pop(best_index)
        selected.append((start, start + length, score))

    # If the requested count is not reached, relax only the safety gap;
    # never allow overlap or reuse of an excluded moment.
    while remaining and len(selected) < count:
        eligible = [
            (index, item) for index, item in enumerate(remaining)
            if allowed(item[1], item[1] + item[2], 0)
        ]
        if not eligible:
            break
        index, (score, start, length) = max(
            eligible, key=lambda pair: (pair[1][0], -pair[1][1], -pair[1][2])
        )
        remaining.pop(index)
        selected.append((start, start + length, score))

    return sorted(selected, key=lambda item: item[0])


def build_fallback_ranges(duration, count, source_key, exclude_ranges=None):
    """Create distributed fallback moments with varied 20–60 second lengths."""
    exclude_ranges = exclude_ranges or []
    duration = float(duration)
    if duration < MIN_CLIP_SECONDS or count < 1:
        return []

    seed = int(hashlib.sha256(str(source_key).encode()).hexdigest()[:8], 16)
    lengths = [20, 30, 45, 60]
    rotation = seed % len(lengths)
    lengths = lengths[rotation:] + lengths[:rotation]
    selected = []

    def is_clear(start, end, gap):
        if any(not (end + gap <= item["start_time"] or start >= item["end_time"] + gap)
               for item in selected):
            return False
        return not any(
            not (end + gap <= float(item[0]) or start >= float(item[1]) + gap)
            for item in exclude_ranges
        )

    for index in range(count):
        preferred = lengths[index % len(lengths)]
        ordered_lengths = [preferred] + [n for n in lengths if n != preferred]
        target = duration * (index + 0.5) / count
        chosen = None

        for gap in (10, 0):
            for length in ordered_lengths:
                length = min(length, int(duration))
                if length < MIN_CLIP_SECONDS:
                    continue
                last_start = max(0, int(duration - length))
                step = max(5, length // 3)
                positions = list(range(0, last_start + 1, step))
                if not positions or positions[-1] != last_start:
                    positions.append(last_start)
                ideal_start = min(last_start, max(0, int(target - length / 2)))
                positions.sort(key=lambda start: (abs(start - ideal_start), (start + seed) % max(1, step)))
                for start in positions:
                    end = start + length
                    if is_clear(float(start), float(end), gap):
                        chosen = (float(start), float(end), length)
                        break
                if chosen:
                    break
            if chosen:
                break

        if not chosen:
            break
        start, end, length = chosen
        selected.append({
            "start_time": start,
            "end_time": end,
            "title": "Momento alternativo (%ds)" % length,
            "score": None
        })

    return sorted(selected, key=lambda item: item["start_time"])


def analyze_audio_highlights(audio_path, duration, count, mode="balanced", exclude_ranges=None):
    exclude_ranges = exclude_ranges or []
    """Rank moments using lightweight energy, activity and short audio-burst cues."""
    wav_path = audio_path.with_suffix(".analysis.wav")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(wav_path)], capture_output=True, check=True, timeout=900)
    try:
        # Medir RMS en bloques de 250 ms: permite distinguir picos breves
        # (gritos, risas o golpes de energía) sin usar modelos pesados.
        short_levels = []
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            chunk_frames = max(1, sample_rate // 4)
            while True:
                raw = wav.readframes(chunk_frames)
                if not raw:
                    break
                samples = array.array("h")
                samples.frombytes(raw)
                if not samples:
                    short_levels.append(0.0)
                    continue
                if os.sys.byteorder != "little":
                    samples.byteswap()
                square_mean = sum(int(v) * int(v) for v in samples) / len(samples)
                short_levels.append(math.sqrt(square_mean))

        # Conservar una serie por segundo para el cálculo de actividad general.
        levels = [
            statistics.fmean(short_levels[i:i + 4])
            for i in range(0, len(short_levels), 4)
        ]
        if len(levels) < MIN_CLIP_SECONDS:
            raise RuntimeError("No se pudo analizar suficiente audio del vídeo.")

        candidates = []
        available = min(len(levels), int(duration))
        ordered = sorted(levels[:available])
        p20 = ordered[int((len(ordered) - 1) * 0.20)] if ordered else 0
        p80 = ordered[int((len(ordered) - 1) * 0.80)] if ordered else 0
        if p80 < 120:
            raise RuntimeError("No se detectó suficiente actividad de audio.")
        noise_floor = max(80.0, p20 * 1.6)
        reference = max(1.0, p80)
        burst_threshold = max(noise_floor * 2.2, reference * 1.25)
        weights = {
            "balanced": (0.34, 0.14, 0.24, 0.10, 0.18),
            "reactions": (0.20, 0.25, 0.10, 0.15, 0.30),
            "conversation": (0.24, 0.08, 0.44, 0.10, 0.14),
            "gameplay": (0.26, 0.24, 0.12, 0.12, 0.26),
        }.get(mode, (0.34, 0.14, 0.24, 0.10, 0.18))

        for length in (20, 30, 45, 60):
            if available < length:
                continue
            for start in range(0, available - length + 1, 5):
                window = levels[start:start + length]
                avg = statistics.fmean(window)
                peak = max(window)
                variation = statistics.pstdev(window)
                active = sum(1 for value in window if value > noise_floor) / length
                energy_score = min(1.5, avg / reference)
                peak_score = min(2.0, peak / reference)
                variation_score = min(1.0, variation / reference)

                fine_window = short_levels[start * 4:min((start + length) * 4, len(short_levels))]
                burst_count = 0
                was_loud = False
                for value in fine_window:
                    is_loud = value > burst_threshold
                    if is_loud and not was_loud:
                        burst_count += 1
                    was_loud = is_loud
                burst_score = min(1.0, burst_count / max(1.0, length * 0.10))

                silence_penalty = max(0.0, 0.35 - active)
                # Dar prioridad a picos con contexto: unos segundos más tranquilos
                # antes y después suelen conservar mejor el inicio y cierre de una reacción.
                before = statistics.fmean(levels[max(0, start - 5):start]) if start > 0 else avg
                after = statistics.fmean(levels[min(available, start + length):min(available, start + length + 5)]) if start + length < available else avg
                context_score = min(1.0, (max(0.0, avg - before) + max(0.0, avg - after)) / (2.0 * reference))
                length_bonus = 0.04 if length in (30, 45) else 0.0
                score = (
                    weights[0] * energy_score
                    + weights[1] * peak_score
                    + weights[2] * active
                    + weights[3] * variation_score
                    + weights[4] * burst_score
                    + 0.06 * context_score
                    + length_bonus
                    - silence_penalty
                )
                candidates.append((score, start, length))

        # Selección voraz con diversidad: combina puntuación, duración y
        # distribución temporal sin sacrificar momentos de alta actividad.
        chosen = select_diverse_candidates(candidates, count, available, exclude_ranges)

        # Ajustar bordes solo cuando hay silencio claro y sin bajar de 20 s.
        refined = []
        for start, end, score in chosen:
            segment = levels[start:end]
            threshold = max(noise_floor * 1.15, statistics.fmean(segment) * 0.30)
            active_positions = [i for i, value in enumerate(segment) if value > threshold]
            if active_positions:
                # Mantener contexto antes y después del pico para que el clip
                # no empiece justo en mitad de una frase ni termine de golpe.
                new_start = max(start, start + active_positions[0] - 2)
                new_end = min(end, start + active_positions[-1] + 1 + 3)
                if MIN_CLIP_SECONDS <= new_end - new_start <= MAX_CLIP_SECONDS:
                    start, end = new_start, new_end
            refined.append((start, end, score))

        refined.sort(key=lambda item: item[0])
        best = max((item[2] for item in refined), default=1.0)
        return [
            {
                "start_time": float(start),
                "end_time": float(end),
                "title": "Momento destacado %d (%ds)" % (i + 1, end - start),
                "score": max(1, min(99, int(round(100 * score / max(0.01, best)))))
            }
            for i, (start, end, score) in enumerate(refined)
        ]
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except OSError:
            pass

def detect_visible_crop(source_path):
    """Detect letterboxing across the clip, not just its opening seconds."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(source_path)],
            capture_output=True, text=True, timeout=8
        )
        source_width, source_height = [int(v) for v in probe.stdout.strip().split("x", 1)]
        duration_probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source_path)],
            capture_output=True, text=True, timeout=8
        )
        duration = max(1.0, float(duration_probe.stdout.strip() or 1.0))
        # Sample the beginning, middle and end: Kick scenes can change layout
        # during a clip, so a single opening sample often misses the real frame.
        sample_times = sorted(set(min(max(0.0, duration - 0.7), value) for value in (
            0.5, duration * 0.25, duration * 0.50, duration * 0.75, duration * 0.90
        )))
        valid = []
        for sample_time in sample_times:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-ss", str(sample_time), "-i", str(source_path),
                 "-t", "0.6", "-vf", "cropdetect=limit=24:round=2:reset=0",
                 "-an", "-f", "null", "-"],
                capture_output=True, text=True, timeout=10
            )
            matches = re.findall(r"crop=(-?\\d+):(\\d+):(-?\\d+):(\\d+)", result.stderr or "")
            for item in matches:
                width, height, x, y = [int(value) for value in item]
                # cropdetect reports negative width for frames with only
                # horizontal bars. In that case, retain the full source width.
                if width <= 0 or x < 0 or x + width > source_width:
                    width, x = source_width, 0
                if height <= 0 or y < 0 or y + height > source_height:
                    continue
                if width < source_width * 0.55 or height < source_height * 0.18:
                    continue
                if width >= source_width * 0.97 and height >= source_height * 0.97:
                    continue
                valid.append((width, height, x, y))
        if not valid:
            return None
        values = [int(round(statistics.median([item[i] for item in valid]))) for i in range(4)]
        width, height, x, y = values
        if x < 0 or y < 0 or x + width > source_width or y + height > source_height:
            return None
        return width, height, x, y
    except Exception as crop_exc:
        print("CLIPS.ONTHE content crop detection unavailable: %s" % crop_exc, flush=True)
        return None

def full_frame_vertical_filter(content_crop=None):
    """Fill 9:16 with a soft, non-distracting backdrop and preserve the full scene."""
    crop = ""
    if content_crop:
        width, height, x, y = content_crop
        crop = "crop=%d:%d:%d:%d," % (width, height, x, y)
    return (
        "split=2[bgsrc][fgsrc];"
        # Build the backdrop at low resolution before blurring to keep CPU use low.
        # This avoids the visible enlarged top/bottom strips from the source image.
        "[bgsrc]" + crop +
        # Stretch only the backdrop, then blur it. This keeps dark gameplay scenes
        # visible as a soft background instead of crushing them to black.
        "scale=90:160,gblur=sigma=10,eq=brightness=0.02:saturation=0.8,"
        "scale=720:1280[bg];"
        "[fgsrc]" + crop +
        "scale=720:1280:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def build_face_crop_filter(source_path):
    """Track a lone face; keep the full scene whenever a group is present."""
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
        # Regla conservadora: solo recortar cuando TODAS las muestras muestran
        # claramente una única persona. Si aparece un grupo, falta detección o hay
        # duda, conservar el plano completo para no cortar a nadie.
        if any(int(item.get("face_count") or 0) != 1 for item in centers):
            return ""
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

def source_history_path(source_key):
    digest = hashlib.sha256(str(source_key).encode("utf-8")).hexdigest()
    return BASE / ("seen_" + digest + ".json")


def load_seen_ranges(source_key):
    path = source_history_path(source_key)
    cutoff = time.time() - JOB_TTL_SECONDS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [item for item in data if float(item.get("created_at", 0)) >= cutoff]
        if entries != data:
            path.write_text(json.dumps(entries), encoding="utf-8")
        return [[float(item["start"]), float(item["end"])] for item in entries]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def remember_seen_range(source_key, start, end):
    path = source_history_path(source_key)
    cutoff = time.time() - JOB_TTL_SECONDS
    with JOBS_LOCK:
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        except (OSError, ValueError):
            entries = []
        entries = [item for item in entries if float(item.get("created_at", 0)) >= cutoff]
        entries.append({"start": float(start), "end": float(end), "created_at": time.time()})
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(entries), encoding="utf-8")
        temp.replace(path)


def process_job(job_id, url, count, mode="balanced", follow_face=False):
    global ACTIVE_JOB
    folder = BASE / job_id
    source_dir = folder / "source"
    clips = []
    try:
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "processing", "message": "Analizando vídeo…", "clips": [], "progress_percent": 2}

        meta_options = {
            "format": "best[height<=720][ext=mp4]/best[height<=720]/worst[ext=mp4]/worst",
            "noplaylist": True, "quiet": True, "no_warnings": True,
            "socket_timeout": 20, "retries": 2, "extractor_retries": 2,
        }
        with yt_dlp.YoutubeDL(meta_options) as ydl:
            info = ydl.extract_info(url, download=False)

        duration = float(info.get("duration") or 0)
        source_key = "%s:%s" % (info.get("extractor_key") or info.get("extractor") or "video", info.get("id") or url)
        seen_ranges = load_seen_ranges(source_key)
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
                "clips": [], "progress_percent": 7
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
                    "clips": [], "progress_percent": 12
                }
            ranges = analyze_audio_highlights(audio_files[0], duration, total, mode, seen_ranges)
            if len(ranges) < total:
                raise RuntimeError("No quedan suficientes momentos nuevos para esta cantidad de clips.")
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
                    "clips": [], "progress_percent": 12
                }
            # Incluso si el análisis de audio no está disponible, variar las
            # duraciones y repartir los momentos por todo el vídeo.
            ranges = build_fallback_ranges(duration, total, source_key, seen_ranges)
            if len(ranges) < total:
                raise RuntimeError("Ya se han utilizado casi todos los momentos disponibles de este vídeo. Prueba con menos clips o espera 48 horas para volver a utilizar esos momentos.")
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
                current = JOBS.get(job_id, {})
                download_fraction = (completed - 0.2) if active_item["done"] else (completed + 0.8 * active_item["percent"] / 100.0)
                progress_percent = 15 + int(80 * max(0.0, download_fraction) / total)
                JOBS[job_id] = {
                    "status": "processing",
                    "message": message,
                    "clips": list(current.get("clips") or []),
                    "progress_percent": min(79, progress_percent)
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
                "clips": [], "progress_percent": 15
            }

        clips = []
        # Descarga y convierte cada fragmento antes de pasar al siguiente,
        # para que el usuario pueda reproducir el clip cuanto antes.
        for i, clip_range in enumerate(ranges, start=1):
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Descargando el fragmento %d/%d…" % (i, total),
                    "clips": list(clips), "progress_percent": 15 + int(80 * (i - 1) / total)
                }

            _, source = download_one(i, clip_range)

            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Creando clip vertical %d/%d…" % (i, total),
                    "clips": list(clips), "progress_percent": 15 + int(80 * (i - 0.2) / total)
                }

            filename = "clip_%02d.mp4" % i
            output = folder / filename
            content_crop = detect_visible_crop(source)
            # If the source contains an embedded/letterboxed scene, preserve that
            # entire scene. Face zoom would otherwise magnify a small webcam inset
            # and discard the gameplay or the other people on screen.
            face_crop_filter = build_face_crop_filter(source) if follow_face and not content_crop else ""
            full_frame_filter = full_frame_vertical_filter(content_crop)
            # Convertir a vertical conservando la imagen completa; sin procesamiento de texto.
            if face_crop_filter:
                video_filter = face_crop_filter + "scale=720:1280,setsar=1"
            else:
                video_filter = full_frame_filter
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
                # Si el seguimiento facial falla, conservar el encuadre completo.
                if not face_crop_filter:
                    raise
                print("CLIPS.ONTHE face reframe failed for %s clip %d; retrying full frame" % (job_id, i), flush=True)
                video_filter = full_frame_filter + "[v]"
                ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1] = video_filter
                subprocess.run(ffmpeg_command, capture_output=True, check=True, timeout=180)

            clips.append({
                "name": clip_range.get("title") or ("Clip %d" % i),
                "url": "/download/%s/%s" % (job_id, filename),
                "score": clip_range.get("score"),
                "duration": int(clip_range["end_time"] - clip_range["start_time"]),
                "start_time": float(clip_range["start_time"]),
                "end_time": float(clip_range["end_time"])
            })
            remember_seen_range(source_key, clip_range["start_time"], clip_range["end_time"])
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "status": "processing",
                    "message": "Clip %d/%d listo. Puedes reproducirlo mientras se prepara el siguiente." % (i, total),
                    "clips": list(clips), "progress_percent": 15 + int(80 * i / total)
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
                "clips": clips, "progress_percent": 100
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
                "clips": list(clips), "progress_percent": 100 if has_partial_clips else 0
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
def create_clips(background_tasks: BackgroundTasks, url: str = Form(...), count: int = Form(5), mode: str = Form("balanced"), follow_face: bool = Form(True)):
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
        JOBS[job_id] = {"status": "queued", "message": "Trabajo en cola…", "clips": [], "progress_percent": 0}
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
                "progress_percent": int(job.get("progress_percent") or 0),
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
