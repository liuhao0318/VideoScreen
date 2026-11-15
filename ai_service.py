"""AI 统一服务模块 (VideoScreen AI Service)

支持：
1. 本地 Ollama (本地 AI 模型，如 qwen2.5:7b, deepseek-r1:8b 等)
2. 云端大模型 API (兼容 OpenAI 标准接口，如 DeepSeek, 通义千问 DashScope, 硅基流动, 智谱清言, OpenAI 等)
"""

import json
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

DEFAULT_AI_CONFIG = {
    "provider": "ollama",  # "ollama" 或 "api"
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5:7b",
        "temperature": 0.55,
    },
    "api": {
        "preset": "deepseek",  # deepseek | qwen | siliconflow | zhipu | moonshot | openai | custom
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.55,
    },
}

PRESETS = {
    "deepseek": {
        "name": "DeepSeek (深度求索 - 推荐)",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "name": "阿里通义千问 (DashScope)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "siliconflow": {
        "name": "硅基流动 (SiliconFlow)",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
    },
    "zhipu": {
        "name": "智谱清言 (Zhipu AI)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "moonshot": {
        "name": "月之暗面 (Moonshot / Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "openai": {
        "name": "OpenAI (GPT-4o-mini / GPT-4o)",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "custom": {
        "name": "自定义 OpenAI 兼容接口",
        "base_url": "",
        "model": "",
    },
}


def load_config():
    """读取 config.json 中的全局配置"""
    try:
        if CONFIG_PATH.is_file():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {}


def save_config(data):
    """保存配置至 config.json"""
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def get_ai_config():
    """获取完整的 AI 配置（含默认值补全）"""
    cfg = load_config().get("ai", {})
    provider = cfg.get("provider") or DEFAULT_AI_CONFIG["provider"]

    ollama_cfg = {**DEFAULT_AI_CONFIG["ollama"], **(cfg.get("ollama") or {})}
    api_cfg = {**DEFAULT_AI_CONFIG["api"], **(cfg.get("api") or {})}

    return {
        "provider": provider,
        "ollama": ollama_cfg,
        "api": api_cfg,
        "presets": PRESETS,
    }


def update_ai_config(new_ai_cfg):
    """更新 AI 配置"""
    full_cfg = load_config()
    current_ai = get_ai_config()

    if "provider" in new_ai_cfg:
        current_ai["provider"] = "api" if new_ai_cfg["provider"] in ("api", "openai_compatible") else "ollama"

    if "ollama" in new_ai_cfg and isinstance(new_ai_cfg["ollama"], dict):
        current_ai["ollama"].update(new_ai_cfg["ollama"])

    if "api" in new_ai_cfg and isinstance(new_ai_cfg["api"], dict):
        current_ai["api"].update(new_ai_cfg["api"])

    # 剔除 presets 避免存入 json
    save_data = {
        "provider": current_ai["provider"],
        "ollama": current_ai["ollama"],
        "api": current_ai["api"],
    }
    full_cfg["ai"] = save_data
    save_config(full_cfg)
    return get_ai_config()


def _clean_json_text(text: str) -> str:
    """去除 Markdown ```json ``` 代码块或首尾多余字符"""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return text


def _extract_json_object(text: str):
    """尝试从文本中解析 JSON 对象或列表"""
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except ValueError:
        # 兜底：查找最外层的 { ... } 或 [ ... ]
        start_brace = cleaned.find("{")
        end_brace = cleaned.rfind("}")
        if start_brace != -1 and end_brace > start_brace:
            sub = cleaned[start_brace : end_brace + 1]
            try:
                return json.loads(sub)
            except ValueError:
                pass
        start_bracket = cleaned.find("[")
        end_bracket = cleaned.rfind("]")
        if start_bracket != -1 and end_bracket > start_bracket:
            sub = cleaned[start_bracket : end_bracket + 1]
            try:
                return json.loads(sub)
            except ValueError:
                pass
        raise


def chat_completion(
    messages,
    provider=None,
    temperature=None,
    json_format=False,
    config_override=None,
    timeout=120,
    num_ctx=None,
):
    """
    统一的 AI 对话接口。
    
    参数：
        messages: [{"role": "user", "content": "..."}]
        provider: "ollama" | "api" | None (None则使用配置中的默认provider)
        temperature: 浮点数，None 则使用配置中的温度
        json_format: 是否期望返回 JSON 对象
        config_override: 临时覆盖配置（如测试连接时传入未保存的表单数据）
        timeout: 超时秒数（默认 120 秒）
        num_ctx: 可选上下文长度上限，默认 6144（兼顾 8GB 显卡显存余量与长转写窗口）
        
    返回：
        如果 json_format=True，返回解析后的 dict/list；
        如果 json_format=False，返回字符串内容。
    """
    cfg = config_override or get_ai_config()
    active_provider = provider or cfg.get("provider", "ollama")

    if active_provider == "ollama":
        ollama_cfg = cfg.get("ollama", {})
        base_url = (ollama_cfg.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
        model = ollama_cfg.get("model") or "qwen2.5:7b"
        temp = temperature if temperature is not None else float(ollama_cfg.get("temperature", 0.55))
        ctx_limit = int(num_ctx if num_ctx is not None else ollama_cfg.get("num_ctx", 6144))

        endpoint = f"{base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temp,
                "num_ctx": ctx_limit,
            },
        }
        if json_format:
            payload["format"] = "json"

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            raw_content = result.get("message", {}).get("content", "")
        except urllib.error.URLError as err:
            raise ValueError(f"连接本地 Ollama 失败 ({endpoint}): {err}。请确认 Ollama 正在运行。") from err
        except Exception as err:
            raise ValueError(f"Ollama 调用异常: {err}") from err

    elif active_provider in ("api", "openai_compatible"):
        api_cfg = cfg.get("api", {})
        base_url = (api_cfg.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
        api_key = (api_cfg.get("api_key") or "").strip()
        model = api_cfg.get("model") or "deepseek-chat"
        temp = temperature if temperature is not None else float(api_cfg.get("temperature", 0.55))

        if not api_key:
            raise ValueError("未配置云端大模型 API Key，请在 AI 设置中填入您的 API Key")

        endpoint = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temp,
        }
        if json_format:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            raw_content = result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as err:
            error_msg = f"HTTP {err.code}: {err.reason}"
            try:
                body = err.read().decode("utf-8", errors="replace")
                parsed_err = json.loads(body)
                if "error" in parsed_err:
                    msg = parsed_err["error"].get("message") or parsed_err["error"]
                    error_msg = f"{error_msg} - {msg}"
            except Exception:
                pass
            raise ValueError(f"调用云端大模型 API 失败: {error_msg}") from err
        except urllib.error.URLError as err:
            raise ValueError(f"无法连接到 API 地址 ({endpoint}): {err.reason}") from err
        except Exception as err:
            raise ValueError(f"API 调用异常: {err}") from err

    else:
        raise ValueError(f"不支持的 AI 模式：{active_provider}")

    if json_format:
        try:
            return _extract_json_object(raw_content)
        except Exception as err:
            raise ValueError(f"AI 未返回合法的 JSON 格式内容：{raw_content[:200]}...") from err

    return raw_content


def test_connection(provider=None, config=None):
    """测试指定 provider 或当前配置的连通性"""
    start_time = time.time()
    cfg = config or get_ai_config()
    target_provider = provider or cfg.get("provider", "ollama")

    messages = [
        {"role": "user", "content": "你好，这是一次连接测试，请仅回复“连接成功”四个字。"}
    ]

    try:
        reply = chat_completion(
            messages=messages,
            provider=target_provider,
            temperature=0.1,
            json_format=False,
            config_override=cfg,
            timeout=25,
        )
        latency_ms = round((time.time() - start_time) * 1000)
        model = (
            cfg["ollama"].get("model")
            if target_provider == "ollama"
            else cfg["api"].get("model")
        )
        return {
            "ok": True,
            "provider": target_provider,
            "model": model,
            "latency_ms": latency_ms,
            "reply": reply.strip(),
        }
    except Exception as err:
        latency_ms = round((time.time() - start_time) * 1000)
        return {
            "ok": False,
            "provider": target_provider,
            "latency_ms": latency_ms,
            "error": str(err),
        }

