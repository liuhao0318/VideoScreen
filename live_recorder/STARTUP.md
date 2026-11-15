# DouyinLiveRecorder 启动说明

本文说明如何在 Linux 环境下安装、配置和启动 DouyinLiveRecorder。

## 1. 项目简介

DouyinLiveRecorder 是一个基于 Python 和 FFmpeg 的直播录制工具。程序会循环检查配置的直播间，主播开播后自动开始录制，并将文件保存在 `downloads` 目录。

项目入口为：

```text
main.py
```

## 2. 运行环境

项目需要以下软件：

- Python 3.10 或更高版本，推荐 Python 3.11
- FFmpeg
- Node.js
- pip 或 Conda

在 Ubuntu 上可以检查环境：

```bash
python3 --version
ffmpeg -version
node --version
```

## 3. 当前机器上的推荐启动方式

当前机器已经存在名为 `live-recorder` 的 Conda 环境，其中安装了项目所需的 Python 依赖。

首次运行前安装 Node.js：

```bash
sudo apt update
sudo apt install -y nodejs npm
```

然后进入项目并启动：

```bash
cd /home/ubuntu/Applications/DouyinLiveRecorder
conda activate live-recorder
python main.py
```

如果当前终端无法使用 `conda activate`，可以直接调用环境中的 Python：

```bash
cd /home/ubuntu/Applications/DouyinLiveRecorder
/home/ubuntu/miniconda3/envs/live-recorder/bin/python main.py
```

## 4. 全新环境安装

如果需要在另一台机器上运行，推荐创建独立的 Python 虚拟环境。

### 4.1 安装系统依赖

Ubuntu/Debian：

```bash
sudo apt update
sudo apt install -y ffmpeg nodejs npm python3-venv
```

### 4.2 创建并启用虚拟环境

```bash
cd /path/to/DouyinLiveRecorder
python3 -m venv .venv
source .venv/bin/activate
```

### 4.3 安装 Python 依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4.4 启动程序

```bash
python main.py
```

## 5. 配置直播间

直播间列表保存在：

```text
config/URL_config.ini
```

每行填写一个直播间地址，例如：

```text
https://live.douyin.com/example
https://live.kuaishou.com/u/example
```

可以在地址后添加主播名称：

```text
https://live.douyin.com/example,主播: 示例主播
```

也可以为单个直播间指定录制画质：

```text
超清,https://live.douyin.com/example,主播: 示例主播
```

支持的画质包括：

- 原画
- 蓝光
- 超清
- 高清
- 标清
- 流畅

暂时不监测某个直播间时，在该行开头添加 `#`：

```text
#https://live.douyin.com/example,主播: 示例主播
```

## 6. 录制参数

主要设置保存在：

```text
config/config.ini
```

常用配置包括：

```ini
[录制设置]
直播保存路径(不填则默认) =
视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频 = ts
原画|超清|高清|标清|流畅 = 原画
是否使用代理ip(是/否) = 否
代理地址 =
循环时间(秒) = 100
分段录制是否开启 = 是
视频分段时间(秒) = 1800
录制完成后自动转为mp4格式 = 是
```

说明：

- 保存路径为空时，文件默认写入项目的 `downloads` 目录。
- 长时间值守时不建议把循环间隔设置得过短，以免请求过于频繁。
- 录制 TikTok、SOOP 等海外平台时，通常需要启用代理并填写代理地址。
- 抖音等平台可能需要有效 Cookie。Cookie 属于敏感信息，不要提交到公开仓库或发送给他人。

## 7. 输出和日志

默认录制目录：

```text
downloads/
```

运行日志目录：

```text
logs/
```

配置备份目录：

```text
backup_config/
```

## 8. 停止程序

在运行程序的终端按：

```text
Ctrl+C
```

如果只想停止某个直播间的监测和录制，可以在 `config/URL_config.ini` 对应行开头添加 `#`。程序会停止该直播间的任务，并正常保存已经录制的内容。

## 9. 后台运行

需要关闭终端后继续运行时，可以使用 `nohup`：

```bash
cd /home/ubuntu/Applications/DouyinLiveRecorder
nohup /home/ubuntu/miniconda3/envs/live-recorder/bin/python main.py \
  > recorder-console.log 2>&1 &
```

查看后台输出：

```bash
tail -f /home/ubuntu/Applications/DouyinLiveRecorder/recorder-console.log
```

查找进程：

```bash
pgrep -af 'python.*main.py'
```

建议先找到准确的进程号，再停止对应进程：

```bash
kill <PID>
```

## 10. Docker 启动（可选）

安装 Docker 和 Docker Compose 后，可以在项目根目录运行：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f
```

停止容器：

```bash
docker compose down
```

容器会挂载以下目录，因此配置、日志和录制文件都会保存在宿主机：

- `config/`
- `logs/`
- `backup_config/`
- `downloads/`

## 11. 常见问题

### 缺少 Python 模块

报错示例：

```text
ModuleNotFoundError: No module named 'loguru'
```

处理方法：

```bash
python -m pip install -r requirements.txt
```

请确认安装依赖和启动程序使用的是同一个 Python 环境：

```bash
which python
python --version
python -m pip --version
```

### 找不到 FFmpeg

报错示例：

```text
缺少ffmpeg无法进行录制
```

处理方法：

```bash
sudo apt install -y ffmpeg
ffmpeg -version
```

### 找不到 Node.js

处理方法：

```bash
sudo apt install -y nodejs npm
node --version
```

### 能启动但没有生成视频

依次检查：

1. 主播当前是否正在直播。
2. `config/URL_config.ini` 中的链接是否有效且未以 `#` 开头。
3. `logs/` 中是否有请求、Cookie、代理或 FFmpeg 错误。
4. 磁盘剩余空间是否高于配置的阈值。
5. 海外平台是否需要代理。

### 修改配置后何时生效

程序会循环读取配置。直播间列表和部分设置通常会在后续检测周期生效；如果行为没有变化，可以按 `Ctrl+C` 停止后重新启动程序。
