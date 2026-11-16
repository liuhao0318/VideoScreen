#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import urllib.request
from pathlib import Path

import ai_service
import traffic_service
import benchmark_radar
import remix_service
import live_recorder_service


ROOT = Path(__file__).resolve().parent
DB = ROOT / "videos_v2.db"
RESULTS_DIR = ROOT / "results"
AI_DIR = ROOT / "ai_analysis"
FINAL_CSV = AI_DIR / "final_candidates.csv"
QUEUE_JSON = ROOT / "publish_queue.json"
MANIFEST_JSON = ROOT / "clip_manifest.json"
LOG_DIR = ROOT / "logs"
DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
JOBS = {}
JOBS_LOCK = threading.Lock()
SCAN_LOCK = threading.Lock()
QUEUE_LOCK = threading.Lock()
AI_GEN_LOCK = threading.Lock()
SCAN_STATE = {
    "last_started_at": None,
    "last_completed_at": None,
    "last_error": None,
    "is_scanning": False,
}


def get_python_executable():
    """优先使用包含完整依赖（Playwright、Torch等）的 video-screen 专用 Python 解释器"""
    dedicated = Path("/home/ubuntu/miniconda3/envs/video-screen/bin/python")
    if dedicated.is_file() and os.access(dedicated, os.X_OK):
        return str(dedicated)
    return sys.executable


