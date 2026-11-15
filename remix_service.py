"""标杆视频无水印下载与智能二次创作引擎 (Benchmark Video Downloader & Secondary Creation Engine)

功能：
1. 解析并下载抖音/快手标杆视频的高清无水印视频
2. 全自动深度二次创作重构（画面指纹打破、微无感变速、画质增强、去重调色）
3. AI 重新提炼黄金 3 秒爆款标题与专业评论发布文案
4. 自动注册入成片库与待发布队列，实现一键从同行动向到原创跟发的全闭环
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DOWNLOADS_DIR = ROOT / "downloads_radar"
CLIPS_DIR = ROOT / "clips"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
USER_AGENT_PC = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def extract_url_from_text(text):
    """从用户的粘贴文本（如包含标题、复制提示和短链接的文本）中提取真实 URL"""
    if not text:
        return ""
    matches = re.findall(r"https?://[a-zA-Z0-9./_?=&%-]+", str(text))
    return matches[0] if matches else str(text).strip()


def resolve_douyin_video_info(share_url):
    """
    解析抖音分享链接，提取无水印视频直链与原标题
    支持短链接 v.douyin.com 和长链接 www.douyin.com/video/...
    """
    clean_url = extract_url_from_text(share_url)
    if not clean_url:
        raise ValueError("未检测到有效的视频链接")

    # 1. 如果已是本地视频文件路径
    local_path = Path(clean_url).expanduser().resolve()
    if local_path.is_file():
        return {
            "title": local_path.stem,
            "play_url": str(local_path),
            "is_local": True,
            "author": "本地导入",
        }

    # 2. 如果已是直链 mp4
    if clean_url.split("?")[0].lower().endswith(".mp4"):
        return {
            "title": "直链视频_" + str(int(time.time())),
            "play_url": clean_url,
            "is_local": False,
            "author": "标杆作品",
        }

    # 3. 处理短链接跳转获取实际视频 ID
    req = urllib.request.Request(clean_url, headers={"User-Agent": USER_AGENT_MOBILE})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            final_url = resp.geturl()
    except Exception as e:
        final_url = clean_url

    # 从 URL 中提取 item_id / video_id
    video_id_match = re.search(r"/(?:video|note)/(\d+)", final_url) or re.search(r"modal_id=(\d+)", final_url)
    if not video_id_match:
        video_id_match = re.search(r"(\d{18,21})", final_url)

    if not video_id_match:
        # 如果是其他平台网页，尝试使用 yt-dlp 或通用探测
        return probe_generic_video(clean_url)

    video_id = video_id_match.group(1)

    # 4. 请求官方移动端接口获取详情
    api_url = f"https://www.iesdouyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=1128&version_name=23.5.0&device_platform=android&os_version=2333"
    api_req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": USER_AGENT_MOBILE,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(api_req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        aweme = data.get("aweme_detail", {})
        title = aweme.get("desc", f"douyin_{video_id}")
        author = aweme.get("author", {}).get("nickname", "标杆切片号")

        video_info = aweme.get("video", {})
        play_list = video_info.get("play_addr", {}).get("url_list", [])
        if not play_list:
            play_list = video_info.get("bit_rate", [{}])[0].get("play_addr", {}).get("url_list", [])

        if not play_list:
            raise ValueError("未能从解析数据中获取到播放地址")

        # 替换水印标识以获取无水印源文件
        raw_play_url = play_list[0]
        nwm_url = raw_play_url.replace("playwm", "play")

        return {
            "title": title.strip() or f"douyin_{video_id}",
            "play_url": nwm_url,
            "is_local": False,
            "author": author,
            "video_id": video_id,
        }
    except Exception as err:
        logger.warning(f"API 解析失败，尝试备用探测: {err}")
        return probe_generic_video(clean_url)


def probe_generic_video(url):
    """通用备用探测"""
    # 尝试通过 yt-dlp 抓取流地址（如果安装）
    try:
        cmd = ["yt-dlp", "-g", "-f", "best", url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            return {
                "title": "标杆视频_" + str(int(time.time())),
                "play_url": res.stdout.strip().split("\n")[0],
                "is_local": False,
                "author": "同行标杆",
            }
    except Exception:
        pass

    raise ValueError(
        "无法自动解析该视频链接（目标平台可能存在反爬/验证码限制）。"
        "建议：1) 将原视频下载到本地后直接填入本地 .mp4 路径进行二创；"
        "2) 或复制对方标题在“全素材库同款检索”中定位自己直播原声片段一键跟剪。"
    )


def download_video_file(url, target_path, progress_cb=None):
    """将视频流安全下载到本地"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT_PC,
            "Referer": "https://www.douyin.com/",
        },
    )
    downloaded = 0
    with urllib.request.urlopen(req, timeout=60) as resp, open(target_path, "wb") as out_f:
        total_bytes = 0
        try:
            total_bytes = int(resp.headers.get("Content-Length") or 0)
        except ValueError:
            total_bytes = 0
        while True:
            chunk = resp.read(1024 * 512)  # 512KB chunks
            if not chunk:
                break
            out_f.write(chunk)
            downloaded += len(chunk)
            if progress_cb:
                mb = downloaded / (1024 * 1024)
                if total_bytes > 0:
                    frac = min(1.0, downloaded / total_bytes)
                    pct = 15 + int(frac * 30)
                    progress_cb(pct, f"正在下载高清原片 ({mb:.1f} MB / {total_bytes/(1024*1024):.1f} MB)")
                else:
                    progress_cb(25, f"正在下载高清原片 ({mb:.1f} MB)")

    if not target_path.is_file() or target_path.stat().st_size < 10000:
        raise RuntimeError("下载失败：生成文件过小或为空")
    return target_path


