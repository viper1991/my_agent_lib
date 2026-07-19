# my_agent_lib — 通用 AI Agent 框架设计文档

> 版本: 1.0
> 来源: 从 hab/lib 提取并重构为独立项目
> 目标: 任何项目只需实现接口 + 提供配置，即可接入 LLM Agent 能力

---

## 一、设计哲学

my_agent_lib 是一个纯粹的 Agent 框架库。它**定义接口 + 提供通用实现**，不做任何业务决策。

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
│  │ DeepSeekProvider LLM 调用                            │    │
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

**核心原则**：lib 不偏袒任何项目。hab 的 `refresh_heavyweight.py` 和 home-tel 的 `ai_secretary/main.py` 平级——都是 lib 的消费者，各自通过构造参数注入自己的配置。

---

## 二、目录结构

```
my_agent_lib/
├── DESIGN.md                      ← 本文档
│
├── agent/
│   ├── orchestrator.py            Agent Loop 编排引擎
│   └── snapshot.py                首轮快照构建器（通用能力，项目可选使用）
│
├── tools/
│   ├── base.py                    Tool ABC + ToolRegistry + TerminalOutputTool 接口
│   ├── room_status.py             HA 房间状态查询
│   ├── trend.py                   HA 实体趋势查询
│   ├── events.py                  HA + UniFi 事件查询
│   ├── wifi_env.py                UniFi WiFi 环境分析
│   ├── client_status.py           UniFi 客户端状态
│   ├── traffic_analysis.py        UniFi DPI 流量分析
│   ├── device_inventory.py        UniFi 设备清单
│   └── network_alarms.py          UniFi 网络告警
│   # 注意：没有 final_output.py — 终结工具由各项目实现 TerminalOutputTool 接口
│
├── llm/
│   ├── provider.py                LLMProvider 抽象基类 + LLMResponse 数据结构
│   └── deepseek.py                DeepSeek 实现（OpenAI SDK 兼容）
│
├── clients/
│   ├── ha_client.py               Home Assistant REST API 客户端
│   └── unifi_client.py            UniFi Controller REST API 客户端
│
├── prompts.py                     提示词加载与模板替换
├── config.py                      YAML 配置加载器
├── interaction_log.py             LLM 交互日志（JSONL + console）
└── tool_counter.py                持久化工具调用计数器
```

---

## 三、核心接口

### 3.1 Tool ABC

所有工具的抽象基类。

| 属性/方法 | 类型 | 说明 |
|-----------|------|------|
| `name: str` | 类属性 | 工具名称，对应 OpenAI function name |
| `description: str` | 类属性 | 工具描述，LLM 看到的内容 |
| `parameters: dict` | 类属性 | JSON Schema 参数定义 |
| `max_calls: int \| None` | 类属性 | 单次运行最大调用次数。`None` = 无限制 |
| `terminal: bool` | 类属性 | 是否为终结工具。默认 `False` |
| `execute(**kwargs) -> Any` | 抽象方法 | 执行工具逻辑，返回可 JSON 序列化的结果 |
| `to_openai_tool() -> dict` | 方法 | 生成 OpenAI function calling 格式 |

### 3.2 TerminalOutputTool（终结工具接口）

**这是项目唯一必须实现的接口。** 每个项目的输出格式不同（仪表盘 JSON / 口语回复文本 / 控制指令 / ...），lib 只定义接口，不提供实现。

```python
class TerminalOutputTool(Tool):
    terminal = True  # 固定，Orchestrator 通过此标记识别

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """执行后 Orchestrator 立即结束循环，返回该 dict。"""
        ...
```

各项目继承此类：

- **hab**: `HabFinalOutputTool(TerminalOutputTool)` → 输出 `{sensor_panel: [...], summary: [...]}`
- **ai_secretary**: `SecretaryFinalOutputTool(TerminalOutputTool)` → 输出 `{reply_text: "..."}`

### 3.3 LLMProvider ABC

统一的 LLM 交互接口。

```python
class LLMProvider(ABC):
    def chat(messages, tools=None, **kwargs) -> LLMResponse: ...

class LLMResponse:
    content: str | None
    tool_calls: list[dict]
    assistant_message: dict | None    # 含 reasoning_content，用于多轮回传
    raw: Any                          # 原始 API 响应
```

内置实现：`DeepSeekProvider`（OpenAI SDK 兼容，可配置 base_url 适配其他兼容 API）。

---

## 四、ToolRegistry：工具注册与配额

### 4.1 API

| 方法/属性 | 说明 |
|-----------|------|
| `register(tool: Tool)` | 注册工具实例。name 不可重复 |
| `get(name) -> Tool \| None` | 按名称获取工具 |
| `all_tools -> list[Tool]` | 所有已注册工具 |
| `terminal_tool_name -> str \| None` | 自动检测：返回第一个 `terminal=True` 的工具名 |
| `execute(name, arguments) -> Any` | 执行工具（arguments 可为 str JSON 或 dict） |

