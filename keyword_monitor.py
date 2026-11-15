import json
import argparse
from pathlib import Path

BASE = Path.home() / "Applications/VideoScreen"

parser = argparse.ArgumentParser()
parser.add_argument("transcript", help="转写JSON路径")
args = parser.parse_args()

config = json.loads(
    (BASE / "config.json").read_text(encoding="utf-8")
)

keywords = config["keywords"]
aliases = config.get("keyword_aliases", {})

records = json.loads(
    Path(args.transcript).read_text(encoding="utf-8")
)

# 关键词命中前后各90秒
CONTEXT_SECONDS = 90

matches = []

for seg in records:
    text = seg.get("text", "")
    found = []

    for keyword in keywords:
        variants = aliases.get(keyword, [keyword])

        # 无论是否配置别名，都保留原关键词
        variants = list(set([keyword] + variants))

        if any(v.casefold() in text.casefold() for v in variants):
            found.append(keyword)

    if not found:
        continue

    start = max(0, seg["start"] - CONTEXT_SECONDS)
    end = seg["end"] + CONTEXT_SECONDS

    context = [
        item for item in records
        if item["end"] >= start and item["start"] <= end
    ]

    matches.append({
        "start": seg["start"],
        "end": seg["end"],
        "keywords": found,
        "text": text,
        "context_start": context[0]["start"] if context else start,
        "context_end": context[-1]["end"] if context else end,
        "context": context
    })

output = Path(args.transcript).parent / "keyword_monitor.json"

output.write_text(
    json.dumps(matches, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f"监控关键词数量：{len(keywords)}")
print(f"命中语音片段数量：{len(matches)}")

for item in matches:
    seconds = int(item["start"])
    timestamp = (
        f"{seconds // 3600:02d}:"
        f"{seconds // 60 % 60:02d}:"
        f"{seconds % 60:02d}"
    )

    print(
        f"[{timestamp}] "
        f"{','.join(item['keywords'])} | "
        f"{item['text']}"
    )

print(f"\n结果保存：{output}")
