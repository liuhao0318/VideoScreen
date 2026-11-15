from faster_whisper import WhisperModel
from pathlib import Path
import os

video = Path.home() / (
    "Applications/DouyinLiveRecorder/downloads/"
    "抖音直播/董路/董路_2026-11-03_18-48-55_000.mp4"
)

if not video.exists():
    raise FileNotFoundError(video)

print("正在加载 Whisper GPU 模型...")

model = WhisperModel(
    "small",
    device="cuda",
    compute_type="float16"
)

print("开始中文语音识别...")

segments, info = model.transcribe(
    str(video),
    language="zh",
    beam_size=5,
    vad_filter=True
)

output = Path("transcript.txt")

with output.open("w", encoding="utf-8") as f:
    for seg in segments:
        line = (
            f"[{seg.start:.1f}s - {seg.end:.1f}s] "
            f"{seg.text.strip()}"
        )
        print(line)
        f.write(line + "\n")

print(f"\n识别完成，结果保存到: {output.resolve()}")
