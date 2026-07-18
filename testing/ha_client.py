"""Dry-run HA Client — returns mock data for testing.

所有方法返回预设的样板数据，不发起真实 HTTP 请求。
数据格式与 ha_client.HAClient 完全一致。
"""
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Mock entity data keyed by entity_id
_MOCK_STATES: dict[str, dict] = {
    'sensor.ke_ting_wen_du': {
        'entity_id': 'sensor.ke_ting_wen_du',
        'state': '26.5',
        'attributes': {
            'unit_of_measurement': '°C',
            'friendly_name': '客厅温度',
            'device_class': 'temperature',
        },
    },
    'sensor.ke_ting_shi_du': {
        'entity_id': 'sensor.ke_ting_shi_du',
        'state': '60',
        'attributes': {
            'unit_of_measurement': '%',
            'friendly_name': '客厅湿度',
            'device_class': 'humidity',
        },
    },
    'climate.ke_ting_kong_diao': {
        'entity_id': 'climate.ke_ting_kong_diao',
        'state': 'cool',
        'attributes': {
            'friendly_name': '客厅空调',
            'hvac_action': 'cooling',
            'current_temperature': 26.5,
            'temperature': 24.0,
            'fan_mode': 'auto',
            'hvac_modes': ['off', 'cool', 'heat', 'auto'],
        },
    },
    'sensor.zhu_wo_wen_du': {
        'entity_id': 'sensor.zhu_wo_wen_du',
        'state': '24.1',
        'attributes': {
            'unit_of_measurement': '°C',
            'friendly_name': '主卧温度',
        },
    },
    'sensor.shu_fang_wen_du': {
        'entity_id': 'sensor.shu_fang_wen_du',
        'state': '27.3',
        'attributes': {
            'unit_of_measurement': '°C',
            'friendly_name': '书房温度',
        },
    },
    'cover.ke_ting_chuang_lian': {
        'entity_id': 'cover.ke_ting_chuang_lian',
        'state': 'open',
        'attributes': {
            'friendly_name': '客厅窗帘',
            'current_position': 100,
            'is_closed': False,
        },
    },
    'light.can_ting_deng': {
        'entity_id': 'light.can_ting_deng',
        'state': 'off',
        'attributes': {
            'friendly_name': '餐厅灯',
        },
    },
}


class DryRunHAClient:
    """模拟 HA Client，返回预设数据。"""

    def __init__(self, url: str = '', token: str = '', timeout: float = 10.0):
        self._url = url
        self._token = token
        self._timeout = timeout
        logger.info('[DryRun] HAClient initialized (mock)')

    def get_state(self, entity_id: str) -> dict:
        if entity_id in _MOCK_STATES:
            return _MOCK_STATES[entity_id]
        return {
            'entity_id': entity_id,
            'state': 'unknown',
            'attributes': {'friendly_name': entity_id},
        }

    def get_states(self) -> list[dict]:
        return list(_MOCK_STATES.values())

    def get_states_batch(self, entity_ids: list[str]) -> list[dict]:
        return [self.get_state(eid) for eid in entity_ids]

    def get_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime | None = None,
    ) -> list[dict]:
        # 返回模拟历史数据
        return [
            {
                'entity_id': entity_id,
                'state': '25.0',
                'last_changed': (datetime.now().isoformat()),
                'attributes': {'unit_of_measurement': '°C'},
            },
            {
                'entity_id': entity_id,
                'state': '26.0',
                'last_changed': (datetime.now().isoformat()),
                'attributes': {'unit_of_measurement': '°C'},
            },
            {
                'entity_id': entity_id,
                'state': '26.5',
                'last_changed': (datetime.now().isoformat()),
                'attributes': {'unit_of_measurement': '°C'},
            },
        ]

    def get_logbook(
        self,
        start_time: datetime,
        end_time: datetime | None = None,
    ) -> list[dict]:
        return [
            {'name': '客厅门磁', 'message': '门窗打开', 'entity_id': 'binary_sensor.ke_ting_men', 'when': datetime.now().isoformat()},
            {'name': '人体传感器', 'message': '移动 detected', 'entity_id': 'binary_sensor.ke_ting_ren_ti', 'when': datetime.now().isoformat()},
        ]
