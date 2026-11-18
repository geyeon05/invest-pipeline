"""투자기준 3: 주주환원 기록 — 결과만 보여준다 (판정하지 않음)

규칙 문서: criteria/03_주주환원_기록.md

사용자 결정 (2026-11-18)
- 기간: 최근 5년. 판정·통과선 없이 결과만 표시. 표시는 데이터에 있는 사실만.
- A 배당 지급액: 지배기업이 자기 주주에게 준 배당만. 현금흐름표 값을 쓰고, 소수주주 배당이 별도 줄이면 구분,
  한 줄뿐이면 '구분 불가' 표시.
- B 자사주 매입액: 임직원 보상 목적 매입은 제외.
  한국: 취득결정 공시의 취득목적 → 보상 목적 비율 → 결과보고서의 일별(신탁은 월별) 취득 내역을 연도별로 합산 → 차감.
  목적이 섞인 공시는 공시에 적힌 금액 비율로 나누고, 나눌 수 없으면 '목적 혼합'으로 표시(차감하지 않음).
  미국: 세금 원천징수용 매입은 현금흐름표에 별도 태그라 자사주 매입 태그에 들어가지 않는다.
- C 자사주 소각: 한국 DART '자기주식 취득 및 처분 현황'의 소각 수량, 미국 XBRL 소각 수량.
- D 환원 비율: (A + B) ÷ 지배주주 순이익.
- E 주식 수: 발행주식 총수와 유통주식 수 둘 다.
"""
import re

import pandas as pd

from . import dart_shares
from . import promises as P
from . import standard as S

YEARS = 5
COMP_RX = re.compile(r"보상|임직원|우리사주|스톡옵션|주식기준|상여")
AMOUNT_RX = re.compile(r"(?:약\s*)?(?:(\d+)\s*조\s*)?(?:([\d,]+)\s*억)?\s*원")


# ---------------- 보상 목적 자사주 매입 (한국) ----------------
def _won(m) -> int:
    jo, eok = m.group(1), m.group(2)
    return (int(jo) * 10 ** 12 if jo else 0) + (int(eok.replace(",", "")) * 10 ** 8 if eok else 0)


def purpose_split(text: str, plan_amount: int | None) -> dict:
    """취득목적 → {'purpose', 'comp_fraction' (0~1 또는 None=나눌 수 없음), 'basis'}"""
    L = text.split("\n")
    line = next((l for l in L if re.match(r"^\d+\.(취득목적|계약목적)\|", re.sub(r"\s", "", l))), "")
    purpose = line.split("|", 1)[1].strip() if "|" in line else ""
    # 본문에 '약 N억원은 ... 보상 목적' 같은 금액 문장이 있으면 그것이 우선이다
    # (예: 현대차 2024-11 취득목적은 '주주가치 제고 등'이지만 본문에 '약 3,000억원은 주식기준보상 등의 목적')
    comp, total = 0, 0
    for sent in re.split(r"(?<=[.。])|\n", text):
        ms = [m for m in AMOUNT_RX.finditer(sent) if m.group(1) or m.group(2)]
        for i, m in enumerate(ms):
            seg = sent[m.end(): ms[i + 1].start() if i + 1 < len(ms) else m.end() + 60]
            if not re.search(r"목적", seg):
                continue
            amt = _won(m)
            total += amt
            if COMP_RX.search(seg):
                comp += amt
    if comp and plan_amount:
        base = total if total and abs(total - plan_amount) / plan_amount < 0.05 else plan_amount
        return {"purpose": purpose, "comp_fraction": min(comp / base, 1.0),
                "basis": f"본문의 금액: 보상 {comp / 1e8:,.0f}억 / {base / 1e8:,.0f}억"}
    if not COMP_RX.search(purpose):
        return {"purpose": purpose, "comp_fraction": 0.0, "basis": "보상 목적 아님"}
    if not re.search(r"주주|가치|소각|안정|환원", re.sub(COMP_RX, "", purpose)):
        return {"purpose": purpose, "comp_fraction": 1.0, "basis": "전부 보상 목적"}
    return {"purpose": purpose, "comp_fraction": None, "basis": "목적 혼합 (본문에서 금액을 나눌 수 없음)"}


