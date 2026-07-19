# HA 工具重构设计 v2.0

## 概述

基于 HA REST API 实际能力，将原有的 3 个 HA 工具重构为 4 个更清晰、更高效的只读工具。

### 核心原则

- **只读** — 所有工具仅查询数据，不执行任何控制操作
- **合理合并 API 调用** — 全屋状态只需一次 `/api/states`
- **分组输出** — 控制事件与环境读数分离，避免 LLM 被噪声淹没
- **纯客观数据** — 不做趋势判定，不写自然语言备注，只返回统计值

---

## 一、clients/ha_client.py 改动

### 保留的方法

```python
class HAClient:
    def get_state(self, entity_id: str) -> dict
        → GET /api/states/{entity_id}

    def get_states(self) -> list[dict]
        → GET /api/states

    def get_history(self, entity_id: str, start_time: datetime, end_time: datetime | None = None) -> list[dict]
        → GET /api/history/period/{utc}?filter_entity_id={entity_id}&end_time={end_time}

    def get_logbook(self, start_time: datetime, end_time: datetime | None = None) -> list[dict]
        → GET /api/logbook/{utc}?end_time={end_time}
```

### 新增的方法

```python
    def get_history_batch(self, entity_ids: list[str], start_time: datetime, end_time: datetime | None = None) -> dict[str, list[dict]]
        """批量查多个实体的历史数据。

        HA 的 history API 一次只支持一个 filter_entity_id，
        内部逐个调用 get_history()，返回 {entity_id: [points]}。
        """
```

### 删除

- `get_states_batch(entity_ids)` — 替代方式：调一次 `get_states()` 全量后用列表推导 `[s for s in states if s['entity_id'] in entity_ids]`

---

## 二、工具矩阵

| # | 工具 | 用途 | API 调用 |
|---|------|------|----------|
| ① | `get_household_snapshot` | 全屋当前状态总览 | `get_states()` × 1 |
| ② | `get_device_history` | 设备控制变更记录 | `get_history_batch()` × 1~N |
| ③ | `get_sensor_statistics` | 传感器客观统计数据 | `get_history()` × 1 |
| ④ | `get_events_log` | 家庭事件日志（去噪） | `get_logbook()` × 1 |

---

## 三、工具详细设计

### 工具① `get_household_snapshot`

**文件**: `tools/household_snapshot.py`

```
名称: get_household_snapshot

用途: 获取当前全屋各房间的环境数据 + 电器运行状态

输入参数:
  rooms: list[str] | None
    可选，房间名列表。不传或传空则返回所有房间。

API 调用: get_states() × 1 次

依赖: entity_catalog — 房间→实体的映射（构造时注入）

处理流程:
  1. get_states() 一次拉回全量 states
  2. 按 entity_catalog 的 rooms 列表提取每个房间的实体
  3. domain → type 映射:
     sensor/binary_sensor → sensors
     light → lights
     cover → covers
     climate/vacuum/media_player/fan/humidifier → appliances
  4. 按 type 白名单提取关键属性
  5. 按房间归入响应结构

domain → type 白名单:
  ✅ sensor         → sensors         传感器读数
  ✅ binary_sensor  → binary_sensors  门磁/人体/窗磁
  ✅ light          → lights          灯光
  ✅ cover          → covers          窗帘/卷帘
  ✅ climate        → appliances      空调
  ✅ vacuum         → appliances      扫地机
  ✅ media_player   → appliances      音箱/电视
  ✅ fan            → appliances      风扇
  ✅ humidifier     → appliances      加湿器
  ❌ number/select/switch/button/event/text/notify/sun/zone → 过滤

各 type 提取的 attrs 白名单:
  sensors:
    - state, unit_of_measurement, device_class
  binary_sensors:
    - state, device_class
  lights:
    - state, brightness, color_temp_kelvin
  covers:
    - state, current_position
  appliances:
    climate:       → type_label="空调", state, current_temperature,
                      temperature, fan_mode, preset_mode, hvac_modes
    vacuum:        → type_label="扫地机", state, battery_level, fan_speed
    media_player:  → type_label="音箱", state, volume_level, source
    fan:           → type_label="风扇", state, percentage
    humidifier:    → type_label="加湿器", state, humidity, target_humidity

输出结构:
  {
    "rooms": {
      "客厅": {
        "sensors": [
          {"id": "sensor.temp", "label": "温度", "value": 25.0, "unit": "°C"}
        ],
        "binary_sensors": [
          {"id": "binary_sensor.door", "label": "大门", "state": "off"}
        ],
        "lights": [
          {"id": "light.ceiling", "label": "吸顶灯", "state": "on", "brightness": 80}
        ],
        "covers": [
          {"id": "cover.curtain", "label": "窗帘", "state": "open", "position": 100}
        ],
        "appliances": [
          {"id": "climate.ke_ting", "label": "空调", "type": "空调",
           "state": "cool", "current_temp": 25, "target_temp": 23}
        ]
      },
      "书房": { ... }
    }
  }
```

