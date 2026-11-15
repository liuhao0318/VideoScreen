from pathlib import Path
from ollama import Client
import json

transcript = Path("transcript.txt")

if not transcript.exists():
    raise FileNotFoundError("找不到 transcript.txt")

lines = transcript.read_text(encoding="utf-8").splitlines()

client = Client(host="http://127.0.0.1:11434")

# 每批约100行，避免一次输入过长
batch_size = 100
results = []

for i in range(0, len(lines), batch_size):
    batch = lines[i:i + batch_size]

    if not batch:
        continue

    text = "\n".join(batch)

    print(f"\n正在分析第 {i // batch_size + 1} 批...")

    prompt = f"""
你是一名专业的中文直播视频内容分析师。

你的任务是分析直播转写文本，判断内容是否具有剪辑价值。

重点关注：
1. 足球战术分析
2. 中国足球相关观点
3. 球员和教练评价
4. 争议性讨论
5. 有趣且相对完整的故事
6. 有传播价值的观点

对于日常闲聊、无意义重复、内容不完整的片段，应降低评分。

要求：
- 只根据提供的文字分析，不得编造内容。
- 评分范围为0到100。
- 不要为了凑数量而推荐片段。
- 识别文字中存在的时间戳。
- 返回JSON，不要输出其他解释。

JSON格式：
{{
  "score": 0,
  "topic": "主要话题",
  "summary": "内容摘要",
  "reason": "评分原因",
  "interesting": false,
  "start_time": 0,
  "end_time": 0
}}

直播转写内容：

{text}
"""

    try:
        response = client.chat(
            model="qwen2.5:7b",
            messages=[
                {"role": "user", "content": prompt}
            ],
            format="json",
            options={
                "temperature": 0.2,
                "num_ctx": 8192
            }
        )

        result = json.loads(response.message.content)
        result["batch"] = i // batch_size + 1
        results.append(result)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print("分析失败:", e)

Path("screen_results.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("\n分析完成，结果保存到 screen_results.json")
