"""한국 기업 주식 수 데이터 (DART 사업보고서 주요정보 API).

- 자기주식 취득 및 처분 현황: /api/tesstkAcqsDspsSttus.json  → 연도별 취득·처분·소각 수량
- 주식의 총수 현황:          /api/stockTotqySttus.json      → 발행주식 총수, 자기주식 수, 유통주식 수

받은 응답은 data/raw/KR/<고유번호>/shares/ 에 그대로 보관한다. fetch() 는 사용자 승인 후에만 호출한다.
"""
import json
from datetime import date

from .config import RAW_DIR, dart_key
from .http import get

ENDPOINTS = ("tesstkAcqsDspsSttus", "stockTotqySttus")
ANNUAL = "11011"


def _dir(company_id: str):
    return RAW_DIR / "KR" / company_id.split(":", 1)[1] / "shares"


def target_years(n: int = 5) -> list[int]:
    """사업보고서가 나왔을 최근 n개 사업연도 (사업보고서는 다음 해 3월 제출)."""
    t = date.today()
    last = t.year - 1 if t.month >= 4 else t.year - 2
    return list(range(last - n + 1, last + 1))


def missing(company_id: str, years: list[int]) -> list[tuple[str, int]]:
    d = _dir(company_id)
    return [(ep, y) for ep in ENDPOINTS for y in years if not (d / f"{ep}_{y}.json").exists()]


def fetch(company_id: str, years: list[int], progress=print) -> int:
    """승인 후에만 호출. 아직 없는 연도·항목만 받는다."""
    d = _dir(company_id)
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for ep, y in missing(company_id, years):
        r = get(f"https://opendart.fss.or.kr/api/{ep}.json",
                params={"crtfc_key": dart_key(), "corp_code": company_id.split(":", 1)[1],
                        "bsns_year": str(y), "reprt_code": ANNUAL}).json()
        if r.get("status") not in ("000", "013"):
            progress(f"  실패 {ep} {y}: {r.get('status')} {r.get('message')}")
            continue
        (d / f"{ep}_{y}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        n += 1
        progress(f"  받음 {ep} {y} ({r.get('status')})")
    return n


def _n(s) -> int | None:
    s = str(s or "").replace(",", "").strip()
    return int(s) if s.lstrip("-").isdigit() else None


def load(company_id: str, years: list[int]) -> dict[int, dict]:
    """{연도: {issued, treasury, outstanding, acquired, disposed, retired}} (보통주+우선주 합계). 없으면 None."""
    d = _dir(company_id)
    out = {}
    for y in years:
        row = {"issued": None, "treasury": None, "outstanding": None, "acquired": None, "disposed": None,
               "retired": None, "status": {}}
        f = d / f"stockTotqySttus_{y}.json"
        if f.exists():
            r = json.loads(f.read_text(encoding="utf-8"))
            row["status"]["stockTotqySttus"] = r.get("status")
            tot = next((x for x in r.get("list", []) if x.get("se") == "합계"), None)
            if tot:
                row["issued"], row["treasury"], row["outstanding"] = (
                    _n(tot.get("istc_totqy")), _n(tot.get("tesstk_co")), _n(tot.get("distb_stock_co")))
                row["rcept_no"] = tot.get("rcept_no")   # 사업보고서 접수번호 (앞 8자리 = 제출일, 분할 맞추기용)
        f = d / f"tesstkAcqsDspsSttus_{y}.json"
        if f.exists():
            r = json.loads(f.read_text(encoding="utf-8"))
            row["status"]["tesstkAcqsDspsSttus"] = r.get("status")
            totals = [x for x in r.get("list", []) if x.get("acqs_mth1") == "총계"]
            if totals:
                for key, fld in (("acquired", "change_qy_acqs"), ("disposed", "change_qy_dsps"), ("retired", "change_qy_incnr")):
                    vals = [_n(x.get(fld)) for x in totals]
                    row[key] = sum(v for v in vals if v) if any(v is not None for v in vals) else 0
            elif r.get("status") == "000":
                row["acquired"] = row["disposed"] = row["retired"] = 0   # 표가 비어 있음('-') = 그해 변동 없음
        out[y] = row
    return out
