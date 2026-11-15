import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE_CSV = BASE / "ai_analysis" / "candidates.csv"
FINAL_CSV = BASE / "ai_analysis" / "final_candidates.csv"
FINAL_JSON = BASE / "ai_analysis" / "final_candidates.json"
MANIFEST_JSON = BASE / "clip_manifest.json"
CLIPS_DIR = BASE / "clips"


def resolve_video_path(video_str):
    p = Path(video_str)
    if p.is_file():
        return p
    # 候选备选路径检索
    alternatives = [
        Path.home() / "Applications" / "DouyinLiveRecorder" / "downloads" / p.name,
        Path.home() / "Applications" / "VideoScreen" / "videos" / p.name,
        BASE / "videos" / p.name,
    ]
    for alt in alternatives:
        if alt.is_file():
            return alt
    # 递归搜索 DouyinLiveRecorder/downloads 目录
    dls = Path.home() / "Applications" / "DouyinLiveRecorder" / "downloads"
    if dls.is_dir():
        for match in dls.rglob(p.name):
            if match.is_file():
                return match
    return p


def update_manifest(rows):
    try:
        existing = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        existing = []
    by_output = {
        str(Path(item.get("output", "")).resolve()): item
        for item in existing
        if item.get("output")
    }
    for row in rows:
        output = Path(row.get("output", ""))
        if output.is_file() and output.stat().st_size > 50 * 1024:
            by_output[str(output.resolve())] = {
                **row,
                "output": str(output.resolve()),
            }
    temporary = MANIFEST_JSON.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(list(by_output.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(MANIFEST_JSON)


def get_video_duration(video):
    # 优先 probe format duration
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video)
            ],
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=15
        )
        val = result.stdout.strip()
        if val:
            return float(val)
    except Exception:
        pass

    # 回退 probe stream duration
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video)
            ],
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=15
        )
        val = result.stdout.strip()
        if val:
            return float(val)
    except Exception:
        pass

    return 0.0


