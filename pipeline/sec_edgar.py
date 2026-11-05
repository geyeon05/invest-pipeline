"""SEC EDGAR 수집기 (미국 상장사).

사용하는 공식 무료 API (API 키 불필요):
- 티커 → CIK 매핑:  https://www.sec.gov/files/company_tickers.json
- 재무 데이터(XBRL): https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
- 공시 목록:         https://data.sec.gov/submissions/CIK##########.json
"""
import time
from datetime import date

import requests

from .config import SEC_USER_AGENT
from .db import connect

HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F"}
KEY_FILING_FORMS = {"10-K", "10-K/A", "10-Q", "8-K", "20-F", "6-K", "DEF 14A"}

# 표준 지표명 → 후보 us-gaap 태그 (기업·연도마다 쓰는 태그가 달라서 여러 개를 순서대로 시도)
METRIC_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "shares_outstanding": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}


def _get(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    time.sleep(0.2)  # SEC 권장: 초당 10회 이하
    return resp.json()


def lookup_cik(ticker: str) -> tuple[str, str]:
    data = _get("https://www.sec.gov/files/company_tickers.json")
    for row in data.values():
        if row["ticker"].upper() == ticker.upper():
            return f"{int(row['cik_str']):010d}", row["title"]
    raise ValueError(f"SEC에서 티커를 찾을 수 없습니다: {ticker}")


def _duration_days(item: dict) -> int | None:
    if "start" not in item:
        return None
    return (date.fromisoformat(item["end"]) - date.fromisoformat(item["start"])).days


def _annual_values(facts: dict, tag: str) -> dict[str, dict]:
    """한 태그에서 연간 값만 골라 {회계기간종료일: 항목} 으로 반환. 정정공시가 있으면 최신 제출본 사용."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return {}
    out: dict[str, dict] = {}
    for unit, items in node["units"].items():
        for it in items:
            if it.get("form") not in ANNUAL_FORMS or it.get("fp") != "FY":
                continue
            dur = _duration_days(it)
            if dur is not None and not (330 <= dur <= 400):
                continue  # 분기·누적 등 연간이 아닌 기간 제외
            prev = out.get(it["end"])
            if prev is None or it["filed"] > prev["filed"]:
                out[it["end"]] = {**it, "unit": unit, "tag": tag}
    return out


def collect(ticker: str, years: int = 10) -> str:
    ticker = ticker.upper()
    cik, name = lookup_cik(ticker)
    company_id = f"US:{ticker}"
    min_year = date.today().year - years

    facts = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    subs = _get(f"https://data.sec.gov/submissions/CIK{cik}.json")

    conn = connect()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO companies (company_id, market, ticker, name, source_key) VALUES (?,?,?,?,?)",
            (company_id, "US", ticker, name, cik),
        )

        n_fin = 0
        for metric, tags in METRIC_TAGS.items():
            by_year: dict[int, dict] = {}
            for tag in tags:  # 앞쪽 태그 우선, 비어 있는 연도만 뒤쪽 태그로 보충
                for end, it in _annual_values(facts, tag).items():
                    fy = int(end[:4])
                    if fy >= min_year and fy not in by_year:
                        by_year[fy] = it
            for fy, it in by_year.items():
                conn.execute(
                    """INSERT OR REPLACE INTO financials
                       (company_id, fiscal_year, period_end, metric, value, unit, source_tag, form, accession, filed)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (company_id, fy, it["end"], metric, it["val"], it["unit"],
                     f"us-gaap:{it['tag']}", it["form"], it["accn"], it["filed"]),
                )
                n_fin += 1

        recent = subs["filings"]["recent"]
        cik_int = int(cik)
        n_fil = 0
        for i, form in enumerate(recent["form"]):
            filed = recent["filingDate"][i]
            if form not in KEY_FILING_FORMS or int(filed[:4]) < min_year:
                continue
            accn = recent["accessionNumber"][i]
            url = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                   f"{accn.replace('-', '')}/{recent['primaryDocument'][i]}")
            conn.execute(
                """INSERT OR REPLACE INTO filings
                   (company_id, accession, form, filed, report_date, description, url)
                   VALUES (?,?,?,?,?,?,?)""",
                (company_id, accn, form, filed, recent["reportDate"][i],
                 recent["primaryDocDescription"][i], url),
            )
            n_fil += 1

    print(f"[SEC] {name} ({ticker}, CIK {cik}): 재무 {n_fin}건, 공시 {n_fil}건 저장")
    return company_id