def _probe_duration(video_path):
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            return max(0.1, float(res.stdout.strip()))
    except Exception:
        pass
    return 0.0


def apply_secondary_remix(
    input_video,
    output_video,
    speed_factor=1.02,
    crop_pct=0.03,
    color_grade=True,
    sharpen=True,
    add_top_banner=True,
    banner_text="【董路足球深度复盘】",
    progress_cb=None,
):
    """
    全自动深度二次创作与画质指纹打破引擎：
    1. 边缘智能微裁剪 3%（彻底去除原作者残留的边缘水印和标识）
    2. 无感智能微变速 1.02x（音画帧时间戳全面打破原始 MD5 和时间指纹）
    3. 专业调色增强（对比度 +4%，饱和度 +8%，色彩更饱满通透）
    4. 画面轻度锐化（提升画质清晰度，消除多层压制模糊）
    5. 可选顶部/上下画框包装，重构画面视觉构图
    """
    src = Path(input_video).resolve()
    dst = Path(output_video).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    # 构建视频滤镜链
    vf_filters = []

    # 1. 边缘微裁切 (去除水印及边缘指纹)
    crop_w = round(1.0 - crop_pct * 2, 3)
    crop_h = round(1.0 - crop_pct * 2, 3)
    vf_filters.append(f"crop=in_w*{crop_w}:in_h*{crop_h}")

    # 2. 调色增强 (对比度与饱和度微调)
    if color_grade:
        vf_filters.append("eq=contrast=1.05:brightness=0.01:saturation=1.08")

    # 3. 画面锐化 (提升画质通透感)
    if sharpen:
        vf_filters.append("unsharp=3:3:0.8:3:3:0.0")

    # 4. 视频微调变速 (setpts)
    pts_factor = round(1.0 / speed_factor, 4)
    vf_filters.append(f"setpts={pts_factor}*PTS")

    vf_string = ",".join(vf_filters)

    # 音频微调变速 (atempo) 与重新编码
    af_string = f"atempo={speed_factor}"

    import shutil
    nice_prefix = ["nice", "-n", "10"] if shutil.which("nice") else []
    cmd = nice_prefix + [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", vf_string,
        "-af", af_string,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-threads", "4",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-progress", "pipe:1",
        str(dst),
    ]

    total_sec = _probe_duration(src)
    expected_out_sec = (total_sec / max(0.5, speed_factor)) if total_sec > 0 else 0.0
    if progress_cb:
        progress_cb(48, "正在执行 FFmpeg 画质去重、微变速与调色渲染...")

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    last_pct = 48
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") and expected_out_sec > 0 and progress_cb:
                try:
                    us = int(line.split("=", 1)[1])
                    cur_s = us / 1_000_000.0
                    frac = min(1.0, max(0.0, cur_s / expected_out_sec))
                    pct = 48 + int(frac * 37)  # 48% -> 85%
                    if pct > last_pct:
                        last_pct = pct
                        progress_cb(pct, f"FFmpeg 二创渲染中 ({int(frac * 100)}% · {cur_s:.0f}s/{expected_out_sec:.0f}s)")
                except ValueError:
                    pass
        _, stderr_txt = proc.communicate(timeout=300)
    except Exception:
        proc.kill()
        raise

    if proc.returncode != 0 or not dst.is_file():
        logger.error(f"FFmpeg Remix 失败: {stderr_txt}")
        raise RuntimeError(f"二次创作视频渲染失败：{(stderr_txt or '')[-300:]}")

    return dst


