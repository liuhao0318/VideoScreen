#!/usr/bin/env bash
set -u

# 导出 Conda 环境变量供后台子进程使用
export PATH="/home/ubuntu/miniconda3/bin:/home/ubuntu/miniconda3/condabin:$PATH"

PROJECT="/home/ubuntu/Applications/VideoScreen"
cd "$PROJECT" || exit 1

# 优先查找具备 PyQt5 桌面界面的 Python 解释器（Ubuntu 系统原生环境自带 PyQt5 5.15）
PYTHON=""
for candidate in \
    "/usr/bin/python3" \
    "/home/ubuntu/miniconda3/envs/video-screen/bin/python" \
    "$(which python3 2>/dev/null)" \
    "$(which python 2>/dev/null)"
do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        if "$candidate" -c "import PyQt5" >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "提示：未在当前虚拟环境中检测到 PyQt5，正在尝试系统默认 python3..."
    PYTHON=$(command -v python3)
fi

# 启动本地原生桌面界面
exec "$PYTHON" desktop_app.py "$@"