### 4.2 配额管控

| 方法 | 说明 |
|------|------|
| `is_exhausted(name) -> bool` | 检查工具配额是否耗尽 |
| `usage_count(name) -> int` | 已调用次数 |
| `increment(name)` | 计数 +1（触发 `on_tool_call` 回调） |
| `get_openai_tool_defs() -> list[dict]` | 生成 OpenAI 格式，自动排除已耗尽工具 |

### 4.3 持久化计数器

`ToolRegistry.__init__` 接受 `on_tool_call: Callable[[str], None] | None` 回调。项目可传入 `tool_counter.increment` 实现持久化，或传 `None` 仅内存计数。

---

## 五、Orchestrator：Agent Loop 引擎

### 5.1 构造参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `llm` | `LLMProvider` | 必填 | LLM 实例 |
| `tools` | `ToolRegistry` | 必填 | 工具注册表 |
| `snapshot` | `str` | 必填 | 首轮 user message 文本 |
| `prompts` | `Prompts` | 必填 | 提示词配置 |
| `max_rounds` | `int` | `6` | 最大额外轮次（不含快照） |
| `tools_per_round` | `int` | `1` | 每轮最大工具调用数 |
| `terminal_tool_name` | `str` | 自动从 tools 检测 | 终结工具名称 |
| `interaction_log` | `InteractionLog \| None` | `None` | 文件日志（None = 仅 console） |
| `default_output` | `Callable[[], dict]` | 内置默认值 | 兜底输出函数 |
| `format_summaries` | `Callable \| None` | `None` | 格式化近期摘要（None = 跳过） |

### 5.2 循环流程

```
首轮: system_prompt + snapshot → LLM

For round in 1..max_rounds:
  ├─ 最后一轮？→ 仅保留 terminal_tool_name 工具，强制提交
  ├─ 调用 LLM (messages + tools)
  ├─ 无 tool_calls → 退出循环
  ├─ 截断至 tools_per_round 个调用
  └─ 对每个 tool_call:
       ├─ 配额已尽？→ 返回错误消息
       ├─ 执行工具（JSON 格式错误时自动修复，最多 1 次重试）
       ├─ 是终结工具？→ 返回结果，结束
       └─ 否则追加 tool result 到 messages

循环耗尽无输出:
  └─ fallback: 仅保留终结工具 → 再试一次 → 仍失败则调 default_output()
```

### 5.3 消息模板

Orchestrator 在特定场景向 LLM 注入提示消息，消息内容来自 `Prompts.get_message()`：

| 消息键 | 触发场景 |
|--------|---------|
| `discarded_tool_call` | LLM 单轮调用超过 `tools_per_round` 个工具 |
| `quota_exhausted` | 工具配额耗尽 |
| `json_fix_request` | 工具参数 JSON 格式错误 |
| `validation_fix_request` | 工具参数校验失败 |
| `fallback_prompt` | 循环耗尽，要求立即提交 |
| `fallback_fix_request` | fallback 的 JSON 仍有问题 |

---

## 六、支持模块

### 6.1 InteractionLog（日志）

记录每轮 LLM 交互的完整输入/输出到 JSONL 文件（含 tool_defs 工具定义摘要），同时向 console 输出结构化摘要。

| 构造参数 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `log_dir` | `str` | `'logs/interactions'` | JSONL 文件目录 |
| `run_label` | `str` | `'agent'` | 文件名前缀 |
| `enabled` | `bool` | `True` | False 时不创建文件 |

**静态方法** `log_console()` 始终可用，不受 `enabled` 影响。

### 6.2 Prompts（提示词引擎）

从 YAML 加载提示词，支持 `{{placeholder}}` 模板替换。

| 方法 | 说明 |
|------|------|
| `Prompts.load(path) -> Prompts` | 从 YAML 文件加载 |
| `get(key) -> Any` | 点号路径访问（`'messages.fallback_prompt'`） |
| `format(key, **kwargs) -> str` | 获取模板并替换占位符 |
| `get_message(name, **kwargs) -> str` | `format(f'messages.{name}', **kwargs)` 的快捷方式 |

### 6.3 Config（配置加载）

`load_config(path) -> SimpleNamespace`：加载 YAML → 递归转为 `SimpleNamespace`，支持 `config.llm.model` 式访问。path 为 None 时自动在常见位置搜索。

### 6.4 API 客户端

- **HAClient**: Home Assistant REST API（`/api/states/`, `/api/history/period`, `/api/logbook`）。`from_config(cfg)` 从配置命名空间创建。
- **UniFiClient**: UniFi Controller REST API（devices, clients, rogue APs, DPI, alarms, statistics）。`from_config(cfg)` 从配置命名空间创建。