def process_benchmark_url_to_remix(share_link_or_text, custom_title="", speed_factor=1.02, progress_cb=None):
    """
    一键从标杆短视频链接全自动二次创作：
    1. 解析并下载无水印高清原片
    2. 执行深度二次创作与音画指纹重构
    3. 调用大模型 AI 重新撰写黄金 3 秒爆款标题与发布文案
    4. 自动注册到成片库置顶并推入待发布队列
    """
    if progress_cb:
        progress_cb(5, "正在解析视频链接与源文件...")
    info = resolve_douyin_video_info(share_link_or_text)
    raw_title = custom_title.strip() or info.get("title", "标杆二次创作作品")
    clean_title = re.sub(r'[\\/:*?"<>|]+', "_", raw_title).strip()[:35] or f"remix_{int(time.time())}"

    # 1. 准备下载路径
    url_hash = hashlib.md5(share_link_or_text.encode()).hexdigest()[:8]
    if info.get("is_local"):
        downloaded_file = Path(info["play_url"])
        if progress_cb:
            progress_cb(45, f"已载入本地视频：{downloaded_file.name}")
    else:
        if progress_cb:
            progress_cb(15, "正在下载无水印高清原片...")
        temp_download_name = f"raw_{int(time.time())}_{url_hash}.mp4"
        temp_download_path = DOWNLOADS_DIR / temp_download_name
        downloaded_file = download_video_file(info["play_url"], temp_download_path, progress_cb=progress_cb)

    # 2. 执行 ffmpeg 深度二次创作
    remix_dir = CLIPS_DIR / f"remix_{int(time.time())}_{url_hash}"
    remix_dir.mkdir(parents=True, exist_ok=True)
    output_remix_path = remix_dir / f"remix_{clean_title}.mp4"

    apply_secondary_remix(
        input_video=downloaded_file,
        output_video=output_remix_path,
        speed_factor=speed_factor,
        crop_pct=0.03,
        color_grade=True,
        sharpen=True,
        progress_cb=progress_cb,
    )

    if progress_cb:
        progress_cb(87, "正在读取二创成片时长并调用 AI 重写爆款文案...")

    # 获取视频时长
    duration = round(_probe_duration(output_remix_path) or 60.0, 1)

    # 3. 组织 AI 发布文案与标题
    # 生成对齐标杆风格的全新爆款文案
    publish_title = f"【深度复盘】{clean_title}"
    publish_content = (
        f"【战术与青训深度二次创作】{clean_title}\n"
        f"观点分析：从比赛实战逻辑与年轻球员成长来看，战术执行力与对抗细节直接决定胜负走向。\n"
        f"声明：本视频为赛事精选战术二创与评论解读。\n"
        f"#董路 #足球 #青训 #中国足球 #战术分析"
    )

    try:
        # 尝试调用大模型重写更惊艳的文案
        import ai_service
        prompt = f"""
请为一条经过二次创作的董路足球精选短视频撰写抖音发布标题和文案。
原视频主题：{raw_title}
视频时长：{duration}秒

硬性要求：
1. 必须紧扣原视频主题撰写，严禁脑补未出现的人物、比赛结果、数据或战术名词。
2. 若原视频主题中出现具体人名（球员、教练等），标题和正文中必须保留该人名。
3. 标题控制在 12~26 字，准确直白或适度有张力；正文 2~3 句简洁陈述核心看点，最后附一句二创说明。
4. 仅返回JSON：{{"title":"发布标题","content":"发布文案","tags":["董路","足球"]}}
"""
        ai_res = ai_service.chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.25,
            json_format=True,
            timeout=25,
        )
        if isinstance(ai_res, dict) and ai_res.get("title"):
            publish_title = ai_res["title"]
            tags_str = " ".join(f"#{t.replace('#', '')}" for t in ai_res.get("tags", ["董路", "足球", "青训"]))
            publish_content = f"{ai_res.get('content', publish_content)}\n{tags_str}"
    except Exception as e:
        logger.warning(f"AI 重写文案失败，使用默认模版: {e}")

    if progress_cb:
        progress_cb(95, "正在写入成片清单与待发布队列...")

    # 4. 注册到成片库 clip_manifest.json (置顶)
    manifest_item = {
        "output": str(output_remix_path.resolve()),
        "video": str(downloaded_file.resolve()),
        "title": publish_title,
        "start": 0.0,
        "end": duration,
        "duration": duration,
        "score": 95,
        "summary": f"标杆视频二次创作：{raw_title}",
        "reason": f"标杆作品高清无水印深度二次创作 (变速1.02x+去重调色)",
    }

    manifest_path = ROOT / "clip_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = []
    manifest = [x for x in manifest if str(Path(x.get("output", "")).resolve()) != str(output_remix_path.resolve())]
    manifest.insert(0, manifest_item)
    tmp_m = manifest_path.with_suffix(".json.tmp")
    tmp_m.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_m.replace(manifest_path)

    # 5. 注册到发布队列 publish_queue.json (置顶)
    queue_path = ROOT / "publish_queue.json"
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    except Exception:
        queue = []
    queue = [x for x in queue if str(Path(x.get("output", "")).resolve()) != str(output_remix_path.resolve())]
    queue_item = {
        "id": hashlib.md5(str(output_remix_path).encode()).hexdigest()[:16],
        "title": publish_title,
        "output": str(output_remix_path.resolve()),
        "duration": duration,
        "score": 95,
        "captions": {},
        "publish_title": publish_title,
        "publish_content": publish_content,
        "clip_deleted": False,
        "status": {"douyin": "pending", "kuaishou": "pending"},
    }
    queue.insert(0, queue_item)
    tmp_q = queue_path.with_suffix(".json.tmp")
    tmp_q.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_q.replace(queue_path)

    # 6. 初始化流量追踪
    try:
        import traffic_service
        traffic_service.update_clip_traffic(str(output_remix_path.resolve()), 0, 0, 0, 0)
    except Exception:
        pass

    if progress_cb:
        progress_cb(100, f"二创完成：{publish_title}")

    return {
        "success": True,
        "output": str(output_remix_path.resolve()),
        "title": publish_title,
        "publish_content": publish_content,
        "duration": duration,
        "original_author": info.get("author", "同行标杆"),
        "raw_title": raw_title,
    }

