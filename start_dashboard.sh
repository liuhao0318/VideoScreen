#!/usr/bin/env bash
set -u

export PATH="/home/ubuntu/miniconda3/bin:/home/ubuntu/miniconda3/condabin:$PATH"

PROJECT="/home/ubuntu/Applications/VideoScreen"
PYTHON=""
for candidate in \
    "/usr/bin/python3" \
    "/home/ubuntu/miniconda3/envs/video-screen/bin/python" \
    "$(which python3 2>/dev/null)" \
    "$(which python 2>/dev/null)"
do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        PYTHON="$candidate"
        break
    fi
done

URL="http://127.0.0.1:8780"
LOG="$PROJECT/dashboard_server.log"

show_error() {
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="VideoScreen" --text="$1"
    else
        notify-send "VideoScreen" "$1" 2>/dev/null || true
    fi
}

if [ ! -f "$PROJECT/dashboard_server.py" ]; then
    show_error "找不到 dashboard_server.py，请先安装网页后台。"
    exit 1
fi

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    show_error "找不到可用的 Python 解释器。"
    exit 1
fi

# 如果后台已经启动且是最新版本（包含最新接口），直接打开网页
IS_LATEST=false
if "$PYTHON" - <<'CHECK' >/dev/null 2>&1
import json, urllib.request
res = urllib.request.urlopen("http://127.0.0.1:8780/api/health", timeout=1)
data = json.loads(res.read().decode("utf-8"))
if res.status == 200 and data.get("version") == "2026-11-10-r2":
    exit(0)
exit(1)
CHECK
then
    IS_LATEST=true
fi

if [ "$IS_LATEST" = "true" ]; then
    xdg-open "$URL" >/dev/null 2>&1 &
    exit 0
else
    # 如果端口被旧版本进程占用，自动释放并重启最新服务
    fuser -k 8780/tcp >/dev/null 2>&1 || true
    sleep 0.5
fi

# 启动后台
cd "$PROJECT" || exit 1

nohup "$PYTHON" -u dashboard_server.py \
    >> "$LOG" 2>&1 &

# 最多等待15秒
for second in $(seq 1 30); do
    if "$PYTHON" - <<'CHECK' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen(
    "http://127.0.0.1:8780/api/overview",
    timeout=1
).read()
CHECK
    then
        xdg-open "$URL" >/dev/null 2>&1 &
        exit 0
    fi

    sleep 0.5
done

show_error "网页后台启动失败，请检查 dashboard_server.log。"
exit 1
