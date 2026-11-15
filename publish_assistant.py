
import argparse
import csv
import hashlib
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
FINAL_CSV = BASE / "ai_analysis" / "final_candidates.csv"
QUEUE_FILE = BASE / "publish_queue.json"
LOCK = threading.Lock()


def make_tags(text):
    priority_terms = [
        "董路",
        "老二",
        "吕梦洋",
        "李昊炎",
        "刘凯源",
        "黄子杰",
        "王修浩",
        "邵佳一",
        "邝兆镭",
        "浮岛敏",
        "安东尼奥",
        "国足",
        "青训",
        "足球小将",
        "战术",
        "中超",
        "教练",
        "45度炸",
        "保护性接应",
        "不在乎成绩"
    ]

    tags = []

    for term in priority_terms:
        if term in text and term not in tags:
            tags.append(term)

    for default_tag in ("直播精选", "精彩切片", "直播高光"):
        if default_tag not in tags:
            tags.append(default_tag)

    return tags[:5]
def make_caption(
    title,
    topics,
    matched_terms,
    source_video,
    platform
):
    search_text = " ".join([
        title,
        topics,
        matched_terms,
        Path(source_video).stem
    ])

    tags = make_tags(search_text)
    tag_text = " ".join(f"#{tag}" for tag in tags)

    return f"{title}\\n{tag_text}"


def make_publish_content(summary, title, topics, matched_terms, source_video):
    search_text = " ".join([
        title, topics, matched_terms, summary, Path(source_video).stem
    ])
    tag_text = " ".join(f"#{tag}" for tag in make_tags(search_text))
    return "\n".join(part for part in (summary.strip(), tag_text) if part)
def make_id(row):
    value = "|".join([
        row["video"],
        row["start"],
        row["end"],
        row["output"]
    ])
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:16]


def load_existing():
    if not QUEUE_FILE.is_file():
        return {}

    try:
        rows = json.loads(
            QUEUE_FILE.read_text(encoding="utf-8")
        )
        return {
            row["id"]: row
            for row in rows
            if isinstance(row, dict) and row.get("id")
        }
    except (OSError, ValueError, TypeError):
        return {}


def sync_queue():
    if not FINAL_CSV.is_file():
        raise FileNotFoundError(
            f"找不到最终候选清单：{FINAL_CSV}"
        )

    existing = load_existing()
    existing_by_output = {
        str(Path(item.get("output", "")).resolve()): item
        for item in existing.values()
        if item.get("output")
    }
    queue = []

    with FINAL_CSV.open(
        encoding="utf-8-sig",
        newline=""
    ) as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        output = Path(row["output"])

        if not output.is_file():
            print("成片不存在，跳过：", output)
            continue

        item_id = make_id(row)
        old = existing.get(
            item_id,
            existing_by_output.get(str(output.resolve()), {})
        )

        title = row.get("title", "").strip() or output.stem
        topics = row.get("topics", "").strip()
        matched_terms = row.get(
            "matched_terms", ""
        ).strip()
        source_video = row["video"]
        summary = row.get("summary", "").strip()

        default_captions = {
            "douyin": make_caption(
                title, topics, matched_terms, source_video, "douyin"
            ),
            "kuaishou": make_caption(
                title, topics, matched_terms, source_video, "kuaishou"
            )
        }

        queue.append({
            "id": item_id,
            "title": title,
            "output": str(output.resolve()),
            "duration": float(row["duration"]),
            "score": int(float(row["score"])),
            "captions": old.get(
                "captions",
                default_captions
            ),
            "publish_title": old.get("publish_title", title),
            "publish_content": old.get("publish_content")
            or make_publish_content(
                summary, title, topics, matched_terms, source_video
            ),
            "clip_deleted": old.get("clip_deleted", False),
            "status": old.get(
                "status",
                {
                    "douyin": "pending",
                    "kuaishou": "pending"
                }
            )
        })

    QUEUE_FILE.write_text(
        json.dumps(
            queue,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    return queue


def load_queue():
    with LOCK:
        return json.loads(
            QUEUE_FILE.read_text(encoding="utf-8")
        )


def save_queue(queue):
    with LOCK:
        tmp = QUEUE_FILE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                queue,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )
        tmp.replace(QUEUE_FILE)


PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VideoScreen发布助手</title>
<style>
body {
    margin: 0;
    background: #f3f4f6;
    color: #1f2937;
    font-family: sans-serif;
}
header {
    background: #111827;
    color: white;
    padding: 18px 24px;
}
main {
    max-width: 1100px;
    margin: 20px auto;
    padding: 0 15px;
}
.card {
    background: white;
    margin-bottom: 18px;
    padding: 18px;
    border-radius: 12px;
    box-shadow: 0 2px 10px #0001;
}
.columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}
.platform {
    border: 1px solid #ddd;
    padding: 13px;
    border-radius: 9px;
}
textarea {
    width: 100%;
    min-height: 100px;
    box-sizing: border-box;
}
button, .button {
    display: inline-block;
    border: 0;
    border-radius: 6px;
    padding: 9px 11px;
    margin: 7px 4px 0 0;
    cursor: pointer;
    text-decoration: none;
}
.blue { background: #2563eb; color: white; }
.green { background: #16a34a; color: white; }
.gray { background: #e5e7eb; color: #111827; }
.path {
    background: #f8fafc;
    padding: 9px;
    word-break: break-all;
    margin: 10px 0;
}
@media(max-width:700px) {
    .columns { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<header>
<h2>VideoScreen 双平台发布助手</h2>
</header>
<main>
<div id="summary" class="card">正在读取发布队列……</div>
<div id="list"></div>
</main>
<script>
const platformNames = {
    douyin: "抖音",
    kuaishou: "快手"
};

const platformUrls = {
    douyin: "https://creator.douyin.com/",
    kuaishou: "https://cp.kuaishou.com/"
};

function esc(value) {
    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

async function copyText(value) {
    await navigator.clipboard.writeText(value);
    alert("已复制");
}

async function saveCaption(id, platform, value) {
    await fetch("/api/caption", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            id: id,
            platform: platform,
            value: value
        })
    });
}

async function markPublished(id, platform) {
    await fetch("/api/status", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            id: id,
            platform: platform,
            status: "published"
        })
    });

    loadQueue();
}

