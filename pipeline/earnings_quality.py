"""분석 도구: 이익의 질 · 이익조정 신호 — 결과만 보여준다 (판정하지 않음)

규칙 문서: criteria/04_이익의_질.md

사용자 결정 (2026-11-18)
- 기간 최근 5년. 판정 없이 결과만 표시. 표시는 데이터에 있는 사실만.
- 순이익은 기준 2와 같은 연결 순이익.
- A 발생액: (순이익 − 영업CF) ÷ 평균 총자산 ((기초 + 기말) ÷ 2)
- B 매출채권: 매출채권 증가율과 매출 증가율을 나란히 놓는다.
  매출채권만 쓰고, 매출채권및기타채권뿐인 해는 '범위 차이'. 계약자산(미청구공사)은 별도 줄로 함께 표시.
- C 재고: 재고 증가율과 매출 증가율을 나란히 놓는다.
- B·C 신호 (2026-11-20 변경): ② 매출은 줄었는데 그 항목은 늘었거나, ③ 매출보다 빨리 늘어난 해가 2년 연속.
  (처음 결정 '매출보다 빨리 늘면 표시'는 29개사 회사×연도의 절반 이상에서 켜져서 바꿈)
- D 작은 이익: 순이익 ÷ 평균 총자산이 0% 이상 1% 미만인 해.
- E 빅 배스: 새 대표이사가 처음 서명한 사업보고서(10-K)의 연도에 순손실이거나, 순이익이 전년의 절반 이하.
"""
import re

import pandas as pd

from . import dart_officers, service
from . import promises as P
from . import standard as S
from . import us_promises as U

YEARS = 5
SMALL_PROFIT = (0.0, 0.01)
BIG_DROP = 0.5
USED = ("net_income", "operating_cf", "total_assets", "revenue", "receivables", "contract_assets", "inventory")


def _growth(cur, prev):
    if cur is None or prev is None or prev <= 0:
        return None
    return cur / prev - 1


def _std_year(report_date: str) -> int:
    d = pd.Timestamp(report_date)
    return d.year if d.month >= 6 else d.year - 1


def _parse_ceo_us(text: str) -> str | None:
    """기준 1의 10-K 서명 읽기(us_promises.parse_ceo)에, 서명 아래 줄에 '(Principal Executive Officer)'만 있는
    양식을 더한다 (실제 사례: Boeing, Walmart). 기준 1 코드는 건드리지 않는다."""
    if who := U.parse_ceo(text):
        return who
    L = text.split("\n")
    for i, line in enumerate(L):
        if "Principal Executive Officer" in line and "/s/" not in line:
            for j in range(i - 1, max(i - 5, -1), -1):
                if (m := re.search(r"/s/\s*([^|]{3,60}?)\s*(\||$)", L[j])):
                    return U._display(m.group(1))
    return None


def ceo_by_year(company_id: str, years: list[int]) -> dict[int, list[str] | None]:
    """연도별 대표이사(CEO). 한국: DART 임원 현황, 미국: 그 해 10-K 서명자."""
    if company_id.startswith("KR:"):
        return dart_officers.ceos(company_id, years)
    out = {y: None for y in years}
    for k in U.ten_ks(company_id):
        rep = P._ro().execute("SELECT report_date FROM filings WHERE company_id = ? AND rcept_no = ?",
                              (company_id, k["rcept_no"])).fetchone()
        y = _std_year(rep[0] if rep and rep[0] else k["filed"])
        if y in out and (t := P._text(company_id, k["rcept_no"])):
            who = _parse_ceo_us(t)
            out[y] = [U._norm_person(who)] if who else None
            out.setdefault("_display", {})[y] = who
    return out


def missing_ceo_data(company_id: str, years: list[int]) -> list:
    """E에 필요한데 아직 받지 않은 데이터. 한국: 연도 목록, 미국: 10-K 목록."""
    if company_id.startswith("KR:"):
        return dart_officers.missing(company_id, years)
    want = set(years)
    out = []
    for k in U.missing_docs(company_id):
        rep = P._ro().execute("SELECT report_date FROM filings WHERE company_id = ? AND rcept_no = ?",
                              (company_id, k["rcept_no"])).fetchone()
        if _std_year(rep[0] if rep and rep[0] else k["filed"]) in want:
            out.append(k)
    return out


