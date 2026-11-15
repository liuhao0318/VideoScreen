import argparse
import json
from pathlib import Path
from faster_whisper import WhisperModel

parser = argparse.ArgumentParser()
parser.add_argument("video", help="视频文件路径")
parser.add_argument("--model", default="small")
args = parser.parse_args()

video = Path(args.video).expanduser().resolve()

if not video.is_file():
    raise FileNotFoundError(video)

output_dir = Path.home() / "Applications/VideoScreen/results" / video.stem
output_dir.mkdir(parents=True, exist_ok=True)

print("视频:", video)
print("加载 Whisper 模型:", args.model)

model = WhisperModel(
    args.model,
    device="cuda",
    compute_type="float16"
)

segments, info = model.transcribe(
    str(video),
    language="zh",
    beam_size=5,
    vad_filter=True
)

records = []

with (output_dir / "transcript.txt").open("w", encoding="utf-8") as f:
    for seg in segments:
        item = {
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip()
        }

        records.append(item)

        line = (
            f"[{item['start']:.1f}s - {item['end']:.1f}s] "
            f"{item['text']}"
        )

        print(line, flush=True)
        f.write(line + "\n")

(output_dir / "transcript.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("\n转写完成")
print("输出目录:", output_dir)
print("语音片段数量:", len(records))