function platformBox(item, platform) {
    const textareaId =
        "caption-" + item.id + "-" + platform;

    return `
      <section class="platform">
        <h3>
          ${platformNames[platform]}：
          ${item.status[platform] === "published"
            ? "已发布"
            : "待发布"}
        </h3>

        <textarea id="${textareaId}"
          onblur="saveCaption(
            '${item.id}',
            '${platform}',
            this.value
          )">${esc(item.captions[platform])}</textarea>

        <button class="gray"
          onclick="copyText(
            document.getElementById('${textareaId}').value
          )">
          复制标题和标签
        </button>

        <a class="button blue"
          target="_blank"
          href="${platformUrls[platform]}">
          打开${platformNames[platform]}
        </a>

        <button class="green"
          onclick="markPublished(
            '${item.id}',
            '${platform}'
          )">
          标记已发布
        </button>
      </section>
    `;
}

async function loadQueue() {
    const response = await fetch("/api/queue");
    const items = await response.json();

    document.getElementById("summary").innerHTML =
        `当前有 <b>${items.length}</b> 个成片，
         共 <b>${items.length * 2}</b> 个双平台发布任务。`;

    document.getElementById("list").innerHTML =
        items.map((item, index) => `
          <article class="card">
            <h2>${index + 1}. ${esc(item.title)}</h2>
            <p>
              时长：${item.duration.toFixed(1)} 秒；
              AI评分：${item.score}
            </p>

            <div class="path">${esc(item.output)}</div>

            <button class="gray"
              onclick='copyText(${JSON.stringify(item.output)})'>
              复制视频路径
            </button>

            <div class="columns">
              ${platformBox(item, "douyin")}
              ${platformBox(item, "kuaishou")}
            </div>
          </article>
        `).join("");
}

loadQueue();
</script>
</body>
</html>'''


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(
            self.headers.get("Content-Length", "0")
        )
        return json.loads(
            self.rfile.read(length).decode("utf-8")
        )

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )
            self.send_header(
                "Content-Length",
                str(len(body))
            )
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/queue":
            self.send_json(load_queue())
            return

        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            request = self.read_json()
        except Exception:
            self.send_json(
                {"error": "请求格式错误"},
                400
            )
            return

        queue = load_queue()
        item = next(
            (
                row for row in queue
                if row["id"] == request.get("id")
            ),
            None
        )

        if item is None:
            self.send_json(
                {"error": "任务不存在"},
                404
            )
            return

        platform = request.get("platform")

        if platform not in ("douyin", "kuaishou"):
            self.send_json(
                {"error": "平台错误"},
                400
            )
            return

        if path == "/api/status":
            item["status"][platform] = request.get(
                "status",
                "pending"
            )
        elif path == "/api/caption":
            item["captions"][platform] = str(
                request.get("value", "")
            )[:1000]
        else:
            self.send_error(404)
            return

        save_queue(queue)
        self.send_json({"ok": True})

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        type=int,
        default=8765
    )
    parser.add_argument(
        "--no-browser",
        action="store_true"
    )
    args = parser.parse_args()

    queue = sync_queue()
    url = f"http://127.0.0.1:{args.port}"

    print("发布队列：", len(queue), "个成片")
    print("打开地址：", url)
    print("按 Ctrl+C 停止")

    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        Handler
    )

    if not args.no_browser:
        threading.Timer(
            1,
            lambda: webbrowser.open(url)
        ).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n发布助手已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
