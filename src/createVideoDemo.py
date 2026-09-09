import subprocess
import os

# ===================== 配置参数 =====================
VIDEO_1 = r"D:\tldrawWorkspace\temp_media\e9aa8b7d-29c4-46e8-bc70-3469ff604c5b.mp4"
VIDEO_2 = r"D:\tldrawWorkspace\temp_media\fb5de65a-74d8-4af1-af47-b3ed5ea318fd.mp4"
OUTPUT_PATH = r"D:\tldrawWorkspace\temp_media\output_wipe_left.mp4"

# 转场参数
TRANSITION_TYPE = "wipeleft"
TRANSITION_DURATION = 5
TRANSITION_START = 12.5
CENTER_POINT = 15.0
FADE_HALF = CENTER_POINT - TRANSITION_START  # 2.5

# ===================== 修正后的FFmpeg命令 =====================
cmd = [
    "ffmpeg",
    "-y",
    "-i", VIDEO_1,
    "-i", VIDEO_2,
    "-filter_complex",
    # ---------- 视频流 ----------
    f"[0:v]trim=duration=15,setpts=PTS-STARTPTS[v0];"
    f"[1:v]trim=duration=15,setpts=PTS-STARTPTS[v1];"
    f"[v0][v1]xfade=transition={TRANSITION_TYPE}:duration={TRANSITION_DURATION}:offset={TRANSITION_START}[outv];"
    # ---------- 音频流：setpts 改为 asetpts（音频专用时间戳滤镜） ----------
    f"[0:a]atrim=duration=15,asetpts=PTS-STARTPTS,afade=type=out:start_time={TRANSITION_START}:duration={FADE_HALF}:curve=tri[a0];"
    f"[1:a]atrim=duration=15,asetpts=PTS-STARTPTS,adelay={int(CENTER_POINT*1000)}|{int(CENTER_POINT*1000)},"
    f"afade=type=in:start_time={CENTER_POINT}:duration={FADE_HALF}:curve=tri[a1];"
    f"[a0][a1]amix=inputs=2:duration=longest[outa]",
    "-map", "[outv]",
    "-map", "[outa]",
    "-c:v", "libx264",
    "-c:a", "aac",
    "-r", "30",
    OUTPUT_PATH
]

# ===================== 执行 =====================
print("执行命令：")
print(" ".join(cmd))
print("\n开始渲染...")

proc = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    encoding="utf-8"
)

if proc.returncode == 0:
    print(f"\n渲染完成！输出文件：{OUTPUT_PATH}")
    print(f"文件大小：{os.path.getsize(OUTPUT_PATH)/1024/1024:.2f} MB")
else:
    print("\n渲染失败！错误信息：")
    print(proc.stderr)
