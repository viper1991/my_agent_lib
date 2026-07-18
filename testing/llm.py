"""Dry-run LLM Provider — simulates LLM responses for testing.

Returns predetermined tool calls in sequence, ending with final_output.
"""
import json
import logging
import uuid
from typing import Any

from my_agent_lib.llm.provider import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

# Default tool call sequence for dry-run
_DEFAULT_RESPONSES: list[list[dict]] = [
    # Round 1: call get_wifi_environment
    [{
        'function': {
            'name': 'get_wifi_environment',
            'arguments': json.dumps({'band': 'all'}, ensure_ascii=False),
        },
    }],
    # Round 2: call get_network_alarms
    [{
        'function': {
            'name': 'get_network_alarms',
            'arguments': json.dumps({'hours_back': 24}, ensure_ascii=False),
        },
    }],
    # Round 3: call get_client_status
    [{
        'function': {
            'name': 'get_client_status',
            'arguments': json.dumps({}, ensure_ascii=False),
        },
    }],
]


class DryRunLLMProvider(LLMProvider):
    """模拟 LLM 响应，逐个返回预设的工具调用序列。

    在最后一轮或遇到仅 final_output 可用时，自动提交终结工具。
    适用于集成测试和 dry-run，不消耗 API 配额。
    """

    def __init__(self, responses: list[list[dict]] | None = None):
        self._responses = responses or _DEFAULT_RESPONSES
        self._call_count = 0
        self._all_responses: list[LLMResponse] = []

    @property
    def all_responses(self) -> list[LLMResponse]:
        """返回所有已发出的 LLM 响应（用于测试断言）。"""
        return self._all_responses

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        self._call_count += 1
        call_id = f'DRY#{self._call_count}'

        # 判断是否是最后一轮（仅 terminal 工具可用）
        tool_names = [t.get('function', {}).get('name', '') for t in (tools or [])]
        is_terminal_only = len(tool_names) == 1 and any(
            t.get('function', {}).get('name') for t in (tools or [])
        )

        if is_terminal_only:
            # 最后一轮：提交终结工具
            terminal_name = tool_names[0]
            # 检查调用历史，如果已有数据则包含在 final_output 中
            tool_calls = [{
                'id': f'call_{uuid.uuid4().hex[:8]}',
                'type': 'function',
                'function': {
                    'name': terminal_name,
                    'arguments': json.dumps({
                        'sensor_panel': [
                            {'label': '客厅温度', 'value': '26°C', 'trend': '→', 'remark': '舒适'},
                            {'label': '客厅湿度', 'value': '60%', 'trend': '→'},
                            {'label': '主卧温度', 'value': '24°C', 'trend': '↓', 'remark': '较2h前-1°C'},
                            {'label': '书房温度', 'value': '27°C', 'trend': '↑'},
                        ],
                        'summary': [
                            '各房间温度正常，湿度舒适',
                            '2.4G 信道 6 有 12 个干扰 AP，建议换信道',
                            '主卧温度正在下降，空调可能已关闭',
                        ],
                    }, ensure_ascii=False),
                },
            }]
        elif self._call_count <= len(self._responses):
            # 使用预设的响应序列
            tool_calls = []
            for t in self._responses[self._call_count - 1]:
                tc = dict(t)
                tc['id'] = f'call_{uuid.uuid4().hex[:8]}'
                tc['type'] = 'function'
                tool_calls.append(tc)
        else:
            # 响应序列用尽，返回空（让 Orchestrator 自然结束）
            tool_calls = []

        # 模拟 thinking
        reasoning = f'[DryRun] 模拟思考过程，第{self._call_count}轮调用，工具: {[t.get("function", {}).get("name", "?") for t in tool_calls]}'

        asst_msg = {'role': 'assistant', 'content': None}
        if tool_calls:
            asst_msg['tool_calls'] = tool_calls
        asst_msg['reasoning_content'] = reasoning

        response = LLMResponse(
            content=None,
            tool_calls=tool_calls,
            assistant_message=asst_msg,
        )
        self._all_responses.append(response)

        names = ', '.join(tc['function']['name'] for tc in tool_calls) if tool_calls else '(none)'
        logger.info('%s << tool(s): %s', call_id, names)
        return response
