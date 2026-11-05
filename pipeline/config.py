import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "invest.db"

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "invest-pipeline student-project contact@example.com")
DART_API_KEY = os.getenv("DART_API_KEY", "")
