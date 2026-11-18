"""한국 기업 연도별 대표이사 (DART 사업보고서 주요정보 API '임원 현황': /api/exctvSttus.json).

사업보고서(연도 y)에 실린 임원 현황 중 직위에 '대표'가 들어간 사람을 그 해의 대표이사로 본다.
사업보고서는 다음 해 3월에 제출되므로, 그 시점의 대표이사(= 보고서에 서명한 사람)가 실린다.
받은 응답은 data/raw/KR/<고유번호>/officers/ 에 그대로 보관한다. fetch() 는 사용자 승인 후에만 호출한다.
"""
import json
import re

from .config import RAW_DIR, dart_key
from .http import get

ENDPOINT = "exctvSttus"
ANNUAL = "11011"


def _dir(company_id: str):
    return RAW_DIR / "KR" / company_id.split(":", 1)[1] / "officers"


def missing(company_id: str, years: list[int]) -> list[int]:
    return [y for y in years if not (_dir(company_id) / f"{ENDPOINT}_{y}.json").exists()]


def fetch(company_id: str, years: list[int], progress=print) -> int:
    """승인 후에만 호출. 아직 없는 연도만 받는다."""
    d = _dir(company_id)
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for y in missing(company_id, years):
        r = get(f"https://opendart.fss.or.kr/api/{ENDPOINT}.json",
                params={"crtfc_key": dart_key(), "corp_code": company_id.split(":", 1)[1],
                        "bsns_year": str(y), "reprt_code": ANNUAL}).json()
        if r.get("status") not in ("000", "013"):
            progress(f"  실패 {ENDPOINT} {y}: {r.get('status')} {r.get('message')}")
            continue
        (d / f"{ENDPOINT}_{y}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        n += 1
        progress(f"  받음 {ENDPOINT} {y} ({r.get('status')})")
    return n


# '대표이사'가 직위(ofcps)가 아니라 담당업무(chrg_job)에 적힌 회사가 많다
#   (실제 사례: 현대차 ofcps '사장', chrg_job '대표이사, 업무총괄' / 삼성전자 chrg_job 'ㆍ대표이사 (DX 부문 경영전반)')
# 담당업무의 '계열사대표이사후보추천위원장' 같은 위원회 이름은 제외한다 (KB금융).
# 'CEO'만 적은 회사도 있다 (NC 2022년~: chrg_job 'CEO'). '경영총괄'처럼 대표 여부가 안 적힌 경우는 추측하지 않는다.
CEO_JOB = re.compile(r"(?<![가-힣])대표이사(?!후보)|각자대표|공동대표|대표집행임원|(?<![A-Za-z])CEO(?![A-Za-z])")


def is_ceo(row: dict) -> bool:
    ofcps = re.sub(r"\s", "", row.get("ofcps", ""))
    job = re.sub(r"\s", "", row.get("chrg_job", ""))
    return "대표" in ofcps or bool(CEO_JOB.search(job))


def ceos(company_id: str, years: list[int]) -> dict[int, list[str] | None]:
    """{연도: [대표이사 이름]}. 받지 않았거나 표가 비어 있으면 None."""
    out = {}
    for y in years:
        f = _dir(company_id) / f"{ENDPOINT}_{y}.json"
        if not f.exists():
            out[y] = None
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        names = [re.sub(r"\s", "", x.get("nm", "")) for x in r.get("list", []) if x.get("nm") and is_ceo(x)]
        out[y] = sorted(set(names)) or None
    return out
