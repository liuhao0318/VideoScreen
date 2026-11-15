import argparse
import csv
import hashlib
import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

import ai_service

BASE = Path(__file__).resolve().parent
DB = BASE / "videos_v2.db"
OUT = BASE / "ai_analysis"
API = "http://127.0.0.1:11434/api/chat"

WINDOW = 600
OVERLAP = 120
MIN_SCORE = 70
MODEL = "qwen2.5:7b"
PROMPT_VERSION = "football_v5_traffic_score_config_terms"

CONFIG_PATH = BASE / "config.json"


def load_focus_terms():
    """从统一配置读取关键词，避免分析规则覆盖用户维护的人名。"""
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        terms = config.get("keywords", [])
    except (OSError, ValueError, TypeError):
        terms = []

    return list(dict.fromkeys(
        str(term).strip()
        for term in terms
        if str(term).strip()
    ))


FOCUS_TERMS = load_focus_terms()


def build_system_prompt():
    focus_text = "、".join(FOCUS_TERMS) or "无自定义重点词"
    return f"""
你是专业的中文直播短视频编辑，负责从直播转写中筛选具有传播潜力、
且能脱离直播上下文独立观看的精彩完整片段。

用户长期维护的重点人物、赛事、行业话题与核心观点词如下，必须完整保留并优先识别：
{focus_text}

内容优先级（聚焦深度干货、高光观点与名场面）：
1. 深入的专业分析、实战复盘与核心干货提炼。
2. 鲜明犀利的独家观点、独到见解或反常识深度认知。
3. 对具体人物、热点事件或核心议题的深度专业剖析。
4. 情绪充沛、具有极高讨论度与传播价值的金句名场面。
5. 有明确依据与论证逻辑、能脱离直播独立成片的精彩案例。

内容评分维度（总分100）：
- 包含扎实的专业干货或深刻认知，信息密度高：25分。
- 围绕具体话题、关键事件或实际场景深入剖析：20分。
- 主播立场鲜明、观点犀利自洽，直击问题本质：20分。
- 结构完整独立，起因、论证与结论闭环：15分。
- 具有反常识思维、话题悬念或引发深度讨论的价值：10分。
- 开头快速切入核心矛盾，节奏紧凑抓人：10分。

扣分与排除规则：
- 商品介绍、价格、优惠、赠品、下单引导：至少扣50分。
- 唱歌、歌词、无关情感、感谢礼物、纯直播互动：至少扣50分。
- 无意义重复、大量停顿、零散喊话或没有结论：扣20至40分。
- 只有宽泛议论，没有具体人物、问题、事实或观点：扣15至30分。
- 与已表达内容只是重复措辞、没有新增信息：扣20分。
- 未经证实的私生活、侮辱攻击或可能侵权的爆料：不得推荐。

重点词只用于发现内容，不能仅因命中重点词就给高分。出现重点人物后，
仍必须围绕该人物形成清楚、完整、有依据的观点，才可获得人物和观点分。
不要为了制造争议而夸大原话。转写可能有同音字和识别错误，不能确定的
人名、术语和比赛信息不要擅自纠正。

评分区间：
90-100：人物或事件明确、观点鲜明、证据充分、结构完整，极值得剪辑。
80-89：有较强信息价值和讨论价值，稍作剪辑即可发布。
70-79：内容基本完整，但传播点或证据相对一般。
50-69：宽泛讨论、重复或上下文依赖较强，暂不推荐。
0-49：广告、歌曲、闲聊、零散内容或无有效观点。

仅输出JSON对象，不要输出Markdown代码块或额外说明。
格式：
{{
  "candidates": [
    {{
      "start": 120.0,
      "end": 210.0,
      "title": "包含具体人物或问题、准确且有吸引力的中文标题",
      "topic": "话题类别",
      "score": 82,
      "summary": "该片段主要讨论什么",
      "reason": "按照上述评分项说明为什么值得剪辑"
    }}
  ]
}}

边界规则：
- start、end必须采用转写中提供的秒数。
- 从完整观点真正开始处切入，到自然结论结束；删除无关寒暄和重复。
- 优先推荐35至180秒能讲完整的内容；完整故事或深度战术可放宽至300秒。
- 核心内容不足35秒时可以保留必要上下文，但不能拼接无关话题凑时长。
- 同一连续话题只输出一个候选，高度重叠内容只保留最完整的一个。
- 每个窗口最多输出3个最有价值的候选；没有合格内容就返回空列表。
- 标题不得编造转写中不存在的观点、人物或事实。
"""

SYSTEM_PROMPT = build_system_prompt()

def call_ollama(messages, timeout=300):
    try:
        return ai_service.chat_completion(
            messages=messages,
            temperature=0.1,
            json_format=True,
            timeout=timeout,
        )
    except Exception as error:
        raise ValueError(f"AI 模型分析失败：{error}") from error


