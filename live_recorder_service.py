#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直播录制服务集成控制器 (DouyinLiveRecorder Service Controller)

集成 /home/ubuntu/Applications/DouyinLiveRecorder 项目至 VideoScreen 自动化切片系统。
提供：
1. 录制器进程生命周期管理 (运行状态检测、一键启动、安全停止、重启)
2. 监控直播间配置管理 (解析、添加、删除、禁用 URL_config.ini 中的目标主播)
3. 录制控制台日志读取与流式监听
4. 活跃 ffmpeg 录制流监控与分段成片统计
"""

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
LOCAL_RECORDER_DIR = BASE_DIR / "live_recorder"
GLOBAL_RECORDER_DIR = Path.home() / "Applications/DouyinLiveRecorder"

# 首选内置 live_recorder 目录，若未就绪则回退至全局目录
RECORDER_DIR = LOCAL_RECORDER_DIR if (LOCAL_RECORDER_DIR / "main.py").is_file() else GLOBAL_RECORDER_DIR

# 寻找 Conda 环境中的专用 Python 解释器
CONDA_PYTHONS = [
    Path("/home/ubuntu/miniconda3/envs/live-recorder/bin/python"),
    Path("/home/ubuntu/miniconda3/envs/live-recorder/bin/python3"),
    Path.home() / "miniconda3/envs/live-recorder/bin/python",
    Path("/opt/conda/envs/live-recorder/bin/python"),
]

def get_python_executable() -> str:
    """获取运行 DouyinLiveRecorder 的最优 Python 解释器"""
    for p in CONDA_PYTHONS:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    # 回退到当前环境解释器
    return sys.executable

def get_url_config_path() -> Path:
    """获取 URL_config.ini 配置文件路径"""
    local_cfg = RECORDER_DIR / "config/URL_config.ini"
    if local_cfg.is_file():
        return local_cfg
    global_cfg = GLOBAL_RECORDER_DIR / "config/URL_config.ini"
    if global_cfg.is_file():
        return global_cfg
    return local_cfg

def get_main_config_path() -> Path:
    """获取主配置文件 config.ini 路径"""
    local_cfg = RECORDER_DIR / "config/config.ini"
    if local_cfg.is_file():
        return local_cfg
    global_cfg = GLOBAL_RECORDER_DIR / "config/config.ini"
    if global_cfg.is_file():
        return global_cfg
    return local_cfg

def get_console_log_path() -> Path:
    """获取控制台日志路径"""
    return RECORDER_DIR / "recorder-console.log"

def detect_platform(url: str) -> str:
    """根据直播间 URL 识别平台"""
    u = url.lower()
    if "douyin.com" in u:
        return "抖音直播"
    elif "kuaishou.com" in u:
        return "快手直播"
    elif "tiktok.com" in u:
        return "TikTok"
    elif "huya.com" in u:
        return "虎牙直播"
    elif "douyu.com" in u:
        return "斗鱼直播"
    elif "bilibili.com" in u:
        return "B站直播"
    elif "xiaohongshu.com" in u:
        return "小红书"
    return "其他直播"

def list_monitored_rooms() -> List[Dict[str, Any]]:
    """读取并解析监控的直播间列表"""
    cfg_path = get_url_config_path()
    rooms = []
    if not cfg_path.is_file():
        return rooms

    try:
        content = cfg_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        content = cfg_path.read_text(encoding="gbk", errors="ignore")

    for raw_line in content.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        is_disabled = line.startswith("#")
        clean = line.lstrip("#").strip().lstrip("\ufeff")
        if not clean or "http" not in clean:
            continue

        parts = [p.strip() for p in clean.split(",") if p.strip()]
        url = parts[0]
        name = ""
        for p in parts[1:]:
            if p.startswith("主播:") or p.startswith("主播："):
                name = p.split(":", 1)[-1].split("：", 1)[-1].strip()
            elif not name:
                name = p

        if not name:
            name = url.split("/")[-1]

        rooms.append({
            "url": url,
            "name": name,
            "platform": detect_platform(url),
            "enabled": not is_disabled,
            "raw": line
        })
    return rooms

def save_monitored_rooms(rooms: List[Dict[str, Any]]) -> bool:
    """保存直播间列表至 URL_config.ini 并同步备份"""
    cfg_path = get_url_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # 备份历史版本
    backup_dir = RECORDER_DIR / "backup_config"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if cfg_path.is_file():
        ts_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        try:
            shutil.copy2(cfg_path, backup_dir / f"URL_config.ini_{ts_str}")
        except Exception:
            pass

    lines = []
    for r in rooms:
        url = r.get("url", "").strip()
        if not url:
            continue
        name = r.get("name", "").strip()
        prefix = "" if r.get("enabled", True) else "# "
        if name:
            lines.append(f"{prefix}{url},主播: {name}")
        else:
            lines.append(f"{prefix}{url}")

    new_text = "\n".join(lines) + "\n"
    cfg_path.write_text(new_text, encoding="utf-8")

    # 若全局目录不同，则同步写一份
    if GLOBAL_RECORDER_DIR.is_dir() and GLOBAL_RECORDER_DIR != RECORDER_DIR:
        try:
            (GLOBAL_RECORDER_DIR / "config/URL_config.ini").write_text(new_text, encoding="utf-8")
        except Exception:
            pass
    return True

def add_room(url: str, name: str = "") -> bool:
    """添加新的监控直播间"""
    rooms = list_monitored_rooms()
    for r in rooms:
        if r["url"] == url:
            r["name"] = name or r["name"]
            r["enabled"] = True
            return save_monitored_rooms(rooms)
    rooms.append({
        "url": url,
        "name": name,
        "platform": detect_platform(url),
        "enabled": True
    })
    return save_monitored_rooms(rooms)

def remove_room(url: str) -> bool:
    """移除监控直播间"""
    rooms = list_monitored_rooms()
    new_rooms = [r for r in rooms if r["url"] != url]
    return save_monitored_rooms(new_rooms)

def get_recorder_process() -> Optional[Dict[str, Any]]:
    """检测 DouyinLiveRecorder 核心进程 (main.py) 是否存活"""
    try:
        # 使用 pgrep 匹配 main.py 以及 DouyinLiveRecorder / live_recorder
        output = subprocess.check_output(
            ["pgrep", "-fa", "python.*main.py"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8"
        )
    except subprocess.CalledProcessError:
        output = ""

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        pid_str, cmd = parts[0], parts[1]
        if "DouyinLiveRecorder" in cmd or "live_recorder" in cmd:
            try:
                pid = int(pid_str)
                # 读取进程状态
                stat_path = Path(f"/proc/{pid}/stat")
                if stat_path.exists():
                    # 探测启动时间与资源
                    return {
                        "pid": pid,
                        "cmd": cmd,
                        "is_running": True
                    }
            except Exception:
                pass
    return None

def get_active_ffmpeg_streams() -> List[Dict[str, Any]]:
    """获取当前所有由录制器调起的 ffmpeg 直播录制流"""
    streams = []
    try:
        output = subprocess.check_output(
            ["pgrep", "-fa", "ffmpeg.*downloads"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8"
        )
    except subprocess.CalledProcessError:
        output = ""

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        pid_str, cmd = parts[0], parts[1]
        try:
            pid = int(pid_str)
            # 解析输出目标文件
            out_file = ""
            for seg in cmd.split():
                if "downloads" in seg:
                    out_file = seg
            anchor_name = ""
            if "快手直播/" in cmd or "抖音直播/" in cmd:
                m = re.search(r'(快手直播|抖音直播)/([^/]+)/', cmd)
                if m:
                    anchor_name = m.group(2)

            streams.append({
                "pid": pid,
                "anchor": anchor_name or "直播录制中",
                "out_file": out_file,
                "cmd": cmd
            })
        except Exception:
            pass
    return streams

def get_status() -> Dict[str, Any]:
    """获取完整的录制系统综合健康状态数据"""
    proc = get_recorder_process()
    is_running = proc is not None
    ffmpeg_streams = get_active_ffmpeg_streams()
    rooms = list_monitored_rooms()

    # 统计下载目录近 24 小时产生的文件数
    downloads_dir = RECORDER_DIR / "downloads"
    if not downloads_dir.exists() and (GLOBAL_RECORDER_DIR / "downloads").exists():
        downloads_dir = GLOBAL_RECORDER_DIR / "downloads"

    recent_files = []
    total_size_bytes = 0
    if downloads_dir.exists():
        try:
            for root, _, files in os.walk(str(downloads_dir)):
                for f in files:
                    if f.endswith((".mp4", ".ts", ".flv", ".mkv")):
                        fp = Path(root) / f
                        try:
                            st = fp.stat()
                            total_size_bytes += st.st_size
                            # 最近 10 个视频文件
                            recent_files.append({
                                "name": f,
                                "path": str(fp),
                                "size_mb": round(st.st_size / (1024 * 1024), 1),
                                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                                "raw_mtime": st.st_mtime
                            })
                        except Exception:
                            pass
        except Exception:
            pass

    recent_files.sort(key=lambda x: x["raw_mtime"], reverse=True)

    return {
        "is_running": is_running,
        "pid": proc["pid"] if proc else None,
        "python": get_python_executable(),
        "recorder_dir": str(RECORDER_DIR),
        "ffmpeg_streams": ffmpeg_streams,
        "active_stream_count": len(ffmpeg_streams),
        "rooms_count": len(rooms),
        "enabled_rooms_count": len([r for r in rooms if r["enabled"]]),
        "rooms": rooms,
        "total_recordings_size_gb": round(total_size_bytes / (1024 * 1024 * 1024), 2),
        "recent_files": recent_files[:10],
        "log_path": str(get_console_log_path())
    }

def start_recorder() -> Dict[str, Any]:
    """启动 DouyinLiveRecorder 后台服务"""
    proc = get_recorder_process()
    if proc:
        return {"success": True, "message": f"录制器已在运行中 (PID: {proc['pid']})", "pid": proc["pid"]}

    py_bin = get_python_executable()
    main_py = RECORDER_DIR / "main.py"
    if not main_py.is_file():
        # 回退全局
        main_py = GLOBAL_RECORDER_DIR / "main.py"
        cwd_dir = GLOBAL_RECORDER_DIR
    else:
        cwd_dir = RECORDER_DIR

    log_path = get_console_log_path()
    log_file = open(str(log_path), "a", encoding="utf-8")

    try:
        p = subprocess.Popen(
            [py_bin, "-u", str(main_py)],
            cwd=str(cwd_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True  # 独立会话后台执行
        )
        time.sleep(1.0)
        if p.poll() is None:
            return {"success": True, "message": f"录制器启动成功 (PID: {p.pid})", "pid": p.pid}
        else:
            return {"success": False, "message": f"录制器进程退出，返回码: {p.returncode}", "code": p.returncode}
    except Exception as e:
        return {"success": False, "message": f"启动录制器异常: {str(e)}"}

def stop_recorder() -> Dict[str, Any]:
    """停止 DouyinLiveRecorder 及其下属 ffmpeg 录制任务"""
    proc = get_recorder_process()
    if not proc:
        # 同时检查并清理孤儿 ffmpeg
        streams = get_active_ffmpeg_streams()
        for s in streams:
            try:
                os.kill(s["pid"], signal.SIGTERM)
            except Exception:
                pass
        return {"success": True, "message": "录制服务未处于运行状态"}

    pid = proc["pid"]
    try:
        # 发送 SIGTERM 优雅停止
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        return {"success": False, "message": f"向进程 {pid} 发送终止信号失败: {e}"}

    # 等待最多 5 秒
    for _ in range(10):
        time.sleep(0.5)
        if not get_recorder_process():
            break
    else:
        # 强制 SIGKILL
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    # 同时清理下属 ffmpeg
    for s in get_active_ffmpeg_streams():
        try:
            os.kill(s["pid"], signal.SIGTERM)
        except Exception:
            pass

    return {"success": True, "message": f"录制器 (PID: {pid}) 已成功停止"}

def restart_recorder() -> Dict[str, Any]:
    """重启录制服务"""
    stop_recorder()
    time.sleep(1.5)
    return start_recorder()

def get_recent_logs(lines: int = 120) -> str:
    """读取最近的录制控制台日志"""
    log_path = get_console_log_path()
    if not log_path.is_file():
        # 尝试读取 global log
        global_log = GLOBAL_RECORDER_DIR / "recorder-console.log"
        if global_log.is_file():
            log_path = global_log
        else:
            return "暂无控制台日志输出 (服务尚未产生日志或未启动)"

    try:
        with open(str(log_path), "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"读取日志错误: {e}"

if __name__ == "__main__":
    import pprint
    print("=== DouyinLiveRecorder Service Controller ===")
    status = get_status()
    pprint.pprint(status)
