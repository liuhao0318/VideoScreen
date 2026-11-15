import time
import torch
from pathlib import Path
from funasr import AutoModel

assert torch.cuda.is_available(), "CUDA不可用，请检查GPU环境"

print("GPU:", torch.cuda.get_device_name(0))

model = AutoModel(
    model="iic/SenseVoiceSmall",
    device="cuda:0",
    disable_update=True
)

print("开始识别5分钟中文直播...")

start = time.perf_counter()

result = model.generate(
    input="test.wav",
    language="zh",
    use_itn=True,
    batch_size_s=60
)

elapsed = time.perf_counter() - start

text = "\n".join(
    item.get("text", "") for item in result
)

Path("sensevoice_result.txt").write_text(
    text,
    encoding="utf-8"
)

print("\n========== 识别结果 ==========\n")
print(text)

print("\n========== 性能统计 ==========")
print(f"识别耗时: {elapsed:.2f} 秒")
print(f"实时因子RTF: {elapsed / 300:.3f}")
print("结果保存: sensevoice_result.txt")