def load_videos():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT path, transcript_path
        FROM videos
        WHERE status = 'completed'
        ORDER BY path
    """).fetchall()
    conn.close()
    return rows


def load_segments(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("transcript.json 不是列表")

    segments = []
    for item in data:
        try:
            start = float(item["start"])
            end = float(item["end"])
            text = str(item["text"]).strip()
            if end > start and start >= 0 and text:
                segments.append({
                    "start": start,
                    "end": end,
                    "text": text
                })
        except (KeyError, TypeError, ValueError):
            continue

    return sorted(segments, key=lambda x: x["start"])


def build_windows(segments):
    if not segments:
        return []

    duration = max(s["end"] for s in segments)
    windows = []
    start = 0.0

    while start < duration:
        end = min(start + WINDOW, duration)

        selected = [
            s for s in segments
            if s["end"] > start and s["start"] < end
        ]

        if selected:
            windows.append((start, end, selected))

        if end >= duration:
            break

        start += WINDOW - OVERLAP

    return windows


def format_transcript(segments):
    return "\n".join(
        f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}"
        for s in segments
    )


def normalize_candidates(data, start, end, duration):
    result = []

    for c in data.get("candidates", []):
        try:
            a = float(c["start"])
            b = float(c["end"])
            score = max(0, min(100, int(float(c["score"]))))

            # 限制模型输出到当前分析窗口
            a = max(start, min(end, a))
            b = max(start, min(end, b))

            if b <= a or score < MIN_SCORE:
                continue

            result.append({
                "start": round(a, 2),
                "end": round(b, 2),
                "title": str(c.get("title", ""))[:100],
                "topic": str(c.get("topic", ""))[:60],
                "score": score,
                "summary": str(c.get("summary", ""))[:500],
                "reason": str(c.get("reason", ""))[:500]
            })
        except (KeyError, TypeError, ValueError):
            continue

    return result


def analyze_window(start, end, segments, duration):
    transcript = format_transcript(segments)

    matched_terms = [
        term
        for term in FOCUS_TERMS
        if term in transcript
    ]

    matched_text = (
        "、".join(matched_terms)
        if matched_terms
        else "本窗口未发现精确匹配词"
    )

    # 防止异常密集转写超出模型上下文
    if len(transcript) > 18000:
        raise ValueError(
            f"窗口文本过长（{len(transcript)}字符），"
            "需调整窗口大小，不能直接截断"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"视频总时长约：{duration:.1f}秒\n"
                f"当前分析窗口：{start:.1f}-{end:.1f}秒\n"
                f"本窗口重点词命中：{matched_text}\n"
                "请优先检查命中词附近的上下文，"
                "但不要仅因命中关键词就给出高分。\n"
                "请根据以下转写文本寻找有价值的话题。\n\n"
                + transcript
            )
        }
    ]

    data = call_ollama(messages)

    if not isinstance(data, dict):
        raise ValueError("模型没有返回JSON对象")

    candidates = normalize_candidates(
        data, start, end, duration
    )

    for candidate in candidates:
        candidate_text = " ".join(
            segment["text"]
            for segment in segments
            if segment["end"] > candidate["start"]
            and segment["start"] < candidate["end"]
        )

        candidate["matched_terms"] = [
            term
            for term in FOCUS_TERMS
            if term in candidate_text
        ]

    return candidates


def candidate_overlap(a, b):
    intersection = max(
        0, min(a["end"], b["end"]) - max(a["start"], b["start"])
    )
    shorter = min(
        a["end"] - a["start"],
        b["end"] - b["start"]
    )
    return intersection / shorter if shorter > 0 else 0


def deduplicate(candidates):
    # 时间高度重叠的候选视为同一素材，不依赖模型生成的标题或话题文字
    selected = []

    ordered = sorted(
        candidates,
        key=lambda x: (
            -x["score"],
            -(x["end"] - x["start"])
        )
    )

    for c in ordered:
        duplicate = any(
            candidate_overlap(c, old) >= 0.7
            for old in selected
        )

        if not duplicate:
            selected.append(c)

    return sorted(selected, key=lambda x: x["start"])


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    tmp.replace(path)


def process_video(row, force=False, video_index=1, total_videos=1):
    source_id = hashlib.sha256(
        row["path"].encode("utf-8")
    ).hexdigest()[:16]
    video_dir = OUT / source_id
    report_path = video_dir / "analysis.json"

    if report_path.is_file() and not force:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            candidates = report.get("candidates", [])
            print(
                f"\n视频：{Path(row['path']).name} "
                f"已有分析记录，跳过（{len(candidates)}个候选）",
                flush=True,
            )
            return "recorded", candidates
        except (OSError, ValueError, TypeError):
            pass

    transcript_path = row["transcript_path"]

    if not transcript_path:
        return "skipped", []

    path = Path(transcript_path)
    if not path.is_file():
        return "skipped", []

    segments = load_segments(path)
    if not segments:
        return "skipped", []

    duration = max(s["end"] for s in segments)
    video_dir.mkdir(parents=True, exist_ok=True)

    windows = build_windows(segments)
    candidates = []

    v_name = Path(row["path"]).name
    print(
        f"\n视频：{v_name} "
        f"窗口数：{len(windows)}",
        flush=True
    )

    total_win = max(1, len(windows))
    total_vids = max(1, total_videos)
    for index, (start, end, selected) in enumerate(windows):
        cur_pct = min(99, int(((video_index - 1) + index / total_win) * 100 / total_vids))
        print(
            f"[PROGRESS] {cur_pct}% | AI 分析视频 [{video_index}/{total_vids}] {v_name[:22]} (窗口 {index + 1}/{total_win})",
            flush=True,
        )
        cache_path = video_dir / f"window_{index:04d}.json"

        fingerprint = hashlib.sha256(
            (
                MODEL + PROMPT_VERSION
                + json.dumps(FOCUS_TERMS, ensure_ascii=False)
                + format_transcript(selected)
                + f"{start}:{end}"
            ).encode("utf-8")
        ).hexdigest()

        cached = None
        if cache_path.is_file() and not force:
            try:
                cached = json.loads(
                    cache_path.read_text(encoding="utf-8")
                )
            except (ValueError, OSError):
                pass

        if (
            cached is not None
            and cached.get("fingerprint") == fingerprint
        ):
            found = cached["candidates"]
            print(
                f"  窗口 {index + 1}/{len(windows)}：使用缓存",
                flush=True
            )
        else:
            print(
                f"  窗口 {index + 1}/{len(windows)}："
                f"{start:.0f}-{end:.0f}s 分析中...",
                flush=True
            )

            found = analyze_window(start, end, selected, duration)

            save_json(cache_path, {
                "fingerprint": fingerprint,
                "model": MODEL,
                "start": start,
                "end": end,
                "candidates": found
            })

        candidates.extend(found)

    candidates = deduplicate(candidates)

    report = {
        "video": row["path"],
        "transcript": str(path),
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "focus_terms": FOCUS_TERMS,
        "duration": duration,
        "windows": len(windows),
        "candidates": candidates
    }

    save_json(video_dir / "analysis.json", report)

    print(
        f"  完成：推荐 {len(candidates)} 个候选片段",
        flush=True
    )

    return "completed", candidates


def export_csv(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "candidates.csv"

    fields = [
        "video", "start", "end", "duration",
        "score", "title", "topic", "matched_terms",
        "summary", "reason"
    ]

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n候选清单：{csv_path}", flush=True)


def main():
    global MODEL, MIN_SCORE

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--min-score", type=int, default=MIN_SCORE)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    MODEL = args.model
    MIN_SCORE = args.min_score

    OUT.mkdir(parents=True, exist_ok=True)

    videos = load_videos()
    if args.limit > 0:
        videos = videos[:args.limit]

    print("待检查视频：", len(videos), flush=True)
    print("使用模型：", MODEL, flush=True)

    completed = 0
    failed = 0
    skipped = 0

    total_vids = len(videos)
    for index, row in enumerate(videos, 1):
        print(f"\n[{index}/{total_vids}]", flush=True)
        pct_v = int((index - 1) * 100 / max(1, total_vids))
        print(f"[PROGRESS] {pct_v}% | 检查视频 [{index}/{total_vids}]", flush=True)

        try:
            status, _ = process_video(row, force=args.force, video_index=index, total_videos=total_vids)
            if status in ("completed", "recorded"):
                completed += 1
            else:
                skipped += 1
            pct_done = int(index * 100 / max(1, total_vids))
            print(f"[PROGRESS] {pct_done}% | 视频分析完成 [{index}/{total_vids}]", flush=True)

        except KeyboardInterrupt:
            print("\n用户中断，已完成的窗口缓存保留。")
            break

        except Exception as e:
            failed += 1
            print(f"  分析失败：{e}", flush=True)

    # 汇总所有已经生成的完整视频分析报告
    all_rows = []

    for report_path in OUT.glob("*/analysis.json"):
        try:
            report = json.loads(
                report_path.read_text(encoding="utf-8")
            )
            for c in report.get("candidates", []):
                all_rows.append({
                    "video": report["video"],
                    "start": c["start"],
                    "end": c["end"],
                    "duration": round(c["end"] - c["start"], 2),
                    "score": c["score"],
                    "title": c["title"],
                    "topic": c["topic"],
                    "matched_terms": "、".join(
                        c.get("matched_terms", [])
                    ),
                    "summary": c["summary"],
                    "reason": c["reason"]
                })
        except (OSError, ValueError, KeyError):
            continue

    all_rows.sort(key=lambda x: -x["score"])
    export_csv(all_rows)

    print("\n本次运行统计：")
    print("完成分析：", completed)
    print("跳过：", skipped)
    print("失败：", failed)
    print("累计候选片段：", len(all_rows))


if __name__ == "__main__":
    main()
