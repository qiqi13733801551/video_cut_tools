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
    ratioW: Optional[float] = None  # 新增：画布比例宽
    ratioH: Optional[float] = None  # 新增：画布比例高

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
    # 后缀为空时，通过文件头识别常见图片/视频格式兜底
    if not suffix:
        header = await mediaFile.read(12)
        await mediaFile.seek(0)
        if header.startswith(b'\xff\xd8\xff'):
            suffix = '.jpg'
        elif header.startswith(b'\x89PNG\r\n\x1a\n'):
            suffix = '.png'
        elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
            suffix = '.gif'
        elif header.startswith(b'\x1aE\xdf\xa3'):
            suffix = '.webp'
        else:
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
    # 分辨率基准高度映射
    RESOLUTION_HEIGHT = {
        "1080p": 1080,
        "720p": 720,
        "2k": 1440,
        "540p": 540,
        "480p": 480,
    }

    if export_opt.resolution == "original":
        # 原始分辨率逻辑不变
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
        base = RESOLUTION_HEIGHT.get(export_opt.resolution, 1080)
        ratio_w = export_opt.ratioW
        ratio_h = export_opt.ratioH

        if ratio_w is not None and ratio_h is not None and ratio_h > 0:
            r = ratio_w / ratio_h
            if r >= 1.0:
                # 横屏：宽高比 >=1，以高度为基准
                h = base
                w = int(h * r)
            else:
                # 竖屏：宽高比 <1，以宽度为基准
                w = base
                h = int(w / r)
            # h264要求宽高必须偶数
            if w % 2 != 0:
                w += 1
            if h % 2 != 0:
                h += 1
        else:
            w, h = RESOLUTION_MAP.get(export_opt.resolution, (1920, 1080))



    codec = export_opt.codec

    # 坐标换算比例
    coord_scale_x = w / PREVIEW_CANVAS_WIDTH
    coord_scale_y = h / PREVIEW_CANVAS_HEIGHT
    #avg_coord_scale = (coord_scale_x + coord_scale_y) / 2.0
    input_args = []
    filter_complex_segments = []
    audio_mix_inputs = []
    video_in_idx = 0

    # ========== 修改1：基底改为纯黑不透明背景 ==========
    base_seg = (
        f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration},"
        f"format=yuva420p,fps={fps},settb=1/{fps}[base]"
    )
    filter_complex_segments.append(base_seg)

    # ========== 重构：按轨道分离处理（主序列 + 叠加图层） ==========
    # 1. 分离主序列轨道、叠加视频轨道
    main_sequence_track = None
    overlay_video_tracks = []
    for track in tracks:
        if not track.get("visible", True):
            continue
        if track["type"] != "video":
            continue
        if track.get("mainTrack") and main_sequence_track is None:
            main_sequence_track = track
        else:
            overlay_video_tracks.append(track)
    # 叠加轨道按order升序（层级从下到上）
    overlay_video_tracks.sort(key=lambda t: safe_float(t.get("order", 0)))

    if not main_sequence_track and len(overlay_video_tracks) == 0:
        raise HTTPException(status_code=400, detail="至少需要一条视频片段")

    global_input_idx = 0  # 全局视频/图片输入索引
    all_track_audio_tags = []  # 收集所有视频轨道的音频流tag

    # ========== 单轨道内部处理通用函数 ==========
    def process_track_clips(track_clips, track_transitions, prefix):
        nonlocal global_input_idx
        clips_sorted = sorted(track_clips, key=lambda c: safe_float(c["startTime"]))
        layer_tags = []
        aud_items = []
        prev_end_time = 0.0

        for idx, clip in enumerate(clips_sorted):
            clip_start = safe_float(clip["startTime"])
            clip_end = safe_float(clip["endTime"])
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
            scale_val = safe_float(transform.get("scale"), 1.0)
            vol = safe_float(clip.get("volume"), 1.0)
            is_image = clip.get("sourceType") == "image"
            src = clip["source"]

            # ---------- 间隙：黑帧垫片 + 静音音频垫片 ----------
            pad_duration = clip_start - prev_end_time
            pad_v_tag = ""
            pad_a_tag = ""
            if pad_duration > 0.001:
                pad_v_tag = f"{prefix}_pad_v_{idx}"
                pad_a_tag = f"{prefix}_pad_a_{idx}"
                filter_complex_segments.append(
                    f"color=c=black:size={w}x{h}:rate={fps}:d={pad_duration},format=yuva420p[{pad_v_tag}]"
                )
                filter_complex_segments.append(
                    f"aevalsrc=0:sample_rate=44100:channel_layout=stereo:d={pad_duration}[{pad_a_tag}]"
                )
                aud_items.append((pad_a_tag, {"endTime": prev_end_time + pad_duration}))

            # ---------- 输入源 ----------
            if is_image:
                input_args.extend([
                    "-loop", "1", "-t", str(src_duration),
                    "-framerate", str(fps), "-i", src
                ])
            else:
                input_args.extend(["-ss", str(trim_start), "-i", src])
            in_idx = global_input_idx
            global_input_idx += 1

            # ---------- 调色参数 ----------
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

            # ---------- 尺寸适配计算：直接基于输出画布等比contain ----------
            natural_w = safe_float(clip.get("naturalWidth"), 1920)
            natural_h = safe_float(clip.get("naturalHeight"), 1080)
            r1 = natural_w / natural_h  # 素材宽高比
            canvas_r = w / h  # 输出画布宽高比
            # 等比适配输出画布，1倍scale下的宽度
            if r1 > canvas_r:
                base_w = w  # 素材更宽，宽度撑满画布
            else:
                base_w = h * r1  # 素材更高，高度撑满画布
            # 应用transform.scale缩放系数，得到最终输出宽度
            out_w = base_w * scale_val


            # ---------- 原始视频流处理 ----------
            raw_tag = f"{prefix}_raw_{idx}"
            seg_raw = (
                f"[{in_idx}:v]"
                f"trim=duration={src_duration},setpts=PTS-STARTPTS,"
                f"setpts=PTS/{rate},"
                f"colorchannelmixer=rr={b}:gg={b}:bb={b},"
                f"eq=contrast={contrast}:saturation={saturation},"
                f"colorchannelmixer=rr={rr_temp}:gg=1.0:bb={bb_temp},"
                f"colorchannelmixer=rr={mix_r}:gg={mix_g}:bb={mix_b},"
                f"vignette=a={vignette*2.2},"
                f"scale={out_w}:-1,"
                f"fps={fps},"
                f"format=yuva420p,"
                f"colorchannelmixer=aa={opacity}"
                f"[{raw_tag}]"
            )
            filter_complex_segments.append(seg_raw)
            # ---------- 画布位置对齐：中心点表达式自动居中 ----------
            center_x = safe_float(transform.get("x", 0.0)) * coord_scale_x
            center_y = safe_float(transform.get("y", 0.0)) * coord_scale_y
            layer_duration = src_duration / rate
            canvas_tag = f"{prefix}_canvas_{idx}"
            layer_tag = f"{prefix}_layer_{idx}"
            seg_layer = (
                f"color=c=black@0:size={w}x{h}:rate={fps}:d={layer_duration}[{canvas_tag}];"
                f"[{canvas_tag}][{raw_tag}]overlay=x='{center_x}-w/2':y='{center_y}-h/2':shortest=0:repeatlast=0,"
                f"format=yuva420p,fps={fps}[{layer_tag}]"
            )
            filter_complex_segments.append(seg_layer)


            # ---------- 与前面垫片拼接 ----------
            final_layer_tag = layer_tag
            if pad_duration > 0.001 and pad_v_tag:
                pad_merge_tag = f"{prefix}_padmerge_{idx}"
                filter_complex_segments.append(
                    f"[{pad_v_tag}][{layer_tag}]concat=n=2:v=1:a=0,settb=1/{fps}[{pad_merge_tag}]"
                )
                final_layer_tag = pad_merge_tag
            layer_tags.append(final_layer_tag)

            # ---------- 音频处理 ----------
            has_split_audio = safe_float(clip.get("hasSplitAudio", False), 0)
            if is_image:
                # 图片素材无原生音频，生成等时长静音垫片，保证音画时间轴完全对齐
                aud_tag = f"{prefix}_aud_{idx}"
                filter_complex_segments.append(
                    f"aevalsrc=0:sample_rate=44100:channel_layout=stereo:d={layer_duration}[{aud_tag}]"
                )
                aud_items.append((aud_tag, clip))
            elif not has_split_audio:
                aud_tag = f"{prefix}_aud_{idx}"
                atempo_chain = f"atempo={rate}"
                if rate > 2.0:
                    atempo_chain = "atempo=2,atempo=" + str(rate / 2)
                elif rate < 0.5:
                    atempo_chain = "atempo=0.5,atempo=" + str(rate * 2)
                aud_seg = (
                    f"[{in_idx}:a]"
                    f"atrim=duration={src_duration},asetpts=PTS-STARTPTS,"
                    f"{atempo_chain},"
                    f"volume={vol}"
                    f"[{aud_tag}]"
                )
                filter_complex_segments.append(aud_seg)
                aud_items.append((aud_tag, clip))


            prev_end_time = clip_end

        # ---------- 轨道内部 xf转场 / concat 拼接 ----------
        prev_stream = layer_tags[0]
        first_trim = safe_float(clips_sorted[0]["trimEnd"]) - safe_float(clips_sorted[0]["trimStart"])
        first_rate = safe_float(clips_sorted[0].get("playbackRate"), 1.0)
        acc_time = first_trim / first_rate
        for i in range(1, len(layer_tags)):
            curr_stream = layer_tags[i]
            clip_a = clips_sorted[i-1]
            clip_cur = clips_sorted[i]
            cur_trim = safe_float(clip_cur["trimEnd"]) - safe_float(clip_cur["trimStart"])
            cur_rate = safe_float(clip_cur.get("playbackRate"), 1.0)
            cur_dur = cur_trim / cur_rate

            # 仅匹配本轨道内的转场
            matched_trans = None
            for t_clip in track_transitions:
                if t_clip.get("beforeClipId") == clip_a["id"] and t_clip.get("afterClipId") == clip_cur["id"]:
                    matched_trans = t_clip
                    break

            out_tag = f"{prefix}_join_{i}"
            if matched_trans:
                trans_dur = safe_float(matched_trans.get("transitionDuration", 1.0))
                xfade_filter = TRANS_XFADE_MAP.get(matched_trans.get("transitionType", ""), "fade")
                offset = safe_float(matched_trans["startTime"]) - safe_float(clips_sorted[0]["startTime"])
                cur_len = acc_time
                need_extend = (offset + trans_dur) - cur_len
                if need_extend > 0:
                    prev_ext_tag = f"{prefix}_preext_{i}"
                    filter_complex_segments.append(
                        f"[{prev_stream}]tpad=stop_duration={need_extend}[{prev_ext_tag}]"
                    )
                    prev_used = prev_ext_tag
                else:
                    prev_used = prev_stream
                out_tag = f"{prefix}_xfade_{i}"
                filter_complex_segments.append(
                    f"[{prev_used}][{curr_stream}]xfade=transition={xfade_filter}:duration={trans_dur}:offset={offset},settb=1/{fps}[{out_tag}]"
                )
                acc_time = acc_time + cur_dur - trans_dur
            else:
                filter_complex_segments.append(
                    f"[{prev_stream}][{curr_stream}]concat=n=2:v=1:a=0,settb=1/{fps}[{out_tag}]"
                )
                acc_time = acc_time + cur_dur
            prev_stream = out_tag

        # ---------- 轨道内部音频拼接 ----------
        final_aud_tag = None
        if len(aud_items) > 0:
            if len(aud_items) == 1:
                final_aud_tag = aud_items[0][0]
            else:
                prev_a_stream, clip_a = aud_items[0]
                for idx in range(1, len(aud_items)):
                    curr_a_stream, clip_cur = aud_items[idx]
                    matched_trans = None
                    for t_clip in track_transitions:
                        clip_a_id = clip_a.get("id")
                        clip_cur_id = clip_cur.get("id")
                        if clip_a_id and clip_cur_id and t_clip.get("beforeClipId") == clip_a_id and t_clip.get("afterClipId") == clip_cur_id:
                            matched_trans = t_clip
                            break
                    a_out_tag = f"{prefix}_audxfade_{idx}"
                    if matched_trans:
                        trans_dur = safe_float(matched_trans.get("transitionDuration", 1.0))
                        center_point = safe_float(clip_a["endTime"]) - safe_float(clips_sorted[0]["startTime"])
                        T_end = center_point + trans_dur / 2.0
                        pre_extend_tag = f"{prefix}_audpre_{idx}"
                        filter_complex_segments.append(
                            f"[{prev_a_stream}]apad=whole_dur={T_end}[{pre_extend_tag}]"
                        )
                        post_delay_tag = f"{prefix}_audpost_{idx}"
                        filter_complex_segments.append(
                            f"[{curr_a_stream}]adelay=0|0[{post_delay_tag}]"
                        )
                        filter_complex_segments.append(
                            f"[{pre_extend_tag}][{post_delay_tag}]acrossfade=d={trans_dur}:c1=tri:c2=tri[{a_out_tag}]"
                        )
                    else:
                        trans_dur = 0.001
                        filter_complex_segments.append(
                            f"[{prev_a_stream}][{curr_a_stream}]acrossfade=d={trans_dur}:c1=tri:c2=tri[{a_out_tag}]"
                        )
                    prev_a_stream = a_out_tag
                    clip_a = clip_cur
                final_aud_tag = prev_a_stream

        return prev_stream, final_aud_tag

    # ========== 处理主序列轨道 ==========
    if main_sequence_track:
        main_clips = [c for c in main_sequence_track["clips"] if c["type"] == "video"]
        main_trans = [t for t in transition_clips if t.get("trackId") == main_sequence_track["id"]]
        main_v, main_a = process_track_clips(main_clips, main_trans, "main")
        # ✅ 关键修复：主序列叠加到黑色基底上，消费 base 流，避免端口悬空
        main_base_out = "main_base_out"
        filter_complex_segments.append(
            f"[base][{main_v}]overlay=x=0:y=0:shortest=0:repeatlast=0,settb=1/{fps}[{main_base_out}]"
        )
        current_video = main_base_out
        if main_a:
            all_track_audio_tags.append(main_a)
    else:
        # 无主序列轨道时，直接用黑色基底作为当前画面
        current_video = "base"


    # ========== 处理所有叠加图层轨道（画中画） ==========
    for ov_idx, ov_track in enumerate(overlay_video_tracks):
        ov_clips = [c for c in ov_track["clips"] if c["type"] == "video"]
        if not ov_clips:
            continue
        ov_trans = [t for t in transition_clips if t.get("trackId") == ov_track["id"]]
        prefix = f"ov{ov_idx}"
        ov_v, ov_a = process_track_clips(ov_clips, ov_trans, prefix)

        # 叠加轨道整体时间偏移，对齐全局时间轴
        ov_start_time = safe_float(ov_clips[0]["startTime"])
        ov_end_time = max(safe_float(c["endTime"]) for c in ov_clips)

        shifted_v = f"{prefix}_shifted_v"
        filter_complex_segments.append(
            f"[{ov_v}]setpts=PTS+{ov_start_time}/TB[{shifted_v}]"
        )

        # 叠加到主画布
        ov_out = f"{prefix}_out"
        filter_complex_segments.append(
            f"[{current_video}][{shifted_v}]overlay=x=0:y=0:shortest=0:repeatlast=0"
            f":enable='between(t,{ov_start_time},{ov_end_time})'[{ov_out}]"
        )
        current_video = ov_out

        # 音频偏移+收集
        if ov_a:
            shifted_a = f"{prefix}_shifted_a"
            filter_complex_segments.append(
                f"[{ov_a}]asetpts=PTS+{ov_start_time}/TB[{shifted_a}]"
            )
            all_track_audio_tags.append(shifted_a)

    # ========== 输出命名兼容后续逻辑 ==========
    filter_complex_segments.append(f"[{current_video}]format=yuva420p[vid_main]")
    video_in_idx = global_input_idx
    sticker_in_start_idx = video_in_idx


    # -------------------------- 组装混音列表 --------------------------
    audio_mix_inputs = []
    # ======================【无条件执行：贴纸/特效/滤镜/字幕，不要缩进进if】======================
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
        # 贴纸尺寸：直接基于输出画布等比适配
        r1 = natW / natH
        canvas_r = w / h
        if r1 > canvas_r:
            base_w = w
            base_h = w / r1
        else:
            base_h = h
            base_w = h * r1
        out_draw_w = base_w * s_scale
        out_draw_h = base_h * s_scale
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
            scale_w_expr = (
                f"clip( {w} * ((1.0-{intensity:.4f}) + min(max(((t-{t0})/{dur_e})\\,0)\\,1)*{intensity:.4f})\\, 0\\, {w})"
            )
            filter_complex_segments.append(f"[{tag_mask_src}]scale=w='{scale_w_expr}':h={h}:flags=lanczos:eval=frame[{tag_mask_scaled}]")
            filter_complex_segments.append(f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_black_bg2}]")
            filter_complex_segments.append(f"[{tag_black_bg2}][{tag_mask_scaled}]overlay=x='(W-w)/2':y=0:eval=frame:shortest=0[{tag_mask_alpha}]")
            filter_complex_segments.append(f"[{tag_eff}][{tag_mask_alpha}]alphamerge[{tag_fg_alpha}]")
            filter_complex_segments.append(f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_black_bg}]")
            filter_complex_segments.append(f"[{tag_black_bg}][{tag_fg_alpha}]overlay=shortest=0[{tag_fg_alpha}]")
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
            scale_w_expr = (
                f"clip( {w} * (1.0 - ((1.0-{intensity:.4f}) + min(max(((t-{t0})/{dur_e})\\,0)\\,1)*{intensity:.4f}))\\, 0\\, {w})"
            )
            filter_complex_segments.append(f"[{tag_mask_src}]scale=w='{scale_w_expr}':h={h}:flags=lanczos:eval=frame[{tag_mask_scaled}]")
            filter_complex_segments.append(f"color=c=black:size={w}x{h}:rate={fps}:d={total_output_duration}[{tag_black_bg2}]")
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
            sigma = round(intensity * 10.0, 2)
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
            size_scale = h / PREVIEW_CANVAS_HEIGHT
            real_font_size = base_font_size * s_scale * size_scale
            fill_color = style.get("fill","#ffffff")
            base_stroke_w = safe_float(style.get("strokeWidth",3))
            real_stroke_w = base_stroke_w * s_scale * size_scale
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
        filter_complex_segments.append(f"[filter_done]subtitles=filename='{safe_ass_path}'[outv]")
    else:
        filter_complex_segments.append(f"[filter_done]format=yuv420p[outv]")

    # 4. 处理独立音频片段（输入索引 = 视频轨道输入数 + 贴纸输入数）
    audio_in_start_idx = global_input_idx + len(sticker_clips)
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

    # ========== 最终音频混音：所有视频轨道音频 + 独立音频轨道 ==========
    final_audio_tag = None
    has_video_aud = len(all_track_audio_tags) > 0
    has_extra_aud = len(audio_mix_inputs) > 0

    if has_video_aud and has_extra_aud:
        all_aud = all_track_audio_tags + audio_mix_inputs
        inputs_str = "][".join(all_aud)
        filter_complex_segments.append(f"[{inputs_str}]amix=inputs={len(all_aud)}:duration=longest[outa]")
        final_audio_tag = "outa"
    elif has_video_aud and not has_extra_aud:
        if len(all_track_audio_tags) == 1:
            final_audio_tag = all_track_audio_tags[0]
        else:
            inputs_str = "][".join(all_track_audio_tags)
            filter_complex_segments.append(f"[{inputs_str}]amix=inputs={len(all_track_audio_tags)}:duration=longest[outa]")
            final_audio_tag = "outa"
    elif not has_video_aud and has_extra_aud:
        inputs_str = "][".join(audio_mix_inputs)
        filter_complex_segments.append(f"[{inputs_str}]amix=inputs={len(audio_mix_inputs)}:duration=longest[outa]")
        final_audio_tag = "outa"


    # 5. 组装命令
    full_filter = ";".join(filter_complex_segments)
    # ========== 根据输出格式动态设置音视频编码 =========
    # ========== 根据输出格式动态设置音视频编码 =========
    format_name = export_opt.format.lower()
    user_video_codec = export_opt.codec

    cmd = [
        "ffmpeg",
        *input_args,
        "-filter_complex", full_filter,
        "-map", "[outv]",
    ]
    if final_audio_tag is not None:
        cmd.extend(["-map", f"[{final_audio_tag}]"])

    if format_name == "webm":
        # webm：vp9视频 + libopus正式音频编码器
        cmd.extend(["-c:v", "vp9", "-c:a", "libopus"])
    elif format_name == "mov":
        cmd.extend(["-c:v", user_video_codec, "-c:a", "aac"])
    else:
        # mp4
        cmd.extend(["-c:v", user_video_codec, "-c:a", "aac"])

    cmd.extend([
        "-r", str(fps),
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