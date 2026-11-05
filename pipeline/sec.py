"""미국(SEC EDGAR) 수집기. API 키 불필요.

- 기업정보·공시목록: https://data.sec.gov/submissions/CIK##########.json
- 재무(XBRL 전체):  https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
"""
import json
from datetime import date

from .config import RAW_DIR, YEARS
from .http import get

PROFILE_KEYS = ["name", "tickers", "exchanges", "sic", "sicDescription", "category", "entityType",
                "fiscalYearEnd", "stateOfIncorporation", "website", "investorWebsite",
                "addresses", "phone", "formerNames", "ein"]


def _save_raw(cik: str, name: str, data: dict) -> None:
    d = RAW_DIR / "US" / cik
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _filing_rows(company_id: str, cik: str, block: dict, since: str) -> list[tuple]:
    rows = []
    for i, accn in enumerate(block["accessionNumber"]):
        filed = block["filingDate"][i]
        if filed < since:
            continue
        doc = block["primaryDocument"][i]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{doc}"
        rows.append((company_id, accn, block["form"][i], block["primaryDocDescription"][i] or block["form"][i],
                     filed, block["reportDate"][i], "", url))
    return rows


def fetch(conn, company: dict) -> dict:
    cik = company["source_key"]
    company_id = company["company_id"]
    since = f"{date.today().year - YEARS}-01-01"

    # 1) 기업정보 + 공시목록
    subs = get(f"https://data.sec.gov/submissions/CIK{cik}.json", sec=True).json()
    _save_raw(cik, "submissions", subs)
    filings = _filing_rows(company_id, cik, subs["filings"]["recent"], since)
    for f in subs["filings"].get("files", []):  # 오래된 공시는 별도 파일로 나뉘어 있음
        if f.get("filingTo", "") >= since:
            older = get(f"https://data.sec.gov/submissions/{f['name']}", sec=True).json()
            filings += _filing_rows(company_id, cik, older, since)

    # 2) XBRL 재무 팩트 (전 태그, 전 기간 → 최근 YEARS 년만 저장)
    facts_rows = []
    try:
        facts = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", sec=True).json()
        _save_raw(cik, "companyfacts", facts)
        for taxonomy, tags in facts.get("facts", {}).items():
            for tag, node in tags.items():
                for unit, items in node.get("units", {}).items():
                    for it in items:
                        if it.get("end", "") < since:
                            continue
                        facts_rows.append((company_id, taxonomy, tag, node.get("label") or tag, unit, it.get("val"),
                                           it.get("start"), it["end"], it.get("fy"), it.get("fp"), it.get("form"),
                                           it.get("frame"), it.get("accn"), it.get("filed")))
    except Exception as e:
        if "404" not in str(e):  # 404 = XBRL 재무 데이터가 없는 기업 (일부 해외기업 등)
            raise

    conn.executemany("INSERT INTO sec_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", facts_rows)
    conn.executemany("INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?,?,?)", filings)

    profile = {k: subs.get(k) for k in PROFILE_KEYS}
    tickers = subs.get("tickers") or company.get("tickers") or []
    return {"name": subs.get("name") or company["name"], "name_en": subs.get("name") or company["name"],
            "ticker": ", ".join(tickers), "profile": profile,
            "counts": {"재무 팩트": len(facts_rows), "공시": len(filings)}}
