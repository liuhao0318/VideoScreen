#!/usr/bin/env python3
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIPS = ROOT / "clips"
DB = ROOT / "videos_v2.db"
QUEUE = ROOT / "publish_queue.json"
MANIFEST = ROOT / "clip_manifest.json"


def duration(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True,
        )
        return round(float(result.stdout.strip()), 2)
    except Exception:
        return ""


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    sources = [row[0] for row in conn.execute("SELECT path FROM videos")]
    conn.close()
    source_by_hash = {
        hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]: path
        for path in sources
    }
    try:
        queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception:
        queue = []
    queue_by_output = {
        str(Path(item.get("output", "")).resolve()): item
        for item in queue if item.get("output")
    }
    rows = []
    for output in sorted(CLIPS.rglob("*.mp4")):
        key = str(output.resolve())
        old = queue_by_output.get(key, {})
        folder_hash = output.parent.name.rsplit("_", 1)[-1]
        rows.append({
            "video": source_by_hash.get(folder_hash, ""),
            "start": "",
            "end": "",
            "duration": old.get("duration", "") or duration(output),
            "score": old.get("score", ""),
            "title": old.get("title", "") or output.stem.split("_", 1)[-1],
            "topics": "",
            "matched_terms": "",
            "summary": "",
            "reason": "",
            "output": key,
        })
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(MANIFEST)
    print(f"已恢复 {len(rows)} 个成片记录：{MANIFEST}")


if __name__ == "__main__":
    main()