def _yearly_acquisitions(text: str, trust: bool) -> dict[int, int]:
    """결과보고서의 일별(직접)·월별(신탁) 취득 내역을 연도별로 합산 (원)."""
    out, unit = {}, 1
    for line in text.replace("&cr;", "").split("\n"):
        s = re.sub(r"\s", "", line)
        if "단위:" in s:
            unit = 1_000_000 if "백만원" in s else (1 if "원" in s else unit)
        # 날짜 형식: '2026년 01월 30일', '2020.10.27', '2018/04/30' (한 공시 안에서도 섞임)
        # 주식 종류: '보통주식', '우선주', '기명식2우선주', '종류주식', '기타주식' 등
        m = re.match(r"^(\d{4})(?:년|\.|/|-)\d{1,2}(?:월|\.|/|-)\d{1,2}일?\|(기명식)?(보통주|\d?우선주|기타주|종류주)", s)
        if not m:
            continue
        cells = [c.strip() for c in line.split("|")]
        idx = 3 if trust else 5
        if len(cells) > idx:
            v = P._num(cells[idx]) * unit
            out[int(m.group(1))] = out.get(int(m.group(1)), 0) + v
    return out


def comp_buybacks(company_id: str) -> tuple[dict[int, int], list[dict]]:
    """연도별 보상 목적 자사주 매입액(원)과, 약속별 근거."""
    by_year, detail = {}, []
    for p in P.evaluate(company_id):
        src = next((c for c in reversed([p.plan_rcept] + p.corrections) if P._have_doc(company_id, c)), None)
        if not src:
            detail.append({"plan": p.plan_rcept, "filed": p.plan_filed, "note": "취득결정 본문 미수집 → 목적 확인 불가"})
            continue
        sp = purpose_split(P._text(company_id, src), p.amount)
        d = {"plan": p.plan_rcept, "filed": p.plan_filed, "purpose": sp["purpose"], "basis": sp["basis"],
             "fraction": sp["comp_fraction"], "years": {}}
        if sp["comp_fraction"] and p.result_rcept:
            yearly = _yearly_acquisitions(P._text(company_id, p.result_rcept) or "", trust=p.kind == "신탁")
            if not yearly and p.actual:
                yearly = {int((p.result_filed or p.plan_filed)[:4]): p.actual}
                d["basis"] += " / 일별 내역을 읽지 못해 결과보고서 연도에 전액 배정"
            for y, v in yearly.items():
                amt = int(v * sp["comp_fraction"])
                by_year[y] = by_year.get(y, 0) + amt
                d["years"][y] = amt
        elif sp["comp_fraction"] and not p.result_rcept:
            d["basis"] += " / 결과보고서 없음 (진행 중이거나 미수집)"
        if sp["comp_fraction"] != 0.0:
            detail.append(d)
    return by_year, detail


