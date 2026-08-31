import os
import uuid
import wave
import io
import numpy as np
import subprocess
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from typing import Any, Dict, List
from contextlib import asynccontextmanager
import threading
import time
import re
import math

app = FastAPI()

# API接口跨域中间件（只作用接口，静态文件无效）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "./temp_media"
os.makedirs(TEMP_DIR, exist_ok=True)
STATIC_DIR = "./static"
os.makedirs(STATIC_DIR, exist_ok=True)  # 程序启动时自动创建


# ====================== 重点修改：不再直接mount StaticFiles，改用自定义路由 ======================
@app.get("/static/{file_name}")
async def get_static_file(file_name: str):
    file_path = os.path.join(TEMP_DIR, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    resp = FileResponse(file_path)
    # 手动追加跨域头，解决WebAudio CORS限制
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    return resp

# 处理OPTIONS预检请求
@app.options("/static/{file_name}")
async def static_options(file_name: str):
    from fastapi.responses import Response
    resp = Response()
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    return resp


@app.get("/{file_name}")
async def get_public_file(file_name: str):
    file_path = os.path.join(TEMP_DIR, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    resp = FileResponse(file_path)
    # 手动追加跨域头，解决WebAudio CORS限制
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    return resp

# 处理OPTIONS预检请求
@app.options("/{file_name}")
async def public_options(file_name: str):
    from fastapi.responses import Response
    resp = Response()
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    return resp

class ExtractAudioRequest(BaseModel):
    videoUrl: str


def download_file(url: str, save_path: str):
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def extract_audio(video_path: str, audio_path: str):
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "copy", audio_path
    ]
    ret = subprocess.run(cmd, capture_output=True, text=True)
    if ret.returncode == 0 and os.path.exists(audio_path):
        return
    cmd2 = [
        "ffmpeg", "-y", "-i", video_path, "-vn", "-c:a", "aac", audio_path
    ]
    ret2 = subprocess.run(cmd2, capture_output=True, text=True)
    if ret2.returncode != 0:
        raise Exception(ret2.stderr)

def generate_audio_waveform(audio_file_path, sample_points=150):
    """
    使用ffmpeg转成wav，再计算波形采样
    返回 [0~1] 数组
    """
    # ffmpeg 转成单声道 16bit wav
    cmd = [
        "ffmpeg",
        "-y",
        "-i", audio_file_path,
        "-ac", "1",
        "-f", "wav",
        "-"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wav_data, _ = proc.communicate()

    with wave.open(io.BytesIO(wav_data), 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16)

    # 归一化到 0~1
    abs_samples = np.abs(samples)
    max_val = np.max(abs_samples)
    if max_val == 0:
        normalized = abs_samples
    else:
        normalized = abs_samples / max_val

    block_size = len(normalized) / sample_points
    waveform = []
    for i in range(sample_points):
        start = int(i * block_size)
        end = int((i + 1) * block_size)
        chunk = normalized[start:end]
        waveform.append(float(np.max(chunk)))
    return waveform

@app.post("/api/media/extract-audio")
async def extract(video: UploadFile = File(...)):
    tid = str(uuid.uuid4())
    video_path = os.path.join(TEMP_DIR, f"{tid}.mp4")
    audio_path = os.path.join(TEMP_DIR, f"{tid}.aac")

    save_path = os.path.join(TEMP_DIR, f"{tid}.aac")

    try:
        # 保存前端上传的视频
        with open(video_path, "wb") as f:
            f.write(await video.read())

        extract_audio(video_path, audio_path)
        waveform = generate_audio_waveform(audio_path) # 你原来代码bug：这里之前传了video_path！我顺便修复
        audio_url = f"http://127.0.0.1:8095/static/{tid}.aac"

        print(f"上传blob文件保存到本地: {save_path}, 对应访问url: {audio_url}")

        # 存入内存映射
        url_to_local_map[audio_url] = save_path

        return {"success": True, "audioUrl": audio_url,"localPath": save_path, "waveform": waveform}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


@app.post("/api/media/getAudioWaveform")
async def upload_audio(audio: UploadFile = File(...)):
    tid = str(uuid.uuid4())
    temp_raw = os.path.join(TEMP_DIR, f"{tid}_raw")
    try:
        # 保存上传文件
        with open(temp_raw, "wb") as f:
            f.write(await audio.read())

        fn = audio.filename.lower()

        # 复制到static目录
        suffix = fn[fn.rfind("."):]
        static_name = f"{tid}{suffix}"
        static_path = os.path.join(STATIC_DIR, static_name)
        with open(temp_raw, "rb") as src, open(static_path, "wb") as dst:
            dst.write(src.read())

        # 生成波形
        waveform = generate_audio_waveform(static_path)

        return {
            "success": True,
            "waveform": waveform
        }
    finally:
        if os.path.exists(temp_raw):
            os.remove(temp_raw)


# 任务状态池 单进程内存
task_store: Dict[str, Dict[str, Any]] = {}
url_to_local_map: Dict[str, str] = {}
# 映射：http静态url → 服务器本地磁盘绝对路径，单进程内存缓存
url_to_local_map: Dict[str, str] = {}
# ----- 数据模型 -----
class ExportOptions(BaseModel):
    format: str
    resolution: str
    bitrate: str
    fps: str
    codec: str

class ExportPayload(BaseModel):
    exportOptions: ExportOptions
    tracks: List[Dict[str, Any]]

# 分辨率映射
RESOLUTION_MAP = {
    "original": None,
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "2k": (2560, 1440),
    "540p": (960, 540),
    "480p": (854, 480),
}

def clean_expired_task():
    """清理超过1小时过期任务"""
    now = time.time()
    remove_keys = []
    for tid, item in task_store.items():
        create_ts = item.get("create_ts", 0)
        if now - create_ts > 3600:
            remove_keys.append(tid)
    for k in remove_keys:
        del task_store[k]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # =========应用启动阶段：yield之前，等价于旧的 startup =========
    # 启动定时清理后台守护线程
    def loop_clean():
        while True:
            time.sleep(60)
            clean_expired_task()
    t_clean = threading.Thread(target=loop_clean, daemon=True)
    t_clean.start()

    yield   # 此处交出控制权，应用开始接收http请求

    # =========应用关闭阶段：yield之后，等价于旧的 shutdown =========
    # 程序关闭可以在这里释放资源，清空内存缓存
    task_store.clear()
    url_to_local_map.clear()

def parse_ffmpeg_time_str(time_str: str) -> float:
    """ffmpeg out_time格式 00:00:03.400000 → 返回秒数 float"""
    h,m,s = time_str.split(":")
    return int(h)*3600 + int(m)*60 + float(s)

def background_ffmpeg_task(task_id: str, cmd: List[str], out_path: str, total_output_duration:float):
    try:
        task_store[task_id]["status"] = "running"
        task_store[task_id]["progress"] = 0
        cmd_ext = cmd.copy()
        idx = cmd_ext.index("-y")
        cmd_ext[idx:idx] = ["-v","error","-progress","pipe:2"]
        proc = subprocess.Popen(
            cmd_ext,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )

        # 收集完整stderr，用于错误日志
        stderr_lines = []
        while proc.poll() is None:
            line = proc.stderr.readline()
            if not line:
                continue
            line = line.strip()
            stderr_lines.append(line)

            # 进度解析
            if line.startswith("out_time="):
                time_part = line.split("=",1)[1]
                if time_part != "N/A":
                    current_sec = parse_ffmpeg_time_str(time_part)
                    if total_output_duration > 0:
                        pct = min(99.0, round((current_sec / total_output_duration)*100,1))
                        task_store[task_id]["progress"] = pct
            if "progress=end" in line:
                task_store[task_id]["progress"] = 100

        # 读取剩余未读完的stderr
        remaining = proc.stderr.read()
        if remaining:
            stderr_lines.append(remaining.strip())
        
        full_stderr = "\n".join(stderr_lines)
        retcode = proc.wait()
        
        if retcode != 0:
            # ========== 失败：打印详细排查日志 ==========
            print("\n" + "="*70)
            print(f"[FFmpeg执行失败] 任务ID: {task_id}")
            print(f"输出文件: {out_path}")
            print(f"完整命令: {' '.join(cmd_ext)}")
            print("-"*70)
            print("错误详情:")
            print(full_stderr)
            print("="*70 + "\n")
            
            task_store[task_id]["status"] = "failed"
            task_store[task_id]["errorMsg"] = full_stderr[:800]  # 接口返回摘要
            return
        
        # 执行成功
        task_store[task_id]["status"] = "finished"
        task_store[task_id]["progress"] = 100
        download_filename = os.path.basename(out_path)
        task_store[task_id]["downloadUrl"] = f"http://127.0.0.1:8095/static/{download_filename}"

    except Exception as e:
        # 代码异常也打印日志
        print(f"[渲染任务异常] 任务ID: {task_id}, 异常信息: {str(e)}")
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["errorMsg"] = str(e)[:800]

@app.post("/api/media/upload-blob")
async def api_upload_blob(mediaFile: UploadFile = File(...)):
    """接收前端上传的blob二进制，保存临时文件，返回http访问地址 + 后端本地路径"""
    import uuid
    tid = str(uuid.uuid4())
    orig_name = mediaFile.filename or "temp.mp4"
    suffix = os.path.splitext(orig_name)[1]
    if not suffix:
        suffix = ".mp4"
    save_name = f"{tid}{suffix}"
    save_path = os.path.abspath(os.path.join(TEMP_DIR, save_name))
    with open(save_path, "wb") as f:
        chunk = await mediaFile.read()
        f.write(chunk)
    resource_url = f"http://127.0.0.1:8095/static/{save_name}"

    print(f"上传blob文件保存到本地: {save_path}, 对应访问url: {resource_url}")

    # 存入内存映射
    url_to_local_map[resource_url] = save_path
    return {
        "success": True,
        "resourceUrl": resource_url,
        "localPath": save_path  # 返回给前端，但前端不要使用此字段，仅后端内部用映射表
    }



def safe_float(v, default=1.0):
    if v is None:
        return default
    return float(v)

def download_http_to_tempfile(http_url: str) -> str:
    """
    优先查表，如果是本地上传的资源直接返回本地路径；外部http才执行下载
    """
    # 命中本地上传资源，直接返回本地磁盘路径，跳过下载
    if http_url in url_to_local_map:
        return url_to_local_map[http_url]

    if not (http_url.startswith("http://") or http_url.startswith("https://")):
        return http_url

    # 从url路径中提取原始后缀，取?之前的部分，去掉query参数
    from urllib.parse import urlparse
    parsed = urlparse(http_url)
    path = parsed.path
    # 获取路径后缀
    _, ext = os.path.splitext(path)
    if not ext:
        ext = ".mp4" # 没有后缀兜底mp4

    tmp_name = f"dl_{uuid.uuid4()}{ext}"
    local_path = os.path.abspath(os.path.join(TEMP_DIR, tmp_name))
    print(f"外部网络资源，执行下载: {http_url}")
    resp = requests.get(http_url, stream=True, timeout=30)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)

    print(f"保存到本地: {local_path}")
    return local_path


# 前端预览画布尺寸常量
PREVIEW_CANVAS_WIDTH = 783
PREVIEW_CANVAS_HEIGHT = 450

# ====================== 核心改造：nullsrc+setpts 渲染接口 ======================
@app.post("/api/export/render")
async def export_render(payload: ExportPayload):

    export_opt = payload.exportOptions
    tracks = payload.tracks

    all_end = []
    for track in tracks:
        for clip in track.get("clips",[]):
            all_end.append(safe_float(clip["endTime"]))
    total_output_duration = max(all_end) if len(all_end)>0 else 15.0
    fps = safe_float(export_opt.fps)

    video_clips = []
    audio_clips = []
    subtitle_clips = []  # 新增：收集字幕片段
    sticker_clips = [] # 新增贴纸列表
    filter_clips = [] # 新增滤镜片段
    effect_clips = [] # 新增特效片段
    transition_clips = [] # 新增转场片段
    for track in tracks:
        track_visible = track.get("visible", True)
        if track_visible:
            for clip in track.get("clips", []):
                t = clip["type"]
                # 只对存在source字段的素材执行下载转换本地路径
                if "source" in clip and clip["source"]:
                    original_src = clip["source"]
                    local_src = download_http_to_tempfile(original_src)
                    clip["source"] = local_src

                if t == "video":
                    video_clips.append(clip)
                elif t == "audio":
                    audio_clips.append(clip)
                elif t == "subtitle":
                    subtitle_clips.append(clip)
                elif t == "sticker":
                    sticker_clips.append(clip)
                elif t == "filter":
                    filter_clips.append(clip)
                elif t == "effect":
                    effect_clips.append(clip)
                elif t == "transition":
                    transition_clips.append(clip)

    # 转场type映射ffmpeg xfade滤镜名
    TRANS_XFADE_MAP = {
        "dissolve": "dissolve",
        "cross-dissolve": "fade",
        "dip-to-black": "dipblack",
        "dip-to-white": "dipwhite",
        "wipe-left": "wipeleft",
        "wipe-right": "wiperight"
    }
    
    if len(video_clips) == 0:
        raise HTTPException(status_code=400, detail="至少需要一条视频片段")

    task_id = str(uuid.uuid4())
    out_filename = f"{task_id}.{export_opt.format}"
    out_path = os.path.abspath(os.path.join(TEMP_DIR, out_filename))

    # 计算输出分辨率
    if export_opt.resolution == "original":
        main_video_clip = None
        for track in tracks:
            if track.get("mainTrack"):
                for clip in track.get("clips", []):
                    if clip.get("type") == "video":
                        main_video_clip = clip
                        break
                if main_video_clip:
                    break
        if not main_video_clip:
            main_video_clip = video_clips[0]
        w = int(main_video_clip.get("naturalWidth", 1920))
        h = int(main_video_clip.get("naturalHeight", 1080))
    else:
        w, h = RESOLUTION_MAP.get(export_opt.resolution, (1920, 1080))
    codec = export_opt.codec

    # 坐标换算比例
    coord_scale_x = w / PREVIEW_CANVAS_WIDTH
    coord_scale_y = h / PREVIEW_CANVAS_HEIGHT
    avg_coord_scale = (coord_scale_x + coord_scale_y) / 2.0
    input_args = []
    filter_complex_segments = []
    audio_mix_inputs = []
    video_in_idx = 0

    # ========== 修改1：基底改为纯黑不透明背景 ==========
    """
    base_seg = (
        f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration},"
        f"format=yuva420p,fps={fps}[base]"
    )
    """
    base_seg = (
        f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration},"
        f"format=yuva420p,fps={fps},settb=1/{fps}[base]"
    )

    filter_complex_segments.append(base_seg)

    # 视频按开始时间升序排序，确保拼接顺序与时间轴一致
    video_clips.sort(key=lambda c: safe_float(c["startTime"]))
    
    # 2. 处理每个视频片段：生成调色缩放流 → 合成到透明画布 → 按序xfade拼接
    video_layer_tags = []
    for i, clip in enumerate(video_clips):
        src = clip["source"]
        clip_start = safe_float(clip["startTime"])
        trim_start = safe_float(clip["trimStart"])
        trim_end = safe_float(clip["trimEnd"])
        src_duration = trim_end - trim_start
        rate = safe_float(clip.get("playbackRate"), 1.0)
        opacity = safe_float(clip.get("opacity"), 1.0)
        brightness = safe_float(clip.get("brightness"), 1.0)
        contrast = safe_float(clip.get("contrast"), 1.0)
        saturation = safe_float(clip.get("saturation"), 1.0)
        temp = safe_float(clip.get("temp"), 0.0)
        tint = safe_float(clip.get("tint"), 0.0)
        vignette = safe_float(clip.get("vignette"), 0.0)
        transform = clip.get("transform", {})
        scale_val = safe_float(transform.get("scale", 1.0))
        vol = safe_float(clip.get("volume"), 1.0)


        input_args.extend([
            "-ss", str(trim_start),
            "-i", src
        ])


        # ========== 调色参数与前端 shader 顺序完全一致 ==========
        b = brightness
        temp_factor = temp / 100.0
        rr_temp = 1.0 + temp_factor * 0.15
        bb_temp = 1.0 - temp_factor * 0.15
        tint_factor = safe_float(tint, 0.0) / 100.0
        TINT_NEG_R, TINT_NEG_G, TINT_NEG_B = 0.72, 0.92, 0.76
        TINT_POS_R, TINT_POS_G, TINT_POS_B = 0.92, 0.72, 0.72
        if tint_factor < 0.0:
            abs_f = abs(tint_factor)
            mix_r = 1.0 * (1.0 - abs_f) + TINT_NEG_R * abs_f
            mix_g = 1.0 * (1.0 - abs_f) + TINT_NEG_G * abs_f
            mix_b = 1.0 * (1.0 - abs_f) + TINT_NEG_B * abs_f
        else:
            f = tint_factor
            mix_r = 1.0 * (1.0 - f) + TINT_POS_R * f
            mix_g = 1.0 * (1.0 - f) + TINT_POS_G * f
            mix_b = 1.0 * (1.0 - f) + TINT_POS_B * f


        vig = safe_float(vignette, 0.0)
        vig_scale = vig * 1.8
        if vig > 0:
            dist_expr = "sqrt(pow((X/W-0.5),2)+pow((Y/H-0.5),2))"
            smooth_expr = f"clamp(({dist_expr}*{vig_scale}-0.35)/0.5,0,1)"
            vig_factor_expr = f"(1-({smooth_expr}*{smooth_expr}*(3-2*{smooth_expr})))"
            geq_expr = (
                f"r='r(X,Y)*{vig_factor_expr}':"
                f"g='g(X,Y)*{vig_factor_expr}':"
                f"b='b(X,Y)*{vig_factor_expr}':"
                f"a='A'"
            )
        else:
            geq_expr = "r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='A'"


        # 生成原始处理流：trim、调速、调色、缩放、透明度，PTS从0开始
        seg_raw = (
            f"[{i}:v]"
            f"trim=duration={src_duration},setpts=PTS-STARTPTS,"
            f"setpts=PTS/{rate},"
            f"colorchannelmixer=rr={b}:gg={b}:bb={b},"
            f"eq=contrast={contrast}:saturation={saturation},"
            f"colorchannelmixer=rr={rr_temp}:gg=1.0:bb={bb_temp},"
            f"colorchannelmixer=rr={mix_r}:gg={mix_g}:bb={mix_b},"
            f"vignette=a={vig*2.2},"
            f"scale=iw*{scale_val}:ih*{scale_val},"
            f"fps={fps},"
            f"format=yuva420p,"
            f"colorchannelmixer=aa={opacity}"
            f"[v_raw_{i}]"
        )
        filter_complex_segments.append(seg_raw)


        # 计算视频在输出画布上的位置（与原逻辑完全对齐）
        center_x = safe_float(transform.get("x", 0.0)) * coord_scale_x
        center_y = safe_float(transform.get("y", 0.0)) * coord_scale_y
        natural_w = safe_float(clip.get("naturalWidth", 1920))
        natural_h = safe_float(clip.get("naturalHeight", 1080))
        layer_w = natural_w * scale_val
        layer_h = natural_h * scale_val
        ox = center_x - layer_w / 2
        oy = center_y - layer_h / 2
        layer_duration = src_duration / rate


        # 合成到透明画布：画布为底图，视频为叠加层，输出统一YUVA420P格式
        """
        seg_layer = (
            f"color=c=black@0:size={w}x{h}:rate={fps}:d={layer_duration}[canvas_{i}];"
            f"[canvas_{i}][v_raw_{i}]overlay=x={ox}:y={oy}:shortest=0:repeatlast=0,"
            f"format=yuva420p[v_layer_{i}]"
        )
        """

        seg_layer = (
            f"color=c=black@0:size={w}x{h}:rate={fps}:d={layer_duration}[canvas_{i}];"
            f"[canvas_{i}][v_raw_{i}]overlay=x={ox}:y={oy}:shortest=0:repeatlast=0,"
            f"format=yuva420p,fps={fps}[v_layer_{i}]"
        )

        filter_complex_segments.append(seg_layer)
        video_layer_tags.append(f"v_layer_{i}")


        # ========== 视频自带音频处理（逻辑保持不变） ==========
        has_split_audio = safe_float(clip.get("hasSplitAudio", False), 0)
        atempo_chain = f"atempo={rate}"
        if rate > 2.0:
            atempo_chain = "atempo=2,atempo=" + str(rate / 2)
        elif rate < 0.5:
            atempo_chain = "atempo=0.5,atempo=" + str(rate * 2)
        vid_aud_tag = f"vid_aud_{i}"
        aud_seg = (
            f"[{i}:a]"
            f"atrim=duration={src_duration},asetpts=PTS-STARTPTS,"
            f"{atempo_chain},"
            f"volume={vol}"
            f"[{vid_aud_tag}]"
        )
        if not has_split_audio:
            filter_complex_segments.append(aud_seg)
            # 仅生成音频流，暂不加入混音列表，后续统一做 acrossfade 链式拼接


    video_in_idx = len(video_clips)
    sticker_in_start_idx = video_in_idx


    # ========== 核心：XFADE 转场拼接 ==========
        # ========== 核心：视频拼接｜有转场用xfade，无转场用concat ==========
    prev_stream = video_layer_tags[0]
    # 按图层实际调速后的时长计算累计时间，和流真实时长严格对齐
    first_trim = safe_float(video_clips[0]["trimEnd"]) - safe_float(video_clips[0]["trimStart"])
    first_rate = safe_float(video_clips[0].get("playbackRate"), 1.0)
    acc_time = first_trim / first_rate

    for i in range(1, len(video_layer_tags)):
        curr_stream = video_layer_tags[i]
        clip_a = video_clips[i - 1]
        clip_cur = video_clips[i]
        # 当前视频图层的实际调速后时长
        cur_trim = safe_float(clip_cur["trimEnd"]) - safe_float(clip_cur["trimStart"])
        cur_rate = safe_float(clip_cur.get("playbackRate"), 1.0)
        cur_dur = cur_trim / cur_rate

        # 匹配两个视频之间的转场片段
        matched_trans = None
        for t_clip in transition_clips:
            t_end = safe_float(t_clip["endTime"])
            if abs(t_end - safe_float(clip_a["endTime"])) < 0.1:
                matched_trans = t_clip
                break

        out_tag = f"v_join_{i}"
        if matched_trans:
            trans_dur = safe_float(matched_trans.get("duration", 1.0))
            xfade_filter = TRANS_XFADE_MAP.get(matched_trans.get("transitionType", ""), "fade")
            offset = acc_time - trans_dur
            out_tag = f"v_xfade_{i}"
            """
            filter_complex_segments.append(
                f"[{prev_stream}][{curr_stream}]xfade=transition={xfade_filter}:duration={trans_dur}:offset={offset}[{out_tag}]"
            )
            """
            filter_complex_segments.append(
                f"[{prev_stream}][{curr_stream}]xfade=transition={xfade_filter}:duration={trans_dur}:offset={offset},settb=1/{fps}[{out_tag}]"
            )
            acc_time = acc_time + cur_dur - trans_dur
        else:
            # 图层尺寸格式已完全统一，无转场直接concat硬切，稳定不黑屏
            """
            filter_complex_segments.append(
                f"[{prev_stream}][{curr_stream}]concat=n=2:v=1:a=0[{out_tag}]"
            )
            """
            filter_complex_segments.append(
                f"[{prev_stream}][{curr_stream}]concat=n=2:v=1:a=0,settb=1/{fps}[{out_tag}]"
            )
            acc_time = acc_time + cur_dur
        prev_stream = out_tag

    # 拼接完成视频层叠加到黑色基底，输出主画面，后续贴纸/特效/滤镜链路沿用vid_main
    """
    filter_complex_segments.append(
        f"[base][{prev_stream}]overlay=x=0:y=0:shortest=0:repeatlast=0[vid_main]"
    )
    """

    filter_complex_segments.append(
        f"[base][{prev_stream}]overlay=x=0:y=0:shortest=0:repeatlast=0,settb=1/{fps}[vid_main]"
    )


    # ==========【音频：视频自带音频 acrossfade 链式拼接，和画面转场完全同步】 ==========
    vid_audio_tags = []
    for i, clip in enumerate(video_clips):
        has_split_audio = safe_float(clip.get("hasSplitAudio", False), 0)
        if not has_split_audio:
            vid_audio_tags.append(f"vid_aud_{i}")

    audio_final_tag = ""
    if len(vid_audio_tags) > 0:
        if len(vid_audio_tags) == 1:
            # 单段视频音频无需拼接
            audio_final_tag = vid_audio_tags[0]
        else:
            acc_audio_time = safe_float(video_clips[0]["endTime"]) - safe_float(video_clips[0]["startTime"])
            prev_a_stream = vid_audio_tags[0]

            for idx in range(1, len(vid_audio_tags)):
                curr_a_stream = vid_audio_tags[idx]
                clip_a = video_clips[idx - 1]
                clip_cur = video_clips[idx]
                cur_dur = safe_float(clip_cur["endTime"]) - safe_float(clip_cur["startTime"])

                # 和视频xfade共用同一套转场匹配逻辑
                matched_trans = None
                for t_clip in transition_clips:
                    t_end = safe_float(t_clip["endTime"])
                    if abs(t_end - safe_float(clip_a["endTime"])) < 0.1:
                        matched_trans = t_clip
                        break

                a_out_tag = f"a_xfade_{idx}"
                if matched_trans:
                    trans_dur = safe_float(matched_trans.get("duration", 1.0))
                    # 音频交叉淡入淡出时长 = 视频转场时长，完全对齐
                    filter_complex_segments.append(
                        f"[{prev_a_stream}][{curr_a_stream}]acrossfade=d={trans_dur}:c1=tri:c2=tri[{a_out_tag}]"
                    )
                    acc_audio_time = acc_audio_time + cur_dur - trans_dur
                else:
                    # 无转场极短过渡模拟硬切，和视频一致
                    trans_dur = 0.001
                    filter_complex_segments.append(
                        f"[{prev_a_stream}][{curr_a_stream}]acrossfade=d={trans_dur}:c1=tri:c2=tri[{a_out_tag}]"
                    )
                    acc_audio_time = acc_audio_time + cur_dur - trans_dur
                prev_a_stream = a_out_tag
            audio_final_tag = prev_a_stream

    # -------------------------- 组装最终混音列表 --------------------------
    audio_mix_inputs = []
    # 加入拼接完成的视频主音频
    if audio_final_tag:
        audio_mix_inputs.append(audio_final_tag)


    # ------------------ 复刻前端 getBaseDrawSize 逻辑，预览画布基准783*450 ----------------
    def get_base_draw_size(naturalW: float, naturalH: float):
            cw = PREVIEW_CANVAS_WIDTH   #783
            ch = PREVIEW_CANVAS_HEIGHT  #450
            r1 = naturalW / naturalH
            r2 = cw / ch
            if r1 > r2:
                w = cw
                h = cw / r1
            else:
                h = ch
                w = ch * r1
            return w, h

    cur_sticker_buf = "vid_main"
    for s_idx, clip in enumerate(sticker_clips):
        src = clip["source"]
        # ----新增：贴纸素材追加为ffmpeg输入源，修正索引越界！！！----
        input_args.extend([
            "-ss", "0.0",
            "-i", src
        ])
        clip_start = safe_float(clip["startTime"])
        clip_end = safe_float(clip["endTime"])
        clip_total_dur = clip_end - clip_start
        is_gif = src.lower().endswith(".gif")
        tf = clip.get("transform", {})
        pos_x = safe_float(tf.get("x",0.0)) * coord_scale_x
        pos_y = safe_float(tf.get("y",0.0)) * coord_scale_y
        s_scale = safe_float(tf.get("scale", 1.0))
        s_rotate_deg = safe_float(clip.get("rotate", 0.0))
        opacity = safe_float(clip.get("opacity",1.0))
        natW = safe_float(clip.get("naturalWidth",60))
        natH = safe_float(clip.get("naturalHeight",60))
        prev_draw_w, prev_draw_h = get_base_draw_size(natW, natH)
        out_draw_w = prev_draw_w * avg_coord_scale * s_scale
        out_draw_h = prev_draw_h * avg_coord_scale * s_scale
        sticker_in_idx = sticker_in_start_idx + s_idx
        tag_src = f"st_src_{s_idx}"
        tag_rot = f"st_rot_{s_idx}"
        tag_overlay = f"st_out_{s_idx}"
        if is_gif:
            sticker_filter = (
                f"[{sticker_in_idx}:v]"
                f"trim=duration={clip_total_dur},setpts=PTS-STARTPTS,"
                f"scale={out_draw_w}:{out_draw_h},"
                f"format=yuva420p,"
                f"colorchannelmixer=aa={opacity},"
                f"setpts=PTS+{clip_start}/TB"
                f"[{tag_src}]"
            )
        else:
            sticker_filter = (
                f"[{sticker_in_idx}:v]"
                f"loop=-1:size=1:start=0,"
                f"trim=duration={clip_total_dur},setpts=PTS-STARTPTS,"
                f"scale={out_draw_w}:{out_draw_h},"
                f"format=yuva420p,"
                f"colorchannelmixer=aa={opacity},"
                f"setpts=PTS+{clip_start}/TB"
                f"[{tag_src}]"
            )
        filter_complex_segments.append(sticker_filter)
        rot_rad = s_rotate_deg * math.pi / 180.0
        rot_filter = f"[{tag_src}]rotate={rot_rad}:fillcolor=none[{tag_rot}]"
        filter_complex_segments.append(rot_filter)
        overlay_filter = (
            f"[{cur_sticker_buf}][{tag_rot}]"
            f"overlay=x={pos_x}:y={pos_y}:shortest=0:repeatlast=0"
            f":enable='between(t,{clip_start},{clip_end})'"
            f"[{tag_overlay}]"
        )
        filter_complex_segments.append(overlay_filter)
        cur_sticker_buf = tag_overlay

    # 贴纸全部处理完成输出 sticker_done
    filter_complex_segments.append(f"[{cur_sticker_buf}]format=yuv420p[sticker_done]")

    cur_effect_buf = "sticker_done"
    for e_clip in effect_clips:
        eid = e_clip["id"]
        e_key = e_clip["effectKey"]
        e_start = safe_float(e_clip["startTime"])
        e_end = safe_float(e_clip["endTime"])
        e_int = safe_float(e_clip.get("intensity", 1.0))
        duration_e = e_end - e_start
        tag_out = f"e_out_{eid}"

        if e_key == "open":
            t0 = e_start
            t1 = e_end
            dur_e = duration_e
            intensity = e_int
            tag_split_src = f"e_split_src_{eid}"
            tag_eff = f"e_eff_{eid}"
            tag_raw = f"e_raw_{eid}"
            tag_mask_src = f"e_mask_src_{eid}"
            tag_mask_scaled = f"e_mask_scaled_{eid}"
            tag_black_bg2 = f"e_black_bg2_{eid}"
            tag_mask_alpha = f"e_mask_alpha_{eid}"
            tag_fg_alpha = f"e_fg_alpha_{eid}"
            tag_black_bg = f"e_black_bg_{eid}"
            tag_out = f"e_out_{eid}"

            filter_complex_segments.append(f"[{cur_effect_buf}]split=2[{tag_eff}][{tag_raw}]")
            filter_complex_segments.append(f"color=c=white:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_mask_src}]")
            # 对齐Vue shader mix(1.0, progress, intensity) 逻辑
            scale_w_expr = (
                f"clip( {w} * ((1.0-{intensity:.4f}) + min(max(((t-{t0})/{dur_e})\\,0)\\,1)*{intensity:.4f})\\, 0\\, {w})"
            )
            filter_complex_segments.append(f"[{tag_mask_src}]scale=w='{scale_w_expr}':h={h}:flags=lanczos:eval=frame[{tag_mask_scaled}]")
            filter_complex_segments.append(f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_black_bg2}]")
            # 注意：x='(W-w)/2' 减号必须是键盘普通ASCII `-`，禁止复制粘贴
            filter_complex_segments.append(f"[{tag_black_bg2}][{tag_mask_scaled}]overlay=x='(W-w)/2':y=0:eval=frame:shortest=0[{tag_mask_alpha}]")
            filter_complex_segments.append(f"[{tag_eff}][{tag_mask_alpha}]alphamerge[{tag_fg_alpha}]")
            filter_complex_segments.append(f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_black_bg}]")
            filter_complex_segments.append(f"[{tag_black_bg}][{tag_fg_alpha}]overlay=shortest=0[{tag_fg_alpha}]")
            # between内部逗号 \\,
            filter_complex_segments.append(f"[{tag_raw}][{tag_fg_alpha}]overlay=shortest=0:enable=between(t\\,{t0}\\,{t1})[{tag_out}]")

            cur_effect_buf = tag_out


        elif e_key == "close":
            t0 = e_start
            t1 = e_end
            dur_e = duration_e
            intensity = e_int
            tag_split_src = f"e_split_src_{eid}"
            tag_eff = f"e_eff_{eid}"
            tag_raw = f"e_raw_{eid}"
            tag_mask_src = f"e_mask_src_{eid}"
            tag_mask_scaled = f"e_mask_scaled_{eid}"
            tag_black_bg2 = f"e_black_bg2_{eid}"
            tag_mask_alpha = f"e_mask_alpha_{eid}"
            tag_fg_alpha = f"e_fg_alpha_{eid}"
            tag_black_bg = f"e_black_bg_{eid}"
            tag_out = f"e_out_{eid}"

            filter_complex_segments.append(f"[{cur_effect_buf}]split=2[{tag_eff}][{tag_raw}]")
            filter_complex_segments.append(f"color=c=white:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_mask_src}]")

            # 完全对齐shader: p = mix(1.0, progress, intensity) = (1.0‑intensity) + progress*intensity
            # mask_w = w * (1.0 - p)
            scale_w_expr = (
                f"clip( {w} * (1.0 - ((1.0-{intensity:.4f}) + min(max(((t-{t0})/{dur_e})\\,0)\\,1)*{intensity:.4f}))\\, 0\\, {w})"
            )

            filter_complex_segments.append(f"[{tag_mask_src}]scale=w='{scale_w_expr}':h={h}:flags=lanczos:eval=frame[{tag_mask_scaled}]")
            filter_complex_segments.append(f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_black_bg2}]")
            # ⚠️ x='(W-w)/2' 减号必须是键盘手动敲普通ASCII `-`，禁止复制粘贴
            filter_complex_segments.append(f"[{tag_black_bg2}][{tag_mask_scaled}]overlay=x='(W-w)/2':y=0:eval=frame:shortest=0[{tag_mask_alpha}]")
            filter_complex_segments.append(f"[{tag_eff}][{tag_mask_alpha}]alphamerge[{tag_fg_alpha}]")
            filter_complex_segments.append(f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_black_bg}]")
            filter_complex_segments.append(f"[{tag_black_bg}][{tag_fg_alpha}]overlay=shortest=0[{tag_fg_alpha}]")
            filter_complex_segments.append(f"[{tag_raw}][{tag_fg_alpha}]overlay=shortest=0:enable=between(t\\,{t0}\\,{t1})[{tag_out}]")

            cur_effect_buf = tag_out


        elif e_key == "blur‑gauss":
            t0 = e_start
            t1 = e_end
            intensity = e_int
            tag_out = f"e_out_{eid}"
            # intensity映射sigma，1.0 → sigma=10，按需调系数
            sigma = round(intensity * 10.0, 2)
            # 输入直接使用cur_effect_buf（上一步输出流标签），不要tag_img
            filter_complex_segments.append(
                f"[{cur_effect_buf}]gblur=sigma={sigma}"
                f":enable='between(t\\,{t0}\\,{t1})'[{tag_out}]"
            )
            cur_effect_buf = tag_out


        else:
            filter_complex_segments.append(f"[{cur_effect_buf}]copy[{tag_out}]")
            cur_effect_buf = tag_out

    filter_complex_segments.append(f"[{cur_effect_buf}]format=yuv420p[effect_done]")


    
    cur_filter_buf = "effect_done"
    # ========= 应用filter类型片段滤镜，复刻VideoPreview.vue各滤镜效果 =========
    for f_clip in filter_clips:
        f_start = safe_float(f_clip["startTime"])
        f_end = safe_float(f_clip["endTime"])
        f_intensity = safe_float(f_clip.get("intensity", 0.0))
        f_key = f_clip.get("filterKey","")
        if f_intensity < 0.01:
            continue
        tag_out = f"f_out_{f_clip['id']}"

        if f_key == "filter-film-gray":
            # 直接展开glsl mix(col,vec3(dot(col,W)),t)的矩阵公式
            t = f_intensity
            w_r = 0.2126
            w_g = 0.7152
            w_b = 0.0722
            rr = (1.0 - t) + w_r * t
            rg = w_g * t
            rb = w_b * t
            gr = w_r * t
            gg = (1.0 - t) + w_g * t
            gb = w_b * t
            br = w_r * t
            bg = w_g * t
            bb = (1.0 - t) + w_b * t

            flt_expr = (
                f"colorchannelmixer="
                f"rr={rr:.6f}:rg={rg:.6f}:rb={rb:.6f}:"
                f"gr={gr:.6f}:gg={gg:.6f}:gb={gb:.6f}:"
                f"br={br:.6f}:bg={bg:.6f}:bb={bb:.6f}"
            )
            seg = (
                f"[{cur_filter_buf}]{flt_expr}:enable='between(t,{f_start},{f_end})'[{tag_out}]"
            )
            filter_complex_segments.append(seg)
            cur_filter_buf = tag_out
            continue

        elif f_key == "filter-art-oil":
            # 直接作用当前画面，不做原图混合
            i = f_intensity
            cont_coeff = round(1.0 + 0.35 * i, 4)
            y0 = (-0.5) * cont_coeff + 0.5
            y1 = 0.5 * cont_coeff + 0.5
            y0 = max(0.0, min(1.0, y0))
            y1 = max(0.0, min(1.0, y1))
            curve_str = f"0/{y0:.6f} 0.5/0.5 1/{y1:.6f}"

            sat_factor = 1.0 + 0.40 * i
            lum_r = 0.2126
            lum_g = 0.7152
            lum_b = 0.0722
            one_minus_s = 1.0 - sat_factor

            rr = sat_factor
            rg = one_minus_s * lum_g
            rb = one_minus_s * lum_b
            gr = one_minus_s * lum_r
            gg = sat_factor
            gb = one_minus_s * lum_b
            br = one_minus_s * lum_r
            bg = one_minus_s * lum_g
            bb = sat_factor

            flt_expr = (
                f"curves=r='{curve_str}':g='{curve_str}':b='{curve_str}',"
                f"colorchannelmixer="
                f"rr={rr:.6f}:rg={rg:.6f}:rb={rb:.6f}:"
                f"gr={gr:.6f}:gg={gg:.6f}:gb={gb:.6f}:"
                f"br={br:.6f}:bg={bg:.6f}:bb={bb:.6f}"
            )
            seg = (
                f"[{cur_filter_buf}]{flt_expr}:enable='between(t,{f_start},{f_end})'[{tag_out}]"
            )
            filter_complex_segments.append(seg)
            cur_filter_buf = tag_out
            continue

        # ============ 其余滤镜：retro / blue‑film / clear / dusk / sunny / sea ============
        tag_orig = f"f_orig_{f_clip['id']}"
        tag_proc = f"f_proc_{f_clip['id']}"
        filter_complex_segments.append(f"[{cur_filter_buf}]split=2[{tag_orig}][{tag_proc}]")

        flt_expr = ""
        if f_key == "filter-film-retro":
            sepia_r = 0.393
            sepia_g = 0.769
            sepia_b = 0.189
            sepia_r2 = 0.349
            sepia_g2 = 0.686
            sepia_b2 = 0.168
            sepia_r3 = 0.272
            sepia_g3 = 0.534
            sepia_b3 = 0.131
            sat = 1.0 + 0.20 * f_intensity
            cont = 1.0 + 0.22 * f_intensity
            flt_expr = (
                f"eq=contrast={cont}:saturation={sat},"
                f"colorchannelmixer="
                f"rr={sepia_r}:rg={sepia_g}:rb={sepia_b}:"
                f"gr={sepia_r2}:gg={sepia_g2}:gb={sepia_b2}:"
                f"br={sepia_r3}:bg={sepia_g3}:bb={sepia_b3}"
            )
        elif f_key == "filter-film-blue":
            sat = 1.0 - 0.35 * f_intensity
            hue_deg = 210.0 * f_intensity
            flt_expr = f"eq=saturation={sat},hue={hue_deg}"
        elif f_key == "filter-fresh-clear":
            i = f_intensity
            b_factor = 1.0 + 0.18 * i
            s_factor = 1.0 + 0.25 * i
            lum_r = 0.2126
            lum_g = 0.7152
            lum_b = 0.0722
            one_minus_s = 1.0 - s_factor
            rr = b_factor * s_factor
            rg = b_factor * one_minus_s * lum_g
            rb = b_factor * one_minus_s * lum_b
            gr = b_factor * one_minus_s * lum_r
            gg = b_factor * s_factor
            gb = b_factor * one_minus_s * lum_b
            br = b_factor * one_minus_s * lum_r
            bg = b_factor * one_minus_s * lum_g
            bb = b_factor * s_factor
            flt_expr = (
                f"colorchannelmixer="
                f"rr={rr:.6f}:rg={rg:.6f}:rb={rb:.6f}:"
                f"gr={gr:.6f}:gg={gg:.6f}:gb={gb:.6f}:"
                f"br={br:.6f}:bg={bg:.6f}:bb={bb:.6f}"
            )
        elif f_key == "filter-fresh-dusk":
            i = f_intensity
            b_factor = 1.0 + 0.12 * i
            m = 0.22 * i
            rr = b_factor * ((1.0 - m) + 0.393 * m)
            rg = b_factor * (0.769 * m)
            rb = b_factor * (0.189 * m)
            gr = b_factor * (0.349 * m)
            gg = b_factor * ((1.0 - m) + 0.686 * m)
            gb = b_factor * (0.168 * m)
            br = b_factor * (0.272 * m)
            bg = b_factor * (0.534 * m)
            bb = b_factor * ((1.0 - m) + 0.131 * m)
            flt_expr = (
                f"colorchannelmixer="
                f"rr={rr:.6f}:rg={rg:.6f}:rb={rb:.6f}:"
                f"gr={gr:.6f}:gg={gg:.6f}:gb={gb:.6f}:"
                f"br={br:.6f}:bg={bg:.6f}:bb={bb:.6f}"
            )
        elif f_key == "filter-travel-sunny":
            i = f_intensity
            b_factor = 1.0 + 0.25 * i
            s_factor = 1.0 + 0.35 * i
            lum_r = 0.2126
            lum_g = 0.7152
            lum_b = 0.0722
            one_minus_s = 1.0 - s_factor
            rr = b_factor * s_factor
            rg = b_factor * one_minus_s * lum_g
            rb = b_factor * one_minus_s * lum_b
            gr = b_factor * one_minus_s * lum_r
            gg = b_factor * s_factor
            gb = b_factor * one_minus_s * lum_b
            br = b_factor * one_minus_s * lum_r
            bg = b_factor * one_minus_s * lum_g
            bb = b_factor * s_factor
            flt_expr = (
                f"colorchannelmixer="
                f"rr={rr:.6f}:rg={rg:.6f}:rb={rb:.6f}:"
                f"gr={gr:.6f}:gg={gg:.6f}:gb={gb:.6f}:"
                f"br={br:.6f}:bg={bg:.6f}:bb={bb:.6f}"
            )
        elif f_key == "filter-travel-sea":
            hue_deg = 195.0 * f_intensity
            sat = 1.0 + 0.20 * f_intensity
            flt_expr = f"hue={hue_deg},eq=saturation={sat}"
        else:
            filter_complex_segments.append(f"[{cur_filter_buf}]copy[{tag_out}]")
            cur_filter_buf = tag_out
            continue

        filter_complex_segments.append(f"[{tag_proc}]{flt_expr}[{tag_proc}]")
        # normal模式等价glsl mix(a,b,t)
        blend_seg = (
            f"[{tag_orig}][{tag_proc}]blend=all_mode='normal':all_opacity={f_intensity}"
            f":enable='between(t,{f_start},{f_end})'[{tag_out}]"
        )
        filter_complex_segments.append(blend_seg)
        cur_filter_buf = tag_out

    filter_complex_segments.append(f"[{cur_filter_buf}]format=yuv420p[filter_done]")






    # ==========【ASS字幕 完全对齐VideoPreview预览】 ==========
    ass_temp_file = None
    if len(subtitle_clips) > 0:
        ass_lines = []
        ass_lines.append("[Script Info]")
        ass_lines.append("ScriptType: v4.00+")
        ass_lines.append(f"PlayResX: {w}")
        ass_lines.append(f"PlayResY: {h}")
        ass_lines.append("")
        ass_lines.append("[V4+ Styles]")
        ass_lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
        style_idx = 0
        style_name_map = {}
        def sec_to_ass_time(s):
            h=int(s//3600)
            m=int((s%3600)//60)
            sec = s%60
            return f"{h:01d}:{m:02d}:{sec:05.2f}"
        def hex_to_ass_color(hexstr:str):
            h = hexstr.lstrip('#')
            r=int(h[0:2],16)
            g=int(h[2:4],16)
            b=int(h[4:6],16)
            return f"&H00{b:02X}{g:02X}{r:02X}"
        for sub_clip in subtitle_clips:
            tf = sub_clip.get("transform", {})
            rotate_deg = -1.0 * safe_float(tf.get("rotate",0.0))
            rot_key = f"{rotate_deg:.2f}"
            if rot_key not in style_name_map:
                st_name = f"ST_{style_idx}"
                style_name_map[rot_key] = st_name
                ass_lines.append(f"Style: {st_name},SimHei,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,{rotate_deg:.2f},1,2,0,2,0,0,0,1")
                style_idx +=1
            used_style = style_name_map[rot_key]
            sub_start = safe_float(sub_clip["startTime"])
            sub_end = safe_float(sub_clip["endTime"])
            sx = safe_float(tf.get("x", 0)) * coord_scale_x
            sy = safe_float(tf.get("y", 0)) * coord_scale_y
            s_scale = safe_float(tf.get("scale",1.0))
            text_content = sub_clip.get("text","")
            style = sub_clip.get("style",{})
            base_font_size = safe_float(style.get("fontSize",18))
            real_font_size = base_font_size * s_scale * avg_coord_scale
            fill_color = style.get("fill","#ffffff")
            base_stroke_w = safe_float(style.get("strokeWidth",3))
            real_stroke_w = base_stroke_w * s_scale * avg_coord_scale
            t_start = sec_to_ass_time(sub_start)
            t_end = sec_to_ass_time(sub_end)
            ass_color = hex_to_ass_color(fill_color)
            line_spacing = real_font_size * 0.2
            effect_tag = (
                f"{{\\pos({sx:.2f},{sy:.2f})"
                f"\\bord{real_stroke_w:.1f}"
                f"\\fs{real_font_size:.0f}"
                f"\\1c{ass_color}"
                f"\\fsp{line_spacing:.1f}}}"
            )
            line = f"Dialogue: 0,{t_start},{t_end},{used_style},,0,0,0,,{effect_tag}{text_content}"
            ass_lines.append(line)
        ass_lines.append("")
        ass_lines.append("[Events]")
        ass_lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
        ass_temp_file = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.ass")
        with open(ass_temp_file, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_lines))
        safe_ass_path = ass_temp_file.replace("\\","/")
        # ✅输入源 filter_done，**这里是整个filter_complex唯一一处生成 [outv]**
        filter_complex_segments.append(f"[filter_done]subtitles=filename='{safe_ass_path}'[outv]")
    else:
        # ✅无字幕分支：消费filter_done，**唯一生成 outv**
        filter_complex_segments.append(f"[filter_done]format=yuv420p[outv]")



    # 4. 处理独立音频片段
    audio_in_start_idx = video_in_idx
    for aidx, clip in enumerate(audio_clips):
        src = clip["source"]
        clip_start = safe_float(clip["startTime"])
        trim_start = safe_float(clip["trimStart"])
        trim_end = safe_float(clip["trimEnd"])
        src_dur = trim_end - trim_start
        vol = safe_float(clip.get("volume"),1.0)
        rate = safe_float(clip.get("playbackRate"),1.0)
        input_args.extend([
            "-ss", str(trim_start),
            "-t", str(src_dur),
            "-i", src
        ])
        real_in_idx = audio_in_start_idx + aidx
        atempo_chain = f"atempo={rate}"
        if rate>2.0:
            atempo_chain = "atempo=2,atempo=" + str(rate/2)
        elif rate <0.5:
            atempo_chain = "atempo=0.5,atempo=" + str(rate*2)
        tag = f"extra_aud_{aidx}"
        f_a = (
            f"[{real_in_idx}:a]"
            f"{atempo_chain},volume={vol},"
            f"adelay={int(clip_start*1000)}|{int(clip_start*1000)}[{tag}]"
        )
        filter_complex_segments.append(f_a)
        audio_mix_inputs.append(tag)

    has_audio = bool(len(audio_mix_inputs) > 0)
    if has_audio:
        # 多输入滤镜标签用 [a][b][c] 格式，不能用逗号
        inputs_str = "][".join(audio_mix_inputs)
        filter_complex_segments.append(f"[{inputs_str}]amix=inputs={len(audio_mix_inputs)}:duration=longest[outa]")

    # 5. 组装命令
    full_filter = ";".join(filter_complex_segments)
    cmd = [
        "ffmpeg",
        *input_args,
        "-filter_complex", full_filter,
        "-map", "[outv]",
    ]
    if has_audio:
        cmd.extend(["-map","[outa]"])
    cmd.extend([
        "-r", str(fps),
        "-c:v", codec,
        "-t", str(total_output_duration),
        "-y",
        out_path
    ])

    print("==== ffmpeg cmd ====")
    print(" ".join(cmd))
    print("==== filter_complex ====")
    print(full_filter)


    print("==================="+task_id)

    task_store[task_id] = {
        "taskId": task_id,
        "status": "pending",
        "progress": 0,
        "downloadUrl": "",
        "errorMsg": "",
        "create_ts": time.time()
    }
    t = threading.Thread(target=background_ffmpeg_task, args=(task_id, cmd, out_path, total_output_duration), daemon=True)
    t.start()
    return {
        "success": True,
        "taskId": task_id,
        "msg": "渲染任务已提交，请轮询状态接口查询进度"
    }




@app.get("/api/export/status")
async def get_export_status(taskId: str):
    """查询渲染任务进度"""
    task = task_store.get(taskId)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {
        "success": True,
        "taskId": task["taskId"],
        "status": task["status"], # pending / running / finished / failed
        "progress": task["progress"],
        "downloadUrl": task["downloadUrl"],
        "errorMsg": task["errorMsg"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8095)