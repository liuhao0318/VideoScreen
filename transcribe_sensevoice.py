import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

# 限制 PyTorch CPU 线程数，防止 VAD 算法吃满所有 CPU 核心导致系统交互卡死
torch.set_num_threads(4)
if hasattr(torch, "set_num_interop_threads"):
    try:
        torch.set_num_interop_threads(2)
    except Exception:
        pass
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

from funasr import AutoModel

SAMPLE_RATE = 16000
CHUNK_SECONDS = 300
MAX_SPEECH_SECONDS = 30


def clean_text(text):
    text = re.sub(r"<\|[^|]+\|>", "", text)
    return " ".join(text.split()).strip()


def has_audio_stream(video):
    """快速检测视频文件是否包含可用音频流，避免无音轨视频白白加载大模型报错"""
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(video),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return res.returncode == 0 and "audio" in res.stdout.lower()
    except Exception:
        return True


def extract_audio(video, wav):
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-err_detect", "ignore_err",
        "-y", "-i", str(video),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-threads", "4",
        "-c:a", "pcm_s16le", str(wav)
    ]
    if shutil.which("nice"):
        cmd = ["nice", "-n", "10"] + cmd
    subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        check=True,
        timeout=900
    )


def get_speech_intervals(vad_model, audio):
    if len(audio) < int(0.2 * SAMPLE_RATE):
        return []

    # FunASR fsmn-vad 在纯静音或异常尾帧上偶尔会用
    # batch_data_time=0 计算实时率，触发 ZeroDivisionError。
    # 这类分块没有可转写语音，安全跳过即可。
    if not np.isfinite(audio).all() or float(np.max(np.abs(audio))) < 1e-5:
        return []

    try:
        result = vad_model.generate(
            input=audio,
            cache={},
            is_final=True
        )
    except ZeroDivisionError:
        print("  VAD遇到空白/异常尾块，已跳过。", flush=True)
        return []

    intervals = []

    for item in result:
        for start_ms, end_ms in item.get("value", []):
            if end_ms > start_ms:
                intervals.append((
                    max(0, int(start_ms)),
                    int(end_ms)
                ))

    return intervals


