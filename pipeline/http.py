import time

import requests

from .config import sec_user_agent

_session = requests.Session()


def get(url: str, params: dict | None = None, sec: bool = False, retries: int = 3) -> requests.Response:
    headers = {"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"} if sec else {}
    for attempt in range(retries):
        resp = _session.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code in (429, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        if sec:
            time.sleep(0.15)  # SEC 요청 한도: 초당 10회
        return resp
    resp.raise_for_status()
    return resp
