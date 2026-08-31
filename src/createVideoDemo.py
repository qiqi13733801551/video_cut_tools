import subprocess

filter_complex = (
    r"color=c=black:size=1920x1080:rate=30:d=14,format=yuva420p[base];"
    r"[0:v]trim=duration=14,setpts=PTS-STARTPTS,fps=30,format=yuva420p[v0];"
    r"[0:a]atrim=duration=14,asetpts=PTS-STARTPTS,volume=1.0[outa];"
    r"[base][v0]overlay=x=20:y=0:shortest=0:repeatlast=0[vo0];"
    r"[vo0]format=yuv420p[img];"
    r"[img]dblur=angle=90:radius=12:enable='between(t\,0\,8.85)'[blurred];"
    r"[blurred]subtitles=filename='./temp_media/ba4639c2-88f3-4778-b4ac-1852581f6d0c.ass'[outv]"
)


cmd_list = [
    "ffmpeg",
    "-ss", "0.0",
    "-i", r"D:\tldrawWorkspace\temp_media\810c7c1f-652f-4e23-8a7d-90a3c09f57c8.mp4",
    "-filter_complex", filter_complex,
    "-map", "[outv]",
    "-map", "[outa]",
    "-r", "30",
    "-c:v", "libx264",
    "-c:a", "aac",
    "-t", "14",
    "-y",
    r"D:\tldrawWorkspace\temp_media\test1.mp4"
]

result = subprocess.run(
    cmd_list,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace"
)
print("stdout:\n", result.stdout)
print("stderr:\n", result.stderr)
print(f"returncode = {result.returncode}")
