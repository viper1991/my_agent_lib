"""配置加载模块。从 YAML 配置文件返回嵌套命名空间对象。"""

import os
import yaml
from types import SimpleNamespace


def _to_namespace(d):
    """递归将 dict 转为 SimpleNamespace，方便点号访问。"""
    if isinstance(d, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in d.items()})
    if isinstance(d, list):
        return [_to_namespace(i) for i in d]
    return d


def load_config(path: str | None = None) -> SimpleNamespace:
    """加载 YAML 配置文件。

    Args:
        path: 配置文件路径。为 None 时自动在常见位置查找 config/config.yaml。

    Returns:
        SimpleNamespace 嵌套对象，支持 config.llm.model 式访问。
    """
    if path is None:
        _search_dirs = [
            os.getcwd(),
            os.path.dirname(os.path.abspath(__file__)),           # my_agent_lib/
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # C:/pj/
        ]
        for d in _search_dirs:
            candidate = os.path.join(d, 'config', 'config.yaml')
            if os.path.exists(candidate):
                path = candidate
                break
        if path is None:
            raise FileNotFoundError(
                "config/config.yaml not found. Searched: " +
                ", ".join(_search_dirs)
            )
    with open(path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)
    return _to_namespace(raw)
