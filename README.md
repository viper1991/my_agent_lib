<p align="center">
  <h1 align="center">my_agent_lib</h1>
  <p align="center">
    <b>通用 AI Agent 框架 — 定义接口 + 提供实现，不做任何业务决策</b>
  </p>
  <p align="center">
    Architecture: Agent Loop + Tool Matrix + LLM Abstraction &nbsp;|&nbsp; Philosophy: Interface over Implementation
  </p>
  <p align="center">
    Stack: Python 3.10+ &nbsp;|&nbsp; LLM: DeepSeek (OpenAI SDK Compatible)
  </p>
  <p align="center">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
    <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python 3.10+">
  </p>
</p>

---

## 这是什么？

`my_agent_lib` 是从 [Home-AgentOps-Blueprint (HAB)](https://github.com/viper1991/Home-AgentOps-Blueprint) 项目中提取的通用 Agent 框架。它把 Agent Loop、工具注册、LLM 调用、日志等能力沉淀为独立库，让**任何项目**只需实现一个接口 + 写配置，即可获得完整的 AI Agent 能力。

### 设计哲学

```
┌──────────────────────────────────────────────────────────────┐
│                      my_agent_lib                            │
│                                                              │
│  接口（项目必须实现）                                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ TerminalOutputTool ABC    终结输出工具               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  通用实现（开箱即用）                                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Orchestrator    Agent Loop 引擎                      │    │
│  │ ToolRegistry    工具注册 + 配额管控                   │    │
│  │ 8 个数据工具     HA + UniFi 查询                     │    │
│  │ DeepSeekProvider LLM 调用 (OpenAI SDK 兼容)          │    │
│  │ InteractionLog  LLM 交互日志                         │    │
│  │ Prompts         提示词模板引擎                        │    │
│  │ Config          YAML 配置加载                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  完全由项目决定                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 提示词 · 工具配额 · LLM 参数 · 日志路径 · 上下文构造  │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

**核心信念**：在 AI 时代，框架不应替开发者做决策。`my_agent_lib` 提供所有通用能力，但不决定你用哪个模型、写什么提示词、配多少工具配额——这些都是你的事。

---

## 快速开始

### 1. 实现终结工具

每个项目的输出格式不同，你需要实现 `TerminalOutputTool` 接口：

```python
from my_agent_lib.tools.base import TerminalOutputTool

class MyFinalOutput(TerminalOutputTool):
    name = 'final_output'
    description = '提交最终输出'

    def __init__(self):
        self.parameters = {
            'type': 'object',
            'properties': {
                'reply_text': {
                    'type': 'string',
                    'description': '回复文本',
                },
            },
            'required': ['reply_text'],
        }

    def execute(self, **kwargs) -> dict:
        return kwargs  # Orchestrator 拦截后直接返回此 dict
```

### 2. 编写配置

```yaml
# config.yaml
llm:
  model: "deepseek-v4-flash"
  temperature: 0.5

agent:
  max_rounds: 4
  tools_per_round: 1
```

```yaml
# prompts.yaml
system_prompt: |
  你是一个智能助手，使用中文回答问题。

messages:
  fallback_prompt: 请调用 final_output 提交回复。
```

### 3. 组装 Agent

```python
import sys
sys.path.insert(0, '/path/to/parent')

from my_agent_lib import Orchestrator, ToolRegistry, DeepSeekProvider
from my_agent_lib import InteractionLog, Prompts, load_config

# 加载配置
config = load_config('config.yaml')
prompts = Prompts.load('prompts.yaml')

# 注册工具
tools = ToolRegistry()
tools.register(MyFinalOutput())

# 初始化 LLM
llm = DeepSeekProvider(model=config.llm.model)

# 运行 Agent
log = InteractionLog(log_dir='logs', run_label='my_app')
orch = Orchestrator(
    llm, tools, '用户问：今天天气怎么样？',
    prompts=prompts, interaction_log=log,
)
result = orch.run()
print(result)  # → {"reply_text": "..."}
```

---

## 架构

```
my_agent_lib/
├── agent/
│   └── orchestrator.py      Agent Loop 编排引擎
│
├── tools/
│   ├── base.py               Tool ABC + ToolRegistry + TerminalOutputTool
│   ├── room_status.py        HA 房间状态查询
│   ├── trend.py              HA 实体趋势分析
│   ├── events.py             事件日志（HA + UniFi）
│   ├── wifi_env.py           WiFi 环境分析
│   ├── client_status.py      客户端状态
│   ├── traffic_analysis.py   DPI 流量分析
│   ├── device_inventory.py   设备盘点
│   └── network_alarms.py     网络告警
│
├── llm/
│   ├── provider.py           LLMProvider 抽象基类
│   └── deepseek.py           DeepSeek 实现（OpenAI SDK 兼容）
│
├── clients/
│   ├── ha_client.py          Home Assistant REST API 客户端
│   └── unifi_client.py       UniFi Controller REST 客户端
│
├── testing/                   Dry-run 测试工具
│   ├── llm.py                模拟 LLM 响应
│   ├── ha_client.py          模拟 HA 数据
│   └── unifi_client.py       模拟 UniFi 数据
│
├── interaction_log.py        LLM 交互日志（JSONL）
├── prompts.py                提示词模板引擎
├── config.py                 YAML 配置加载器
└── tool_counter.py           持久化工具调用计数器
```

---

## 接入清单

任何项目只需 5 步即可接入，其中**只有第 1 步是必须实现的接口**：

| 步骤 | 做什么 | 说明 |
|------|--------|------|
| 1 | 实现 `TerminalOutputTool` | 定义你自己的输出格式 |
| 2 | 编写 `prompts.yaml` | 系统提示词 + 消息模板 |
| 3 | 编写 `config.yaml` | LLM/Agent 参数 |
| 4 | 编写入口脚本 | 注册工具 → 初始化 Orchestrator → 运行 |
| 5 | 构建上下文 | 构造首轮 user message |

详细 API 文档见 [`DESIGN.md`](DESIGN.md)。

---

## Dry-Run 测试

`my_agent_lib` 内置了完整的模拟测试工具，不消耗 API 费用即可验证全链路：

```python
from my_agent_lib.testing import DryRunLLMProvider, DryRunHAClient, DryRunUniFiClient

llm = DryRunLLMProvider()          # 返回预设的工具调用序列
ha = DryRunHAClient()              # 返回预设的 HA 传感器数据
unifi = DryRunUniFiClient()        # 返回预设的 UniFi 网络数据
```

---

## 与 HAB 的关系

```
C:/pj/
├── my_agent_lib/          ← 通用 Agent 框架（本仓库）
├── hab/                   ← 消费者之一：墨水屏仪表盘
└── home-tel/              ← 消费者之二：AI 电话秘书
```

`my_agent_lib` 提取自 [HAB](https://github.com/viper1991/Home-AgentOps-Blueprint)，与其平级。两者都是独立项目，通过 `sys.path` 引用。

---

## 许可证

MIT
