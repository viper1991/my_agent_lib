"""my_agent_lib — 通用 AI Agent 框架。

定义接口 + 提供通用实现，不做任何业务决策。

用法:
    from my_agent_lib import Orchestrator, ToolRegistry, Tool, TerminalOutputTool
    from my_agent_lib import DeepSeekProvider, InteractionLog, Prompts
    from my_agent_lib import load_config, HAClient, UniFiClient
    from my_agent_lib.tools import GetRoomStatusTool, GetWifiEnvironmentTool
"""
from my_agent_lib.agent.orchestrator import Orchestrator
from my_agent_lib.tools.base import Tool, ToolRegistry, TerminalOutputTool
from my_agent_lib.llm.deepseek import DeepSeekProvider
from my_agent_lib.llm.provider import LLMProvider, LLMResponse
from my_agent_lib.interaction_log import InteractionLog
from my_agent_lib.prompts import Prompts
from my_agent_lib.config import load_config
from my_agent_lib.clients.ha_client import HAClient
from my_agent_lib.clients.unifi_client import UniFiClient
from my_agent_lib import tool_counter
from my_agent_lib.testing import DryRunLLMProvider, DryRunHAClient, DryRunUniFiClient
