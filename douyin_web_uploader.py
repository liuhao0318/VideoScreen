
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
CSV_FILE = BASE / "ai_analysis" / "final_candidates.csv"
MANIFEST_FILE = BASE / "clip_manifest.json"
QUEUE_FILE = BASE / "publish_queue.json"
PROFILE = Path.home() / ".config" / "videoscreen-publisher"
UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"


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
def load_rows():
    rows = []
    seen = set()

    try:
        manifest_rows = json.loads(
            MANIFEST_FILE.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        manifest_rows = []

    csv_rows = []
    if CSV_FILE.is_file():
        with CSV_FILE.open(
            encoding="utf-8-sig",
            newline=""
        ) as f:
            csv_rows = list(csv.DictReader(f))

    for row in manifest_rows + csv_rows:
        output = row.get("output", "")
        if not output:
            continue
        key = str(Path(output).resolve())
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    result = []
    try:
        queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        queue = []
    queue_by_output = {
        str(Path(item.get("output", "")).resolve()): item
        for item in queue
        if isinstance(item, dict) and item.get("output")
    }

    for row in rows:
        video = Path(row["output"]).resolve()

        if not video.is_file():
            continue

        title = row.get("title", "").strip() or video.stem
        summary = row.get("summary", "").strip()
        topics = row.get("topics", "").strip()
        matched_terms = row.get(
            "matched_terms", ""
        ).strip()

        search_text = " ".join([
            title,
            topics,
            matched_terms,
            summary,
            Path(row["video"]).stem
        ])

        tags = make_tags(search_text)
        tag_text = " ".join(f"#{tag}" for tag in tags)

        description_parts = []

        if summary:
            description_parts.append(summary)

        description_parts.append(tag_text)

        queue_item = queue_by_output.get(str(video), {})
        result.append({
            "video": video,
            "title": queue_item.get("publish_title", title),
            "description": queue_item.get(
                "publish_content", "\n".join(description_parts)
            ),
            "duration": row.get("duration", ""),
            "score": row.get("score", "")
        })

    return result


def dismiss_popups(page):
    for text in ("我知道了", "知道了", "关闭"):
        try:
            button = page.get_by_role(
                "button",
                name=text,
                exact=True
            )

            if button.count() and button.first.is_visible():
                button.first.click(timeout=2000)
        except Exception:
            pass


def fill_description(page, description):
    editor = page.locator(
        '[contenteditable="true"][data-placeholder="添加作品简介"]'
    ).first

    editor.wait_for(
        state="visible",
        timeout=600000
    )

    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.insert_text(description)


def click_first_text(page, texts, timeout=5000):
    for text in texts:
        try:
            locator = page.get_by_text(text, exact=False)
            for index in range(locator.count()):
                item = locator.nth(index)
                if item.is_visible():
                    item.click(timeout=timeout)
                    return text
        except Exception:
            continue
    return ""


def confirm_cover_application(page):
    prompt = page.get_by_text("是否确认应用此封面？", exact=False).last
    try:
        prompt.wait_for(state="visible", timeout=10000)
    except Exception:
        return False

    confirm = None
    candidates = page.get_by_text("确定", exact=True)
    for index in range(candidates.count() - 1, -1, -1):
        item = candidates.nth(index)
        try:
            if item.is_visible():
                confirm = item
                break
        except Exception:
            continue
    if confirm is None:
        screenshot = BASE / "douyin_cover_confirm_button_missing.png"
        page.screenshot(path=str(screenshot), full_page=True)
        print("封面确认按钮定位失败，截图：", screenshot, flush=True)
        return False
    confirm.click(force=True)
    try:
        prompt.wait_for(state="hidden", timeout=10000)
    except Exception:
        pass
    print("已点击“确定”，AI封面已应用。", flush=True)
    return True


def select_ai_cover(page):
    print("正在选择AI生成封面……", flush=True)
    if not click_first_text(page, ("选择封面", "编辑封面", "设置封面"), 10000):
        raise RuntimeError("找不到封面设置入口")
    page.wait_for_timeout(2000)

    # 新版抖音在封面编辑器左侧提供“推荐封面”，这里的图片
    # 才是平台生成的AI推荐结果。
    dialogs = page.get_by_role("dialog")
    dialog = dialogs.last
    try:
        dialog.wait_for(state="visible", timeout=8000)
        recommend = dialog.get_by_text(
            re.compile(r"^AI封面$|^推荐封面$")
        ).last
        recommend.wait_for(state="visible", timeout=5000)
        recommend.click(force=True)
        print("已点击封面编辑器左侧的“AI封面”。", flush=True)

        deadline = time.time() + 90
        while time.time() < deadline:
            dialog_text = dialog.inner_text(timeout=5000)
            if "生成中" not in dialog_text:
                break
            time.sleep(2)
        else:
            raise RuntimeError("等待90秒后推荐封面仍未生成完成")

        page.wait_for_timeout(1500)
        dialog_box = dialog.bounding_box()
        if not dialog_box:
            raise RuntimeError("无法定位封面编辑器")
        # “AI封面”页左上方第一张卡片即“为你推荐”的第一张AI结果。
        # 该标题由CSS绘制，无法稳定通过文字定位，因此以弹窗为基准点击卡片中心。
        page.mouse.click(
            dialog_box["x"] + 158,
            dialog_box["y"] + 153,
        )
        page.wait_for_timeout(1000)
        print("已点击AI封面页“为你推荐”的第一张卡片。", flush=True)

        confirm = dialog.get_by_role(
            "button", name=re.compile(r"^完成$|^确定$|^保存$")
        ).last
        confirm.wait_for(state="visible", timeout=5000)
        deadline = time.time() + 10
        while time.time() < deadline and not confirm.is_enabled():
            time.sleep(0.2)
        if not confirm.is_enabled():
            raise RuntimeError("AI推荐封面已选择，但“完成”按钮仍不可用")
        confirm.click(force=True)
        confirm_cover_application(page)
        dialog.wait_for(state="hidden", timeout=10000)
        page.wait_for_timeout(1000)
        screenshot = BASE / "douyin_ai_cover_selected.png"
        page.screenshot(path=str(screenshot), full_page=True)
        print("AI推荐封面已确认，截图：", screenshot, flush=True)
        return
    except Exception as dialog_error:
        print(
            f"封面编辑器推荐封面流程不可用，尝试页面内推荐区域：{dialog_error}",
            flush=True,
        )
        try:
            if dialog.is_visible():
                page.keyboard.press("Escape")
        except Exception:
            pass

    page.wait_for_timeout(1000)
    ai_heading = page.get_by_text(
        re.compile(r"AI智能推荐封面|Ai智能推荐封面|AI生成|智能推荐封面")
    ).first
    try:
        ai_heading.wait_for(state="visible", timeout=15000)
    except Exception:
        screenshot = BASE / "douyin_ai_cover_unavailable.png"
        page.screenshot(path=str(screenshot), full_page=True)
        print(
            "本次发布页未提供AI封面，保留平台默认推荐封面继续发布。",
            flush=True,
        )
        print("诊断截图：", screenshot, flush=True)
        return

    print("等待AI推荐封面生成完成……", flush=True)
    deadline = time.time() + 90
    while time.time() < deadline:
        text = ai_heading.inner_text(timeout=5000)
        body_text = page.locator("body").inner_text(timeout=10000)
        if "生成中" not in text and "AI智能推荐封面生成中" not in body_text and "Ai智能推荐封面生成中" not in body_text:
            break
        time.sleep(2)
    else:
        screenshot = BASE / "douyin_ai_cover_timeout.png"
        try:
            page.screenshot(path=str(screenshot), full_page=True)
        except Exception:
            pass
        print("⚠️ AI推荐封面生成超过90秒仍未完成，保留平台默认推荐封面继续发布。", flush=True)
        return

    page.wait_for_timeout(1500)
    ai_heading.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    box = ai_heading.bounding_box()
    if not box:
        raise RuntimeError("AI封面已生成，但无法定位推荐封面区域")

    # 抖音的AI推荐封面位于标题正下方，属于页面内联卡片而非弹窗。
    # 点击第一张生成结果的中心位置。
    page.mouse.click(
        box["x"] + 34,
        box["y"] + box["height"] + 46,
    )
    page.wait_for_timeout(1000)
    print("已点击页面内AI推荐图，继续在封面编辑器中确认选择。", flush=True)

    # 选择推荐封面后，抖音会再弹出“是否确认应用此封面”。
    # 必须点击这里的“确定”，封面才真正写入发布表单。
    if not confirm_cover_application(page):
        print("未出现封面二次确认弹窗，继续检查封面编辑器。", flush=True)

    # 页面内推荐图被点击后可能自动打开封面编辑器，必须点击“完成”
    # 关闭编辑器，才能继续操作后面的自主声明。
    try:
        open_dialog = page.get_by_role("dialog").last
        if open_dialog.is_visible():
            ai_tab = open_dialog.get_by_text(
                re.compile(r"^AI封面$|^推荐封面$")
            ).last
            ai_tab.wait_for(state="visible", timeout=5000)
            ai_tab.click(force=True)
            page.wait_for_timeout(1500)
            dialog_box = open_dialog.bounding_box()
            if not dialog_box:
                raise RuntimeError("无法定位封面编辑器")
            page.mouse.click(
                dialog_box["x"] + 158,
                dialog_box["y"] + 153,
            )
            page.wait_for_timeout(1000)
            print("已在封面编辑器内选择第一张AI推荐卡片。", flush=True)
            finish = open_dialog.get_by_role(
                "button", name=re.compile(r"^完成$|^确定$|^保存$")
            ).last
            finish.wait_for(state="visible", timeout=5000)
            if finish.is_enabled():
                finish.click(force=True)
                confirm_cover_application(page)
                open_dialog.wait_for(state="hidden", timeout=10000)
                print("封面编辑器已保存并关闭。", flush=True)
            else:
                raise RuntimeError("封面编辑器“完成”按钮不可用")
    except Exception as error:
        raise RuntimeError(f"AI封面已选择，但封面编辑器未能关闭：{error}")

    screenshot = BASE / "douyin_ai_cover_selected.png"
    page.screenshot(path=str(screenshot), full_page=True)
    print("AI封面选择截图：", screenshot, flush=True)


def set_declaration(page):
    print("正在设置作品声明：虚构演绎，仅供娱乐……", flush=True)
    page.locator("body").press("End")
    page.wait_for_timeout(1000)
    click_first_text(
        page,
        ("更多设置", "展开更多", "发布设置", "高级设置"),
        5000,
    )
    page.wait_for_timeout(1000)

    declaration_entry = click_first_text(
        page,
        (
            "请选择自主声明",
            "自主声明",
            "内容声明",
            "作品声明",
            "声明作品",
            "添加声明",
        ),
        10000,
    )
    if not declaration_entry:
        screenshot = BASE / "douyin_declaration_not_found.png"
        page.screenshot(path=str(screenshot), full_page=True)
        visible_text = page.locator("body").inner_text(timeout=10000)
        print("声明入口查找失败时的页面文字：", flush=True)
        print(visible_text[-8000:], flush=True)
        print("诊断截图：", screenshot, flush=True)
        raise RuntimeError("找不到内容声明入口，已保存诊断截图")
    page.wait_for_timeout(1000)
    selected = False
    option_texts = (
        "虚构演绎，仅供娱乐",
        "虚构演绎（仅供娱乐）",
        "虚构内容，仅供娱乐",
    )
    for option_text in option_texts:
        try:
            text_node = page.get_by_text(option_text, exact=True).last
            text_node.wait_for(state="visible", timeout=3000)
            row = text_node.locator("xpath=ancestor::*[.//input[@type='radio']][1]")
            if row.count():
                row.click(force=True)
            else:
                text_node.click(force=True)
            page.wait_for_timeout(500)
            checked = page.locator("input[type='radio']:checked")
            if checked.count():
                selected = True
                print(f"已选择自主声明：{option_text}", flush=True)
                break
        except Exception:
            continue

    if not selected:
        screenshot = BASE / "douyin_declaration_option_not_found.png"
        page.screenshot(path=str(screenshot), full_page=True)
        print("诊断截图：", screenshot, flush=True)
        raise RuntimeError("声明弹窗已打开，但单选框未能选中")

    confirm = page.get_by_role("button", name="确定", exact=True).last
    confirm.wait_for(state="visible", timeout=5000)
    deadline = time.time() + 10
    while time.time() < deadline and not confirm.is_enabled():
        time.sleep(0.2)
    if not confirm.is_enabled():
        raise RuntimeError("自主声明已选中，但确定按钮仍不可用")
    confirm.click(force=True)
    print("作品声明设置完成。", flush=True)


def wait_and_publish(page):
    print("等待视频上传和平台预审完成……", flush=True)
    publish = page.get_by_role(
        "button",
        name=re.compile(r"^发布$|确认发布"),
    ).last
    publish.wait_for(state="visible", timeout=900000)
    deadline = time.time() + 900
    while time.time() < deadline:
        if publish.is_enabled():
            break
        time.sleep(2)
    else:
        raise RuntimeError("等待15分钟后发布按钮仍不可用")

    print("上传完成，正在点击发布……", flush=True)
    publish.click(timeout=10000)

    deadline = time.time() + 180
    while time.time() < deadline:
        body = page.locator("body").inner_text(timeout=10000)
        if any(text in body for text in ("发布成功", "作品发布成功", "发布完成")):
            print("监控到发布成功提示。", flush=True)
            return
        if "/content/manage" in page.url or "/content/manage/video" in page.url:
            print("发布后已进入作品管理页面。", flush=True)
            return
        time.sleep(2)
    raise RuntimeError("点击发布后未监控到明确的成功状态")


def mark_published(video):
    try:
        queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        queue = []
    target = str(video.resolve())
    for item in queue:
        if str(Path(item.get("output", "")).resolve()) == target:
            item.setdefault("status", {})["douyin"] = "published"
            break
    else:
        queue.append({
            "id": target,
            "title": video.stem,
            "output": target,
            "captions": {},
            "status": {"douyin": "published", "kuaishou": "pending"},
        })
    temporary = QUEUE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(QUEUE_FILE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index",
        type=int,
        default=1,
        help="上传第几个候选视频，从1开始"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="仅显示候选视频"
    )
    parser.add_argument(
        "--output",
        default="",
        help="按成片完整路径选择视频，优先于--index"
    )
    parser.add_argument("--auto-publish", action="store_true")
    parser.add_argument("--ai-cover", action="store_true")
    parser.add_argument("--declaration", action="store_true")
    args = parser.parse_args()

    rows = load_rows()

    if not rows:
        raise SystemExit("没有可上传的剪辑视频")

    if args.list:
        for index, item in enumerate(rows, 1):
            print(
                f"{index}. {item['title']} | "
                f"{item['duration']}秒 | "
                f"{item['video']}"
            )
        return

    if args.output:
        wanted = str(Path(args.output).resolve())
        matches = [
            (i, row) for i, row in enumerate(rows, 1)
            if str(row["video"].resolve()) == wanted
        ]
        if not matches:
            raise SystemExit("上传列表中没有找到指定成片")
        selected_index, item = matches[0]
    elif args.index < 1 or args.index > len(rows):
        raise SystemExit(
            f"--index必须在1至{len(rows)}之间"
        )
    else:
        selected_index = args.index
        item = rows[args.index - 1]
    video = item["video"]

    print("上传序号：", selected_index)
    print("视频：", video)
    print(
        "大小：",
        round(video.stat().st_size / 1024 / 1024, 2),
        "MB"
    )
    print("标题：", item["title"])
    print("简介：")
    print(item["description"])
    print(
        "\n发布模式：",
        "自动点击发布并监控结果" if args.auto_publish else "手动确认发布",
    )

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

        page = (
            context.pages[0]
            if context.pages
            else context.new_page()
        )

        print("[PROGRESS] 10% | 打开抖音创作平台", flush=True)
        page.goto(
            UPLOAD_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        dismiss_popups(page)

        file_input = page.locator(
            'input[type="file"]'
        ).first

        file_input.wait_for(
            state="attached",
            timeout=60000
        )

        print(f"[PROGRESS] 25% | 上传视频文件: {video.name}", flush=True)
        print("\n正在自动选择视频……")
        file_input.set_input_files(str(video))
        print("视频已交给抖音页面上传。")

        title_input = page.locator(
            'input[placeholder="填写作品标题，为作品获得更多流量"]'
        ).first

        title_input.wait_for(
            state="visible",
            timeout=600000
        )

        dismiss_popups(page)

        print("[PROGRESS] 45% | 填写标题与简介", flush=True)
        title_input.fill(item["title"])
        fill_description(
            page,
            item["description"]
        )

        if args.ai_cover:
            print("[PROGRESS] 60% | 选择AI生成封面", flush=True)
            select_ai_cover(page)
        if args.declaration:
            print("[PROGRESS] 75% | 设置作品自主声明", flush=True)
            set_declaration(page)

        screenshot = (
            BASE
            / f"douyin_ready_{selected_index:02d}.png"
        )

        page.screenshot(
            path=str(screenshot),
            full_page=True
        )

        print("\n自动填写完成。")
        print("截图：", screenshot)
        if args.auto_publish:
            print("[PROGRESS] 85% | 等待预审并自动发布", flush=True)
            wait_and_publish(page)
            mark_published(video)
            print("发布状态已写入本地记录。", flush=True)
            print(f"[PROGRESS] 100% | 发布完成: {item['title'][:20]}", flush=True)
            page.wait_for_timeout(3000)
            context.close()
            return

        print("[PROGRESS] 95% | 自动填写完成，请在浏览器中确认发布", flush=True)

        print("请在浏览器中等待上传和预审完成。")
        print("检查标题、简介、封面、声明和可见范围。")
        print("手动模式：确认无误后，由你点击“发布”。")

        if sys.stdin.isatty():
            input("\n完成检查或发布后，回到终端按回车关闭浏览器：")
        else:
            print("\n网页后台模式：发布完成后请关闭此Chrome窗口。")
            while context.pages:
                time.sleep(1)

        context.close()


if __name__ == "__main__":
    main()
