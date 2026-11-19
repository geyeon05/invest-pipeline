"""자본 배분: 번 돈을 어디에 썼고, 그 결과가 어땠나 — 결과만 보여준다 (판정하지 않음)

기준 3(주주환원 기록)을 합친 분석 도구 (사용자 결정 2026-11-19, 프로필 4-2).
- 주주환원은 그 자체로는 증거가 아니라 돈의 여러 쓰임 중 하나로 본다. 의도는 회사마다 논의해서 판단한다.
- 재투자 = 설비 투자만 (유형·무형자산 취득 − 처분, 기준 2의 순capex와 같음). 인수·지분 투자는 넣지 않는다.
- ROE = 연결 순이익 ÷ 평균 자본총계(비지배지분 포함). 기간은 최근 5년.
- 의도를 논의할 때 쓸 사실 다섯 가지를 함께 보여준다:
  ① 환원이 몇 년 이어졌나  ② 환원이 FCF 범위 안인가, 빚이 늘어난 해인가  ③ 산 자사주를 소각했나, 들고 있나
  ④ 주가가 떨어진 뒤에 매입했나  ⑤ 발표한 환원 정책을 지켰나 (기준 1 결과)
"""
import pandas as pd

from . import dart_shares, prices, service
from . import promises as P
from . import returns as R
from . import spread as SP
from . import standard as S
from . import us_promises as U

YEARS = 5
LOOKBACK_DAYS = 182      # ④ 한국: 매입 결정 전 6개월 주가 변화


def _pct(a, b):
    return a / b - 1 if a is not None and b else None


