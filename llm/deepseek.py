"""DeepSeek LLM Provider（OpenAI 兼容 SDK）。

DeepSeek API 完全兼容 OpenAI SDK，仅 base_url 不同。
也适用于其他 OpenAI 兼容 API（如 OpenRouter、vLLM）。
"""
import logging
import os
import time
from types import SimpleNamespace
from typing import Any

from openai import OpenAI

from my_agent_lib.llm.provider import LLMProvider, LLMResponse


def _to_dict(obj: Any) -> Any:
    """递归将 SimpleNamespace 转为 dict，用于 extra_body 参数传递。"""
    if isinstance(obj, SimpleNamespace):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    return obj

logger = logging.getLogger(__name__)


def _count_tokens_est(messages: list[dict]) -> int:
    """粗略估算消息的 token 数（中文字符 * 2 + 英文字符）。"""
    total = 0
    for m in messages:
        content = m.get('content', '') or ''
        if isinstance(content, str):
            for ch in content:
                total += 2 if ord(ch) > 127 else 1
        tc = m.get('tool_calls')
        if tc:
            for t in tc:
                func = t.get('function', {})
                total += len(func.get('name', ''))
                total += len(str(func.get('arguments', '')))
        if m.get('role') == 'tool':
            c = m.get('content', '') or ''
            total += len(str(c))
    return total


class DeepSeekProvider(LLMProvider):
    """DeepSeek LLM 提供者（OpenAI SDK 实现）。

    支持通过构造参数传入 api_key，也可通过环境变量读取。
    """

    def __init__(
        self,
        model: str = 'deepseek-chat',
        base_url: str = 'https://api.deepseek.com',
        api_key_env: str = 'DEEPSEEK_API_KEY',
        api_key: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        reasoning_effort: str | None = None,
        extra_body: dict | None = None,
    ):
        # 优先级: 参数 > 环境变量 > 报错
        resolved_key = api_key or os.environ.get(api_key_env)
        if not resolved_key:
            raise ValueError(
                f'API key not provided. Set {api_key_env} environment variable '
                f'or pass api_key parameter.'
            )
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort
        self._extra_body = extra_body
        self._client = OpenAI(api_key=resolved_key, base_url=base_url)
        self._call_count = 0

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        response_format: dict | None = None,
        **kwargs,
    ) -> LLMResponse:
        self._call_count += 1
        call_id = f'LLM#{self._call_count}'

        params = {
            'model': kwargs.get('model', self._model),
            'messages': messages,
            'max_tokens': kwargs.get('max_tokens', self._max_tokens),
            'temperature': kwargs.get('temperature', self._temperature),
        }

        if self._reasoning_effort:
            params['reasoning_effort'] = self._reasoning_effort
        if self._extra_body:
            params['extra_body'] = _to_dict(self._extra_body)

        if tools:
            params['tools'] = tools
        elif response_format:
            params['response_format'] = response_format

        estimated_input = _count_tokens_est(messages)
        tool_count = len(tools) if tools else 0

        logger.info(
            '%s >> messages=%d, tools=%d, ~%d tok, model=%s',
            call_id, len(messages), tool_count, estimated_input, params['model'],
        )

        t0 = time.monotonic()
        try:
            resp = self._client.chat.completions.create(**params)
        except Exception as e:
            logger.error('%s >> API call failed after %.1fs: %s',
                         call_id, time.monotonic() - t0, e)
            raise

        duration = time.monotonic() - t0

        choice = resp.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    'id': tc.id,
                    'type': tc.type,
                    'function': {
                        'name': tc.function.name,
                        'arguments': tc.function.arguments,
                    },
                })

        asst_msg = {'role': 'assistant'}
        if msg.content:
            asst_msg['content'] = msg.content
        else:
            asst_msg['content'] = None
        if tool_calls:
            asst_msg['tool_calls'] = tool_calls
        rc = getattr(msg, 'reasoning_content', None)
        if rc:
            asst_msg['reasoning_content'] = rc

        if tool_calls:
            names = ', '.join(tc['function']['name'] for tc in tool_calls)
            logger.info('%s << %.1fs, %d tool(s): %s', call_id, duration, len(tool_calls), names)
        elif msg.content:
            preview = msg.content.strip()[:100].replace('\n', ' ')
            logger.info('%s << %.1fs, text (%d chars): %s',
                        call_id, duration, len(msg.content), preview)
        else:
            logger.info('%s << %.1fs, empty response', call_id, duration)

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            assistant_message=asst_msg,
            raw=resp,
        )
