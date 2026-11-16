#!/usr/bin/env bash
# ==============================================================================
# VideoScreen - 桌面快捷方式一键安装脚本 (Desktop Launcher Installer)
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$HOME/Desktop"
APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$PROJECT_DIR/VideoScreen.desktop"

echo "=================================================="
echo "🚀 开始安装 VideoScreen 桌面一键启动快捷方式..."
echo "=================================================="
echo "• 项目目录: $PROJECT_DIR"

# 1. 确保启动脚本与快捷方式具备可执行权限
chmod +x "$PROJECT_DIR/start_gui.sh"

# 2. 动态生成并校准 VideoScreen.desktop 绝对路径
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=VideoScreen 直播切片系统
GenericName=直播切片系统
Comment=全自动直播录制与智能切片发布系统 (本地桌面客户端)
Exec=$PROJECT_DIR/start_gui.sh
Icon=$PROJECT_DIR/assets/icon.png
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
StartupNotify=true
Keywords=video;stream;clip;douyin;live;ai;
EOF

chmod +x "$DESKTOP_FILE"

# 3. 安装到系统应用程序菜单目录 (~/.local/share/applications)
mkdir -p "$APPLICATIONS_DIR" 2>/dev/null || true
if [ -d "$APPLICATIONS_DIR" ] && [ -w "$APPLICATIONS_DIR" ]; then
    cp "$DESKTOP_FILE" "$APPLICATIONS_DIR/"
    echo "✅ 已成功注册到系统应用中心 (~/.local/share/applications/)"
fi

# 4. 安装到桌面 (~/Desktop)
if [ -d "$DESKTOP_DIR" ] && [ -w "$DESKTOP_DIR" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_DIR/"
    chmod +x "$DESKTOP_DIR/VideoScreen.desktop"
    
    # 针对 GNOME 桌面环境标记为受信任启动器（去感叹号）
    if command -v gio >/dev/null 2>&1; then
        gio set "$DESKTOP_DIR/VideoScreen.desktop" metadata::trusted true 2>/dev/null || true
    fi
    echo "✅ 已成功添加到桌面快捷方式 ($DESKTOP_DIR/VideoScreen.desktop)"
else
    echo "提示：若需要桌面图标，请在终端以普通权限运行：bash install_desktop_shortcut.sh"
fi

echo "=================================================="
echo "🎉 安装完成！"
echo "您可以在桌面直接双击「VideoScreen 直播切片系统」图标一键启动，"
echo "或者在终端随时运行: ./start_gui.sh"
echo "=================================================="