def analyze(company_id: str, years: int = YEARS) -> dict:
    out = {"company_id": company_id, "rows": [], "flags": [], "facts": {}}
    df = S.standardize(company_id)
    if df.empty:
        out["flags"].append("재무 데이터가 없음")
        return out
    val = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    g = lambda y, k: val.at[y, k] if (k in val and y in val.index and pd.notna(val.at[y, k])) else None  # noqa: E731
    span = [y for y in sorted(val.index) if g(y, "operating_cf") is not None][-years:]
    kr = company_id.startswith("KR:")
    ret = {x["year"]: x for x in R.analyze(company_id, years)["rows"]}
    spr = SP.by_year(df, span)
    if S.is_financial(service.get_company(company_id) or {}):
        # 금융업: 이자비용이 예금이자(영업비용)라 스프레드의 뜻이 다르다 → 계산하지 않음 (재무 안전성과 같은 원칙)
        spr = {y: {"roa_op": None, "rate": None, "spread": None, "why": "금융업: 이자비용이 영업비용이라 계산 안 함"}
               for y in span}

    for y in span:
        ocf = g(y, "operating_cf")
        capex = sum(v or 0 for v in (g(y, "capex_ppe"), g(y, "capex_intangible"))) \
            - sum(v or 0 for v in (g(y, "disposal_ppe"), g(y, "disposal_intangible")))
        fcf = ocf - capex if ocf is not None else None
        r = ret.get(y, {})
        payout = None if not r else (r.get("dividends") or 0) + (r.get("buyback_net") or 0)
        d1, d0 = g(y, "interest_bearing_debt"), g(y - 1, "interest_bearing_debt")
        eq1, eq0, ni = g(y, "equity_total"), g(y - 1, "equity_total"), g(y, "net_income")
        roe = ni / ((eq1 + eq0) / 2) if ni is not None and eq1 and eq0 and (eq1 + eq0) > 0 else None
        out["rows"].append({"year": y, "ocf": ocf, "capex": capex, "fcf": fcf, "payout": payout,
                            "dividends": r.get("dividends"), "buyback": r.get("buyback_net"),
                            "left": fcf - payout if fcf is not None and payout is not None else None,
                            "debt_change": d1 - d0 if d1 is not None and d0 is not None else None, "roe": roe,
                            "currency": r.get("currency") or "", **spr.get(y, {})})
    rows = out["rows"]
    # 9-②: 빚으로 높인 ROE는 스프레드가 플러스일 때만 인정
    out["facts"]["spread_negative"] = [x["year"] for x in rows if x.get("spread") is not None and x["spread"] < 0]

    # ① 지속성
    pay_years = [x["year"] for x in rows if x["payout"]]
    out["facts"]["persistence"] = {
        "n": len(pay_years), "of": len(rows),
        "div_years": [x["year"] for x in rows if x["dividends"]],
        "buy_years": [x["year"] for x in rows if x["buyback"]]}
    # ② FCF 범위 / 빚
    out["facts"]["over_fcf"] = [(x["year"], x["payout"], x["fcf"], x["debt_change"]) for x in rows
                                if x["payout"] and x["fcf"] is not None and x["payout"] > x["fcf"]]
    # ③ 소각 vs 보유
    if kr:
        sh = dart_shares.load(company_id, span)
        out["facts"]["retire"] = [(y, sh[y].get("acquired"), sh[y].get("retired"), sh[y].get("disposed"),
                                   sh[y].get("treasury")) for y in span]
    else:
        out["facts"]["retire"] = [(y, None, g(y, "shares_retired"), None, None) for y in span]
    # ④ 매입 시점의 주가 흐름
    px, _, _ = prices.load(company_id)
    timing = []
    if not px.empty:
        if kr:
            comp = {d["plan"]: d.get("purpose") for d in R.comp_buybacks(company_id)[1]}
            for p in P.evaluate(company_id):
                day = pd.Timestamp(p.plan_filed)
                if day.year < span[0] if span else True:
                    continue
                now, before = prices.close_on(px, day), prices.close_on(px, day - pd.Timedelta(days=LOOKBACK_DAYS))
                timing.append({"date": p.plan_filed, "kind": p.kind, "amount": p.amount,
                               "change": _pct(now[1], before[1]) if now and before else None,
                               "comp": comp.get(p.plan_rcept)})
        else:
            for x in rows:
                if not x["buyback"]:
                    continue
                pe = df[(df["item"] == "operating_cf") & (df["year"] == x["year"])]["period_end"]
                end = pd.Timestamp(pe.iat[0]) if len(pe) else pd.Timestamp(f"{x['year']}-12-31")
                a, b = prices.close_on(px, end), prices.close_on(px, end - pd.Timedelta(days=365))
                timing.append({"date": str(end.date()), "kind": "연간", "amount": x["buyback"],
                               "change": _pct(a[1], b[1]) if a and b else None, "comp": None})
    else:
        out["flags"].append("주가 미수집 → ④ 매입 시점의 주가 흐름 계산 불가 (data.py price <기업> --fetch, 승인 필요)")
    out["facts"]["timing"] = timing
    # ⑤ 기준 1 결과 (환원 약속만)
    try:
        if kr:
            ps = P.evaluate(company_id)
            v = P.verdict(ps, P.current_ceos(company_id), "result")
            grades = {}
            for p in ps:
                grades[p.grade or p.status] = grades.get(p.grade or p.status, 0) + 1
            out["facts"]["promise"] = {"verdict": v["verdict"], "why": v["why"], "grades": grades,
                                       "scope": "자사주 취득 약속 (기준 1의 A)"}
        else:
            r1 = U.evaluate(company_id)
            v = P.verdict(r1["promises"], [U._norm_person(r1["current_ceo"] or "")], "result")
            out["facts"]["promise"] = {"verdict": v["verdict"], "why": v["why"], "grades": {},
                                       "scope": "10-K의 배당 의도 문장 (기준 1의 미국)"}
    except Exception as e:  # noqa: BLE001
        out["facts"]["promise"] = {"verdict": "확인 불가", "why": str(e)[:80], "grades": {}, "scope": ""}

    if S.is_financial(service.get_company(company_id) or {}):
        out["flags"].append("금융업: 영업CF·설비투자의 의미가 일반 기업과 달라 FCF 비교는 참고만")
    return out