# ---------------- 계산 ----------------
def analyze(company_id: str, years: int = YEARS) -> dict:
    df = S.standardize(company_id)
    out = {"company_id": company_id, "rows": [], "flags": [], "comp_detail": [], "share_years": []}
    if df.empty:
        out["flags"].append("재무 데이터가 없음")
        return out
    val = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    match = df.pivot_table(index="year", columns="item", values="match", aggfunc="first")
    cur = df.pivot_table(index="year", columns="item", values="currency", aggfunc="first")
    base = [y for y in sorted(val.index) if any(k in val and pd.notna(val.at[y, k])
                                                for k in ("net_income_parent", "dividends_paid", "buyback"))]
    span = base[-years:]
    g = lambda y, k: val.at[y, k] if (k in val and y in val.index and pd.notna(val.at[y, k])) else None  # noqa: E731
    listed = set(zip(df["item"], df["year"]))   # 줄은 있으나 금액이 빈 경우를 '계정 없음'과 구분

    kr = company_id.startswith("KR:")
    comp_by_year, comp_detail = comp_buybacks(company_id) if kr else ({}, [])
    out["comp_detail"] = comp_detail
    shares = dart_shares.load(company_id, span) if kr else {}
    if kr and any(not shares[y]["status"] for y in span):
        out["flags"].append("DART 주식 수 데이터 미수집 연도 있음 → C·E 일부 비어 있음 (data.py returns <기업> --fetch, 승인 필요)")

    def money(v, c):
        return f"{v / 1e8:,.0f}억 원" if c == "KRW" else f"{v / 1e6:,.0f}백만 {c}"

    for y in span:
        div, div_nci = g(y, "dividends_paid"), g(y, "dividends_paid_nci")
        bb = g(y, "buyback")
        comp = comp_by_year.get(y, 0) if kr else 0
        bb_net = None if bb is None else max(bb - comp, 0)
        ni = g(y, "net_income_parent")
        ret = (div or 0) + (bb_net or 0)
        ratio = ret / ni if (ni and ni > 0) else None
        if kr:
            sh = shares.get(y, {})
            issued, outst, retired, disposed = sh.get("issued"), sh.get("outstanding"), sh.get("retired"), sh.get("disposed")
        else:
            issued, outst, retired, disposed = g(y, "shares_issued"), g(y, "shares_outstanding"), g(y, "shares_retired"), None
        row = {"year": y, "currency": cur.at[y, "net_income_parent"] if "net_income_parent" in cur and y in cur.index else "",
               "dividends": div, "dividends_nci": div_nci, "buyback": bb, "comp": comp, "buyback_net": bb_net,
               "net_income_parent": ni, "ratio": ratio, "issued": issued, "outstanding": outst,
               "retired": retired, "disposed": disposed, "notes": []}
        # ---- 표시: 데이터에 있는 사실만 ----
        if div is not None and div_nci is None and kr:
            row["notes"].append("배당: 소수주주 배당이 별도 줄로 없음 → 소수주주 몫 구분 불가")
        if div_nci:
            row["notes"].append(f"소수주주 배당 {money(div_nci, row['currency'])} 별도 (환원에 넣지 않음)")
        if div is None:
            row["notes"].append("배당 지급 줄은 있으나 금액이 비어 있음" if ("dividends_paid", y) in listed
                                else "배당 지급 계정 없음 (배당 없음 또는 계정 미확인)")
        if bb is None:
            row["notes"].append("자사주 매입 줄은 있으나 금액이 비어 있음" if ("buyback", y) in listed
                                else "자사주 매입 계정 없음 (매입 없음 또는 계정 미확인)")
        if comp:
            row["notes"].append(f"보상 목적 자사주 매입 {money(comp, row['currency'])} 차감 (근거는 아래)")
        if comp and bb is not None and comp > bb:
            row["notes"].append("보상 목적 매입(결과보고서 기준)이 현금흐름표 매입액보다 큼 → 0으로 처리 (결제 시점 차이 등)")
        if ni is not None and ni <= 0:
            row["notes"].append("지배주주 순이익 적자 → 환원 비율 계산 안 함")
        if disposed:
            row["notes"].append(f"자기주식 처분 {disposed:,}주")
        used = ("dividends_paid", "dividends_paid_nci", "buyback", "net_income_parent",
                "shares_issued", "shares_outstanding", "shares_retired")   # 기준 3이 쓰는 항목만
        nonexact = [f"{S.ITEM_BY_KEY[k].name}={S.MATCH_LABEL.get(match.at[y, k], match.at[y, k])}"
                    for k in match.columns if k in used and y in match.index and pd.notna(match.at[y, k])
                    and match.at[y, k] != "exact"]
        if nonexact:
            row["notes"].append("정의 일치 아님: " + ", ".join(nonexact))
        out["rows"].append(row)

    if [d for d in comp_detail if d.get("fraction") is None]:
        out["flags"].append("목적 혼합으로 보상 목적 금액을 나눌 수 없는 취득결정이 있음 → 차감하지 않음 (아래 근거 참고)")
    if [d for d in comp_detail if "미수집" in d.get("note", "")]:
        out["flags"].append("취득결정 본문 미수집 → 보상 목적 확인 불가 (data.py promises <기업> --fetch, 승인 필요)")
    return out
