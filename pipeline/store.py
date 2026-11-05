"""저장 계층 (SQLite). 원천 데이터를 가공 없이 행 단위로 저장한다."""
import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    company_id   TEXT PRIMARY KEY,   -- KR:00126380 (DART 고유번호) / US:0000320193 (SEC CIK)
    market       TEXT NOT NULL,      -- KR / US
    name         TEXT,
    name_en      TEXT,
    ticker       TEXT,               -- 종목코드 / 티커
    profile_json TEXT,               -- 기업개황 원본 JSON
    fetched_at   TEXT                -- 마지막 수집 시각 (UTC)
);

-- 미국: SEC XBRL companyfacts 의 모든 팩트 (us-gaap, ifrs-full, dei 등 전 태그)
CREATE TABLE IF NOT EXISTS sec_facts (
    company_id TEXT, taxonomy TEXT, tag TEXT, label TEXT, unit TEXT, val REAL,
    start TEXT, "end" TEXT, fy INTEGER, fp TEXT, form TEXT, frame TEXT, accn TEXT, filed TEXT
);
CREATE INDEX IF NOT EXISTS ix_sec_facts ON sec_facts (company_id, tag);

-- 한국: DART 단일회사 전체 재무제표 (모든 계정과목, 응답 필드 그대로)
CREATE TABLE IF NOT EXISTS dart_fin (
    company_id TEXT, bsns_year INTEGER, reprt_code TEXT, fs_div TEXT, sj_div TEXT, sj_nm TEXT,
    account_id TEXT, account_nm TEXT, account_detail TEXT,
    thstrm_nm TEXT, thstrm_amount REAL, frmtrm_nm TEXT, frmtrm_amount REAL,
    bfefrmtrm_nm TEXT, bfefrmtrm_amount REAL, ord INTEGER, currency TEXT, rcept_no TEXT
);
CREATE INDEX IF NOT EXISTS ix_dart_fin ON dart_fin (company_id, bsns_year);

-- 공시 목록 (한국 DART · 미국 EDGAR 공통)
CREATE TABLE IF NOT EXISTS filings (
    company_id TEXT, rcept_no TEXT, form TEXT, title TEXT, filed TEXT,
    report_date TEXT, filer TEXT, url TEXT,
    PRIMARY KEY (company_id, rcept_no)
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def clear_company(conn: sqlite3.Connection, company_id: str) -> None:
    """재수집 전에 해당 기업의 기존 행을 지운다 (원천이 정정되면 최신 상태로 교체)."""
    for table in ("sec_facts", "dart_fin", "filings"):
        conn.execute(f"DELETE FROM {table} WHERE company_id = ?", (company_id,))
