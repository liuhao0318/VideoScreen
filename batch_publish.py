#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", action="append", required=True)
    parser.add_argument("--auto-publish", action="store_true")
    parser.add_argument("--ai-cover", action="store_true")
    parser.add_argument("--declaration", action="store_true")
    args = parser.parse_args()

    total = len(args.output)
    failed = 0
    for index, output in enumerate(args.output, 1):
        name = Path(output).name
        start_pct = round((index - 1) * 100 / max(1, total))
        print(f"\n[{index}/{total}] 自动准备发布：{name}", flush=True)
        print(f"[PROGRESS] {start_pct}% | 批量发布 [{index}/{total}]: {name}", flush=True)
        command = [
            sys.executable,
            "-u",
            str(ROOT / "douyin_web_uploader.py"),
            "--output",
            output,
        ]
        if args.auto_publish:
            command.append("--auto-publish")
        if args.ai_cover:
            command.append("--ai-cover")
        if args.declaration:
            command.append("--declaration")
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            failed += 1
            print("自动发布准备失败，可在网页或桌面端重试或改用“手动发布”。", flush=True)
        else:
            print("本条处理完成。", flush=True)

    print(f"\n批量处理结束：总计{total}，失败{failed}", flush=True)
    print(f"[PROGRESS] 100% | 批量发布结束（成功 {total - failed}/{total}）", flush=True)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