def analyze(company_id: str, years: int = YEARS) -> dict:
    df = S.standardize(company_id)
    company = service.get_company(company_id) or {}
    out = {"company_id": company_id, "rows": [], "flags": [], "ceo": {}}
    if df.empty:
        out["flags"].append("재무 데이터가 없음")
        return out
    fin = S.is_financial(company)
    val = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    match = df.pivot_table(index="year", columns="item", values="match", aggfunc="first")
    g = lambda y, k: val.at[y, k] if (k in val and y in val.index and pd.notna(val.at[y, k])) else None  # noqa: E731
    span = [y for y in sorted(val.index) if g(y, "net_income") is not None][-years:]
    if not span:
        out["flags"].append("순이익 데이터가 없음")
        return out

    ceo = ceo_by_year(company_id, [span[0] - 1] + span)
    display = ceo.pop("_display", {}) if isinstance(ceo.get("_display"), dict) else {}
    by_key = {U._norm_person(v): v for v in display.values() if v}   # 미국: 비교용 키 → 표시 이름
    out["ceo"] = {y: (display.get(y) or ", ".join(v) if v else None) for y, v in ceo.items()}
    if fin:
        out["flags"].append("금융업: 매출채권·재고 개념이 없고, 영업CF가 예금·대출 흐름이라 A의 의미가 일반 기업과 다름")

    for y in span:
        ni, ocf = g(y, "net_income"), g(y, "operating_cf")
        ta, ta0 = g(y, "total_assets"), g(y - 1, "total_assets")
        avg_ta = (ta + ta0) / 2 if ta is not None and ta0 is not None else None
        rev_g = _growth(g(y, "revenue"), g(y - 1, "revenue"))
        rec_g = _growth(g(y, "receivables"), g(y - 1, "receivables"))
        ca_g = _growth(g(y, "contract_assets"), g(y - 1, "contract_assets"))
        inv_g = _growth(g(y, "inventory"), g(y - 1, "inventory"))
        accr = (ni - ocf) / avg_ta if (ni is not None and ocf is not None and avg_ta) else None
        roa = ni / avg_ta if (ni is not None and avg_ta) else None
        row = {"year": y, "ni": ni, "ocf": ocf, "avg_ta": avg_ta, "accruals": accr, "roa": roa,
               "rev_g": rev_g, "rec_g": rec_g, "ca_g": ca_g, "inv_g": inv_g, "ceo": out["ceo"].get(y),
               "B": None, "B_ca": None, "C": None, "D": None, "E": None, "notes": []}
        if not fin:
            # 신호 B·B*·C (사용자 결정 2026-11-20, 처음 결정 '매출보다 빨리 늘면 표시'를 바꿈: 거의 모든 회사에서 켜져서)
            #   ② 매출은 줄었는데 그 항목은 늘었다  또는  ③ 매출보다 빨리 늘어난 해가 2년 연속 (전년도 포함)
            rev_g0 = _growth(g(y - 1, "revenue"), g(y - 2, "revenue"))
            for key, cur_g, item in (("B", rec_g, "receivables"), ("B_ca", ca_g, "contract_assets"), ("C", inv_g, "inventory")):
                prev_g = _growth(g(y - 1, item), g(y - 2, item))
                fast = (cur_g > rev_g) if (cur_g is not None and rev_g is not None) else None
                fast0 = (prev_g > rev_g0) if (prev_g is not None and rev_g0 is not None) else None
                row[key + "_fast"] = fast                          # 사실: 매출보다 빨리 늘었나
                if fast is None:
                    row[key] = None
                else:
                    cross = rev_g < 0 and cur_g > 0
                    row[key] = bool(cross or (fast and fast0))
                    if row[key]:
                        why = "매출은 줄었는데 늘어남" if cross else "2년 연속 매출보다 빨리 늘어남"
                        label = {"B": "B 매출채권", "B_ca": "B* 계약자산", "C": "C 재고"}[key]
                        row["notes"].append(f"{label} 신호: {why}")
        row["D"] = (SMALL_PROFIT[0] <= roa < SMALL_PROFIT[1]) if roa is not None else None

        # E: 새 대표이사의 첫 연도
        now, before = ceo.get(y), ceo.get(y - 1)
        if now is None or before is None:
            row["E"] = None
            row["notes"].append("E: 대표이사 데이터 없음 (이 해 또는 전년)")
        elif set(now) - set(before):
            ni0 = g(y - 1, "net_income")
            loss = ni is not None and ni < 0
            drop = ni is not None and ni0 is not None and ni0 > 0 and ni <= BIG_DROP * ni0
            row["E"] = loss or drop
            new = ", ".join(by_key.get(n, n) for n in sorted(set(now) - set(before)))
            row["notes"].append(f"E: 새 대표이사 첫 연도 ({new})"
                                + (" — 순손실" if loss else (" — 순이익이 전년의 절반 이하" if drop else " — 대규모 손실 없음")))
        else:
            row["E"] = False

        # 사실 표시
        if avg_ta is None:
            row["notes"].append("A·D: 전년 총자산이 없어 평균 총자산 계산 불가")
        if ocf is None:
            row["notes"].append("A: 영업CF 없음")
        if not fin:
            for k, label in (("revenue", "매출"), ("receivables", "매출채권"), ("inventory", "재고")):
                if g(y, k) is None or g(y - 1, k) is None:
                    row["notes"].append(f"{label}: 이 해 또는 전년 값 없음 → 증가율 계산 불가")
            if g(y - 1, "revenue") is not None and g(y - 1, "revenue") <= 0:
                row["notes"].append("매출: 전년 매출이 0 이하 → 증가율 계산 불가")
        nonexact = [f"{S.ITEM_BY_KEY[k].name}={S.MATCH_LABEL.get(match.at[yy, k], match.at[yy, k])}"
                    for yy in (y, y - 1) for k in match.columns
                    if k in USED and yy in match.index and pd.notna(match.at[yy, k]) and match.at[yy, k] != "exact"]
        if nonexact:
            row["notes"].append("정의 일치 아님: " + ", ".join(dict.fromkeys(nonexact)))
        out["rows"].append(row)

    miss = missing_ceo_data(company_id, [span[0] - 1] + span)
    if miss:
        out["flags"].append(f"E에 필요한 대표이사 데이터 미수집 {len(miss)}건 (data.py quality <기업> --fetch, 승인 필요)")
    return out