def safe_name(text, limit=70):
    text = re.sub(r'[\\/:*?"<>|\r\n]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return (text or "未命名片段")[:limit]


def expand_interval(start, end, total, minimum, padding):
    start = max(0.0, start - padding)
    end = min(total, end + padding)

    missing = minimum - (end - start)
    if missing <= 0:
        return start, end

    left_space = start
    right_space = total - end

    left_add = min(left_space, missing / 2)
    start -= left_add
    missing -= left_add

    right_add = min(right_space, missing)
    end += right_add
    missing -= right_add

    if missing > 0:
        extra_left = min(start, missing)
        start -= extra_left

    return max(0.0, start), min(total, end)


def merge_overlapping(items, threshold):
    if not items:
        return []

    items.sort(key=lambda x: (x["start"], x["end"]))
    result = [items[0]]

    for item in items[1:]:
        current = result[-1]
        overlap = current["end"] - item["start"]

        if overlap >= threshold:
            current["start"] = min(current["start"], item["start"])
            current["end"] = max(current["end"], item["end"])
            current["score"] = max(current["score"], item["score"])

            for key in (
                "titles", "topics", "summaries",
                "reasons", "matched_terms"
            ):
                for value in item[key]:
                    if value and value not in current[key]:
                        current[key].append(value)
        else:
            result.append(item)

    return result


def split_long(item, maximum):
    duration = item["end"] - item["start"]

    if duration <= maximum:
        return [item]

    count = math.ceil(duration / maximum)
    part_duration = duration / count
    result = []

    for index in range(count):
        part = {
            key: list(value) if isinstance(value, list) else value
            for key, value in item.items()
        }
        part["start"] = item["start"] + index * part_duration
        part["end"] = (
            item["end"]
            if index == count - 1
            else item["start"] + (index + 1) * part_duration
        )
        result.append(part)

    return result


def prepare_candidates(minimum, maximum, padding, merge_threshold):
    if not SOURCE_CSV.is_file():
        raise FileNotFoundError(f"候选清单不存在：{SOURCE_CSV}")

    with SOURCE_CSV.open(
        encoding="utf-8-sig",
        newline=""
    ) as f:
        source_rows = list(csv.DictReader(f))

    grouped = defaultdict(list)
    for row in source_rows:
        grouped[row["video"]].append(row)

    final_rows = []

    for video_string, rows in grouped.items():
        video = resolve_video_path(video_string)

        if not video.is_file():
            print(f"视频不存在，跳过：{video_string}", flush=True)
            continue

        total = get_video_duration(video)
        if total <= 0:
            print(f"无法读取视频时长，跳过：{video}", flush=True)
            continue
        expanded = []

        for row in rows:
            start = max(0.0, float(row["start"]))
            end = min(total, float(row["end"]))

            if end <= start:
                continue

            start, end = expand_interval(
                start=start,
                end=end,
                total=total,
                minimum=minimum,
                padding=padding
            )

            expanded.append({
                "video": str(video),
                "start": start,
                "end": end,
                "score": int(float(row["score"])),
                "titles": [row.get("title", "")],
                "topics": [row.get("topic", "")],
                "summaries": [row.get("summary", "")],
                "reasons": [row.get("reason", "")],
                "matched_terms": [
                    value.strip()
                    for value in row.get(
                        "matched_terms", ""
                    ).split("、")
                    if value.strip()
                ]
            })

        merged = merge_overlapping(expanded, merge_threshold)

        bounded = []
        for item in merged:
            bounded.extend(split_long(item, maximum))

        video_hash = hashlib.sha256(
            str(video).encode("utf-8")
        ).hexdigest()[:10]

        output_dir = CLIPS_DIR / (
            safe_name(video.stem, 60) + "_" + video_hash
        )

        for index, item in enumerate(bounded, 1):
            title = (
                item["titles"][0]
                if item["titles"]
                else "未命名片段"
            )

            output = output_dir / (
                f"{index:02d}_{safe_name(title)}.mp4"
            )

            final_rows.append({
                "video": str(video),
                "start": round(item["start"], 2),
                "end": round(item["end"], 2),
                "duration": round(item["end"] - item["start"], 2),
                "score": item["score"],
                "title": title,
                "topics": "；".join(item["topics"]),
                "matched_terms": "、".join(
                    item["matched_terms"]
                ),
                "source_titles": "；".join(item["titles"]),
                "summary": "；".join(item["summaries"]),
                "reason": "；".join(item["reasons"]),
                "output": str(output)
            })

    final_rows.sort(key=lambda x: (x["video"], x["start"]))

    fields = [
        "video", "start", "end", "duration", "score",
        "title", "topics", "matched_terms",
        "source_titles",
        "summary", "reason", "output"
    ]

    FINAL_CSV.parent.mkdir(parents=True, exist_ok=True)

    with FINAL_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(final_rows)

    FINAL_JSON.write_text(
        json.dumps(final_rows, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return final_rows


def cut_single_clip(
    source: Path,
    output: Path,
    start: float,
    duration: float,
    overwrite: bool = False,
    mode: str = "auto"
):
    """
    剪辑单个成片：
    - auto: 优先极速无损流拷贝 (-c copy，0.1s级极速)，失败自动平滑回退到快速重编码 (veryfast，限线程防卡死)
    - copy: 纯极速流拷贝
    - transcode: 快速重编码 (libx264 veryfast)
    
    返回 (status, method, cost_seconds, size_mb, error_message)
    status: "skipped" | "completed" | "failed"
    """
    if output.is_file():
        file_size = output.stat().st_size
        if file_size > 50 * 1024 and not overwrite:
            return "skipped", "exist", 0.0, file_size / (1024 * 1024), ""
        # 小于等于 50KB 属于历史异常中断损坏文件，予以清除重剪
        try:
            output.unlink()
        except OSError:
            pass

    output.parent.mkdir(parents=True, exist_ok=True)
    # 使用带 PID 的独立临时文件，杜绝写入中断残留损坏文件
    temp_output = output.with_name(f"{output.stem}.part_{os.getpid()}_{int(time.time()*1000)%100000}.mp4")
    if temp_output.exists():
        try:
            temp_output.unlink()
        except OSError:
            pass

    # 1. 优先尝试极速无损流拷贝 (-c copy，0.1s~0.3s级完成)
    if mode in ("auto", "copy"):
        start_time = time.time()
        cmd_copy = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-fflags", "+genpts+discardcorrupt",
            "-ss", f"{start:.2f}",
            "-i", str(source),
            "-t", f"{duration:.2f}",
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            str(temp_output)
        ]
        try:
            res = subprocess.run(
                cmd_copy,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45
            )
            if res.returncode == 0 and temp_output.is_file() and temp_output.stat().st_size > 50 * 1024:
                temp_output.replace(output)
                cost = time.time() - start_time
                size_mb = output.stat().st_size / (1024 * 1024)
                return "completed", "copy", cost, size_mb, ""
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        finally:
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except OSError:
                    pass

    # 2. 回退到快速高质量重编码 (libx264 veryfast，严格限制线程数防打满CPU导致系统卡死)
    if mode in ("auto", "transcode"):
        start_time = time.time()
        cmd_transcode = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-fflags", "+genpts+discardcorrupt",
            "-ss", f"{start:.2f}",
            "-i", str(source),
            "-t", f"{duration:.2f}",
            "-map", "0:v:0",
            "-map", "0:a?",
            "-sn", "-dn",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-threads", "4",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(temp_output)
        ]
        max_timeout = max(60, int(duration * 2))
        err_msg = ""
        try:
            res = subprocess.run(
                cmd_transcode,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max_timeout
            )
            if res.returncode == 0 and temp_output.is_file() and temp_output.stat().st_size > 50 * 1024:
                temp_output.replace(output)
                cost = time.time() - start_time
                size_mb = output.stat().st_size / (1024 * 1024)
                return "completed", "transcode", cost, size_mb, ""
            else:
                err_msg = res.stderr.decode("utf-8", errors="replace")[-300:]
        except subprocess.TimeoutExpired:
            err_msg = f"转码超过 {max_timeout} 秒已安全超时熔断"
        except Exception as e:
            err_msg = str(e)
        finally:
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except OSError:
                    pass
        return "failed", "none", time.time() - start_time, 0.0, err_msg

    return "failed", "none", 0.0, 0.0, "流拷贝失败且未启用转码回退"


def cut_videos(rows, overwrite=False, mode="auto", limit=0):
    total_candidates = len(rows)
    if limit > 0:
        rows = rows[:limit]
        print(f"📌 设置了剪辑上限，仅处理前 {len(rows)} 个候选 (候选总数: {total_candidates})", flush=True)

    completed = 0
    skipped = 0
    failed = 0
    copy_count = 0
    transcode_count = 0
    total_start = time.time()

    print("\n" + "=" * 55, flush=True)
    print(f"🎬 开始执行 FFmpeg 批量精准剪辑任务 (目标: {len(rows)} 个切片)", flush=True)
    print(f"⚙️ 运行策略: 模式={mode.upper()} | 优先极速无损流拷贝(毫秒级) | 异常超时安全熔断", flush=True)
    print("=" * 55 + "\n", flush=True)

    total_rows = max(1, len(rows))
    for index, row in enumerate(rows, 1):
        source = Path(row["video"])
        output = Path(row["output"])
        dur = float(row.get("duration", 0))
        title = row.get("title", "未命名片段")

        pct_cur = int((index - 1) * 100 / total_rows)
        print(f"[PROGRESS] {pct_cur}% | 正在剪辑 [{index}/{len(rows)}]: {title[:26]}", flush=True)
        print(
            f"[{index}/{len(rows)}] 正在处理: {title[:32]} "
            f"({row['start']:.1f}s - {row['end']:.1f}s, 时长 {dur:.0f}s)...",
            flush=True
        )

        status, method, cost, size_mb, err = cut_single_clip(
            source=source,
            output=output,
            start=float(row["start"]),
            duration=dur,
            overwrite=overwrite,
            mode=mode
        )

        pct_after = int(index * 100 / total_rows)
        if status == "skipped":
            print(f"    ⏩ 已存在有效成片 ({size_mb:.1f} MB)，直接跳过", flush=True)
            skipped += 1
        elif status == "completed":
            completed += 1
            if method == "copy":
                copy_count += 1
                print(f"    ⚡ [极速流拷贝完成] 耗时 {cost:.2f}s | 大小 {size_mb:.1f} MB | {output.name}", flush=True)
            else:
                transcode_count += 1
                print(f"    🎬 [快速重编码完成] 耗时 {cost:.2f}s | 大小 {size_mb:.1f} MB | {output.name}", flush=True)
        else:
            failed += 1
            print(f"    ❌ 剪辑跳过/失败: {err or '未知原因'}", flush=True)
        print(f"[PROGRESS] {pct_after}% | 已处理 [{index}/{len(rows)}]: {title[:26]}", flush=True)

    total_cost = time.time() - total_start
    print("\n" + "=" * 55, flush=True)
    print("📊 剪辑成片完成汇报：", flush=True)
    print(f"  • 成功完成: {completed} 部 (⚡极速流拷贝: {copy_count}, 🎬快速重编码: {transcode_count})", flush=True)
    print(f"  • 已有跳过: {skipped} 部", flush=True)
    print(f"  • 失败/熔断: {failed} 部", flush=True)
    print(f"  • 总计耗时: {total_cost:.1f} 秒 (平均单片: {total_cost/max(1, completed+skipped):.2f}s)", flush=True)
    print("=" * 55 + "\n", flush=True)

    update_manifest(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-duration", type=float, default=60)
    parser.add_argument("--max-duration", type=float, default=600)
    parser.add_argument("--padding", type=float, default=8)
    parser.add_argument("--merge-overlap", type=float, default=30)
    parser.add_argument("--cut", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--mode", choices=["auto", "copy", "transcode"], default="auto", help="剪辑模式：auto(优先流拷贝失败回退), copy(纯流拷贝), transcode(重编码)")
    parser.add_argument("--limit", type=int, default=0, help="最多剪辑切片数量(0为全部)")
    parser.add_argument("--single-output", type=str, default="", help="仅剪辑指定的输出成片文件名")
    parser.add_argument("--single-title", type=str, default="", help="仅剪辑标题包含指定文本的切片")
    args = parser.parse_args()

    rows = prepare_candidates(
        minimum=args.min_duration,
        maximum=args.max_duration,
        padding=args.padding,
        merge_threshold=args.merge_overlap
    )

    if args.single_output:
        rows = [r for r in rows if Path(r["output"]).name == args.single_output or args.single_output in r["output"]]
        print(f"📌 单片过滤模式：匹配到 {len(rows)} 个目标切片", flush=True)

    if args.single_title:
        rows = [
            r for r in rows
            if args.single_title.lower() in r.get("title", "").lower()
            or args.single_title.lower() in r.get("source_titles", "").lower()
        ]
        print(f"📌 标题过滤模式：匹配到 {len(rows)} 个目标切片", flush=True)

    print("最终候选数量：", len(rows), flush=True)
    print("最终清单：", FINAL_CSV, flush=True)

    for index, row in enumerate(rows, 1):
        print(
            f"{index}. {row['start']}-{row['end']}秒，"
            f"时长{row['duration']}秒，"
            f"{row['score']}分，"
            f"{row['source_titles']}",
            flush=True
        )

    if args.cut:
        cut_videos(rows, overwrite=args.overwrite, mode=args.mode, limit=args.limit)


if __name__ == "__main__":
    main()
