"""수시공시 이벤트 (정성 자료 A) — 받아 둔 공시 목록에서 그때그때 보고 싶은 이벤트만 골라 보여준다

사용자 결정 (2026-11-19)
- 고정된 목록을 미리 정하지 않는다. 아래 분류는 고르기 쉽게 둔 '메뉴'이고, 분석할 때 보고 싶은 것만 지정한다.
- 기간, 자회사 공시 포함, 지분 변동 공시 범위도 그때 고른다.
- 새로 받는 데이터 없음: 한국은 DART 공시 목록의 제목, 미국은 받아 둔 SEC submissions.json 의 8-K 항목 번호.

메뉴의 출처 (프로필 답): 보유-① 경영진·자금조달·소송제재사고·대주주 지분, 7-④ 특수관계자, 4-② 채무보증,
4-① 수주, 7-⑤ ESG·지배구조, 2주차 2번 뉴스와 공시의 연결(해명)
"""
import json
import re
import sqlite3

import pandas as pd

from .config import DB_PATH, RAW_DIR

# 분류 → (한국 공시 제목 정규식, 미국 8-K 항목 번호, 미국 공시 종류)
MENU = {
    "경영진": (r"대표이사.*변경", {"5.02"}, set()),
    "자금조달": (r"유상증자결정|전환사채권발행결정|교환사채권발행결정|신주인수권부사채권발행결정|증권신고서\(지분증권\)",
              {"2.03", "3.02"}, set()),
    "소송제재사고": (r"소송등의제기|중대재해|횡령|배임|불성실공시법인|영업정지|회생절차|파산|감사의견|상장폐지|거래정지",
                 {"1.03", "4.02", "3.01"}, set()),
    "대주주": (r"최대주주변경|최대주주등소유주식변동신고서|주식등의대량보유상황보고서", set(), {"SC 13D", "SCHEDULE 13D",
                                                                       "SC 13D/A", "SCHEDULE 13D/A"}),
    "특수관계자": (r"동일인등출자계열회사와의상품|특수관계인에대한|특수관계인으로부터|특수관계인과의", set(), set()),
    "채무보증": (r"채무보증", set(), set()),
    "수주": (r"단일판매ㆍ공급계약|공급계약체결", {"1.01"}, set()),
    "ESG지배구조": (r"지속가능경영|기업지배구조보고서", set(), set()),
    "해명": (r"풍문또는보도|조회공시", set(), set()),
}
# 잦은 공시: 기본으로 빼고, 옵션을 주면 넣는다 (사용자가 그때 고름)
FREQUENT = {"대주주": r"최대주주등소유주식변동신고서(?!\(최대주주변경시\))|주식등의대량보유상황보고서"}
SUBSIDIARY = r"자회사의\s*주요경영사항|종속회사의\s*주요경영사항"

ITEMS_8K = {
    "1.01": "중요 계약 체결", "1.02": "중요 계약 종료", "1.03": "파산·회생", "2.01": "자산 인수·처분 완료",
    "2.02": "실적 발표", "2.03": "채무 발생", "2.04": "채무 조기상환 사유", "2.05": "구조조정 비용",
    "2.06": "자산 손상", "3.01": "상장 기준 미달·상장폐지", "3.02": "미등록 주식 발행", "3.03": "주주 권리 변경",
    "4.01": "감사인 변경", "4.02": "재무제표 신뢰 불가(재작성)", "5.01": "지배권 변경", "5.02": "임원·이사 변경",
    "5.03": "정관 변경", "5.07": "주주총회 결과", "7.01": "공정공시(FD)", "8.01": "기타 사건", "9.01": "재무제표·첨부",
}


def _kr(company_id: str, since: str) -> pd.DataFrame:
    c = sqlite3.connect(DB_PATH)
    return pd.read_sql("SELECT filed, rcept_no, title, url FROM filings WHERE company_id = ? AND filed >= ? ORDER BY filed DESC",
                       c, params=(company_id, since))


def _us(company_id: str, since: str) -> pd.DataFrame:
    f = RAW_DIR / "US" / company_id.split(":", 1)[1] / "submissions.json"
    if not f.exists():
        return pd.DataFrame(columns=["filed", "rcept_no", "form", "items", "url"])
    r = json.loads(f.read_text(encoding="utf-8")).get("filings", {}).get("recent", {})
    cik = int(company_id.split(":", 1)[1])
    rows = []
    for i, form in enumerate(r.get("form", [])):
        d = r["filingDate"][i]
        if d < since:
            continue
        accn = r["accessionNumber"][i]
        rows.append({"filed": d, "rcept_no": accn, "form": form, "items": r.get("items", [""] * (i + 1))[i] or "",
                     "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{r['primaryDocument'][i]}"})
    return pd.DataFrame(rows)


def menu_counts(company_id: str, since: str) -> dict[str, int]:
    return {k: len(find(company_id, [k], since)) for k in MENU}


def find(company_id: str, kinds: list[str], since: str, keyword: str | None = None,
         include_subsidiary: bool = True, include_frequent: bool = False) -> list[dict]:
    """kinds: 메뉴 분류 이름들. keyword: 공시 제목(한국)·8-K 항목 설명(미국)에 대한 자유 검색어 (정규식)."""
    out = []
    if company_id.startswith("KR:"):
        df = _kr(company_id, since)
        for r in df.itertuples():
            t = re.sub(r"\s", "", r.title or "")
            sub = bool(re.search(SUBSIDIARY, t))
            if sub and not include_subsidiary:
                continue
            hits = [k for k in kinds if k in MENU and re.search(MENU[k][0], t)
                    and (include_frequent or k not in FREQUENT or not re.search(FREQUENT[k], t))]
            if keyword and re.search(keyword, r.title or "", re.I):
                hits.append("검색어")
            if hits:
                out.append({"filed": r.filed, "kind": ", ".join(hits), "title": r.title, "rcept_no": r.rcept_no,
                            "url": r.url, "subsidiary": sub})
    else:
        df = _us(company_id, since)
        for r in df.itertuples():
            items = [x.strip() for x in str(r.items).split(",") if x.strip()]
            desc = ", ".join(f"{x} {ITEMS_8K.get(x, '')}".strip() for x in items)
            hits = [k for k in kinds if k in MENU and ((r.form.startswith("8-K") and set(items) & MENU[k][1])
                                                     or r.form in MENU[k][2])]
            if keyword and re.search(keyword, f"{r.form} {desc}", re.I):
                hits.append("검색어")
            if hits:
                out.append({"filed": r.filed, "kind": ", ".join(hits), "title": f"{r.form}" + (f" ({desc})" if desc else ""),
                            "rcept_no": r.rcept_no, "url": r.url, "subsidiary": False})
    return out