def execute_scan():
    """打开网页或刷新时执行一次扫描，将录制目录中的新视频导入数据库。"""
    if SCAN_STATE["is_scanning"]:
        return SCAN_STATE
    with SCAN_LOCK:
        SCAN_STATE["is_scanning"] = True
        SCAN_STATE["last_started_at"] = time.time()
        try:
            result = subprocess.run(
                [get_python_executable(), "-u", str(ROOT / "video_screen.py"), "scan"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode:
                SCAN_STATE["last_error"] = (
                    result.stderr.strip() or result.stdout.strip()
                    or f"扫描进程退出码 {result.returncode}"
                )[-1000:]
            else:
                SCAN_STATE["last_error"] = None
                SCAN_STATE["last_completed_at"] = time.time()
                invalidate_overview_cache()
        except (OSError, subprocess.SubprocessError) as error:
            SCAN_STATE["last_error"] = str(error)
        finally:
            SCAN_STATE["is_scanning"] = False
        return SCAN_STATE


def read_csv(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def source_id(path):
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def load_clip_rows():
    rows = []
    seen = set()
    for collection in (
        read_json(MANIFEST_JSON, []),
        read_csv(FINAL_CSV),
    ):
        for row in collection:
            output = row.get("output", "")
            if not output:
                continue
            key = str(Path(output).resolve())
            if key in seen:
                continue
            seen.add(key)
            rows.append({**row, "output": key})
    return rows


def load_sources():
    if not DB.is_file():
        return []
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT path, size, status, transcript_path,
                   processed_at, error
            FROM videos
            ORDER BY path
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


GENERIC_FOOTBALL_TERMS = {
    "董路", "青训", "战术", "教练", "国足", "中超", "足球小将", "足球", "中国足球"
}
NON_PERSON_KEYWORDS = GENERIC_FOOTBALL_TERMS | {
    "45度炸", "保护性接应", "不在乎成绩", "留洋", "试训", "比赛", "直播", "带货",
    "中国队", "国家队", "西班牙", "欧洲", "联赛", "校园足球", "球迷",
}
KNOWN_PERSON_NAMES = {
    "刘凯源", "黄子杰", "老二", "吕梦洋", "李昊炎", "王修浩", "邵佳一",
    "邝兆镭", "浮岛敏", "安东尼奥", "毛毅军", "孙继海", "徐根宝",
    "C罗", "米里罗", "梅西", "武磊", "王钰栋", "张玉宁", "韦世豪",
    "蒋圣龙", "朱辰杰", "颜骏凌", "王大雷", "拜合拉木", "谢文能",
    "胡荷韬", "蒯纪闻", "依木兰", "陈泽仕", "万项", "谢晋", "帅惟浩",
    "何小珂", "艾菲尔丁", "游明轩", "麦子葵", "田俊明", "李华",
    "伊万", "伊万科维奇", "扬科维奇", "久尔杰维奇", "上村健一",
    "周海滨", "杨晨", "范志毅", "高洪波", "郑智", "李铁", "水庆霞",
    "瓜迪奥拉", "安切洛蒂", "弗里克", "穆里尼奥", "亚马尔", "姆巴佩",
    "哈兰德", "维尼修斯", "孙兴慜", "三笘薰", "久保建英", "李刚仁",
}


def load_clip_transcript_excerpt(row, max_chars=1800):
    """读取当前切片时间段内的真实语音转写文本，作为文案生成的最高事实依据"""
    video_path = str(row.get("video", "")).strip()
    if not video_path:
        return ""

    transcript_path = None
    if DB.is_file():
        conn = None
        try:
            conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            db_row = conn.execute(
                "SELECT transcript_path FROM videos WHERE path = ?",
                (video_path,),
            ).fetchone()
            if not db_row:
                vname = Path(video_path).name
                db_row = conn.execute(
                    "SELECT transcript_path FROM videos WHERE path LIKE ? ORDER BY processed_at DESC LIMIT 1",
                    (f"%/{vname}",),
                ).fetchone()
            if db_row and db_row["transcript_path"]:
                cand = Path(db_row["transcript_path"])
                if cand.is_file():
                    transcript_path = cand
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    if transcript_path is None and RESULTS_DIR.is_dir():
        stem = Path(video_path).stem
        for cand_dir in RESULTS_DIR.glob(f"{stem}_*"):
            cand = cand_dir / "transcript.json"
            if cand.is_file():
                transcript_path = cand
                break

    if transcript_path is None:
        return ""

    segments = read_json(transcript_path, [])
    if not isinstance(segments, list) or not segments:
        return ""

    try:
        start = float(row.get("start") or 0)
    except (TypeError, ValueError):
        start = 0.0
    try:
        end = float(row.get("end") or 0)
    except (TypeError, ValueError):
        end = 0.0

    selected = []
    if end > start:
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            try:
                seg_s = float(seg.get("start") or 0)
                seg_e = float(seg.get("end") or 0)
            except (TypeError, ValueError):
                continue
            if seg_e >= start - 3.0 and seg_s <= end + 3.0:
                txt = str(seg.get("text", "")).strip()
                if txt:
                    selected.append(txt)
    else:
        for seg in segments[:30]:
            if isinstance(seg, dict):
                txt = str(seg.get("text", "")).strip()
                if txt:
                    selected.append(txt)

    text = " ".join(selected).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def extract_required_person_names(row, transcript_excerpt="", configured_keywords=None):
    """提取视频相关话题中的核心人名，确保 AI 文案和标签不遗漏关键人物"""
    if configured_keywords is None:
        configured_keywords = read_json(ROOT / "config.json", {}).get("keywords", [])

    person_pool = []
    seen_pool = set()
    for term in list(configured_keywords) + sorted(KNOWN_PERSON_NAMES):
        t = str(term).strip()
        if t and t not in NON_PERSON_KEYWORDS and t not in seen_pool:
            seen_pool.add(t)
            person_pool.append(t)
    # 先匹配全名再匹配简称（如先“伊万科维奇”再“伊万”）
    person_pool.sort(key=len, reverse=True)

    names = []

    def _add(name):
        name = str(name).strip()
        if not name or name in NON_PERSON_KEYWORDS:
            return
        if name not in names:
            names.append(name)

    # 1. matched_terms 中的非泛化词（如 顿号/逗号分隔的球员、教练名）
    raw_matched = str(row.get("matched_terms", "")).strip()
    if raw_matched:
        for token in re.split(r"[,，、;/|\s]+", raw_matched):
            token = token.strip()
            if token and token not in NON_PERSON_KEYWORDS:
                _add(token)

    # 2. 候选标题/摘要/话题/推荐理由中命中已知人物词库的人名
    meta_text = " ".join(str(row.get(k, "")) for k in (
        "title", "summary", "topics", "topic", "matched_terms", "reason", "source_titles"
    ))
    for person in person_pool:
        if person in meta_text:
            _add(person)

    # 3. 若元数据里未显式给出，从真实转写原文中挑选高频核心人物（最多2位避免点名刷屏）
    if not names and transcript_excerpt:
        hits = []
        for person in person_pool:
            cnt = transcript_excerpt.count(person)
            if cnt > 0:
                hits.append((cnt, len(person), person))
        hits.sort(reverse=True)
        for _, _, person in hits[:2]:
            _add(person)

    return names[:3]


def default_publish_content(row, configured_keywords=None):
    if configured_keywords is None:
        configured = read_json(ROOT / "config.json", {}).get("keywords", [])
    else:
        configured = configured_keywords
    required_names = extract_required_person_names(row, configured_keywords=configured)
    search_text = " ".join(str(row.get(key, "")) for key in (
        "title", "topics", "matched_terms", "summary", "video"
    ))
    tags = []
    for term in ["董路", *required_names, *configured, "中国足球", "足球", "足球分析"]:
        term = str(term).strip()
        if term and term not in tags and (
            term in required_names
            or term in search_text
            or term in ("董路", "中国足球", "足球", "足球分析")
        ):
            tags.append(term)
        if len(tags) >= 5:
            break
    summary = str(row.get("summary", "")).strip()
    tag_text = " ".join(f"#{tag}" for tag in tags)
    return "\n".join(part for part in (summary, tag_text) if part)


OVERVIEW_CACHE = None
OVERVIEW_CACHE_TIME = 0


def invalidate_overview_cache():
    global OVERVIEW_CACHE, OVERVIEW_CACHE_TIME
    OVERVIEW_CACHE = None
    OVERVIEW_CACHE_TIME = 0


def build_overview():
    global OVERVIEW_CACHE, OVERVIEW_CACHE_TIME
    now = time.time()
    if OVERVIEW_CACHE is not None and (now - OVERVIEW_CACHE_TIME) < 6:
        return OVERVIEW_CACHE

    # 已清理的原录制文件不再出现在素材工作列表中；其分析和成片记录仍保留。
    sources = [
        row for row in load_sources()
        if row.get("status") != "source_deleted"
    ]
    final_rows = load_clip_rows()
    queue = read_json(QUEUE_JSON, [])
    configured_keywords = read_json(ROOT / "config.json", {}).get("keywords", [])

    clips_by_source = {}
    for row in final_rows:
        clips_by_source.setdefault(row.get("video", ""), []).append(row)

    queue_by_output = {
        os.path.abspath(item["output"]): item
        for item in queue
        if item.get("output")
    }

    source_items = []
    for row in sources:
        path = row["path"]
        report = AI_DIR / source_id(path) / "analysis.json"
        report_data = read_json(report, {})
        clips = clips_by_source.get(path, [])
        existing_clips = [
            clip for clip in clips
            if os.path.isfile(clip.get("output", ""))
        ]
        publish_states = []
        for clip in existing_clips:
            item = queue_by_output.get(clip["output"], {})
            publish_states.append(
                item.get("status", {}).get("douyin", "pending")
            )

        if publish_states and all(x == "published" for x in publish_states):
            stage = "published"
        elif existing_clips:
            stage = "ready"
        elif report.is_file():
            stage = "analyzed"
        elif row["status"] == "completed":
            stage = "transcribed"
        elif row["status"] == "source_deleted":
            stage = "source_deleted"
        elif row["status"] == "no_audio":
            stage = "no_audio"
        elif row["status"] in ("failed", "error"):
            stage = "failed"
        else:
            stage = "waiting"

        source_items.append({
            **row,
            "name": os.path.basename(path),
            "exists": os.path.isfile(path),
            "transcript_exists": bool(
                row.get("transcript_path")
                and os.path.isfile(row["transcript_path"])
            ),
            "analyzed": report.is_file(),
            "candidate_count": len(report_data.get("candidates", [])),
            "clip_count": len(existing_clips),
            "published_count": sum(x == "published" for x in publish_states),
            "stage": stage,
        })

    traffic_stats = traffic_service.load_traffic_stats()
    clip_items = []
    for index, row in enumerate(final_rows, 1):
        out_str = row.get("output", "")
        if not out_str:
            continue
        clip_target = out_str
        queue_item = queue_by_output.get(clip_target, {})
        if queue_item.get("clip_deleted"):
            continue
        status = queue_item.get("status", {})
        try:
            stat_res = os.stat(clip_target)
            file_exists = True
            file_size = stat_res.st_size
        except OSError:
            file_exists = False
            file_size = 0

        out_name = os.path.basename(clip_target)
        out_stem = os.path.splitext(out_name)[0]
        clip_items.append({
            **row,
            "index": index,
            "name": out_name,
            "exists": file_exists,
            "size": file_size,
            "file_cleaned": bool(queue_item.get("file_cleaned")),
            "douyin_status": status.get("douyin", "pending"),
            "kuaishou_status": status.get("kuaishou", "pending"),
            "publish_title": queue_item.get(
                "publish_title", queue_item.get("title", row.get("title", out_stem))
            ),
            "publish_content": queue_item.get("publish_content")
            or default_publish_content(row, configured_keywords=configured_keywords),
            "ai_summary": row.get("summary", ""),
            "ai_topics": row.get("topics", row.get("topic", "")),
            "ai_matched_terms": row.get("matched_terms", ""),
            "ai_reason": row.get("reason", ""),
            "traffic": traffic_stats.get(clip_target),
        })

    counts = {
        "sources": len(source_items),
        "waiting": sum(x["stage"] in ("waiting", "transcribed") for x in source_items),
        "analyzed": sum(x["analyzed"] for x in source_items),
        "clips": sum(x["exists"] for x in clip_items),
        "douyin_pending": sum(
            x["exists"] and x["douyin_status"] != "published"
            for x in clip_items
        ),
        "douyin_published": sum(
            x["douyin_status"] == "published" for x in clip_items
        ),
    }

    disk_usage = shutil.disk_usage(ROOT)
    cleanable_bytes = sum(
        (x.get("size") or 0)
        for x in source_items
        if x.get("clip_count", 0) > 0 and x.get("exists")
    )
    # 统计成片目录真实占用空间
    clips_bytes = 0
    clips_dir = ROOT / "clips"
    if clips_dir.is_dir():
        try:
            for entry in os.scandir(clips_dir):
                if entry.is_dir(follow_symlinks=False):
                    for f in os.scandir(entry.path):
                        if f.is_file(follow_symlinks=False):
                            clips_bytes += f.stat().st_size
                elif entry.is_file(follow_symlinks=False):
                    clips_bytes += entry.stat().st_size
        except Exception:
            pass

    storage = {
        "disk_free_gb": round(disk_usage.free / (1024**3), 1),
        "disk_total_gb": round(disk_usage.total / (1024**3), 1),
        "cleanable_gb": round(cleanable_bytes / (1024**3), 2),
        "clips_total_gb": round(clips_bytes / (1024**3), 1),
    }

    ai_cfg = ai_service.get_ai_config()
    ai_provider = ai_cfg.get("provider", "ollama")
    ai_model = (
        ai_cfg.get("ollama", {}).get("model", "qwen2.5:7b")
        if ai_provider == "ollama"
        else ai_cfg.get("api", {}).get("model", "deepseek-chat")
    )

    traffic_summary = traffic_service.get_traffic_summary()
    radar_data = benchmark_radar.load_radar_data()
    radar_items = radar_data.get("radar_items", [])
    radar_summary = {
        "tracked_accounts_count": len(radar_data.get("tracked_accounts", [])),
        "breaking_count": sum(1 for x in radar_items if x.get("is_breaking")),
        "items_count": len(radar_items),
    }

    try:
        recorder_status = live_recorder_service.get_status()
    except Exception:
        recorder_status = {"is_running": False, "rooms": []}

    result = {
        "counts": counts,
        "storage": storage,
        "traffic": traffic_summary,
        "radar": radar_summary,
        "recorder": recorder_status,
        "ai": {
            "provider": ai_provider,
            "model": ai_model,
            "is_api": ai_provider == "api",
        },
        "sources": source_items,
        "clips": clip_items,
        "scan": SCAN_STATE,
        "auto_scan": SCAN_STATE,
    }
    OVERVIEW_CACHE = result
    OVERVIEW_CACHE_TIME = now
    return result



def update_publish_status(index, platform, status, output=""):
    if platform not in ("douyin", "kuaishou"):
        raise ValueError("不支持的平台")

    if status not in (
        "pending",
        "published",
        "failed",
        "skipped"
    ):
        raise ValueError("不支持的发布状态")

    final_rows = load_clip_rows()

    selected_row = None
    if output:
        target_output = str(Path(output).resolve())
        selected_row = next(
            (
                row for row in final_rows
                if str(Path(row.get("output", "")).resolve())
                == target_output
            ),
            None,
        )
    elif 1 <= index <= len(final_rows):
        selected_row = final_rows[index - 1]
        target_output = str(Path(selected_row["output"]).resolve())
    else:
        raise ValueError("无效的成片序号")

    if selected_row is None:
        raise ValueError("最终成片列表中没有找到该视频")

    with QUEUE_LOCK:
        queue = read_json(QUEUE_JSON, [])
        found = False

        for item in queue:
            if not item.get("output"):
                continue

            if os.path.abspath(item["output"]) == target_output:
                item.setdefault("status", {})
                item["status"][platform] = status
                found = True
                break

        if not found:
            queue.append({
                "id": source_id(target_output),
                "title": selected_row.get("title")
                or Path(target_output).stem,
                "output": target_output,
                "duration": selected_row.get("duration", ""),
                "score": selected_row.get("score", ""),
                "captions": {},
                "status": {
                    "douyin": "pending",
                    "kuaishou": "pending",
                    platform: status,
                },
            })

        tmp = QUEUE_JSON.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                queue,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )
        tmp.replace(QUEUE_JSON)
    invalidate_overview_cache()

    return {
        "index": index,
        "platform": platform,
        "status": status
    }


def cleanup_source(source):
    source_path = Path(source).resolve()
    rows = [
        row for row in load_clip_rows()
        if Path(row.get("video", "")).resolve() == source_path
    ]
    if not rows:
        raise ValueError("该素材没有剪辑记录，不能清理")
    if not all(Path(row.get("output", "")).is_file() for row in rows):
        raise ValueError("该素材仍有成片缺失，不能清理原文件")
    if not source_path.is_file():
        raise ValueError("原素材文件已经不存在")

    try:
        source_path.unlink(missing_ok=True)
    except Exception as e:
        raise OSError(f"删除原素材失败: {e}")

    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "UPDATE videos SET status='source_deleted', error=NULL WHERE path=?",
            (str(source_path),),
        )
        conn.commit()
    finally:
        conn.close()
    invalidate_overview_cache()
    return {"source": str(source_path), "status": "source_deleted"}


def cleanup_sources(sources):
    if not isinstance(sources, list) or not sources:
        raise ValueError("请至少选择一个已剪辑原素材")
    unique_sources = list(dict.fromkeys(str(source) for source in sources))
    deleted = []
    failed = []
    for source in unique_sources:
        try:
            result = cleanup_source(source)
            deleted.append(result["source"])
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            failed.append({"source": source, "error": str(error)})
    return {"deleted": deleted, "failed": failed}


def update_publish_text(output, title, content):
    target = str(Path(output).resolve())
    final_row = next(
        (
            row for row in load_clip_rows()
            if row.get("output") == target
        ),
        None,
    )
    if final_row is None or not os.path.isfile(target):
        raise ValueError("成片不存在或不在发布清单中")

    title = str(title).strip()
    content = str(content).strip()
    if not title:
        raise ValueError("发布标题不能为空")
    if len(title) > 100:
        raise ValueError("发布标题不能超过100个字符")
    if len(content) > 2000:
        raise ValueError("发布内容不能超过2000个字符")

    with QUEUE_LOCK:
        queue = read_json(QUEUE_JSON, [])
        item = next(
            (
                row for row in queue
                if row.get("output") and os.path.abspath(row["output"]) == target
            ),
            None,
        )
        if item is None:
            item = {
                "id": source_id(target),
                "title": final_row.get("title") or Path(target).stem,
                "output": target,
                "captions": {},
                "status": {"douyin": "pending", "kuaishou": "pending"},
            }
            queue.append(item)

        item["publish_title"] = title
        item["publish_content"] = content
        tmp = QUEUE_JSON.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(QUEUE_JSON)
    invalidate_overview_cache()
    return {"output": target, "publish_title": title, "publish_content": content}


STYLE_PROMPTS = {
    "tactical_youth": (
        "立足视频真实内容，采用资深足球评论与青训观察的克制干货口吻："
        "【点出核心话题与人物 + 紧扣原文细节展开分析 + 提炼真实结论】。"
        "仅当原话确实谈到技战术或青训规律时再展开分析；若聊的是人物近况、团队管理或生活话题，则如实围绕该话题撰写，严禁生搬硬套无关术语。"
    ),
    "tactical": (
        "聚焦片段中真实提及的技战术打法、场上执行或比赛细节进行客观复盘；"
        "若原话未涉及具体阵型战术，则严格围绕原文实际话题归纳重点，不硬套战术名词。"
    ),
    "youth": (
        "聚焦片段中真实提及的年轻球员表现、成长路径或青训实际问题，客观梳理事实与看点，"
        "严格忠于原话，不脱离素材凭空发挥。"
    ),
    "benchmark_viral": (
        "采用紧凑抓人的短视频节奏：标题直指核心人物与关键矛盾或悬念，正文第一句亮出真实观点或结论，"
        "中间补充原文依据，结尾留一个贴合原文的问题引发讨论；禁止编造原文没有的对立金句或假引语。"
    ),
    "opinionated": (
        "立场明确、直击片段真实讨论的核心问题，语言简洁有力，每句判断都必须在提供的原文或摘要中有依据，"
        "不夸大、不和稀泥、不编造。"
    ),
    "humorous_meme": (
        "保留原视频中董路或对话本身的幽默吐槽、鲜活比喻和接地气表达，"
        "只提炼原文真实出现的梗、细节和人物，不擅自编造段子。"
    ),
}


def generate_publish_text(output, style="tactical_youth", provider=None):
    target = str(Path(output).resolve())
    row = next(
        (
            item for item in load_clip_rows()
            if item.get("output") == target
        ),
        None,
    )
    if row is None or not os.path.isfile(target):
        raise ValueError("成片不存在或不在发布清单中")

    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["tactical_youth"])
    configured = read_json(ROOT / "config.json", {}).get("keywords", [])
    transcript_excerpt = load_clip_transcript_excerpt(row, max_chars=1800)
    required_names = extract_required_person_names(
        row,
        transcript_excerpt=transcript_excerpt,
        configured_keywords=configured,
    )
    required_names_str = (
        "、".join(required_names)
        if required_names
        else "（若下方原文/标题/摘要中出现具体球员、教练或其他人物姓名，必须保留在文案中）"
    )
    transcript_section = (
        f"片段字幕原文（最高事实依据）：\n{transcript_excerpt}\n"
        if transcript_excerpt
        else "片段字幕原文：（未检索到独立字幕，请严格只依据下方候选标题与摘要撰写，严禁脑补未给出的细节）\n"
    )

    prompt = f"""
请严格依据以下【真实片段资料】，为这条直播切片撰写抖音发布标题、正文与话题标签。
文案风格定位：{style_instruction}

硬性铁律（必须全部严格遵守）：
1. 【绝对忠于原文，严禁天马行空】标题和正文的每一个事实、人物、事件、原因和结论，都必须直接来源于“片段字幕原文”或下方“候选资料”。严禁凭空编造未提及的战术名词（如45度防守、阵型）、比赛结果、数据或背景故事！
2. 【相关人物姓名必须出现】视频核心话题人物：{required_names_str}。标题中必须包含至少核心人名，正文中必须明确写出上述相关人名；严禁删掉人名，严禁模糊成“某小将”“该球员”，也严禁代入其他无关人员。
3. 【禁止虚假引语】除非“片段字幕原文”中有对应原话，否则严禁编造“董路曾直言：‘……’”“董老师曾说”等假引语；若原片段讲的是人物近况、日常或非足球话题，就如实贴合原话题写，不能硬扯足球战术。
4. 【视角要求】不要使用“主播”二字及“主播讨论了”“主播提醒”“视频讲了”“这段视频”等旁观播报式开头，如需指代主讲人请直呼“董路”或直接陈述事实与观点。
5. 【字数与结构】标题 10 至 26 个汉字，准确概括本片段核心看点；正文 2 至 3 句（控制在 50 至 130 字以内），第一句点出主体人物与核心事件/观点，后续补充原文具体依据或关键点，简洁克制不假大空。
6. 【话题标签】仅保留“董路”、视频必须出现的人名，以及本片段真实涉及的话题词，最多 5 个。

原候选标题：{row.get('title', '')}
AI内容摘要：{row.get('summary', '')}
话题分类：{row.get('topics', row.get('topic', ''))}
命中关键词与人物：{row.get('matched_terms', '')}
入选理由：{row.get('reason', '')}
{transcript_section}
仅返回合法JSON：
{{"title":"贴合原文且含相关人名的标题","content":"贴合原文且含相关人名的正文（不含#标签）","tags":["董路","相关人名","真实话题"]}}
"""
    messages = [{"role": "user", "content": prompt}]
    ai_cfg = ai_service.get_ai_config()
    chosen_provider = provider or ai_cfg.get("provider", "ollama")

    meta_text = " ".join(str(row.get(key, "")) for key in (
        "title", "summary", "topics", "topic", "matched_terms", "reason", "source_titles"
    ))
    source_text = meta_text + (" " + transcript_excerpt if transcript_excerpt else "")
    forbidden_phrases = (
        "主播讨论", "主播分析", "主播分享", "主播通过", "主播提醒",
        "主播表示", "主播认为", "主播称", "视频讲了", "这段视频",
    )
    fake_quote_phrases = ("董路曾直言", "董老师曾直言", "董路直言", "董老师直言")
    boilerplate_tactics = ("45度防守", "45度角", "眼神盯人", "541防反")
    check_terms = set(str(t).strip() for t in configured if str(t).strip()) | KNOWN_PERSON_NAMES

    last_validation_err = None
    title = ""
    content = ""
    generated = {}

    for attempt in range(2):
        try:
            with AI_GEN_LOCK:
                generated = ai_service.chat_completion(
                    messages=messages,
                    provider=chosen_provider,
                    temperature=0.2 if attempt == 0 else 0.1,
                    json_format=True,
                    timeout=180,
                )
        except Exception as error:
            raise ValueError(f"AI生成发布文案失败：{error}") from error

        title = str(generated.get("title", "")).strip()
        content = str(generated.get("content", "")).strip()

        invented_terms = sorted(
            term for term in check_terms
            if term not in GENERIC_FOOTBALL_TERMS
            and term not in source_text
            and (term in title or term in content)
        )
        missing_in_content = [n for n in required_names if n not in content]
        missing_in_title = bool(required_names) and not any(n in title for n in required_names)
        hallucinated_boilerplate = [
            b for b in boilerplate_tactics
            if b not in source_text and (b in title or b in content)
        ]
        fake_quotes = [
            q for q in fake_quote_phrases
            if q in content and "直言" not in source_text
        ]

        if invented_terms:
            last_validation_err = (
                "AI文案出现当前片段未提供的特定人物或专有词汇："
                + "、".join(invented_terms)
            )
        elif hallucinated_boilerplate:
            last_validation_err = (
                "AI文案硬套了原文未提及的战术套话："
                + "、".join(hallucinated_boilerplate)
            )
        elif fake_quotes:
            last_validation_err = "AI文案编造了原文未出现的‘直言’引语，请改为直接依据原文陈述"
        elif missing_in_title or missing_in_content:
            missing_desc = []
            if missing_in_title:
                missing_desc.append(f"标题缺少核心人名（需包含 {'/'.join(required_names)}）")
            if missing_in_content:
                missing_desc.append(f"正文遗漏了必须出现的视频人名：{'、'.join(missing_in_content)}")
            last_validation_err = "；".join(missing_desc)
        elif any(phrase in content for phrase in forbidden_phrases):
            last_validation_err = "AI文案仍使用‘主播/视频讲了’等旁观式表达，请改用‘董路’或直接陈述"
        elif not title or not content:
            last_validation_err = "AI未返回有效的标题或正文"
        else:
            last_validation_err = None
            break

        if attempt == 0:
            messages = list(messages) + [
                {"role": "assistant", "content": json.dumps(generated, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": (
                        f"上一次输出不符合要求：{last_validation_err}。"
                        f"请严格依据片段字幕原文和候选摘要重写，务必在标题和正文中写明相关人名（{required_names_str}），"
                        "删除一切原文没有的词汇、假引语和旁观腔，仅输出合法JSON。"
                    ),
                },
            ]

    if last_validation_err:
        raise ValueError(f"{last_validation_err}，请重试")

    tags = []
    for must_tag in ["董路", *required_names]:
        if must_tag and must_tag not in tags:
            tags.append(must_tag)
    for raw_tag in generated.get("tags", []):
        tag = str(raw_tag).strip().lstrip("#")
        if not tag or tag in tags:
            continue
        in_meta_or_copy = (
            tag in title
            or tag in content
            or tag in meta_text
            or (tag in configured and tag in source_text)
        )
        if not in_meta_or_copy:
            continue
        tags.append(tag)
    if len(tags) < 3 and any(k in source_text for k in ("国足", "青训", "中超", "球员", "足球", "比赛", "教练")):
        for fallback_tag in ("中国足球", "足球"):
            if fallback_tag not in tags:
                tags.append(fallback_tag)

    tag_text = " ".join(f"#{tag}" for tag in tags[:5])
    content = "\n".join(part for part in (content, tag_text) if part)
    saved = update_publish_text(target, title, content)
    saved["source"] = f"ai_{chosen_provider}"
    saved["provider"] = chosen_provider
    saved["model"] = (
        ai_cfg.get("ollama", {}).get("model", "qwen2.5:7b")
        if chosen_provider == "ollama"
        else ai_cfg.get("api", {}).get("model", "deepseek-chat")
    )
    return saved


