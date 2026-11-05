"""한국(DART OpenAPI) 수집기. API 키 필요 (https://opendart.fss.or.kr 무료 발급).

- 기업개황:            /api/company.json
- 단일회사 전체 재무제표: /api/fnlttSinglAcntAll.json  (사업보고서, 연결 우선 · 없으면 별도)
- 공시검색:            /api/list.json
"""
import json
from datetime import date

from .config import RAW_DIR, YEARS, dart_key
from .http import get

BASE = "https://opendart.fss.or.kr/api"
ANNUAL_REPORT = "11011"   # 사업보고서
NO_DATA = "013"           # 조회된 데이터 없음


class DartError(RuntimeError):
    pass


def _call(endpoint: str, **params) -> dict:
    data = get(f"{BASE}/{endpoint}", params={"crtfc_key": dart_key(), **params}).json()
    status = data.get("status")
    if status not in ("000", NO_DATA):
        raise DartError(f"DART {endpoint} 오류 {status}: {data.get('message')}")
    return data


def _save_raw(corp_code: str, name: str, data: dict) -> None:
    d = RAW_DIR / "KR" / corp_code
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch(conn, company: dict) -> dict:
    if not dart_key():
        raise DartError("DART API 키가 설정되지 않았습니다.")
    corp = company["source_key"]
    company_id = company["company_id"]
    today = date.today()

    # 1) 기업개황
    profile = _call("company.json", corp_code=corp)
    _save_raw(corp, "company", profile)

    # 2) 재무제표: 최근 YEARS 개 사업연도 (사업보고서는 다음 해 3월 제출 → 작년까지)
    fin_rows = []
    for year in range(today.year - YEARS, today.year):
        for fs_div in ("CFS", "OFS"):  # 연결재무제표 우선, 없으면 별도재무제표
            data = _call("fnlttSinglAcntAll.json", corp_code=corp, bsns_year=str(year),
                         reprt_code=ANNUAL_REPORT, fs_div=fs_div)
            if data.get("status") == "000":
                _save_raw(corp, f"fin_{year}_{fs_div}", data)
                for it in data["list"]:
                    fin_rows.append((company_id, year, ANNUAL_REPORT, fs_div, it.get("sj_div"), it.get("sj_nm"),
                                     it.get("account_id"), it.get("account_nm"), it.get("account_detail"),
                                     it.get("thstrm_nm"), _num(it.get("thstrm_amount")),
                                     it.get("frmtrm_nm"), _num(it.get("frmtrm_amount")),
                                     it.get("bfefrmtrm_nm"), _num(it.get("bfefrmtrm_amount")),
                                     int(it.get("ord") or 0), it.get("currency"), it.get("rcept_no")))
                break

    # 3) 공시목록: 최근 YEARS 년 전체
    filings, page = [], 1
    bgn = f"{today.year - YEARS}{today:%m%d}"
    while True:
        data = _call("list.json", corp_code=corp, bgn_de=bgn, end_de=f"{today:%Y%m%d}",
                     page_no=str(page), page_count="100")
        for it in data.get("list", []):
            rcp = it["rcept_no"]
            d = it["rcept_dt"]
            filings.append((company_id, rcp, "", it["report_nm"].strip(),
                            f"{d[:4]}-{d[4:6]}-{d[6:]}", "", it.get("flr_nm", ""),
                            f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp}"))
        if page >= int(data.get("total_page") or 1):
            break
        page += 1

    conn.executemany(f"INSERT INTO dart_fin VALUES ({','.join('?' * 18)})", fin_rows)
    conn.executemany("INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?,?,?)", filings)

    return {"name": profile.get("corp_name") or company["name"],
            "name_en": profile.get("corp_name_eng") or company.get("name_en", ""),
            "ticker": profile.get("stock_code") or ", ".join(company.get("tickers", [])),
            "profile": profile,
            "counts": {"재무 계정 행": len(fin_rows), "공시": len(filings),
                       "재무 수집 연도": len({r[1] for r in fin_rows})}}
