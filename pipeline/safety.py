"""분석 도구: 재무 안전성 — 결과만 보여주고, 숫자로 분명한 위험 두 가지만 따로 표시한다

규칙 문서: criteria/05_재무_안전성.md

사용자 결정 (2026-11-18)
- 기간 최근 5년. 판정·통과선 없음 (업종마다 적정 수준이 달라서. 4·5주차 '비교해야 의미가 있다').
- 지표: A 부채비율 = 부채총계 ÷ 자본총계(비지배지분 포함)
        B 유동비율 = 유동자산 ÷ 유동부채
        C 당좌비율 = (유동자산 − 재고자산) ÷ 유동부채
        D 이자보상비율 = 영업이익(보고 그대로) ÷ 이자비용(주석; 한국은 사업보고서 XBRL)
        E 부채 ÷ 영업CF = 본업 현금으로 빚을 몇 년에 갚나
- 분명한 위험 (업종과 무관한 사실): 자본잠식(자본총계 ≤ 0), 이자보상비율 < 1(영업이익으로 이자도 못 냄)
- 이자비용은 회사가 보고한 그대로 (한국은 리스 이자 포함, 미국은 대부분 미포함 — 조정하지 않고 표시만)
"""
import pandas as pd

from . import service
from . import standard as S

YEARS = 5
USED = ("total_liabilities", "equity_total", "current_assets", "current_liabilities", "inventory",
        "operating_income", "interest_expense", "operating_cf")


def analyze(company_id: str, years: int = YEARS) -> dict:
    df = S.standardize(company_id)
    company = service.get_company(company_id) or {}
    out = {"company_id": company_id, "rows": [], "flags": [], "risks": []}
    if df.empty:
        out["flags"].append("재무 데이터가 없음")
        return out
    fin = S.is_financial(company)
    val = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    match = df.pivot_table(index="year", columns="item", values="match", aggfunc="first")
    g = lambda y, k: val.at[y, k] if (k in val and y in val.index and pd.notna(val.at[y, k])) else None  # noqa: E731
    span = [y for y in sorted(val.index) if g(y, "total_assets") is not None][-years:]
    if fin:
        out["flags"].append("금융업: 유동·비유동 구분이 없고 부채 대부분이 예금 등 영업부채, 이자비용은 영업비용이다 → "
                            "일반 기업 비율로 보면 안 됨")

    for y in span:
        tl, eq = g(y, "total_liabilities"), g(y, "equity_total")
        ca, cl, inv = g(y, "current_assets"), g(y, "current_liabilities"), g(y, "inventory")
        oi, ie, ocf = g(y, "operating_income"), g(y, "interest_expense"), g(y, "operating_cf")
        row = {"year": y, "debt_ratio": None, "current": None, "quick": None, "icr": None, "debt_ocf": None,
               "equity": eq, "notes": []}
        if tl is not None and eq is not None and eq > 0:
            row["debt_ratio"] = tl / eq
        if eq is not None and eq <= 0:
            row["notes"].append("자본총계 0 이하 → 부채비율 계산 안 함")
            out["risks"].append((y, f"자본잠식: 자본총계 {eq:,.0f}"))
        if ca is not None and cl:
            row["current"] = ca / cl
            if inv is not None:
                row["quick"] = (ca - inv) / cl
            elif not fin:
                row["notes"].append("재고자산 계정 없음 → 당좌비율 계산 안 함")
        if oi is not None and ie:
            row["icr"] = oi / ie
            # 금융업은 이자비용이 예금이자(영업비용)라 '이자도 못 냄'의 뜻이 아니다 → 위험 표시에서 뺀다 (사용자 결정: 금융업은 표시만)
            if row["icr"] < 1 and not fin:
                out["risks"].append((y, f"이자보상비율 {row['icr']:.2f} < 1: 영업이익 {oi:,.0f}이 이자비용 {ie:,.0f}보다 작음"))
        elif oi is not None and ie == 0:
            row["notes"].append("이자비용 0 → 이자보상비율 계산 안 함")
        elif ie is None:
            row["notes"].append("이자비용 없음 → 이자보상비율 계산 안 함"
                                + (" (한국: 2021년 이전은 주석 XBRL이 없음)" if company_id.startswith("KR:") else ""))
        if tl is not None and ocf is not None:
            if ocf > 0:
                row["debt_ocf"] = tl / ocf
            else:
                row["notes"].append("영업CF 0 이하 → 부채를 갚는 데 걸리는 해 계산 안 함")
        nonexact = [f"{S.ITEM_BY_KEY[k].name}={S.MATCH_LABEL.get(match.at[y, k], match.at[y, k])}"
                    for k in match.columns if k in USED and y in match.index and pd.notna(match.at[y, k])
                    and match.at[y, k] != "exact"]
        if nonexact:
            row["notes"].append("정의 일치 아님: " + ", ".join(nonexact))
        out["rows"].append(row)

    # 검증: 자산 = 부채 + 자본 (부채총계를 파생한 해는 항등식이라 제외)
    chk = S.checks(df)
    bad = chk[(chk["check"] == "자산 = 부채 + 자본") & ~chk["ok"] & chk["year"].isin(span)]
    for r in bad.itertuples():
        out["flags"].append(f"{r.year}: 자산 ≠ 부채 + 자본 ({r.detail}) → 매핑 확인 필요")
    return out
