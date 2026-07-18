"""get_room_status 工具实现。

按房间名获取该房间所有实体的完整状态和完整属性（含 climate 展开）。
内部读 entity_catalog → 批量 HA API。
"""
import logging
from typing import Any

from my_agent_lib.clients.ha_client import HAClient
from my_agent_lib.tools.base import Tool

logger = logging.getLogger(__name__)

CLIMATE_EXPAND_KEYS = [
    'hvac_action', 'current_temperature', 'temperature', 'target_temp_high',
    'target_temp_low', 'fan_mode', 'fan_modes', 'preset_mode', 'swing_mode',
    'hvac_modes',
]
LIGHT_KEYS = ['brightness', 'color_temp_kelvin', 'effect']
COVER_KEYS = ['current_position', 'is_closed']
SENSOR_KEYS = ['unit_of_measurement', 'device_class', 'state_class']


def _compact_attrs(attrs: dict) -> dict:
    result = {}
    for k, v in attrs.items():
        if v is None:
            continue
        if isinstance(v, list) and len(v) > 5:
            result[k] = v[:5]
        else:
            result[k] = v
    return result


_VALUABLE_TYPES = {'sensor', 'climate', 'cover', 'binary_sensor', 'light', 'media_player'}


class GetRoomStatusTool(Tool):
    name = 'get_room_status'
    description = (
        '获取指定房间有意义的实体状态和属性（传感器、空调、窗帘、门磁、灯、播放器）。'
        '过滤开关/按钮/配置等无关实体。房间名从实体目录中获取。'
    )

    def __init__(self, ha: HAClient, catalog_rooms: list[dict], max_calls: int = 3):
        self._ha = ha
        self._catalog_rooms = catalog_rooms
        self.max_calls = max_calls
        self._room_index: dict[str, list[dict]] = {}
        for room in catalog_rooms:
            name = room.get('name', '')
            entities = room.get('entities', [])
            if name and entities:
                self._room_index[name] = entities

        room_names = list(self._room_index.keys())
        self.parameters = {
            'type': 'object',
            'properties': {
                'room_name': {
                    'type': 'string',
                    'description': '房间名',
                    'enum': room_names,
                },
            },
            'required': ['room_name'],
            'additionalProperties': False,
        }

    def execute(self, room_name: str) -> dict:
        entities = self._room_index.get(room_name)
        if entities is None:
            available = list(self._room_index.keys())
            return {
                'error': f'未知房间 "{room_name}"。可用房间: {", ".join(available)}',
                'available_rooms': available,
            }

        filtered = [e for e in entities if e.get('type', '') in _VALUABLE_TYPES]
        if not filtered:
            return {'room': room_name, 'entities': [], 'note': '无传感器或环境设备'}

        entity_ids = [e['id'] for e in filtered]
        states = self._ha.get_states_batch(entity_ids)

        result_entities = []
        for s in states:
            eid = s.get('entity_id', '')
            attrs = s.get('attributes', {})
            cat_entry = next((e for e in filtered if e['id'] == eid), {})
            label = cat_entry.get('label', attrs.get('friendly_name', eid))
            etype = cat_entry.get('type', 'unknown')

            entity_data = {
                'entity_id': eid,
                'label': label,
                'type': etype,
                'state': s.get('state', 'unavailable'),
                'attributes': {},
            }

            if etype == 'climate':
                for key in CLIMATE_EXPAND_KEYS:
                    if key in attrs and attrs[key] is not None:
                        entity_data['attributes'][key] = attrs[key]
            elif etype == 'light':
                for key in LIGHT_KEYS:
                    if key in attrs and attrs[key] is not None:
                        entity_data['attributes'][key] = attrs[key]
            elif etype == 'cover':
                for key in COVER_KEYS:
                    if key in attrs and attrs[key] is not None:
                        entity_data['attributes'][key] = attrs[key]
            elif etype == 'sensor':
                for key in SENSOR_KEYS:
                    if key in attrs and attrs[key] is not None:
                        entity_data['attributes'][key] = attrs[key]
                if attrs.get('friendly_name'):
                    entity_data['attributes']['friendly_name'] = attrs['friendly_name']
            else:
                entity_data['attributes'] = _compact_attrs(attrs)

            result_entities.append(entity_data)

        return {'room': room_name, 'entities': result_entities}
