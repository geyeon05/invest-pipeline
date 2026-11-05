"""SQLite 저장 계층. 모든 수치는 출처(공시 번호, 제출일)와 함께 저장한다."""
import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    company_id   TEXT PRIMARY KEY,   -- 예: US:AAPL, KR:005930
    market       TEXT NOT NULL,      -- US / KR
    ticker       TEXT NOT NULL,
    name         TEXT,
    source_key   TEXT,               -- SEC CIK 또는 DART corp_code
    updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS financials (
    company_id   TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,   -- 회계기간 종료일 기준 연도
    period_end   TEXT NOT NULL,
    metric       TEXT NOT NULL,      -- 표준화된 지표명 (revenue, net_income ...)
    value        REAL NOT NULL,
    unit         TEXT,
    source_tag   TEXT,               -- 원본 태그 (us-gaap:Revenues 등)
    form         TEXT,               -- 10-K, 사업보고서 등
    accession    TEXT,               -- 공시 접수번호 (원문 추적용)
    filed        TEXT,               -- 공시 제출일
    PRIMARY KEY (company_id, fiscal_year, metric)
);

CREATE TABLE IF NOT EXISTS filings (
    company_id   TEXT NOT NULL,
    accession    TEXT NOT NULL,
    form         TEXT,
    filed        TEXT,
    report_date  TEXT,
    description  TEXT,
    url          TEXT,
    PRIMARY KEY (company_id, accession)
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn
