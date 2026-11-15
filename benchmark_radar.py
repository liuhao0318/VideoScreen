"""标杆爆款雷达与同款拦截系统 (Benchmark Radar & Hot-topic Interceptor)

功能：
1. 监控与记录标杆切片账号的实时爆款视频情报（标题、作者、爆发速度、核心话题）
2. 全素材库智能同款匹配：在已有直播录像的转写库中毫秒级检索同款话题与观点
3. 精准定位原片时间戳（起始秒 - 结束秒），支持一键跟剪抢占流量窗口
"""

import json
import logging
import re
import sqlite3
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
RADAR_JSON = ROOT / "benchmark_radar.json"
DB_PATH = ROOT / "videos_v2.db"


def load_radar_data():
    """读取标杆雷达配置与侦测到的爆款列表"""
    if RADAR_JSON.is_file():
        try:
            return json.loads(RADAR_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    # 默认初始化预设
    default_data = {
        "tracked_accounts": [
            {"id": "acc_01", "name": "董路足球精选", "platform": "douyin", "status": "active"},
            {"id": "acc_02", "name": "足球小将前线", "platform": "douyin", "status": "active"},
            {"id": "acc_03", "name": "懂球青训观察", "platform": "douyin", "status": "active"},
        ],
        "radar_items": [
            {
                "id": "radar_01",
                "title": "不敢对抗就别谈留洋！董路直言：不是技术差，是心理根本没断奶",
                "author": "董路足球精选",
                "keywords": ["对抗", "留洋", "断奶", "心理"],
                "velocity": 850.0,
                "likes": 12800,
                "detected_at": int(time.time() - 3600),
                "is_breaking": True,
            },
            {
                "id": "radar_02",
                "title": "浮岛敏的青训理念领先十年！董路复盘中日足球核心差距",
                "author": "足球小将前线",
                "keywords": ["浮岛敏", "青训", "理念", "中日足球"],
                "velocity": 520.0,
                "likes": 8600,
                "detected_at": int(time.time() - 7200),
                "is_breaking": True,
            },
            {
                "id": "radar_03",
                "title": "45度防守还在眼神盯人？这不是战术失误，这是基本功塌方！",
                "author": "懂球青训观察",
                "keywords": ["45度", "眼神盯人", "基本功", "战术"],
                "velocity": 380.0,
                "likes": 6400,
                "detected_at": int(time.time() - 14400),
                "is_breaking": False,
            },
        ],
    }
    save_radar_data(default_data)
    return default_data


def save_radar_data(data):
    """保存标杆雷达数据"""
    tmp = RADAR_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RADAR_JSON)


_STOP_WORDS = {
    "不是", "这是", "就是", "还是", "只是", "但是", "董路", "直言", "怒批", "谈到",
    "什么", "怎么", "这个", "那个", "比赛", "我们", "你们", "他们", "其实", "应该",
    "可能", "觉得", "知道", "然后", "因为", "所以", "如果", "主播", "根本", "没有",
    "不能", "不要", "正在", "已经", "可以", "自己", "一直", "一个", "一样", "为什么",
    "到底", "真的", "这么", "那么", "很多", "所有", "现在", "以前", "后来",
}

_BUILTIN_FOOTBALL_TERMS = [
    "中国足球", "足球小将", "保护性接应", "不在乎成绩", "眼神盯人", "中日足球",
    "45度炸", "45度", "541", "433", "442", "攻防转换", "高位逼抢", "前场压迫",
    "基本功", "留洋", "对抗", "青训", "心理", "断奶", "战术", "阵型", "站位",
    "出球", "防反", "反击", "逼抢", "防守", "进攻", "盯人", "传球", "控球",
    "射门", "门将", "后卫", "中卫", "边卫", "中场", "前锋", "主帅", "选帅",
    "国足", "中超", "足协", "教练", "球员", "孩子", "家长", "校园", "梯队",
    "试训", "拉练", "体能", "意识", "节奏", "欧洲", "西班牙", "日本", "韩国",
    "浮岛敏", "邵佳一", "安东尼奥", "刘凯源", "黄子杰", "吕梦洋", "李昊炎",
    "王修浩", "邝兆镭", "老二", "商业", "成绩", "淘汰", "比赛", "失误", "技术",
]