---

### 工具② `get_device_history`

**文件**: `tools/device_history.py`

```
名称: get_device_history

用途: 查一个或多个设备在历史时间段内的控制变更记录
      （只包含"人为操作"导致的属性变更，不含环境读数被动变化）

输入参数:
  entity_ids: list[str]
    必填。要查询的设备 ID，支持批量。
    示例: ["climate.ke_ting_kong_diao", "light.ceiling"]
  hours_back: float
    可选，默认 24。回溯小时数，范围 0.5~168。

API 调用:
  get_history_batch(entity_ids, start, end) — 内部逐个调 history
    每个实体 1 次 GET /api/history/period/{utc}?filter_entity_id=xxx

控制字段白名单（只检测这些字段的变化）:
  climate:
    state, temperature, target_temp_high, target_temp_low,
    fan_mode, preset_mode, swing_mode, hvac_mode
  light:
    state, brightness, color_temp_kelvin, effect
  cover:
    state, current_position
  media_player:
    state, volume_level, source, media_title
  vacuum:
    state, fan_speed, battery_level
  fan:
    state, percentage, preset_mode, oscillating
  switch:
    state
  input_boolean:
    state
  humidifier:
    state, humidity, target_humidity

  过滤的字段（不追踪）:
    current_temperature, hvac_action, friendly_name,
    supported_features, min_temp, max_temp 等配置/描述性字段

处理流程:
  1. 逐个 entity_id 调 get_history(start, end)
  2. 遍历每个历史点，与上一个点的 attributes 逐字段对比
  3. 只保留「控制字段白名单」中值发生变化的条目
  4. 按 entity_id 分组，按时间正序排列
  5. 没有变更的实体不出现在返回中

输出结构:
  {
    "climate.ke_ting_kong_diao": {
      "label": "客厅空调",
      "control_events": [
        {"time": "2026-07-19 18:00", "field": "state",  "from": "off",  "to": "cool"},
        {"time": "2026-07-19 18:05", "field": "temperature", "from": 25, "to": 23},
        {"time": "2026-07-19 23:00", "field": "state",  "from": "cool", "to": "off"}
      ],
      "total_changes": 3
    },
    "light.ceiling": {
      "label": "吸顶灯",
      "control_events": [
        {"time": "2026-07-19 19:00", "field": "state", "from": "off", "to": "on"},
        {"time": "2026-07-19 22:30", "field": "state", "from": "on", "to": "off"}
      ],
      "total_changes": 2
    }
  }

time 格式: 按 last_changed 转换成本地时间 "YYYY-MM-DD HH:mm"
field: 变更的字段名
from:  前一个历史点中该字段的值
to:    当前历史点中该字段的值
```

---

### 工具③ `get_sensor_statistics`

**文件**: `tools/sensor_statistics.py`

