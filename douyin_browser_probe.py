
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path.home() / ".config" / "videoscreen-publisher"
SCREENSHOT = Path(__file__).resolve().parent / "douyin_upload_page.png"

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
        "https://creator.douyin.com/",
        wait_until="domcontentloaded",
        timeout=120000
    )

    print("\n专用Chrome已经打开。")
    print("请完成以下操作：")
    print("1. 如果尚未登录，请使用抖音扫码登录。")
    print("2. 登录后进入“发布视频”页面。")
    print("3. 停留在选择视频文件的页面。")
    print("4. 回到终端按回车。")

    input("\n准备完成后按回车继续：")

    page.wait_for_timeout(3000)

    print("\n===== 页面信息 =====")
    print("标题：", page.title())
    print("网址：", page.url)

    file_inputs = page.locator('input[type="file"]')
    print("文件选择框数量：", file_inputs.count())

    for index in range(file_inputs.count()):
        item = file_inputs.nth(index)
        print(
            f"文件框{index}:",
            "accept =", item.get_attribute("accept"),
            "multiple =", item.get_attribute("multiple")
        )

    try:
        body_text = page.locator("body").inner_text(timeout=10000)
        lines = []

        for line in body_text.splitlines():
            line = line.strip()
            if (
                line
                and re.search(
                    r"上传|发布|视频|作品|标题|封面",
                    line
                )
                and line not in lines
            ):
                lines.append(line)

        print("\n===== 相关页面文字 =====")
        for line in lines[:40]:
            print(line)

    except Exception as error:
        print("读取页面文字失败：", error)

    page.screenshot(
        path=str(SCREENSHOT),
        full_page=True
    )

    print("\n页面截图：", SCREENSHOT)
    print("探测完成，正在保存登录状态……")

    context.close()