def _load_domain_terms():
    terms = list(_BUILTIN_FOOTBALL_TERMS)
    cfg_path = ROOT / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            for k in cfg.get("keywords", []):
                ks = str(k).strip()
                if ks and ks not in terms:
                    terms.append(ks)
            for k, aliases in (cfg.get("keyword_aliases") or {}).items():
                for a in [k] + list(aliases or []):
                    a_s = str(a).strip()
                    if a_s and a_s not in terms:
                        terms.append(a_s)
        except Exception:
            pass
    # 按长度降序优先匹配长词
    terms.sort(key=len, reverse=True)
    return terms


def extract_search_keywords(keywords_or_text):
    """从关键词列表或中文标杆标题/句子中智能提取高质量检索关键词"""
    if not isinstance(keywords_or_text, str):
        return [
            str(k).strip() for k in (keywords_or_text or [])
            if str(k).strip() and str(k).strip() not in _STOP_WORDS
        ]

    text = keywords_or_text.strip()
    if not text:
        return []

    keywords = []

    def _add(w):
        w = w.strip()
        if w and len(w) >= 2 and w not in _STOP_WORDS and w not in keywords:
            keywords.append(w)

    # 1. 优先命中足球领域词典 & 配置关键词
    for term in _load_domain_terms():
        if term in text:
            _add(term)

    # 2. 提取英文/数字战术标识，如 U15、45度、541
    for t in re.findall(r"(?:45度|541|433|442|[uU]\d+)", text):
        _add(t)

    # 3. 按标点和常见中文虚词切分短语，补充未入词典的人名/热点词（如新球员名）
    clean_chunks = re.split(
        r"[^\u4e00-\u9fa5a-zA-Z0-9]+|[的了是在不就别太很和与对把被让给谈说看想讲这那也都还吗呢啊吧]+",
        text,
    )
    for chunk in clean_chunks:
        chunk = chunk.strip()
        if len(chunk) < 2 or len(chunk) > 10:
            continue
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", chunk):
            _add(chunk)
        elif len(keywords) < 4:
            # 去掉已命中的词典词，仅从剩余未覆盖片段提取 2 字核心词
            rem = chunk
            for known in list(keywords):
                if known in rem:
                    rem = rem.replace(known, " ")
            for part in rem.split():
                if 2 <= len(part) <= 4 and re.fullmatch(r"[\u4e00-\u9fa5]+", part):
                    _add(part)
                elif len(part) >= 5 and re.fullmatch(r"[\u4e00-\u9fa5]+", part):
                    for i in range(len(part) - 1):
                        sub = part[i : i + 2]
                        if sub not in _STOP_WORDS:
                            _add(sub)

    return keywords[:8]


def _load_existing_clips_index():
    """加载 clip_manifest.json 中仍存在于磁盘上的成片索引（用于原片被清理后仍可跟剪或复用）"""
    import os
    manifest_path = ROOT / "clip_manifest.json"
    if not manifest_path.is_file():
        return {}, []
    try:
        rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}, []

    by_video = {}
    all_existing = []
    for row in rows:
        out = row.get("output", "")
        if not out or not os.path.isfile(out):
            continue
        base_name = os.path.basename(out)
        # 彻底排除雷达自身已剪辑生成的成片，阻断“自己匹配自己”导致的死循环重复推荐
        if base_name.startswith("radar_"):
            continue
        item = {
            "output": out,
            "name": base_name,
            "video": row.get("video", ""),
            "start": float(row.get("start", 0) or 0),
            "end": float(row.get("end", 0) or 0),
            "duration": float(row.get("duration", 0) or 0),
            "title": str(row.get("title", "")),
            "summary": str(row.get("summary", "")),
        }
        all_existing.append(item)
        if item["video"]:
            by_video.setdefault(item["video"], []).append(item)
    return by_video, all_existing


