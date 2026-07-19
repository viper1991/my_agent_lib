"""UniFi Controller REST API 客户端。

提供 health / device / sta / rogueap / event 接口。
自动处理登录认证（Cookie + CSRF Token）。

会话策略：
  - 全程只登录一次（lazy init，首次 API 调用时触发）
  - 登录失败后等待 5s 重试，最多 3 次
  - 全部失败后标记不可用，后续 API 调用返回空数据
  - 会话在 UniFiClient 实例销毁时自动释放
  - 下次刷新流程重新创建实例并登录
"""
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_LOGIN_RETRY_DELAY = 5
_LOGIN_MAX_ATTEMPTS = 3


class UniFiClient:
    """UniFi Controller REST API 客户端。"""

    def __init__(self, url: str, username: str, password: str, site: str = 'default',
                 timeout: float = 60.0, verify_ssl: bool = False):
        self._base = url.rstrip('/')
        self._username = username
        self._password = password
        self._site = site
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._session = requests.Session()
        self._session.verify = verify_ssl
        self._csrf_token: str | None = None
        self._logged_in = False
        self._login_failed = False
        self._site_path = f'/api/s/{self._site}'

    @classmethod
    def from_config(cls, cfg) -> 'UniFiClient':
        """从配置命名空间创建客户端。"""
        return cls(url=cfg.url, username=cfg.username, password=cfg.password,
                   site=getattr(cfg, 'site', 'default'),
                   verify_ssl=getattr(cfg, 'verify_ssl', False))

    # ── 会话管理 ──

    def _ensure_logged_in(self):
        if self._login_failed:
            return
        if not self._logged_in:
            self._login_with_retry()

    def _login_with_retry(self):
        for attempt in range(1, _LOGIN_MAX_ATTEMPTS + 1):
            try:
                self._do_login()
                self._logged_in = True
                logger.info('UniFi login success (attempt %d)', attempt)
                return
            except requests.RequestException as e:
                logger.warning('UniFi login attempt %d/%d failed: %s',
                              attempt, _LOGIN_MAX_ATTEMPTS, e)
                if attempt < _LOGIN_MAX_ATTEMPTS:
                    logger.info('Retrying UniFi login in %ds...', _LOGIN_RETRY_DELAY)
                    time.sleep(_LOGIN_RETRY_DELAY)

        self._login_failed = True
        logger.error(
            'UniFi login failed after %d attempts. UniFi data will be unavailable '
            'for this refresh cycle.',
            _LOGIN_MAX_ATTEMPTS,
        )

    def _do_login(self):
        resp = self._session.post(
            f'{self._base}/api/login',
            json={
                'username': self._username,
                'password': self._password,
                'remember': True,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        csrf = resp.headers.get('x-csrf-token')
        if csrf:
            self._csrf_token = csrf

    @property
    def is_available(self) -> bool:
        return self._logged_in and not self._login_failed

    @property
    def site(self) -> str:
        return self._site

    def _get(self, path: str) -> Any:
        self._ensure_logged_in()
        if not self._logged_in:
            return []

        headers = {}
        if self._csrf_token:
            headers['X-Csrf-Token'] = self._csrf_token

        try:
            resp = self._session.get(
                f'{self._base}{path}',
                headers=headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning('UniFi GET %s failed: %s', path, e)
            return []

        csrf = resp.headers.get('x-csrf-token')
        if csrf:
            self._csrf_token = csrf

        data = resp.json()
        return data.get('data', data)

    def post(self, path: str, json: dict | None = None, timeout: float | None = None) -> Any:
        self._ensure_logged_in()
        if not self._logged_in:
            return []

        headers = {}
        if self._csrf_token:
            headers['X-Csrf-Token'] = self._csrf_token

        try:
            resp = self._session.post(
                f'{self._base}{path}',
                json=json,
                headers=headers,
                timeout=timeout or self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning('UniFi POST %s failed: %s', path, e)
            return []

        csrf = resp.headers.get('x-csrf-token')
        if csrf:
            self._csrf_token = csrf

        data = resp.json()
        return data.get('data', data)

    # ── API 方法 ──

    def get_health(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/health')

    def get_devices(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/device')

    def get_clients(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/sta')

    def get_rogue_aps(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/rogueap')

    def get_events(self, limit: int = 50) -> list[dict]:
        return self._get(f'{self._site_path}/stat/event?limit={limit}')

    def get_dpi_summary(self) -> dict:
        return self._get(f'{self._site_path}/stat/dpi')

    def get_dpi_by_app(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/sitedpi?type=by_app')

    def get_dpi_by_cat(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/sitedpi?type=by_cat')

    def get_all_users(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/alluser')

    def get_alarms(self) -> list[dict]:
        return self._get(f'{self._site_path}/stat/alarm')