def split_interval(start, end, max_ms=30000):
    while start < end:
        stop = min(start + max_ms, end)
        yield start, stop
        start = stop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    if not video.is_file():
        raise FileNotFoundError(video)

    if not has_audio_stream(video):
        print("NO_AUDIO_STREAM: 该视频文件不包含音频流（无音轨），无法进行语音转写。", flush=True)
        raise SystemExit(2)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用，停止处理以避免意外使用 CPU")

    # 限制 PyTorch 显存上限为 35% (约 2.8GB)，防止与本地 Ollama (Qwen2.5:7b) 抢显存导致显存颠簸与整机卡死
    try:
        torch.cuda.set_per_process_memory_fraction(0.35, 0)
    except Exception:
        pass

    print("GPU:", torch.cuda.get_device_name(0), flush=True)

    vad_local = Path.home() / ".cache/modelscope/models/iic--speech_fsmn_vad_zh-cn-16k-common-pytorch/snapshots/master"
    sv_local = Path.home() / ".cache/modelscope/models/iic--SenseVoiceSmall/snapshots/master"
    vad_model_id = str(vad_local) if vad_local.is_dir() else "fsmn-vad"
    sv_model_id = str(sv_local) if sv_local.is_dir() else "iic/SenseVoiceSmall"

    print("加载 VAD 模型...", flush=True)
    vad = AutoModel(
        model=vad_model_id,
        device="cpu",
        disable_update=True
    )

    print("加载 SenseVoiceSmall...", flush=True)
    asr = AutoModel(
        model=sv_model_id,
        device="cuda:0",
        disable_update=True
    )

    segments = []

    with tempfile.TemporaryDirectory(prefix="videoscreen_asr_") as tmp:
        wav = Path(tmp) / "audio.wav"

        print("FFmpeg 提取音频...", flush=True)
        extract_audio(video, wav)

        with sf.SoundFile(str(wav)) as audio_file:
            if audio_file.samplerate != SAMPLE_RATE:
                raise ValueError("音频采样率不符合要求")

            total_frames = len(audio_file)
            total_seconds = max(1.0, total_frames / SAMPLE_RATE)
            chunk_frames = CHUNK_SECONDS * SAMPLE_RATE
            last_pct_reported = -5
            total_slices = 0
            failed_slices = 0

            for offset in range(0, total_frames, chunk_frames):
                audio_file.seek(offset)
                samples = audio_file.read(
                    frames=min(chunk_frames, total_frames - offset),
                    dtype="float32",
                    always_2d=False
                )

                if samples.size == 0 or len(samples) < int(0.4 * SAMPLE_RATE):
                    continue

                chunk_start = offset / SAMPLE_RATE
                chunk_pct = min(99, int(chunk_start * 100 / total_seconds))
                print(
                    f"[PROGRESS] {chunk_pct}% | 转写音频 {chunk_start:.0f}s / {total_seconds:.0f}s",
                    flush=True
                )
                last_pct_reported = chunk_pct

                try:
                    intervals = get_speech_intervals(vad, samples)
                except Exception as exc:
                    print(
                        f"⚠️ VAD 分段跳过异常块 [{chunk_start:.0f}s]: {exc}",
                        flush=True,
                    )
                    continue

                for start_ms, end_ms in intervals:
                    for sub_start, sub_end in split_interval(
                        start_ms,
                        end_ms,
                        MAX_SPEECH_SECONDS * 1000
                    ):
                        start_sample = max(
                            0, round(sub_start * SAMPLE_RATE / 1000)
                        )
                        end_sample = min(
                            len(samples),
                            round(sub_end * SAMPLE_RATE / 1000)
                        )

                        speech = samples[start_sample:end_sample]

                        if len(speech) < int(0.2 * SAMPLE_RATE):
                            continue

                        total_slices += 1
                        try:
                            result = asr.generate(
                                input=speech,
                                language="zh",
                                use_itn=True
                            )
                        except Exception as exc:
                            err_upper = str(exc).upper()
                            if "CUDA" in err_upper and (
                                "OUT OF MEMORY" in err_upper
                                or "DEVICE-SIDE" in err_upper
                                or "CUBLAS" in err_upper
                            ):
                                raise
                            failed_slices += 1
                            seg_s = chunk_start + sub_start / 1000
                            seg_e = chunk_start + sub_end / 1000
                            print(
                                f"⚠️ 跳过异常语音片段 [{seg_s:.1f}s - {seg_e:.1f}s]: {exc}",
                                flush=True,
                            )
                            continue

                        text = clean_text(
                            " ".join(
                                item.get("text", "")
                                for item in result
                            )
                        )

                        if not text:
                            continue

                        start = chunk_start + sub_start / 1000
                        end = chunk_start + sub_end / 1000

                        segments.append({
                            "start": round(start, 3),
                            "end": round(end, 3),
                            "text": text
                        })

                        print(
                            f"[{start:.1f}s - {end:.1f}s] {text}",
                            flush=True
                        )

                        cur_pct = min(99, int(end * 100 / total_seconds))
                        if cur_pct - last_pct_reported >= 3:
                            last_pct_reported = cur_pct
                            print(
                                f"[PROGRESS] {cur_pct}% | 语音识别 {end:.0f}s / {total_seconds:.0f}s (已识别 {len(segments)} 句)",
                                flush=True,
                            )

    if failed_slices > 0:
        print(
            f"⚠️ 本次有 {failed_slices}/{total_slices} 个音频切片识别异常已自动跳过",
            flush=True,
        )
        if total_slices > 0 and failed_slices == total_slices and not segments:
            raise RuntimeError(f"所有语音片段识别均失败（共 {failed_slices} 段）")

    segments.sort(key=lambda x: x["start"])

    json_path = output / "transcript.json"
    txt_path = output / "transcript.txt"

    tmp_json = output / "transcript.json.tmp"
    tmp_txt = output / "transcript.txt.tmp"

    tmp_json.write_text(
        json.dumps(segments, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    tmp_txt.write_text(
        "\n".join(
            f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}"
            for s in segments
        ),
        encoding="utf-8"
    )

    tmp_json.replace(json_path)
    tmp_txt.replace(txt_path)

    print("\n转写完成")
    print("语音段数量:", len(segments))
    print("输出目录:", output)


if __name__ == "__main__":
    main()