---

## 七、内置工具（8 个数据工具）

全部实现 `Tool` ABC，查询标准 HA / UniFi API，返回结构化数据。

| # | 工具名 | 类别 | 配额 | 后端 |
|---|--------|------|------|------|
| 1 | `get_room_status` | HA 查询 | 可配（默认 3） | HA `/api/states/` |
| 2 | `get_trend` | HA 查询 | 可配（默认 3） | HA `/api/history/period` |
| 3 | `get_events` | 事件查询 | ∞ | HA logbook + UniFi events |
| 4 | `get_wifi_environment` | 网络诊断 | ∞ | UniFi devices + rogue APs |
| 5 | `get_client_status` | 网络诊断 | ∞ | UniFi `/stat/sta` |
| 6 | `get_traffic_analysis` | 网络诊断 | 可配（默认 2） | UniFi DPI |
| 7 | `get_device_inventory` | 网络诊断 | 可配（默认 1） | UniFi `/stat/alluser` |
| 8 | `get_network_alarms` | 网络诊断 | 可配（默认 1） | UniFi `/stat/alarm` |

配额可通过 `max_calls` 构造参数配置。设为 `None` 则不限制。

---

## 八、接入清单

任何项目只需完成以下 5 步即可接入 Agent 能力。**只有第 1 步是必须实现的接口**，其余是配置和组装。

| 步骤 | 做什么 | 实现方式 |
|------|--------|----------|
| **1. 实现终结工具** | 继承 `TerminalOutputTool` ABC | 各项目定义自己的输出格式 |
| **2. 编写提示词** | YAML 文件，含 `system_prompt` + `messages.*` 模板 | 直接复用 `Prompts.load()` 加载 |
| **3. 编写配置** | YAML 文件，LLM 参数、Agent 参数、工具配额、API 端点、日志路径 | 直接复用 `load_config()` 加载 |
| **4. 构建上下文** | 构造注入首轮的 user message 文本 | 可复用 `agent/snapshot.py`，或自写 |
| **5. 组装入口** | 创建客户端 → 注册工具 → 创建日志器 → 初始化 Orchestrator → 运行 | 参考下方示例 |

最小示例（伪代码）：

```
# 1. 加载配置
config = load_config('config.yaml')

# 2. 初始化 API 客户端
ha = HAClient(config.ha.url, config.ha.token)
unifi = UniFiClient(config.unifi.url, ...)

# 3. 注册工具
tools = ToolRegistry(on_tool_call=tool_counter.increment)
tools.register(GetRoomStatusTool(ha, rooms, max_calls=config.tools.room_status_quota))
tools.register(GetWifiEnvironmentTool(unifi))
# ... 注册其余工具
tools.register(MyTerminalOutputTool())  # 项目自己实现

# 4. 构建上下文
context = build_my_context(...)  # 项目自己构造

# 5. 初始化日志
log = InteractionLog(log_dir=config.logging.dir, run_label=config.logging.label)

# 6. 运行 Agent
orch = Orchestrator(
    llm=DeepSeekProvider(model=config.llm.model, api_key=config.llm.api_key),
    tools=tools,
    snapshot=context,
    prompts=Prompts.load('prompts.yaml'),
    max_rounds=config.agent.max_rounds,
    tools_per_round=config.agent.tools_per_round,
    interaction_log=log,
)
result = orch.run()
```

---

## 九、重构说明（从 hab/lib 提取）

my_agent_lib 从 hab/lib 提取而来，重构消除了以下硬编码：

| 原问题 | 解决方案 |
|--------|----------|
| Orchestrator 硬编码 `'final_output'` | `TerminalOutputTool` 接口 + `ToolRegistry.terminal_tool_name` 自动发现 |
| Orchestrator 内部加载提示词 | 构造参数 `prompts: Prompts`，外部注入 |
| Orchestrator 硬编码仪表盘兜底输出 | 构造参数 `default_output: Callable` |
| Orchestrator 检查 `sensor_panel` 字段 | 移除，接受任意合法 dict |
| InteractionLog 路径写死 | 构造参数 `log_dir` |
| ToolRegistry 硬 import tool_counter | 构造参数 `on_tool_call` 回调 |
| DeepSeekProvider 仅取环境变量 | 构造参数 `api_key` |

所有改动向后兼容——默认值等于旧行为。

---

## 十、依赖

- Python ≥ 3.10
- `openai` — DeepSeek API（OpenAI SDK 兼容）
- `PyYAML` — 配置和提示词加载
- `httpx` 或 `requests` — API 客户端
- 可选：`faster-whisper` + `websocket-client` — ASR（由调用方决定）
