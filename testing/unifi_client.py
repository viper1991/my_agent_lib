"""Dry-run UniFi Client — returns mock data for testing.

所有方法返回预设的样板数据，不发起真实 HTTP 请求。
数据格式与 unifi_client.UniFiClient 完全一致。
"""
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class DryRunUniFiClient:
    """模拟 UniFi Controller，返回预设数据。"""

    def __init__(self, url: str = '', username: str = '', password: str = '',
                 site: str = 'default', timeout: float = 60.0, verify_ssl: bool = False):
        self._base = url
        self._username = username
        self._password = password
        self._site = site
        self._site_path = f'/api/s/{site}'
        logger.info('[DryRun] UniFiClient initialized (mock)')

    @property
    def is_available(self) -> bool:
        return True

    @property
    def site(self) -> str:
        return self._site

    def post(self, path: str, json: dict | None = None, timeout: float | None = None) -> Any:
        return []

    def get_health(self) -> list[dict]:
        return [{'status': 'ok', 'subsystem': 'wan', 'uptime': 360000}]

    def get_devices(self) -> list[dict]:
        now = datetime.now().timestamp() * 1000
        return [
            {
                'type': 'uap',
                'name': '客厅 AP',
                'model': 'U6-LR',
                'mac': 'aa:bb:cc:dd:ee:01',
                'radio_table': [
                    {'name': 'ng', 'channel': 6, 'tx_power': 22, 'channel_width': 20},
                    {'name': 'na', 'channel': 36, 'tx_power': 20, 'channel_width': 80},
                ],
            },
            {
                'type': 'uap',
                'name': '书房 AP',
                'model': 'U6-Lite',
                'mac': 'aa:bb:cc:dd:ee:02',
                'radio_table': [
                    {'name': 'ng', 'channel': 11, 'tx_power': 20, 'channel_width': 20},
                    {'name': 'na', 'channel': 149, 'tx_power': 18, 'channel_width': 80},
                ],
            },
        ]

    def get_clients(self) -> list[dict]:
        return [
            {'hostname': '客厅电视', 'mac': '11:22:33:44:55:01', 'ip': '192.168.1.101',
             'signal': -65, 'channel': 6, 'radio': 'ng', 'ap_mac': 'aa:bb:cc:dd:ee:01',
             'is_wired': False, 'uptime': 7200, 'rx_bytes': 500000000, 'tx_bytes': 20000000},
            {'hostname': '主卧手机', 'mac': '11:22:33:44:55:02', 'ip': '192.168.1.102',
             'signal': -72, 'channel': 6, 'radio': 'ng', 'ap_mac': 'aa:bb:cc:dd:ee:01',
             'is_wired': False, 'uptime': 3600, 'rx_bytes': 50000000, 'tx_bytes': 5000000},
            {'hostname': '书房笔记本', 'mac': '11:22:33:44:55:03', 'ip': '192.168.1.103',
             'signal': -55, 'channel': 149, 'radio': 'na', 'ap_mac': 'aa:bb:cc:dd:ee:02',
             'is_wired': False, 'uptime': 1800, 'rx_bytes': 200000000, 'tx_bytes': 30000000},
        ]

    def get_rogue_aps(self) -> list[dict]:
        return [
            {'essid': '邻居WiFi_5G', 'channel': 6, 'signal': -72, 'radio': 'ng', 'bssid': '11:22:33:44:55:aa'},
            {'essid': 'CMCC-xxxx', 'channel': 6, 'signal': -78, 'radio': 'ng', 'bssid': '11:22:33:44:55:bb'},
            {'essid': 'TP-LINK_1234', 'channel': 1, 'signal': -85, 'radio': 'ng', 'bssid': '11:22:33:44:55:cc'},
            {'essid': '邻居WiFi_2G', 'channel': 11, 'signal': -75, 'radio': 'ng', 'bssid': '11:22:33:44:55:dd'},
            {'essid': 'ChinaNet-abc', 'channel': 6, 'signal': -82, 'radio': 'ng', 'bssid': '11:22:33:44:55:ee'},
            {'essid': '隐藏网络', 'channel': 36, 'signal': -88, 'radio': 'na', 'bssid': '11:22:33:44:55:ff'},
        ]

    def get_events(self, limit: int = 50) -> list[dict]:
        now_ms = int(datetime.now().timestamp() * 1000)
        return [
            {'time': now_ms - 60000, 'msg': 'WiFi 客户端 主卧手机 断开', 'key': 'EVT_CLIENT_DISCONNECTED'},
            {'time': now_ms - 120000, 'msg': 'AP 客厅 AP 重新上线', 'key': 'EVT_AP_Reconnected'},
        ]

    def get_dpi_summary(self) -> dict:
        return {}

    def get_dpi_by_app(self) -> list[dict]:
        return [{
            'by_app': [
                {'app': 2102, 'cat': 5, 'rx_bytes': 800_000_000, 'tx_bytes': 20_000_000, 'known_clients': 1},
                {'app': 2101, 'cat': 5, 'rx_bytes': 300_000_000, 'tx_bytes': 10_000_000, 'known_clients': 1},
                {'app': 1002, 'cat': 1, 'rx_bytes': 50_000_000, 'tx_bytes': 30_000_000, 'known_clients': 2},
                {'app': 3002, 'cat': 17, 'rx_bytes': 200_000_000, 'tx_bytes': 100_000_000, 'known_clients': 5},
                {'app': 1301, 'cat': 5, 'rx_bytes': 150_000_000, 'tx_bytes': 5_000_000, 'known_clients': 1},
            ],
        }]

    def get_dpi_by_cat(self) -> list[dict]:
        return []

    def get_all_users(self) -> list[dict]:
        now = datetime.now().timestamp()
        return [
            {'hostname': '客厅电视', 'mac': '11:22:33:44:55:01', 'last_seen': now - 60, 'first_seen': now - 86400 * 30, 'is_wired': False, 'oui': 'Samsung'},
            {'hostname': '主卧手机', 'mac': '11:22:33:44:55:02', 'last_seen': now - 120, 'first_seen': now - 86400 * 60, 'is_wired': False, 'oui': 'Apple'},
            {'hostname': '书房笔记本', 'mac': '11:22:33:44:55:03', 'last_seen': now - 10, 'first_seen': now - 86400 * 90, 'is_wired': False, 'oui': 'Lenovo'},
            {'hostname': '门锁', 'mac': '11:22:33:44:55:04', 'last_seen': now - 36000, 'first_seen': now - 86400 * 120, 'is_wired': False, 'oui': 'Aqara'},
        ]

    def get_alarms(self) -> list[dict]:
        now_ms = int(datetime.now().timestamp() * 1000)
        return [
            {'key': 'EVT_GW_WANTransition', 'time': now_ms - 3600000, 'msg': 'WAN 线路切换 主→备', 'subsystem': 'gateway'},
            {'key': 'EVT_AP_Lost_Contact', 'time': now_ms - 7200000, 'msg': 'AP 客厅 AP 离线', 'subsystem': 'access_point'},
            {'key': 'EVT_GW_WANTransition', 'time': now_ms - 18000000, 'msg': 'WAN 线路切换 备→主', 'subsystem': 'gateway'},
        ]
