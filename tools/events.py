"""get_events 工具实现。

合并 HA logbook + UniFi events，去噪并按类别过滤。
"""
import logging
from datetime import datetime, timedelta
from typing import Any

from my_agent_lib.clients.ha_client import HAClient
from my_agent_lib.clients.unifi_client import UniFiClient
from my_agent_lib.tools.base import Tool

logger = logging.getLogger(__name__)

NOISE_KEYWORDS = [
    'heartbeat', 'button_unavailable', 'device_tracker',
    'unavailable', 'attribute', 'EVT_WU_Roam',
    '心跳',
]

CATEGORY_KEYWORDS = {
    'climate': ['climate', '空调', '温度', '湿度', 'thermostat'],
    'security': ['motion', 'door', 'window', 'contact', 'alarm', '门磁', '人体'],
    'network': ['network', 'wifi', 'ap', 'client', '连接', '断开'],
    'door': ['door', 'lock', '门', '锁', 'cover', '窗帘'],
}


def _fmt_event_text(e: dict) -> str:
    name = (e.get('name', '') or '').strip()
    msg = (e.get('message', '') or '').strip()
    state = (e.get('state', '') or '').strip()
    eid = (e.get('entity_id', '') or '')
    domain = eid.split('.')[0] if '.' in eid else ''

    if msg:
        return f'{name}: {msg}'[:80]
    if state and state not in ('unknown', '', 'None') and domain != 'event':
        state_map = {
            'cool': '制冷', 'heat': '制热', 'dry': '除湿',
            'fan_only': '送风', 'off': '关闭', 'on': '开启',
            'open': '打开', 'closed': '关闭',
            'idle': '空闲', 'paused': '暂停', 'playing': '播放',
        }
        display_state = state_map.get(state.lower(), state)
        return f'{name} → {display_state}'[:80]
    return name[:80]


def _fmt_ha_time(t_raw) -> str:
    try:
        s = str(t_raw).strip().replace('Z', '+00:00')
        if '+' not in s and s.count('-') >= 2:
            s += '+00:00'
        return datetime.fromisoformat(s).astimezone().strftime('%H:%M')
    except Exception:
        return str(t_raw)[:16]


class GetEventsTool(Tool):
    name = 'get_events'
    description = (
        '获取近期事件，自动合并 HA logbook 和 UniFi 事件并去噪'
        '（过滤 heartbeat/button_unavailable/device_tracker 等噪音）。'
    )

    def __init__(self, ha: HAClient, unifi: UniFiClient):
        self._ha = ha
        self._unifi = unifi
        self.parameters = {
            'type': 'object',
            'properties': {
                'hours_back': {
                    'type': 'number',
                    'description': '回溯小时数，默认 2',
                    'minimum': 0.5,
                    'maximum': 24,
                },
                'categories': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'enum': ['climate', 'security', 'network', 'door'],
                    },
                    'description': '事件类别过滤。不传则返回全部。',
                },
            },
            'required': [],
            'additionalProperties': False,
        }

    def execute(self, hours_back: float = 2.0, categories: list[str] | None = None) -> list[dict]:
        now = datetime.now()
        start = now - timedelta(hours=hours_back)
        all_events = []

        try:
            ha_events = self._ha.get_logbook(start, now)
            for e in ha_events:
                all_events.append({
                    'time': e.get('when', ''),
                    'text': _fmt_event_text(e),
                    'level': 'info',
                    'source': 'ha',
                    'entity_id': e.get('entity_id', ''),
                })
        except Exception as e:
            logger.warning('get_events HA logbook failed: %s', e)

        try:
            u_events = self._unifi.get_events(limit=10)
            for e in u_events:
                msg = e.get('msg', '')
                level = 'warning' if any(w in str(msg).lower()
                                         for w in ['disconnect', 'down', 'fail']) else 'info'
                all_events.append({
                    'time': e.get('time', ''),
                    'text': msg,
                    'level': level,
                    'source': 'unifi',
                    'entity_id': '',
                })
        except Exception as e:
            logger.warning('get_events UniFi failed: %s', e)

        filtered = []
        for e in all_events:
            text = (e.get('text', '') or '').lower()
            if any(kw in text for kw in NOISE_KEYWORDS):
                continue
            filtered.append(e)

        if categories:
            cat_filtered = []
            for e in filtered:
                text = (e.get('text', '') or '').lower()
                for cat in categories:
                    keywords = CATEGORY_KEYWORDS.get(cat, [])
                    if any(kw.lower() in text for kw in keywords):
                        cat_filtered.append(e)
                        break
            filtered = cat_filtered

        def _sort_key(e):
            v = e.get('time', 0)
            if isinstance(v, (int, float)):
                return v
            try:
                s = str(v).strip()
                if s.endswith('Z'):
                    s = s[:-1]
                if '+' not in s and ' ' not in s and s.count('-') >= 2:
                    s += '+00:00'
                return datetime.fromisoformat(s).timestamp() * 1000
            except Exception:
                return 0
        filtered.sort(key=_sort_key, reverse=True)
        top = filtered[:8]

        result = []
        for e in top:
            t_raw = e.get('time', '')
            if isinstance(t_raw, (int, float)):
                from datetime import datetime as dt
                t = dt.fromtimestamp(t_raw / 1000).strftime('%H:%M')
            else:
                t = _fmt_ha_time(t_raw)
            result.append({
                'time': t,
                'text': (e.get('text', '') or '')[:80],
                'level': e.get('level', 'info'),
                'source': e.get('source', '?'),
            })

        return result
