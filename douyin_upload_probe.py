
import csv
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
CSV_FILE = BASE / "ai_analysis" / "final_candidates.csv"
PROFILE = Path.home() / ".config" / "videoscreen-publisher"
SCREENSHOT = BASE / "douyin_after_upload.png"

with CSV_FILE.open(
    encoding="utf-8-sig",
    newline=""
) as f:
    rows = list(csv.DictReader(f))

if not rows:
    raise SystemExit("最终候选清单为空")

row = rows[0]
video = Path(row["output"]).resolve()
title = row.get("title", "").strip()

if not video.is_file():
    raise SystemExit(f"视频不存在：{video}")

print("准备上传测试视频：", video.name)
print("文件大小：", round(video.stat().st_size / 1024 / 1024, 2), "MB")
print("候选标题：", title)
print("注意：本程序只上传文件，不会点击发布。")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        executable_path="/usr/bin/google-chrome",
        headless=False,
        no_viewport=True,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled"
        ]
    )

    page = context.pages[0] if context.pages else context.new_page()

    page.goto(
        "https://creator.douyin.com/creator-micro/content/upload",
        wait_until="domcontentloaded",
        timeout=120000
    )

    file_input = page.locator('input[type="file"]').first
    file_input.wait_for(
        state="attached",
        timeout=60000
    )

    print("\n正在将视频交给抖音上传页面……")
    file_input.set_input_files(str(video))
    print("视频文件已自动选择。")

    print("\n请观察浏览器：")
    print("1. 等待视频上传和预审。")
    print("2. 等到标题、封面、发布设置等编辑区域出现。")
    print("3. 不要点击最终发布。")
    print("4. 回到终端按回车。")

    input("\n编辑页面完整出现后按回车：")

    page.wait_for_timeout(2000)

    print("\n===== 当前页面 =====")
    print("标题：", page.title())
    print("网址：", page.url)

    print("\n===== 普通输入框 =====")
    inputs = page.locator(
        'input:not([type="file"]):not([type="hidden"])'
    )

    for index in range(inputs.count()):
        item = inputs.nth(index)
        try:
            print({
                "index": index,
                "type": item.get_attribute("type"),
                "placeholder": item.get_attribute("placeholder"),
                "value": item.input_value(timeout=1000),
                "maxlength": item.get_attribute("maxlength")
            })
        except Exception:
            pass

    print("\n===== 多行文本框 =====")
    textareas = page.locator("textarea")

    for index in range(textareas.count()):
        item = textareas.nth(index)
        try:
            print({
                "index": index,
                "placeholder": item.get_attribute("placeholder"),
                "value": item.input_value(timeout=1000),
                "maxlength": item.get_attribute("maxlength")
            })
        except Exception:
            pass

    print("\n===== 可编辑区域 =====")
    editables = page.locator('[contenteditable="true"]')

    for index in range(editables.count()):
        item = editables.nth(index)
        try:
            print({
                "index": index,
                "role": item.get_attribute("role"),
                "placeholder": (
                    item.get_attribute("data-placeholder")
                    or item.get_attribute("aria-placeholder")
                    or item.get_attribute("placeholder")
                ),
                "text": item.inner_text(timeout=1000)[:300]
            })
        except Exception:
            pass

    print("\n===== 按钮 =====")
    buttons = page.locator("button")

    for index in range(buttons.count()):
        item = buttons.nth(index)
        try:
            text = item.inner_text(timeout=1000).strip()
            if text:
                print({
                    "index": index,
                    "text": text[:100],
                    "disabled": item.is_disabled()
                })
        except Exception:
            pass

    page.screenshot(
        path=str(SCREENSHOT),
        full_page=True
    )

    print("\n截图已保存：", SCREENSHOT)
    print("没有执行发布，正在关闭专用浏览器。")

    context.close()