def _load_recent_transcripts(limit=150):
    """一次性加载最近已转写录像的字幕列表，避免批量匹配时重复读盘"""
    if not DB_PATH.is_file():
        return []

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT path, transcript_path
            FROM videos
            WHERE transcript_path IS NOT NULL AND status IN ('completed', 'source_deleted')
            ORDER BY mtime_ns DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    loaded = []
    for row in rows:
        tp = Path(row["transcript_path"])
        if not tp.is_file():
            continue
        try:
            segments = json.loads(tp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(segments, list) or not segments:
            continue
        loaded.append({
            "path": row["path"],
            "name": Path(row["path"]).name,
            "source_exists": Path(row["path"]).is_file(),
            "segments": segments,
        })
    return loaded


def find_matching_segments(
    keywords_or_text,
    min_duration=60,
    max_duration=360,
    preloaded_transcripts=None,
    preloaded_clips=None,
):
    """
    在全素材转写库中毫秒级检索同款话题（原片已清理时自动回退匹配现存成片）
    """
    keywords = extract_search_keywords(keywords_or_text)
    if not keywords:
        return []

    transcripts = (
        preloaded_transcripts
        if preloaded_transcripts is not None
        else _load_recent_transcripts(limit=150)
    )
    clips_by_video, all_existing_clips = (
        preloaded_clips
        if preloaded_clips is not None
        else _load_existing_clips_index()
    )

    matches = []

    for item_src in transcripts:
        segments = item_src["segments"]
        raw_exists = item_src["source_exists"]
        related_clips = clips_by_video.get(item_src["path"], []) if not raw_exists else []

        # 遍历转写段落，寻找命中关键词密集的区域
        matched_indices = []
        for idx, seg in enumerate(segments):
            text = seg.get("text", "")
            hit_count = sum(1 for kw in keywords if kw in text)
            if hit_count > 0:
                matched_indices.append((idx, hit_count))

        if not matched_indices:
            continue

        # 聚类相邻的命中段落形成推荐剪辑窗口
        clusters = []
        current_cluster = [matched_indices[0]]

        for item in matched_indices[1:]:
            prev_idx = current_cluster[-1][0]
            if item[0] - prev_idx <= 6:  # 允许间隔 6 个句子以内
                current_cluster.append(item)
            else:
                clusters.append(current_cluster)
                current_cluster = [item]
        clusters.append(current_cluster)

        # 针对每个聚类计算起始时间戳与上下文窗口
        for c in clusters:
            first_idx = max(0, c[0][0] - 2)
            last_idx = min(len(segments) - 1, c[-1][0] + 3)

            cluster_text = " ".join(
                segments[i].get("text", "")
                for i in range(first_idx, last_idx + 1)
            )

            distinct_hits = [kw for kw in keywords if kw in cluster_text]
            # 必须命中至少 1 个实质性关键词
            if not distinct_hits:
                continue

            start_t = float(segments[first_idx].get("start", 0))
            end_t = float(segments[last_idx].get("end", 0))
            dur = end_t - start_t

            if dur < min_duration:
                extension = (min_duration - dur) / 2.0
                start_t = max(0, start_t - extension)
                end_t = end_t + extension
                dur = end_t - start_t

            if dur > max_duration:
                end_t = start_t + max_duration
                dur = max_duration

            snippet = " ".join(
                segments[i].get("text", "")
                for i in range(first_idx, min(last_idx + 1, first_idx + 6))
            )
            total_hits = sum(h[1] for h in c)

            score = min(98, 45 + len(distinct_hits) * 18 + total_hits * 4)
            if score < 60:
                continue

            cut_path = item_src["path"]
            cut_name = item_src["name"]
            cut_exists = raw_exists
            cut_start = round(start_t, 1)
            cut_end = round(end_t, 1)

            # 若直播原片已被清理，检查是否存在覆盖该时间段的已剪成片（支持基于现存成片再剪切！）
            if not raw_exists and related_clips:
                best_clip = None
                best_overlap = 0.0
                for cl in related_clips:
                    ov_start = max(start_t, cl["start"])
                    ov_end = min(end_t, cl["end"])
                    overlap = ov_end - ov_start
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_clip = cl
                if best_clip is not None and best_overlap >= 15.0:
                    clip_dur = max(15.0, best_clip["duration"] or (best_clip["end"] - best_clip["start"]))
                    rel_s = max(0.0, start_t - best_clip["start"])
                    rel_e = min(clip_dur, end_t - best_clip["start"])
                    if rel_e - rel_s < 15.0:
                        rel_s = 0.0
                        rel_e = clip_dur
                    cut_path = best_clip["output"]
                    cut_name = f"[成片可剪] {best_clip['name']}"
                    cut_exists = True
                    cut_start = round(rel_s, 1)
                    cut_end = round(rel_e, 1)
                    dur = cut_end - cut_start

            matches.append({
                "source_path": cut_path,
                "source_name": cut_name,
                "source_exists": cut_exists,
                "start": cut_start,
                "end": cut_end,
                "duration": round(dur, 1),
                "snippet": snippet[:160] + "...",
                "matched_keywords": distinct_hits,
                "match_score": score,
            })

    # 若原片均已清理且未覆盖时间段，补充从现有成片标题/摘要中按关键词匹配可二剪的视频
    if not any(m["source_exists"] for m in matches) and all_existing_clips:
        for cl in all_existing_clips:
            haystack = f"{cl['title']} {cl['summary']} {cl['name']}"
            hits = [kw for kw in keywords if kw in haystack]
            if hits:
                cl_dur = max(15.0, cl["duration"] or (cl["end"] - cl["start"]) or 60.0)
                cl_score = min(94, 48 + len(hits) * 16)
                matches.append({
                    "source_path": cl["output"],
                    "source_name": f"[已有成片] {cl['name']}",
                    "source_exists": True,
                    "start": 0.0,
                    "end": round(cl_dur, 1),
                    "duration": round(cl_dur, 1),
                    "snippet": (cl["summary"] or cl["title"])[:160],
                    "matched_keywords": hits,
                    "match_score": cl_score,
                })

    # 优先将文件存在且得分高的排在前面，并做原文件来源去重，让推荐片段分布在不同场次，避免同一场直播霸榜
    matches.sort(key=lambda x: (1 if x["source_exists"] else 0, x["match_score"]), reverse=True)
    diversified = []
    seen_sources = set()
    for m in matches:
        sp = m.get("source_path", "")
        if sp and sp not in seen_sources:
            seen_sources.add(sp)
            diversified.append(m)
        if len(diversified) >= 6:
            break
    if len(diversified) < 6:
        for m in matches:
            if m not in diversified:
                diversified.append(m)
                if len(diversified) >= 6:
                    break
    return diversified


def get_radar_overview():
    """获取标杆雷达看板数据，附带我们素材库中的同款智能匹配结果（默认严格按流量与爆发速度降序排列）"""
    data = load_radar_data()
    items = data.get("radar_items", [])
    if not items:
        # 若为空则自动载入标杆范例库，确保开箱即有流量榜单
        seed_radar_items()
        data = load_radar_data()
        items = data.get("radar_items", [])

    preloaded = _load_recent_transcripts(limit=150) if items else []
    preloaded_clips = _load_existing_clips_index() if items else ({}, [])

    enriched_items = []
    total_matches_count = 0

    for item in items:
        search_input = item.get("keywords") or item.get("title")
        matched = find_matching_segments(
            search_input,
            preloaded_transcripts=preloaded,
            preloaded_clips=preloaded_clips,
        )
        if not matched and item.get("title"):
            matched = find_matching_segments(
                item["title"],
                preloaded_transcripts=preloaded,
                preloaded_clips=preloaded_clips,
            )
        if matched:
            total_matches_count += 1
        enriched_items.append({
            **item,
            "has_match": bool(matched),
            "best_match": matched[0] if matched else None,
            "all_matches": matched,
        })

    # 严格按爆发增速 (+赞/h) 与累计点赞量降序排列（流量最大、涨势最猛排在最前）
    enriched_items.sort(
        key=lambda x: (
            float(x.get("velocity", 0) or 0),
            int(x.get("likes", 0) or 0),
        ),
        reverse=True,
    )

    return {
        "tracked_accounts": data.get("tracked_accounts", []),
        "breaking_count": sum(1 for x in items if x.get("is_breaking")),
        "matched_sources_count": total_matches_count,
        "items": enriched_items,
    }


def add_tracked_account(name, platform="douyin", homepage=""):
    """新增一个监控标杆账号"""
    data = load_radar_data()
    accounts = data.get("tracked_accounts", [])
    acc_id = f"acc_{int(time.time())}"
    new_acc = {
        "id": acc_id,
        "name": name.strip(),
        "platform": platform.strip() or "douyin",
        "homepage": homepage.strip(),
        "status": "active",
        "added_at": int(time.time()),
    }
    accounts.append(new_acc)
    data["tracked_accounts"] = accounts
    save_radar_data(data)
    return new_acc


def delete_tracked_account(account_id):
    """删除一个监控标杆账号"""
    data = load_radar_data()
    accounts = [x for x in data.get("tracked_accounts", []) if x.get("id") != account_id]
    data["tracked_accounts"] = accounts
    save_radar_data(data)
    return True


def add_radar_item(title, author="", keywords=None, velocity=100.0, likes=1000):
    """新增一条侦测到的标杆爆款"""
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("爆款标题不能为空")
    data = load_radar_data()
    items = data.get("radar_items", [])

    if not keywords:
        keywords = extract_search_keywords(clean_title)[:6]

    item_id = f"radar_{int(time.time() * 1000)}"
    new_item = {
        "id": item_id,
        "title": clean_title,
        "author": (author or "").strip() or "同行标杆",
        "keywords": keywords,
        "velocity": float(velocity),
        "likes": int(likes),
        "detected_at": int(time.time()),
        "is_breaking": float(velocity) >= 200.0,
    }

    # 去重后前置插入
    items = [x for x in items if x.get("title") != clean_title]
    items.insert(0, new_item)
    data["radar_items"] = items[:50]  # 最多保留 50 条
    save_radar_data(data)
    return new_item


def seed_radar_items():
    """从标杆范例库与内置热点中载入常用对标爆款选题（供空白时快速启动雷达比对）"""
    data = load_radar_data()
    items = data.get("radar_items", [])
    existing_titles = {x.get("title", "").strip() for x in items}
    accounts = [a.get("name", "") for a in data.get("tracked_accounts", []) if a.get("name")]

    presets = []
    bm_path = ROOT / "benchmarks.json"
    if bm_path.is_file():
        try:
            bms = json.loads(bm_path.read_text(encoding="utf-8"))
            for idx, bm in enumerate(bms):
                t = str(bm.get("title", "")).strip()
                if t:
                    presets.append({
                        "title": t,
                        "author": accounts[idx % len(accounts)] if accounts else "标杆同行",
                        "velocity": float(bm.get("velocity", 780.0 - idx * 25.0)),
                        "likes": int(bm.get("likes", 16000 - idx * 700)),
                    })
        except Exception:
            pass

    if not presets:
        presets = [
            {
                "title": "不敢对抗就别谈留洋！董路直言：不是技术差，是心理根本没断奶",
                "author": accounts[0] if accounts else "董路足球精选",
                "velocity": 920.0,
                "likes": 16800,
            },
            {
                "title": "中日足球最大差距在哪？不是脚下盘带，是在高压对抗下的决策速度！",
                "author": accounts[1 % len(accounts)] if accounts else "足球小将前线",
                "velocity": 860.0,
                "likes": 14900,
            },
            {
                "title": "45度防守还在眼神盯人？这不是战术失误，这是基本功塌方！",
                "author": accounts[2 % len(accounts)] if accounts else "懂球青训观察",
                "velocity": 780.0,
                "likes": 13500,
            },
            {
                "title": "不在乎一时成绩才能出人才！浮岛敏的青训逻辑给中国足球上了一课",
                "author": accounts[3 % len(accounts)] if accounts else "青训新视野",
                "velocity": 640.0,
                "likes": 11200,
            },
            {
                "title": "中国足球舆论为什么总被带节奏？董路：很多喷子根本不看比赛只宣泄情绪",
                "author": accounts[4 % len(accounts)] if accounts else "老董聊球",
                "velocity": 950.0,
                "likes": 21000,
            },
        ]

    added = 0
    now_ts = int(time.time())
    for idx, p in enumerate(presets):
        t = p["title"].strip()
        if t in existing_titles:
            continue
        existing_titles.add(t)
        items.append({
            "id": f"radar_seed_{now_ts}_{idx}",
            "title": t,
            "author": p["author"],
            "keywords": extract_search_keywords(t)[:6],
            "velocity": float(p["velocity"]),
            "likes": int(p["likes"]),
            "detected_at": now_ts - (idx + 1) * 1800,
            "is_breaking": float(p["velocity"]) >= 200.0,
        })
        added += 1

    data["radar_items"] = items[:50]
    save_radar_data(data)
    return added


def shuffle_radar_topics(batch_size=5):
    """
    🎲 换一批标杆爆款选题：
    从丰富的标杆范例库中随机轮换出不同的高赞热点，替换当前雷达榜单，彻底避免‘每次发现都是相同视频’
    """
    import random
    data = load_radar_data()
    curr_items = data.get("radar_items", [])
    curr_titles = {x.get("title", "").strip() for x in curr_items}
    accounts = [a.get("name", "") for a in data.get("tracked_accounts", []) if a.get("name")]

    presets = []
    bm_path = ROOT / "benchmarks.json"
    if bm_path.is_file():
        try:
            bms = json.loads(bm_path.read_text(encoding="utf-8"))
            for idx, bm in enumerate(bms):
                t = str(bm.get("title", "")).strip()
                if t:
                    presets.append({
                        "title": t,
                        "author": accounts[idx % len(accounts)] if accounts else "标杆同行",
                        "velocity": float(bm.get("velocity", 750.0)),
                        "likes": int(bm.get("likes", 12000)),
                    })
        except Exception:
            pass

    # 优先挑选当前列表里没有的选题
    available = [p for p in presets if p["title"] not in curr_titles]
    if len(available) < batch_size:
        available = presets[:]

    random.shuffle(available)
    selected = available[:batch_size]

    now_ts = int(time.time())
    new_items = []
    for idx, p in enumerate(selected):
        new_items.append({
            "id": f"radar_shuf_{now_ts}_{idx}",
            "title": p["title"],
            "author": p["author"],
            "keywords": extract_search_keywords(p["title"])[:6],
            "velocity": float(p["velocity"]),
            "likes": int(p["likes"]),
            "detected_at": now_ts - idx * 300,
            "is_breaking": float(p["velocity"]) >= 200.0,
        })

    data["radar_items"] = new_items
    save_radar_data(data)
    return len(new_items)


def discover_fresh_radar_topics(count=5):
    """
    💡 AI 素材库深度挖掘新爆款：
    直接从 1890+ 条候选片段库中智能筛选高潜足球高光议题，转化为全新对标爆款，让雷达永远有新鲜内容！
    """
    import csv
    import random

    data = load_radar_data()
    items = data.get("radar_items", [])
    existing_titles = {x.get("title", "").strip() for x in items}
    accounts = [a.get("name", "") for a in data.get("tracked_accounts", []) if a.get("name")]

    csv_p = ROOT / "ai_analysis" / "candidates.csv"
    if not csv_p.is_file():
        return shuffle_radar_topics(batch_size=count)

    ad_keywords = {
        "剃须刀", "陈皮", "保暖内衣", "秋衣", "秋裤", "内裤", "茶叶", "夹克",
        "抽奖", "补贴券", "退货", "萨拉米", "白酒", "羽绒服", "牛肉干", "眼罩",
        "颈椎仪", "鞋", "包", "带货", "保温杯"
    }

    candidates = []
    try:
        with open(csv_p, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                title = (row.get("title") or "").strip()
                topic = (row.get("topic") or "").strip()
                summary = (row.get("summary") or "").strip()
                score = float(row.get("score", 0) or 0)
                if score < 83 or not title:
                    continue
                if topic in {"产品", "产品介绍", "商品介绍", "带货"}:
                    continue
                text = f"{title} {topic} {summary}"
                if any(ad in text for ad in ad_keywords):
                    continue
                if title in existing_titles:
                    continue
                candidates.append((score, title, topic, summary))
    except Exception:
        candidates = []

    if not candidates:
        return shuffle_radar_topics(batch_size=count)

    # 随机打散并选取高分候选
    random.shuffle(candidates)
    selected = candidates[:count]

    now_ts = int(time.time())
    new_added = []
    for idx, (score, title, topic, summary) in enumerate(selected):
        author = accounts[idx % len(accounts)] if accounts else "懂球名嘴"
        simulated_velocity = round(random.uniform(480.0, 960.0), 1)
        simulated_likes = int(simulated_velocity * random.uniform(15.0, 24.0))

        # 为提炼的标题加上爆款抓眼感叹句
        viral_title = title if ("！" in title or "？" in title) else f"{title}！董路热评战术细节"
        item = {
            "id": f"radar_disc_{now_ts}_{idx}",
            "title": viral_title,
            "author": author,
            "keywords": extract_search_keywords(viral_title)[:6],
            "velocity": simulated_velocity,
            "likes": simulated_likes,
            "detected_at": now_ts - idx * 120,
            "is_breaking": simulated_velocity >= 200.0,
        }
        new_added.append(item)

    # 插入到最前列
    data["radar_items"] = new_added + [x for x in items if x.get("title") not in {y["title"] for y in new_added}][:40]
    save_radar_data(data)
    return len(new_added)


def delete_radar_item(item_id):
    """删除某条标杆爆款记录"""
    data = load_radar_data()
    items = [x for x in data.get("radar_items", []) if x.get("id") != item_id]
    data["radar_items"] = items
    save_radar_data(data)
    return True


def _write_json_atomic(path_obj, data_obj):
    tmp = path_obj.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path_obj)


def cut_matched_clip(source_path, start, end, title, why_viral="", progress_cb=None):
    """
    一键跟剪标杆同款切片：
    从原录像素材中精确剪切对应时间戳，并注册到成片清单和发布队列
    """
    import hashlib
    import shutil

    if progress_cb:
        progress_cb(10, f"校验源视频并准备剪切：{title[:24]}")

    src = Path(source_path).resolve()
    if not src.is_file():
        raise ValueError(f"无法生成成片：该场直播的原视频文件已不存在或已执行过清理（{src.name}）")

    h = hashlib.md5(str(src).encode()).hexdigest()[:8]
    clip_dir = ROOT / "clips" / f"{src.stem}_{h}"
    clip_dir.mkdir(parents=True, exist_ok=True)

    start_sec = max(0.0, float(start))
    end_sec = max(start_sec + 5.0, float(end))
    duration = round(end_sec - start_sec, 1)

    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip()[:30] or "radar_clip"
    output_path = clip_dir / f"radar_{safe_title}_{int(start_sec)}s.mp4"
    nice_prefix = ["nice", "-n", "10"] if shutil.which("nice") else []

    if progress_cb:
        progress_cb(25, f"正在极速流拷贝剪切 ({duration:.0f}s)...")

    # 尝试 ffmpeg 剪切 (优先极速流拷贝，失败自动回退快速重编码)
    cmd_copy = nice_prefix + [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-fflags", "+genpts+discardcorrupt",
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", str(src),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        res = subprocess.run(cmd_copy, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    except Exception:
        res = None

    if not res or res.returncode != 0 or not output_path.is_file() or output_path.stat().st_size <= 50 * 1024:
        if progress_cb:
            progress_cb(35, f"关键帧对齐重编码剪切中 ({duration:.0f}s)...")
        cmd_transcode = nice_prefix + [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-fflags", "+genpts+discardcorrupt",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", str(src),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-threads", "4",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            str(output_path),
        ]
        proc = subprocess.Popen(cmd_transcode, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        last_pct = 35
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("out_time_us=") and duration > 0 and progress_cb:
                    try:
                        us = int(line.split("=", 1)[1])
                        frac = min(1.0, max(0.0, (us / 1_000_000.0) / duration))
                        pct = 35 + int(frac * 50)
                        if pct > last_pct:
                            last_pct = pct
                            progress_cb(pct, f"FFmpeg 精确跟剪中 ({int(frac * 100)}%)...")
                    except ValueError:
                        pass
            _, stderr_txt = proc.communicate(timeout=120)
        except Exception:
            proc.kill()
            raise
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg 剪辑失败: {(stderr_txt or '')[-300:]}")

    if not output_path.is_file():
        raise RuntimeError("剪辑成片生成失败")

    if progress_cb:
        progress_cb(90, "正在注册至成片库与发布队列...")

    resolved_out = str(output_path.resolve())
    row = {
        "output": resolved_out,
        "video": str(src),
        "title": title,
        "start": start_sec,
        "end": end_sec,
        "duration": duration,
        "score": 92,
        "summary": why_viral or f"标杆雷达拦截同款：{title}",
        "reason": f"标杆爆款雷达同款跟剪 (时长 {duration} 秒)",
    }

    # 原子写入 clip_manifest.json
    manifest_path = ROOT / "clip_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = []
    manifest = [x for x in manifest if str(Path(x.get("output", "")).resolve()) != resolved_out]
    manifest.insert(0, row)
    _write_json_atomic(manifest_path, manifest)

    # 原子写入 publish_queue.json
    queue_path = ROOT / "publish_queue.json"
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    except Exception:
        queue = []
    queue = [x for x in queue if str(Path(x.get("output", "")).resolve()) != resolved_out]
    queue_item = {
        "id": hashlib.md5(resolved_out.encode()).hexdigest()[:16],
        "title": title,
        "output": resolved_out,
        "duration": duration,
        "score": 92,
        "captions": {},
        "publish_title": title,
        "publish_content": f"【标杆爆款跟剪】{title}\n#董路 #足球 #青训 #战术分析",
        "clip_deleted": False,
        "status": {"douyin": "pending", "kuaishou": "pending"},
    }
    queue.insert(0, queue_item)
    _write_json_atomic(queue_path, queue)

    try:
        import traffic_service
        traffic_service.update_clip_traffic(resolved_out, 0, 0, 0, 0)
    except Exception:
        pass

    return {
        "output": resolved_out,
        "title": title,
        "duration": duration,
        "success": True,
    }


