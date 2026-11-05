"""설정. 비밀값은 로컬에서는 .env, Streamlit Cloud에서는 Secrets 에서 읽는다."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"          # 수집 캐시 (git에 올리지 않음, 언제든 원천에서 다시 받을 수 있음)
RAW_DIR = DATA_DIR / "raw"        # 원천 API 응답 원본 JSON 그대로 보관
REGISTRY_DIR = DATA_DIR / "registry"
DB_PATH = DATA_DIR / "store.db"
for d in (DATA_DIR, RAW_DIR, REGISTRY_DIR):
    d.mkdir(exist_ok=True)

YEARS = 10           # 수집 기간 (년)
REFRESH_DAYS = 7     # 이 기간이 지난 데이터는 다시 수집


def _secret(name: str, default: str = "") -> str:
    if os.getenv(name):
        return os.environ[name]
    try:
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def dart_key() -> str:
    return _secret("DART_API_KEY")


def sec_user_agent() -> str:
    return _secret("SEC_USER_AGENT", "invest-pipeline research-project contact@example.com")
