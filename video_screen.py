import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BASE = Path.home() / "Applications/VideoScreen"
ROOT_LOCAL = BASE / "live_recorder/downloads"
ROOT_EXT = Path.home() / "Applications/DouyinLiveRecorder/downloads"
ROOT = ROOT_LOCAL if ROOT_LOCAL.is_dir() else ROOT_EXT
RESULTS = BASE / "results"
DB_PATH = BASE / "videos_v2.db"
CONFIG_PATH = BASE / "config.json"

EXTS = {".mp4", ".ts", ".mkv", ".flv"}
STABLE_SECONDS = 300


class NoAudioStreamError(RuntimeError):
    """录像文件不包含音频流，无法提取语音。"""


def connect():
    BASE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            path TEXT PRIMARY KEY,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            status TEXT NOT NULL,
            transcript_path TEXT,
            keyword_config_hash TEXT,
            discovered_at REAL NOT NULL,
            processed_at REAL,
            error TEXT
        )
    """)
    db.commit()
    return db


def result_dir(path):
    path = Path(path)
    rel = None
    for r in (ROOT_LOCAL, ROOT_EXT, ROOT):
        try:
            rel = str(path.relative_to(r))
            break
        except (ValueError, Exception):
            pass
    if rel is None:
        rel = str(path)
    key = hashlib.sha256(rel.encode()).hexdigest()[:12]
    return RESULTS / (path.stem + "_" + key)


def load_config():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data.get("keywords"), list):
        raise ValueError("config.json 缺少 keywords 列表")
    return data


def keyword_hash(config):
    relevant = {
        "keywords": config["keywords"],
        "keyword_aliases": config.get("keyword_aliases", {}),
        "context_seconds": config.get("context_seconds", 90)
    }
    encoded = json.dumps(
        relevant, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scan(db):
    roots_to_scan = [r for r in (ROOT_LOCAL, ROOT_EXT) if r.is_dir()]
    if not roots_to_scan:
        if ROOT.is_dir():
            roots_to_scan = [ROOT]
        else:
            raise FileNotFoundError(ROOT)

    added = changed = missing = 0
    discovered = set()

    for r in roots_to_scan:
        for path in r.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in EXTS:
                continue

            try:
                stat = path.stat()
            except OSError:
                continue

            name = str(path.resolve())
            discovered.add(name)
            row = db.execute(
                "SELECT size,mtime_ns,status FROM videos WHERE path=?",
                (name,)
            ).fetchone()

            if row is None:
                db.execute("""
                    INSERT INTO videos
                    (path,size,mtime_ns,status,discovered_at)
                    VALUES (?,?,?,'waiting',?)
                """, (name, stat.st_size, stat.st_mtime_ns, time.time()))
                added += 1

            elif (row["size"], row["mtime_ns"]) != (
                stat.st_size, stat.st_mtime_ns
            ):
                db.execute("""
                    UPDATE videos
                    SET size=?,mtime_ns=?,status='waiting',
                        transcript_path=NULL,
                        keyword_config_hash=NULL,
                        processed_at=NULL,error=NULL
                    WHERE path=?
                """, (stat.st_size, stat.st_mtime_ns, name))
                changed += 1
            elif row["status"] == "source_deleted":
                db.execute("""
                    UPDATE videos
                    SET status='waiting',error=NULL
                    WHERE path=?
                """, (name,))
                changed += 1

    for row in db.execute(
        "SELECT path,status FROM videos WHERE status!='source_deleted'"
    ).fetchall():
        if row["path"] not in discovered and not Path(row["path"]).is_file():
            db.execute("""
                UPDATE videos
                SET status='source_deleted',error=NULL
                WHERE path=?
            """, (row["path"],))
            missing += 1

    db.commit()
    print(
        f"扫描完成：新增 {added}，变化 {changed}，缺失清理 {missing}",
        flush=True,
    )


def probe(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type",
            "-of", "json", str(path)
        ],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "ffprobe失败")

    info = json.loads(result.stdout or "{}")
    fmt = info.get("format") or {}
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise RuntimeError("视频时长无效")

    streams = info.get("streams") or []
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise NoAudioStreamError("该录像文件不包含音频流（无音轨，纯画面无法转写）")
    return duration


def get_sensevoice_cmd():
    """获取 SenseVoice 专用 Python 解释器或 Conda 执行命令"""
    # 1. 优先直接使用 sensevoice 虚拟环境的 Python 解释器（最快、最稳定，完全不依赖 PATH 中的 conda）
    sensevoice_python = Path("/home/ubuntu/miniconda3/envs/sensevoice/bin/python")
    if sensevoice_python.is_file() and os.access(sensevoice_python, os.X_OK):
        return [str(sensevoice_python)]

    # 2. 备选：尝试 conda 绝对路径
    conda_bin = Path("/home/ubuntu/miniconda3/bin/conda")
    if conda_bin.is_file() and os.access(conda_bin, os.X_OK):
        return [str(conda_bin), "run", "--no-capture-output", "-n", "sensevoice", "python"]

    # 3. 备选：从 PATH 中查找 conda
    which_conda = shutil.which("conda")
    if which_conda:
        return [which_conda, "run", "--no-capture-output", "-n", "sensevoice", "python"]

    return ["python"]


def transcribe(path, output):
    output.mkdir(parents=True, exist_ok=True)

    cmd = get_sensevoice_cmd() + [
        "-u",
        str(BASE / "transcribe_sensevoice.py"),
        str(path),
        "--output",
        str(output)
    ]

    proc = subprocess.run(
        cmd,
        cwd=BASE,
    )
    if proc.returncode == 2:
        raise NoAudioStreamError("该录像文件不包含音频流（无音轨，纯画面无法转写）")
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    transcript = output / "transcript.json"

    if not transcript.is_file():
        raise RuntimeError("SenseVoice 未生成 transcript.json")

    return transcript


def keyword_search(transcript_path, output, config):
    records = json.loads(
        transcript_path.read_text(encoding="utf-8")
    )

    keywords = config["keywords"]
    aliases = config.get("keyword_aliases", {})
    context_seconds = config.get("context_seconds", 90)

    hits = []

    for seg in records:
        text = str(seg.get("text", ""))
        found = []

        for keyword in keywords:
            variants = [keyword] + aliases.get(keyword, [])
            if any(
                variant and variant.casefold() in text.casefold()
                for variant in variants
            ):
                found.append(keyword)

        if found:
            hits.append({
                "start": seg["start"],
                "end": seg["end"],
                "keywords": found,
                "text": text
            })

    # 将命中点扩展成时间区间，并合并重叠区间
    intervals = []

    for hit in hits:
        start = max(0, hit["start"] - context_seconds)
        end = hit["end"] + context_seconds

        if intervals and start <= intervals[-1]["end"]:
            intervals[-1]["end"] = max(
                intervals[-1]["end"], end
            )
            intervals[-1]["keywords"].update(hit["keywords"])
        else:
            intervals.append({
                "start": start,
                "end": end,
                "keywords": set(hit["keywords"])
            })

    for interval in intervals:
        interval["keywords"] = sorted(interval["keywords"])
        interval["context"] = [
            seg for seg in records
            if seg["end"] >= interval["start"]
            and seg["start"] <= interval["end"]
        ]

    data = {
        "hits": hits,
        "intervals": intervals,
        "hit_count": len(hits)
    }

    temporary = output / "keyword_monitor.json.tmp"
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temporary.replace(output / "keyword_monitor.json")

    return len(hits), len(intervals)


def process(db, limit=None, keywords_only=False, target_path=None):
    config = load_config()
    current_hash = keyword_hash(config)

    rows = db.execute("""
        SELECT * FROM videos
        ORDER BY discovered_at ASC
    """).fetchall()

    pending_tasks = []

    for row in rows:
        path = Path(row["path"])

        if target_path and path.resolve() != Path(target_path).resolve():
            continue

        if not path.is_file():
            continue

        if target_path is None and row["status"] == "no_audio":
            print(
                f"⏭️ 跳过无音轨录像：{path.name}（纯画面无声音，请检查源录像音轨）",
                flush=True,
            )
            continue

        stat = path.stat()

        if (stat.st_size, stat.st_mtime_ns) != (
            row["size"], row["mtime_ns"]
        ):
            age_changed = time.time() - stat.st_mtime
            if age_changed < STABLE_SECONDS:
                print(
                    f"⏳ 跳过录制中的文件：{path.name}（文件仍在持续写入，录完稳定 {STABLE_SECONDS}s 后自动可转写）",
                    flush=True,
                )
            else:
                print(
                    f"⏳ 跳过大小已变化的录像：{path.name}（请先运行“扫描录像”同步最新文件信息）",
                    flush=True,
                )
            continue

        output = result_dir(path)
        transcript = output / "transcript.json"

        # 已有数据库记录优先使用
        if row["transcript_path"]:
            recorded = Path(row["transcript_path"])
            if recorded.is_file():
                transcript = recorded

        needs_transcribe = not transcript.is_file()
        needs_keywords = (
            needs_transcribe
            or row["keyword_config_hash"] != current_hash
            or not (output / "keyword_monitor.json").is_file()
        )

        if keywords_only and needs_transcribe:
            continue

        if not needs_transcribe and not needs_keywords:
            continue

        if needs_transcribe:
            age = time.time() - stat.st_mtime
            if age < STABLE_SECONDS:
                remain = max(1, int(STABLE_SECONDS - age))
                print(
                    f"⏳ 跳过尚未稳定的录像：{path.name}（距上次写入仅 {int(age)}s，需等待 {remain}s 以确认录制结束）",
                    flush=True,
                )
                continue

            try:
                probe(path)
            except NoAudioStreamError as exc:
                print(f"🔇 跳过无音轨录像：{path.name} ({exc})", flush=True)
                db.execute("""
                    UPDATE videos
                    SET status='no_audio', error=?
                    WHERE path=?
                """, (str(exc)[:1000], str(path)))
                db.commit()
                continue
            except Exception as exc:
                print(f"跳过无法读取的视频：{path.name} ({exc})", flush=True)
                continue

        pending_tasks.append((row, path, output, transcript, needs_transcribe))
        if limit is not None and len(pending_tasks) >= limit:
            break

    total_tasks = len(pending_tasks)
    print(f"待处理视频总数：{total_tasks}", flush=True)
    done = 0

    for idx, (row, path, output, transcript, needs_transcribe) in enumerate(pending_tasks, 1):
        pct_start = round((idx - 1) * 100 / max(1, total_tasks))
        print(f"\n[{idx}/{total_tasks}] 处理：{path.name}", flush=True)
        print(f"[PROGRESS] {pct_start}% | 准备处理 [{idx}/{total_tasks}]: {path.name}", flush=True)

        try:
            output.mkdir(parents=True, exist_ok=True)

            if needs_transcribe:
                print("  SenseVoiceSmall 转写...", flush=True)
                transcript = transcribe(path, output)
            else:
                print("  复用已有转写", flush=True)

            print("  关键词检索...", flush=True)

            hits, intervals = keyword_search(
                transcript, output, config
            )

            # 防止视频处理过程中发生变化
            latest = path.stat()
            if (latest.st_size, latest.st_mtime_ns) != (
                row["size"], row["mtime_ns"]
            ):
                raise RuntimeError("源视频已变化，请重新扫描")

            db.execute("""
                UPDATE videos
                SET status='completed',
                    transcript_path=?,
                    keyword_config_hash=?,
                    processed_at=?,
                    error=NULL
                WHERE path=?
            """, (
                str(transcript), current_hash,
                time.time(), str(path)
            ))
            db.commit()

            done += 1
            pct_done = round(idx * 100 / max(1, total_tasks))
            print(
                f"  完成：命中 {hits} 条，"
                f"合并为 {intervals} 个候选区间",
                flush=True
            )
            print(f"[PROGRESS] {pct_done}% | 已完成 [{idx}/{total_tasks}]: {path.name}", flush=True)

        except NoAudioStreamError as exc:
            db.execute("""
                UPDATE videos
                SET status='no_audio', error=?
                WHERE path=?
            """, (str(exc)[:1000], str(path)))
            db.commit()
            print(f"  🔇 无音轨跳过：{exc}", flush=True)

        except Exception as exc:
            db.execute("""
                UPDATE videos
                SET status='failed',error=?
                WHERE path=?
            """, (str(exc)[:1000], str(path)))
            db.commit()
            print(f"  失败：{exc}", flush=True)

    print(f"\n本次成功处理：{done} 个视频", flush=True)


def status(db):
    print("\n视频状态：")
    for row in db.execute("""
        SELECT status,COUNT(*) AS n
        FROM videos GROUP BY status
    """):
        print(f"  {row['status']}: {row['n']}")

    total = db.execute(
        "SELECT COUNT(*) FROM videos"
    ).fetchone()[0]

    print(f"  总计: {total}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["scan", "status", "batch", "keywords"]
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--path", default=None)
    args = parser.parse_args()

    db = connect()

    if args.command == "scan":
        scan(db)
        status(db)
    elif args.command == "status":
        status(db)
    elif args.command == "batch":
        scan(db)
        process(db, limit=args.limit, target_path=args.path)
        status(db)
    elif args.command == "keywords":
        scan(db)
        process(
            db,
            limit=args.limit,
            keywords_only=True,
            target_path=args.path,
        )
        status(db)


if __name__ == "__main__":
    main()
