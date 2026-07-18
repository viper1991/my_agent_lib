"""工具调用计数器。

每次 LLM 调用某个工具时计数 +1，持久化到 JSON 文件。
文件路径为 config/tool_usage.json，内容为 {tool_name: count}。
"""
import json
import logging
import os

logger = logging.getLogger(__name__)


def _load(path: str) -> dict:
    try:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning('Failed to load tool counter: %s', e)
    return {}


def _save(path: str, data: dict):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.warning('Failed to save tool counter: %s', e)


def increment(tool_name: str, count: int = 1, path: str = 'config/tool_usage.json'):
    """增加指定工具的调用计数。"""
    data = _load(path)
    data[tool_name] = data.get(tool_name, 0) + count
    _save(path, data)
    logger.debug('Tool counter: %s: %d -> %d', tool_name,
                 data[tool_name] - count, data[tool_name])


def get_counts(path: str = 'config/tool_usage.json') -> dict:
    """获取所有工具计数。"""
    return _load(path)


def reset(path: str = 'config/tool_usage.json'):
    """重置所有计数。"""
    _save(path, {})
    logger.info('Tool counter reset')