def delete_clip(output, cleanup_file_only=False):
    target = str(Path(output).resolve())
    row = next(
        (
            item for item in load_clip_rows()
            if str(Path(item.get("output", "")).resolve()) == target
        ),
        None,
    )
    # 若在 load_clip_rows 中未命中，兼容检查发布队列或成片目录
    if row is None:
        with QUEUE_LOCK:
            queue = read_json(QUEUE_JSON, [])
            row = next(
                (entry for entry in queue if entry.get("output") and os.path.abspath(entry["output"]) == target),
                None
            )
        if row is None and not Path(target).is_file():
            raise ValueError("未找到该成片记录且本地文件不存在")

    path = Path(target)
    # 若本地文件存在，直接物理删除以立即释放磁盘空间
    file_deleted = False
    if path.is_file():
        try:
            path.unlink(missing_ok=True)
            file_deleted = True
        except Exception as e:
            raise OSError(f"删除成片文件失败: {e}")

    with QUEUE_LOCK:
        queue = read_json(QUEUE_JSON, [])
        item = next(
            (
                entry for entry in queue
                if entry.get("output") and os.path.abspath(entry["output"]) == target
            ),
            None,
        )

        if cleanup_file_only:
            # 仅清理本地大视频文件释放磁盘空间，保留发布状态与流量归因数据
            if item is None:
                item = {
                    "id": source_id(target),
                    "title": (row.get("title") if row else path.stem) or path.stem,
                    "output": target,
                    "captions": {},
                    "status": {"douyin": "published", "kuaishou": "pending"},
                }
                queue.append(item)
            item["file_cleaned"] = True
        else:
            # 彻底删除成片记录
            if item is None:
                item = {
                    "id": source_id(target),
                    "title": (row.get("title") if row else path.stem) or path.stem,
                    "output": target,
                    "captions": {},
                    "status": {"douyin": "deleted", "kuaishou": "pending"},
                }
                queue.append(item)
            item["clip_deleted"] = True
            item.setdefault("status", {})["douyin"] = "deleted"

        tmp = QUEUE_JSON.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(QUEUE_JSON)

    # 若彻底删除，同步清理 clip_manifest.json 中已删除的记录
    if not cleanup_file_only:
        try:
            manifest_path = ROOT / "clip_manifest.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                new_manifest = [
                    m for m in manifest
                    if str(Path(m.get("output", "")).resolve()) != target
                ]
                if len(new_manifest) != len(manifest):
                    tmp_m = manifest_path.with_suffix(".json.tmp")
                    tmp_m.write_text(json.dumps(new_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    tmp_m.replace(manifest_path)
        except Exception:
            pass

    invalidate_overview_cache()
    return {
        "output": target,
        "status": "file_cleaned" if cleanup_file_only else "deleted",
        "file_deleted": file_deleted,
        "cleanup_file_only": cleanup_file_only,
    }


def validate_outputs(outputs):
    allowed = {
        str(Path(row.get("output", "")).resolve())
        for row in load_clip_rows()
    }
    result = []
    for output in outputs:
        path = str(Path(output).resolve())
        if path not in allowed or not Path(path).is_file():
            raise ValueError(f"无效或缺失的成片：{output}")
        if path not in result:
            result.append(path)
    if not result:
        raise ValueError("请至少选择一个成片")
    return result

def action_command(action, payload):
    # 优先使用包含 Playwright、Torch 的专用环境，避免误用 base 环境导致依赖缺失
    python = get_python_executable()
    if action == "transcribe_all":
        return [python, "-u", str(ROOT / "video_screen.py"), "batch"]
    if action == "analyze_all":
        command = [python, "-u", str(ROOT / "analyze_videos.py")]
        if payload.get("force"):
            command.append("--force")
        return command
    if action == "retry_source":
        source = str(Path(payload.get("source", "")).resolve())
        if source not in {row["path"] for row in load_sources()}:
            raise ValueError("素材记录不存在")
        return [
            python, "-u", str(ROOT / "video_screen.py"),
            "batch", "--path", source, "--limit", "1",
        ]
    if action == "cut_all":
        return [
            python, "-u", str(ROOT / "prepare_clips.py"),
            "--min-duration", "60", "--max-duration", "600", "--cut"
        ]
    if action == "sync_queue":
        code = (
            "import publish_assistant as p; q=p.sync_queue(); "
            "print('发布队列已同步，成片数量：', len(q))"
        )
        return [python, "-u", "-c", code]
    if action == "upload_douyin":
        outputs = validate_outputs([payload.get("output", "")])
        command = [
            python, "-u", str(ROOT / "douyin_web_uploader.py"),
            "--output", outputs[0]
        ]
        if payload.get("auto_publish"):
            command.append("--auto-publish")
        if payload.get("ai_cover"):
            command.append("--ai-cover")
        if payload.get("declaration"):
            command.append("--declaration")
        return command
    if action == "upload_selected":
        outputs = validate_outputs(payload.get("outputs", []))
        command = [python, "-u", str(ROOT / "batch_publish.py")]
        for output in outputs:
            command.extend(["--output", output])
        if payload.get("auto_publish"):
            command.append("--auto-publish")
        if payload.get("ai_cover"):
            command.append("--ai-cover")
        if payload.get("declaration"):
            command.append("--declaration")
        return command
    if action == "manual_publish":
        outputs = validate_outputs([payload.get("output", "")])
        code = (
            "import subprocess, webbrowser; "
            f"webbrowser.open({DOUYIN_UPLOAD_URL!r}); "
            f"subprocess.Popen(['xdg-open', {str(Path(outputs[0]).parent)!r}]); "
            "print('已打开抖音发布页和成片目录，请手动选择视频发布。')"
        )
        return [python, "-u", "-c", code]
    if action == "cleanup_preview":
        script = ROOT / "cleanup_sources.py"
        if not script.is_file():
            raise ValueError("cleanup_sources.py 尚未创建")
        return [python, "-u", str(script)]
    raise ValueError("不支持的任务")


def start_job(action, payload):
    # 重算力任务防并发冲突（避免转写、AI分析、剪辑多任务同时挤占GPU与CPU造成卡顿）
    heavy_actions = {"transcribe_all", "analyze_all", "cut_all", "retry_source"}
    if action in heavy_actions:
        with JOBS_LOCK:
            for job in JOBS.values():
                if job.get("status") == "running" and job.get("action") in heavy_actions:
                    raise ValueError(f"后台正在执行计算任务【{job.get('action')}】，请等待其完成或先停止，防止多任务争抢资源卡死。")

    command = action_command(action, payload)
    if shutil.which("nice"):
        command = ["nice", "-n", "10"] + command

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    log_path = LOG_DIR / f"{job_id}_{action}.log"
    log_stream = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    conda_paths = "/home/ubuntu/miniconda3/bin:/home/ubuntu/miniconda3/condabin"
    env["PATH"] = f"{conda_paths}:{env.get('PATH', '')}" if "PATH" in env else conda_paths
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        start_new_session=True,
    )
    job = {
        "id": job_id,
        "action": action,
        "pid": process.pid,
        "started_at": time.time(),
        "log": str(log_path),
        "status": "running",
        "returncode": None,
        "payload": payload,
    }
    with JOBS_LOCK:
        JOBS[job_id] = {**job, "process": process, "stream": log_stream}
    return job


def cancel_publish_jobs():
    cancelled = []
    with JOBS_LOCK:
        for job_id, job in JOBS.items():
            process = job["process"]
            if (
                job["status"] == "running"
                and job.get("action") in ("upload_douyin", "upload_selected")
                and process.poll() is None
            ):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                job["status"] = "cancelled"
                job["returncode"] = process.returncode
                if not job["stream"].closed:
                    job["stream"].close()
                cancelled.append(job_id)
    return {"cancelled": cancelled, "count": len(cancelled)}


def _extract_job_progress(log_path_str):
    try:
        p = Path(log_path_str)
        if not p.is_file():
            return None, ""
        with p.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 16384), os.SEEK_SET)
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None, ""

    outer_idx, outer_total = 0, 0
    last_pct, last_text = None, ""
    for line in tail.splitlines():
        s = line.strip()
        if not s:
            continue
        m_outer = re.match(r"^\[(\d+)/(\d+)\]\s*(.*)$", s)
        if m_outer:
            idx, total = int(m_outer.group(1)), max(1, int(m_outer.group(2)))
            desc = m_outer.group(3).strip()
            if "处理：" in desc or "自动准备发布：" in desc or desc == "":
                outer_idx, outer_total = idx, total
            elif outer_total <= 1:
                last_pct = min(99, int((idx - 1) * 100 / total))
                last_text = f"[{idx}/{total}] {desc[:28]}"
            continue
        m_prog = re.match(r"^\[PROGRESS\]\s*(\d+)%\s*\|\s*(.+)$", s)
        if m_prog:
            pct = max(0, min(100, int(m_prog.group(1))))
            detail = m_prog.group(2).strip()
            if outer_total > 1 and detail.startswith((
                "转写音频", "语音识别", "打开抖音", "上传视频",
                "填写标题", "选择AI", "设置作品", "等待预审", "发布完成", "自动填写完成",
            )) and outer_idx >= 1:
                last_pct = min(99, int(((outer_idx - 1) + pct / 100.0) * 100.0 / outer_total))
                last_text = f"[{outer_idx}/{outer_total}] {detail}"
            else:
                last_pct = pct
                last_text = detail
    return last_pct, last_text


def public_jobs():
    result = []
    with JOBS_LOCK:
        for job in JOBS.values():
            process = job["process"]
            code = process.poll()
            if code is not None and job["status"] == "running":
                job["returncode"] = code
                job["status"] = "completed" if code == 0 else "failed"
                job["stream"].close()
                if code != 0 and job.get("action") in (
                    "upload_douyin", "upload_selected"
                ):
                    outputs = job.get("payload", {}).get("outputs", [])
                    single = job.get("payload", {}).get("output", "")
                    if single:
                        outputs = [single]
                    for output in outputs:
                        try:
                            update_publish_status(
                                0, "douyin", "failed", output
                            )
                        except ValueError:
                            pass
            item = {k: v for k, v in job.items() if k not in ("process", "stream")}
            if item["status"] == "completed":
                item["progress"] = 100
                item["progress_text"] = "已完成"
            elif item["status"] == "running":
                pct, txt = _extract_job_progress(item.get("log", ""))
                item["progress"] = pct
                item["progress_text"] = txt or "运行中..."
            else:
                item["progress"] = None
                item["progress_text"] = ""
            result.append(item)
    return sorted(result, key=lambda x: -x["started_at"])

