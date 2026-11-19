"""분석 도구: 현금 창출 — 결과만 보여준다 (판정하지 않음)

규칙 문서: criteria/02_꾸준한_현금창출.md

사용자 결정 (2026-11-18)
- 지표: A 영업현금흐름, B 잉여현금흐름(영업현금흐름 − 순설비투자), C 이익의 현금 전환(영업현금흐름 ÷ 연결 순이익)
- 기간: 최근 5년, 해마다 확인
- 순설비투자 = (유형자산 취득 + 무형자산 취득) − (유형자산 처분 + 무형자산 처분)
- 영업현금흐름은 보고된 값 그대로 (국내·해외 회계기준 차이는 표시만)
- 순이익은 연결 순이익 (비지배지분 포함)
- 통과선·판정·판단 기록을 두지 않고 결과만 보여준다. 금융업 등 예외도 표시만 한다.

아래 '표시'는 데이터에 있는 사실만 알려준다 (사용자 결정: 기준 숫자나 해석이 들어간 표시는 두지 않음).
"""
import re

import pandas as pd

from . import promises as P
from . import service
from . import standard as S

YEARS = 5
COMPONENTS = ["capex_ppe", "capex_intangible", "disposal_ppe", "disposal_intangible"]


def _latest_annual_report_year(company_id: str) -> int | None:
    """공시 목록에 있는 가장 최근 연차보고서의 회계연도 (데이터 공백 표시용)."""
    if company_id.startswith("KR:"):
        rows = P._ro().execute("SELECT title FROM filings WHERE company_id = ? AND title LIKE '%사업보고서 (%'",
                               (company_id,)).fetchall()
        ys = [int(m.group(1)) for (t,) in rows if (m := re.search(r"사업보고서\s*\((\d{4})\.", t))]
    else:
        rows = P._ro().execute("SELECT report_date FROM filings WHERE company_id = ? AND form IN ('10-K', '20-F', '40-F')",
                               (company_id,)).fetchall()
        ys = [int(S.standard_year(pd.Series([r[0]])).iat[0]) for r in rows if r[0]]
    return max(ys) if ys else None