```
名称: get_sensor_statistics

用途: 计算单个数值传感器在时间段内的客观统计数据

输入参数:
  entity_id: str
    必填，如 "sensor.temperature" 或 "sensor.humidity"
  hours_back: float
    可选，默认 24，范围 0.5~168

API 调用: get_history() × 1 次

处理流程:
  1. 调 get_history(entity_id, start, end)
  2. 提取 state 转为 float
  3. 非数值或数据不足 → 返回 error
  4. 全面统计: min/max/avg/median/std_dev/p25/p75 等
  5. 取首个和最后一个数据点（含时间）
  6. 按时间序列取 10%/25%/50%/75%/90% 位置的实际采样点
  7. 返回纯统计数据，无趋势判定，无自然语言备注

统计维度:
  ┌──────────────────┬──────────────────────────────────────┐
  │ state            │ 当前值（最后一个采样点）              │
  │ first            │ 第一个采样点的值                     │
  │ min              │ 最小值                               │
  │ max              │ 最大值                               │
  │ avg              │ 算术平均值                           │
  │ median           │ 中位数                               │
  │ std_dev          │ 标准差（总体标准差）                  │
  │ p25              │ 第 25 百分位（按值排序）             │
  │ p75              │ 第 75 百分位（按值排序）             │
  │ range            │ max - min                           │
  │ delta            │ state - first                       │
  │ samples          │ 有效采样点数量                       │
  │ missing          │ 非数值/跳过的历史点数量              │
  │ period_hours     │ 实际覆盖的时间范围                   │
  │ first_point      │ 时间序列第一个数据点 {time, state}   │
  │ last_point       │ 时间序列最后一个数据点 {time, state} │
  │ time_samples     │ 按时间位置取的 5 个采样点            │
  └──────────────────┴──────────────────────────────────────┘

time_samples 选取逻辑:
  将所有数据点按时间排序后，取位置在 10%/25%/50%/75%/90% 处的
  实际数据点（time + state）。如果采样点较少（samples < 10），
  取最近的整数索引位置。

输出结构:
  {
    "entity_id": "sensor.temperature",
    "label": "客厅温度",
    "unit": "°C",
    "statistics": {
      "state": 25.0,
      "first": 22.5,
      "min": 22.0,
      "max": 28.0,
      "avg": 25.3,
      "median": 25.5,
      "std_dev": 1.8,
      "p25": 23.8,
      "p75": 26.9,
      "range": 6.0,
      "delta": 2.5,
      "samples": 12,
      "missing": 0,
      "period_hours": 24.0,
      "first_point": {
        "time": "2026-07-19 08:00",
        "state": 22.5
      },
      "last_point": {
        "time": "2026-07-19 09:00",
        "state": 25.0
      },
      "time_samples": [
        {"pct": 10, "time": "2026-07-19 08:12", "state": 22.8},
        {"pct": 25, "time": "2026-07-19 08:30", "state": 23.5},
        {"pct": 50, "time": "2026-07-19 08:45", "state": 25.5},
        {"pct": 75, "time": "2026-07-19 08:52", "state": 26.9},
        {"pct": 90, "time": "2026-07-19 08:56", "state": 27.5}
      ]
    }
  }

异常返回:
  {"entity_id": "sensor.xxx", "statistics": null,
   "error": "非数值类型，无法统计"}
  {"entity_id": "sensor.xxx", "statistics": null,
   "error": "数据不足（至少需要2个采样点）"}
```

---

### 工具④ `get_events_log`

**文件**: `tools/events_log.py`

```
名称: get_events_log

用途: 查询指定时间范围内的家庭事件，自动去噪

输入参数:
  hours_back: float
    可选，默认 6。回溯小时数，范围 0.5~168。
  categories: list[str] | None
    可选。过滤类别：climate / security / door / network
    不传则返回全部（去噪后）。

API 调用: get_logbook() × 1 次

噪音过滤规则:
  按 domain 过滤（排除）:
    sun      — 日出日落事件，与家庭活动无关
    number   — 数值配置参数变更
    select   — 下拉选择变更
    button   — 按钮触发事件
    event    — 传感器触发事件原始流
    text     — 文本输入变更

  按 keywords 过滤（大小写不敏感）:
    heartbeat, unavailable, attribute

状态翻译表（用于 text 字段）:
  cool     → 制冷      heat     → 制热
  dry      → 除湿      fan_only → 送风
  off      → 关闭      on       → 开启
  idle     → 待机      paused   → 暂停
  playing  → 播放中    docking  → 回充
  cleaning → 清扫中    returning → 返回中
  open     → 打开      closed   → 关闭
  unlocked → 解锁      locked   → 上锁

过滤类别关键词:
  climate:  ["climate", "空调", "温度", "thermostat", "hvac"]
  security: ["motion", "door", "window", "contact", "alarm", "门", "锁"]
  door:     ["door", "lock", "门", "锁", "cover", "窗帘"]
  network:  ["network", "wifi", "连接", "断开", "ap"]

处理流程:
  1. 调 get_logbook(start, end)
  2. 按噪音规则过滤
  3. 若 categories 参数指定，按关键词匹配筛选
  4. 取 TOP 30 条，按时间倒序
  5. 翻译 state 为中文文本

输出结构:
  {
    "total": 89,
    "events": [
      {
        "time": "08:30",
        "entity_id": "binary_sensor.main_door",
        "label": "大门",
        "text": "关闭"
      },
      {
        "time": "09:15",
        "entity_id": "climate.ke_ting_kong_diao",
        "label": "客厅空调",
        "text": "制冷"
      }
    ],
    "filtered": 237,
    "note": "已过滤设备/配置/噪音类事件。"
  }
```

---

## 四、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `clients/ha_client.py` | 新增 `get_history_batch()`，删除 `get_states_batch()` |
| 删除 | `tools/room_status.py` | 被工具①替代 |
| 删除 | `tools/events.py` | 被工具④替代 |
| 删除 | `tools/trend.py` | 被工具③替代 |
| 新建 | `tools/household_snapshot.py` | 工具① |
| 新建 | `tools/device_history.py` | 工具② |
| 新建 | `tools/sensor_statistics.py` | 工具③ |
| 新建 | `tools/events_log.py` | 工具④ |
| 修改 | `__init__.py` | 更新导出 |
| 修改 | `tools/__init__.py` | 注册新工具 |