def analyze(company_id: str, years: int = YEARS) -> dict:
    df = S.standardize(company_id)
    company = service.get_company(company_id) or {"market": company_id[:2], "profile": {}}
    out = {"company_id": company_id, "rows": [], "counts": {}, "flags": [], "sources": df,
           "financial": S.is_financial(company)}
    if df.empty:
        out["flags"].append("표준 재무항목을 계산할 재무 데이터가 없음")
        return out
    val = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    match = df.pivot_table(index="year", columns="item", values="match", aggfunc="first")
    cur = df.pivot_table(index="year", columns="item", values="currency", aggfunc="first")
    have = [y for y in sorted(val.index) if "operating_cf" in val and pd.notna(val.at[y, "operating_cf"])]
    span = have[-years:]

    def g(y, k):
        return val.at[y, k] if (k in val and y in val.index and pd.notna(val.at[y, k])) else None

    for y in span:
        ocf, ni = g(y, "operating_cf"), g(y, "net_income")
        comp = {k: g(y, k) for k in COMPONENTS}
        acq = None if comp["capex_ppe"] is None else comp["capex_ppe"] + (comp["capex_intangible"] or 0)
        disp = (comp["disposal_ppe"] or 0) + (comp["disposal_intangible"] or 0)
        net_capex = None if acq is None else acq - disp
        fcf = None if (ocf is None or net_capex is None) else ocf - net_capex
        conv = None if (ocf is None or ni is None or ni <= 0) else ocf / ni
        row = {"year": y, "currency": cur.at[y, "operating_cf"] if "operating_cf" in cur else "",
               "operating_cf": ocf, "acquisitions": acq, "disposals": disp, "net_capex": net_capex,
               "fcf": fcf, "net_income": ni, "conversion": conv, "notes": []}
        # ---- 표시: 데이터에 있는 사실만 (사용자 결정 2026-11-18. 기준 숫자나 해석이 들어간 표시는 두지 않음) ----
        if ni is not None and ni <= 0:
            row["notes"].append("순이익 적자 → 현금 전환율 계산 안 함")
        missing = [S.ITEM_BY_KEY[k].name for k in ("capex_intangible", "disposal_ppe", "disposal_intangible")
                   if comp[k] is None and acq is not None]
        if missing:
            row["notes"].append("계정 없음 → 0으로 계산: " + ", ".join(missing))
        if comp["capex_ppe"] is None:
            row["notes"].append("유형자산 취득 계정을 찾지 못함 → 순설비투자·FCF 계산 안 함")
        nonexact = [f"{S.ITEM_BY_KEY[k].name}={S.MATCH_LABEL.get(match.at[y, k], match.at[y, k])}"
                    for k in match.columns if y in match.index and pd.notna(match.at[y, k]) and match.at[y, k] != "exact"]
        if nonexact:
            row["notes"].append("정의 일치 아님: " + ", ".join(nonexact))
        out["rows"].append(row)

    rows = out["rows"]
    out["counts"] = {
        "years": len(rows),
        "ocf_pos": sum(1 for r in rows if r["operating_cf"] is not None and r["operating_cf"] > 0),
        "fcf_pos": sum(1 for r in rows if r["fcf"] is not None and r["fcf"] > 0),
        "fcf_known": sum(1 for r in rows if r["fcf"] is not None),
        "conv_ge1": sum(1 for r in rows if r["conversion"] is not None and r["conversion"] >= 1),
        "conv_known": sum(1 for r in rows if r["conversion"] is not None),
    }
    # ---- 내 기준: 영업CF가 꾸준히 늘었나 (프로필 6-①, 숫자 기준 2. 사용자 결정 2026-11-19) ----
    # 최근 5년(전년 대비 5번) 중 3번 이상 증가 + 5년 연평균 증가율 0% 초과. 감소한 해는 따로, 마이너스인 해는 경고.
    series = [(y, g(y, "operating_cf")) for y in ([span[0] - 1] + span if span else [])]
    series = [(y, v) for y, v in series if v is not None]
    changes = [(b[0], (b[1] - a[1]) / abs(a[1]) if a[1] else None) for a, b in zip(series, series[1:])]
    ups = sum(1 for _, c in changes if c is not None and c > 0)
    first, last = (series[0][1], series[-1][1]) if len(series) >= 2 else (None, None)
    n_years = series[-1][0] - series[0][0] if len(series) >= 2 else 0
    cagr = (last / first) ** (1 / n_years) - 1 if first and last and first > 0 and last > 0 and n_years else None
    out["steady"] = {
        "changes": len(changes), "ups": ups, "cagr": cagr,
        "decreases": [(y, c) for y, c in changes if c is not None and c < 0],
        "negatives": [y for y, v in series if v < 0],
        "ok": (ups >= 3 and cagr > 0) if (len(changes) == 5 and cagr is not None) else None,
        "why": None if len(changes) == 5 else f"비교할 수 있는 해가 {len(changes)}번뿐 (5번 필요)",
    }
    if cagr is None and changes:
        out["steady"]["why"] = "처음 또는 마지막 해 영업CF가 0 이하 → 연평균 증가율 계산 불가"
    # ---- 회사 단위 표시 ----
    if out["financial"]:
        out["flags"].append("금융업: 영업현금흐름에 예금·대출이 들어가고 설비투자 개념이 달라, 이 지표들의 의미가 일반 기업과 다름")
    if rows and (ly := _latest_annual_report_year(company_id)) and ly > rows[-1]["year"]:
        out["flags"].append(f"FY{ly} 연차보고서는 나왔지만 재무 데이터에 그해 값이 없음 (최근 값 FY{rows[-1]['year']})")
    ifrs = company_id.startswith("KR:") or df["source"].astype(str).str.startswith("ifrs-full:").any()
    if ifrs:
        out["flags"].append("국제회계기준(IFRS): 리스 원금 상환을 재무활동에, 이자 지급을 영업·재무 중 선택해 적을 수 있어 "
                            "미국 기준 기업보다 영업현금흐름이 크게 나올 수 있음 (조정하지 않음)")
    return out
