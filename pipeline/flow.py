"""엔진: 9단계를 기존 부품으로 계산해 공책에 적을 결과로 만든다.

- 계산은 기존 부품을 그대로 부른다 (부품의 값을 바꾸지 않음).
- **논의 단위 = 켜진 신호 하나하나** (사용자 결정 2026-11-20 '다'): 단계마다 신호를 items 로 돌려준다.
  신호가 없으면 단순 정보, 있으면 신호마다 논의 항목. 숫자 표(summary)는 어느 쪽이든 사실로 보여준다.
  어떤 것을 신호로 볼지는 criteria/README.md 4장 'AI가 정한 값'.
- 결과의 "checks"는 단계 전체의 '확인할 것'(덜 받은 자료 등)으로 공책에 들어간다.
- 붙인 단계: 1~8 전부 (2026-11-20). 엔진은 외부 요청을 하지 않는다: 덜 받은 자료는 '확인할 것(자료 받기)'로 남긴다.
"""
import math

from . import (capital_allocation, cashflow, earnings_quality, events, funding, price_level, promises, related_party,
               safety, us_promises)
from . import standard as S

IMPLEMENTED = (1, 2, 3, 4, 5, 6, 7, 8)


def _py(v):
    """JSON에 쓸 수 있는 값으로 (numpy·NaN 정리)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return None
    return int(f) if f.is_integer() and abs(f) < 2**53 else f


def _sources(df, items: list[str], years: list[int]) -> list[dict]:
    if df is None or df.empty:
        return []
    s = df[df["item"].isin(items) & df["year"].isin(years)]
    return [{"item": r.item, "year": int(r.year), "value": _py(r.value), "match": r.match,
             "account": str(r.source), "filing": str(r.filing)} for r in s.itertuples()]


def _no_data(r: dict) -> dict:
    return {"summary": ["계산할 재무 데이터가 없음"], "flags": r["flags"], "data": None, "sources": [],
            "items": [{"key": "no-data", "title": "데이터 없음", "detail": "계산할 재무 데이터가 없음 → 원인 확인"}]}


def _years(ys) -> str:
    return ", ".join(str(int(y)) for y in ys)


def step2_cashflow(company_id: str) -> dict:
    """2 현금 창출: 영업CF가 꾸준히 늘었나 (숫자 기준 2, 프로필 6-①)."""
    r = cashflow.analyze(company_id)
    rows = r["rows"]
    if not rows:
        return _no_data(r)
    st = dict(r["steady"])
    st["ok"] = None if st["ok"] is None else bool(st["ok"])   # numpy bool은 'is False'로 잡히지 않음
    cur = rows[-1]["currency"]
    unit = "억 원" if cur == "KRW" else f"백만 {cur}"
    ok = {True: "충족", False: "미충족", None: "판단 불가"}[st["ok"]]
    cagr = "-" if st["cagr"] is None else f"{st['cagr']:+.1%}"
    summary = [f"내 기준 '영업CF가 꾸준히 늘었나': {ok}",
               f"전년보다 늘어난 해 {st['ups']}/{st['changes']}번 (기준 3번 이상) · 5년 연평균 {cagr} (기준 0% 초과)"]
    if st["decreases"]:
        summary.append("감소한 해: " + ", ".join(f"{y} {c:+.1%}" for y, c in st["decreases"]))

    # ---- 신호 = 논의 항목 ----
    items = []
    if st["ok"] is False:
        items.append({"key": "criterion", "title": "내 기준 미충족",
                      "detail": f"늘어난 해 {st['ups']}/{st['changes']}번 (기준 3번 이상), 연평균 {cagr} (기준 0% 초과)"})
    if st["ok"] is None:
        items.append({"key": "unknown", "title": "내 기준을 판단할 수 없음", "detail": st.get("why") or ""})
    if st["negatives"]:
        items.append({"key": "negative-ocf", "title": "영업CF가 마이너스인 해",
                      "detail": f"{_years(st['negatives'])} (경고: 탈락이 아니라 원인 확인, 6-①)"})
    if r["financial"]:
        items.append({"key": "financial", "title": "금융업", "detail": "영업CF에 예금·대출이 들어가 의미가 일반 기업과 다름"})

    years = [x["year"] for x in rows]
    data = {"unit": unit, "rows": [{"year": x["year"], "operating_cf": _py(x["operating_cf"]),
                                    "fcf": _py(x["fcf"]), "net_income": _py(x["net_income"]),
                                    "conversion": _py(x["conversion"])} for x in rows],
            "steady": {"ok": st["ok"], "ups": int(st["ups"]), "changes": int(st["changes"]), "cagr": _py(st["cagr"]),
                       "decreases": [[int(y), _py(c)] for y, c in st["decreases"]],
                       "negatives": [int(y) for y in st["negatives"]]}}
    return {"summary": summary, "items": items, "flags": r["flags"], "data": data,
            "sources": _sources(r["sources"], ["operating_cf"], [years[0] - 1] + years)}


def step4_quality(company_id: str) -> dict:
    """4 이익의 질: 켜진 신호(B·B*·C·D·E)마다 논의 항목. E에 필요한 대표이사 자료를 덜 받았으면
    단계 전체의 '확인할 것(자료 받기)'을 남긴다 (사용자 결정 2026-11-20) → 받기 전에는 확정·확인함 불가."""
    r = earnings_quality.analyze(company_id)
    rows = r["rows"]
    if not rows:
        return _no_data(r)
    pct = lambda v: "-" if v is None else f"{v:+.1%}"  # noqa: E731
    label = {"B": "B 매출채권", "B_ca": "B* 계약자산", "C": "C 재고", "D": "D 작은 이익", "E": "E 빅 배스"}
    summary = ["A 발생액/자산 5년: " + " → ".join(f"{x['year']} {pct(x['accruals'])}" for x in rows)
               + "  (플러스 = 현금이 덜 들어온 이익)",
               "매출 증가 5년: " + " → ".join(f"{x['year']} {pct(x['rev_g'])}" for x in rows)]
    items = []
    for k in ("B", "B_ca", "C", "D", "E"):
        hit = [x for x in rows if x.get(k)]
        if not hit:
            continue
        whys = []
        for x in hit:
            w = [n.split("신호: ")[1] for n in x["notes"] if n.startswith(label[k]) and "신호:" in n]
            if k == "E":
                w = [n.replace("E: ", "") for n in x["notes"] if n.startswith("E: 새 대표이사")]
            if k == "D":
                w = [f"순이익/자산 {pct(x['roa'])}"]
            whys.append(f"{x['year']} {'; '.join(w)}" if w else str(x["year"]))
        items.append({"key": k, "title": f"{label[k]} 신호", "detail": " / ".join(whys)})
    if any("금융업" in f for f in r["flags"]):
        items.append({"key": "financial", "title": "금융업", "detail": "매출채권·재고 개념이 없고 발생액의 의미가 다름"})
    if not items:
        summary.append("이익조정 신호(B·B*·C·D·E) 없음")
    checks = []
    if (miss := next((f for f in r["flags"] if "미수집" in f), None)):
        checks.append({"text": "E(빅 배스) 확인: 대표이사 자료 받기 (" + miss.split("(")[0].strip() + ")", "method": "자료 받기"})
    elif (unknown_e := [x["year"] for x in rows if x.get("E") is None]):
        summary.append(f"E 확인 불가인 해: {_years(unknown_e)} (대표이사 여부 미기재, 20-F 등)")
    years = [x["year"] for x in rows]
    keep = ("year", "accruals", "rev_g", "rec_g", "ca_g", "inv_g", "roa")
    data = {"rows": [{**{k: _py(x.get(k)) for k in keep},
                      **{k: (None if x.get(k) is None else bool(x.get(k))) for k in ("B", "B_ca", "C", "D", "E")},
                      "ceo": x.get("ceo")} for x in rows]}
    return {"summary": summary, "items": items, "checks": checks,
            "flags": r["flags"] + [f"{x['year']}: {n}" for x in rows for n in x["notes"] if "신호:" not in n],
            "data": data, "sources": _sources(S.standardize(company_id), list(earnings_quality.USED), [years[0] - 1] + years)}


def step5_safety(company_id: str) -> dict:
    """5 재무 안전성: 숫자는 사실로 보여주고, 분명한 위험·경고(자본잠식, 이자보상비율 1 미만, 스프레드 마이너스)만 논의 항목."""
    r = safety.analyze(company_id)
    rows = r["rows"]
    if not rows:
        return _no_data(r)
    pct = lambda v: "-" if v is None else f"{v:.0%}"  # noqa: E731
    x2 = lambda v: "-" if v is None else f"{v:.2f}배"  # noqa: E731
    yrs = lambda v: "-" if v is None else f"{v:.1f}년"  # noqa: E731
    last = rows[-1]
    summary = [f"최근 해({last['year']}): 부채비율 {pct(last['debt_ratio'])} · 유동비율 {pct(last['current'])} · "
               f"당좌비율 {pct(last['quick'])} · 이자보상비율 {x2(last['icr'])} · 부채를 영업CF로 갚는 데 {yrs(last['debt_ocf'])}",
               "부채비율 5년: " + " → ".join(f"{x['year']} {pct(x['debt_ratio'])}" for x in rows),
               "이자보상비율 5년: " + " → ".join(f"{x['year']} {x2(x['icr'])}" for x in rows),
               "통과선이 없는 숫자: 같은 업종끼리 비교해서 본다"]
    deficit = [(y, t) for y, t in r["risks"] if t.startswith("자본잠식")]
    icr = [(y, t) for y, t in r["risks"] if t.startswith("이자보상")]
    spread = r.get("spread_warn", [])
    items = []
    if deficit:
        items.append({"key": "deficit", "title": "자본잠식", "detail": " / ".join(f"{y}: {t}" for y, t in deficit)})
    if icr:
        items.append({"key": "icr", "title": "이자보상비율 1 미만 (영업이익으로 이자도 못 냄)",
                      "detail": " / ".join(f"{y}: {t.split(': ', 1)[1]}" for y, t in icr)})
    if spread:
        items.append({"key": "spread", "title": "스프레드 마이너스 (빚이 독이 되는 해)",
                      "detail": " / ".join(f"{y}: {v:+.1%}" for y, v in spread)})
    if any("금융업" in f for f in r["flags"]):
        items.append({"key": "financial", "title": "금융업", "detail": "유동·비유동 구분이 없고 부채 대부분이 예금 → 일반 기업 비율로 보면 안 됨"})
    if (bad := [f for f in r["flags"] if "자산 ≠" in f]):
        items.append({"key": "ledger", "title": "장부 검증(자산 = 부채 + 자본)이 안 맞는 해", "detail": " / ".join(bad)})
    if not items:
        summary.append("분명한 위험 신호(자본잠식, 이자보상비율 1 미만, 스프레드 마이너스) 없음")
    years = [x["year"] for x in rows]
    data = {"rows": [{k: (_py(x[k]) if k != "notes" else x[k]) for k in
                      ("year", "debt_ratio", "current", "quick", "icr", "debt_ocf", "notes")} for x in rows]}
    return {"summary": summary, "items": items, "flags": r["flags"] + [f"{x['year']}: {n}" for x in rows for n in x["notes"]],
            "data": data, "sources": _sources(S.standardize(company_id), list(safety.USED), years)}


def _eok(v, cur="KRW") -> str:
    if v is None:
        return "-"
    return f"{v / 1e8:,.0f}억" if cur == "KRW" else f"{v / 1e6:,.0f}백만 {cur}"


def step1_promises(company_id: str) -> dict:
    """1 약속 이행: 기준표의 판정 그대로. 통과 → 단순 정보, 주의·탈락 → 논의 항목(탈락이면 계속할지 묻는다),
    판정 불가 → 논의 항목. 판정에 필요한 본문을 덜 받았으면 단계 전체의 '확인할 것(자료 받기)'."""
    checks = []
    if company_id.startswith("KR:"):
        ps = promises.evaluate(company_id)
        evs = funding.evaluate(company_id)
        v = promises.verdict(ps + evs, promises.current_ceos(company_id), "result")
        miss = {f["rcept_no"] for f in promises.missing_docs(company_id) + funding.missing_docs(company_id)}
        scope = "자기주식 취득(A) + 자금조달 목적(B)"
        n_all = len(ps) + len(evs)
    else:
        r = us_promises.evaluate(company_id)
        v = promises.verdict(r["promises"], [us_promises._norm_person(r["current_ceo"] or "")], "result")
        miss = {f["rcept_no"] for f in us_promises.missing_docs(company_id)}
        scope = "10-K의 주주환원 의도 문장 (배당 증액·지속)"
        n_all = len(r["promises"])
    summary = [f"판정: {v['verdict']} ({v['why']})", f"범위: {scope} · 찾은 약속 {n_all}건",
               f"현 대표이사의 판정 끝난 약속 {v['current_judged']}건 · 불이행 {v['current_fail']}건 · "
               f"이전 대표이사 시절 불이행 {v['past_fail']}건 · 진행 중 {v['pending']}건 · 확인 필요 {v['unresolved']}건",
               "자세한 약속 목록: uv run data.py promises <회사>"]
    if miss:
        checks.append({"text": f"판정에 필요한 공시 본문 {len(miss)}건 받기 (promises --fetch)", "method": "자료 받기"})
    items = []
    if v["verdict"] == "탈락":
        items.append({"key": "fail", "title": "탈락 (현 대표이사 불이행 2건 이상)",
                      "detail": v["why"] + " · 유일하게 '탈락'이 있는 기준: 분석을 계속할지 정한다"})
    elif v["verdict"] == "주의":
        items.append({"key": "caution", "title": "주의", "detail": v["why"]})
    elif v["verdict"] == "판정 불가":
        if miss:   # 본문을 덜 받아서 판정 못 함 → 받은 뒤 다시 본다
            items.append({"key": "unknown", "title": "판정 불가 (본문을 덜 받음)", "detail": v.get("why", "")})
        else:      # 자료는 다 받았는데 약속이 원래 적음 → 단순 정보 (사용자 결정 2026-11-20 '나'). 통과가 아님을 적어 둔다
            summary.insert(1, "판정할 약속 없음: 자료를 다 받았는데도 현 대표이사의 판정 끝난 약속이 3건 미만 "
                              "(통과가 아니라 '판정할 약속이 없다'는 뜻)")
    if v["unresolved"]:
        items.append({"key": "unresolved", "title": f"사람이 판단할 약속 {v['unresolved']}건 (확인 필요·판단 필요)",
                      "detail": "예외 인정 여부 등은 사용자가 정한다 (criteria/judgments/)"})
    return {"summary": summary, "items": items, "checks": checks, "flags": [],
            "data": {k: v[k] for k in v if k != "why"} | {"why": v.get("why")}, "sources": []}


def step3_allocation(company_id: str) -> dict:
    """3 자본 배분: 주주환원이 있으면 '주주환원 의도' 논의 항목 (사실 다섯 가지와 함께).
    스프레드 마이너스는 5단계에서 다루므로 여기서는 항목으로 만들지 않는다 (두 번 논의하지 않게)."""
    r = capital_allocation.analyze(company_id)
    rows, f = r["rows"], r["facts"]
    if not rows:
        return _no_data(r)
    cur = next((x["currency"] for x in rows if x["currency"]), "KRW")
    pct = lambda v: "-" if v is None else f"{v:.1%}"  # noqa: E731
    summary = ["5년: " + " / ".join(f"{x['year']} FCF {_eok(x['fcf'], cur)}·환원 {_eok(x['payout'], cur)}·ROE {pct(x['roe'])}"
                                     for x in rows),
               f"재투자(순설비투자) 5년 합계 {_eok(sum(x['capex'] or 0 for x in rows), cur)}"]
    if f.get("spread_negative"):
        summary.append(f"스프레드 마이너스인 해 {_years(f['spread_negative'])} → 5 재무 안전성에서 논의")
    items = []
    pers = f.get("persistence", {})
    if pers.get("n"):
        facts = [f"① 환원한 해 {pers['n']}/{pers['of']} (배당 {len(pers['div_years'])}해, 자사주 {len(pers['buy_years'])}해)"]
        if f.get("over_fcf"):
            facts.append("② FCF를 넘어 환원한 해: " + ", ".join(
                f"{y} (환원 {_eok(p, cur)} > FCF {_eok(fc, cur)}" + (f", 이자부 부채 {_eok(d, cur)} 늘어남" if d and d > 0 else "") + ")"
                for y, p, fc, d in f["over_fcf"]))
        else:
            facts.append("② 환원은 모두 FCF 범위 안")
        ret = [x for x in f.get("retire", []) if x[2]]
        facts.append("③ 자사주 소각한 해: " + (_years(x[0] for x in ret) if ret else "없음"))
        tm = [t for t in f.get("timing", []) if t.get("change") is not None]
        if tm:
            facts.append("④ 매입 전 주가 변화: " + ", ".join(f"{t['date']} {t['change']:+.0%}" for t in tm[:5]))
        elif any("주가 미수집" in fl for fl in r["flags"]):
            facts.append("④ 주가 미수집 → 매입 시점 주가 흐름 계산 불가")
        pr = f.get("promise") or {}
        facts.append(f"⑤ 환원 약속 이행(기준 1): {pr.get('verdict', '-')}")
        items.append({"key": "payout-intent", "title": "주주환원 의도", "detail": " / ".join(facts)})
        if f.get("over_fcf"):
            items.append({"key": "over-fcf", "title": "FCF를 넘어선 환원",
                          "detail": ", ".join(str(y) for y, *_ in f["over_fcf"])})
    else:
        summary.append("최근 5년 주주환원 없음")
    if any("금융업" in fl for fl in r["flags"]):
        items.append({"key": "financial", "title": "금융업", "detail": "영업CF·설비투자의 의미가 달라 FCF 비교는 참고만"})
    data = {"rows": [{k: _py(x.get(k)) for k in ("year", "ocf", "capex", "fcf", "payout", "dividends", "buyback",
                                                  "debt_change", "roe", "spread")} for x in rows]}
    return {"summary": summary, "items": items, "flags": r["flags"], "data": data,
            "sources": _sources(S.standardize(company_id), ["operating_cf", "net_income", "equity_total"], [x["year"] for x in rows])}


def step6_related(company_id: str) -> dict:
    """6 특수관계자: 항상 논의 항목 1개 (대주주 쪽 거래 상대를 사용자가 고르고, 주의 기준은 분석할 때 정함)."""
    if not company_id.startswith("KR:"):
        return {"summary": ["미국 기업: 특수관계자 거래 자동 표는 아직 없음 (10-K 본문의 Related Party 주석을 찾아 읽음)"],
                "items": [{"key": "pick-owner", "title": "대주주 쪽 거래 확인",
                           "detail": "10-K 'Related Party Transactions' 주석을 doc --grep 으로 찾아 판단"}],
                "flags": [], "data": None, "sources": []}
    cps = related_party.counterparties(company_id)
    picked = related_party.load_owner_side(company_id)
    summary = [f"거래 상대 {len(cps)}곳 (최근 연도 {cps[0]['last_year'] if cps else '-'})"]
    hints = [c for c in cps if c["owner_hint"]]
    if hints:
        summary.append("대주주 쪽일 수 있는 상대(공시 분류 기준): " + ", ".join(c["name"] for c in hints[:6])
                       + (" …" if len(hints) > 6 else ""))
    checks = []
    if not cps:
        checks.append({"text": "특수관계자 표가 없음: 사업보고서 XBRL 받기 (safety --fetch 와 같은 자료)", "method": "자료 받기"})
    if picked:
        rs = related_party.ratios(company_id, [p["member"] for p in picked["owner_side"]])
        summary.append(f"내가 고른 대주주 쪽 {len(picked['owner_side'])}곳 ({picked['decided']}) · 매입 ÷ 매출: "
                       + ", ".join(f"{x['year']} {x['ratio']:.1%}" for x in rs if x["ratio"] is not None))
        item = {"key": "pick-owner", "title": "대주주 쪽 매입 비율 판단",
                "detail": "고른 상대로 계산한 비율을 보고 주의할 수준인지 판단 (기준 %는 분석할 때 정함)"}
    else:
        item = {"key": "pick-owner", "title": "대주주 쪽 거래 상대 고르기와 비율 판단",
                "detail": "related 로 목록을 보고 직접 고른다(--owner 번호들). 자동 분류는 회사마다 달라 믿기 어려움"}
    return {"summary": summary, "items": [item], "checks": checks, "flags": [], "data": None, "sources": []}


IMMEDIATE = ("경영진", "자금조달", "소송제재사고", "대주주")   # 보유-① 바로 확인할 일


def step7_qualitative(company_id: str) -> dict:
    """7 정성 자료: 최근 1년 '바로 확인할 일' 공시가 있으면 분류마다 논의 항목 + 항상 '해자' 항목."""
    from datetime import date, timedelta
    since = str(date.today() - timedelta(days=365))
    items, summary = [], [f"최근 1년({since} 이후) 수시공시 중 바로 확인할 일 (보유-①), 회사 자신의 공시만"]
    for k in IMMEDIATE:
        evs = events.find(company_id, [k], since, include_subsidiary=False)
        summary.append(f"{k}: {len(evs)}건")
        if evs:
            items.append({"key": f"event-{k}", "title": f"{k} 공시 {len(evs)}건",
                          "detail": " / ".join(f"{e['filed']} {e['title']}" for e in evs[:5]) + (" …" if len(evs) > 5 else "")})
    items.append({"key": "moat", "title": "해자",
                  "detail": "대중성·기술 독점성·숫자로 판단 (7-②). 사업보고서: qual --topics 해자,기술 / 뉴스: news"})
    summary.append("뉴스는 판단 근거가 아니라 시야를 넓히는 데 쓴다 (2번 답)")
    return {"summary": summary, "items": items, "flags": [], "data": None, "sources": []}


def step8_price(company_id: str) -> dict:
    """8 가격 판단: 항상 논의 항목 1개 ('지금 비싼가?'). 주가가 없으면 단계 전체의 '확인할 것(자료 받기, 승인)'."""
    r = price_level.analyze(company_id)
    checks = []
    if any("주가 미수집" in f for f in r["flags"]):
        summary = ["주가를 아직 받지 않음 → PER·PBR 계산 불가"]
        checks.append({"text": "주가 받기 (price --fetch, Yahoo Finance, 승인 필요)", "method": "자료 받기"})
    else:
        c = r.get("current") or {}
        x2 = lambda v: "-" if v is None else f"{v:.1f}배"  # noqa: E731
        summary = [f"현재({c.get('date')}): 주가 {c.get('price'):,.0f} · PER {x2(c.get('per'))} (기준 FY{c.get('basis_year')})"
                   + (f" · PBR {x2(c.get('pbr'))}" if c.get("pbr") is not None else "")] if c else []
        if r["rows"]:
            summary.append("회계연도 말 PER: " + ", ".join(f"{x['year']} {x2(x.get('per'))}" for x in r["rows"]))
            summary.append("회계연도 말 PBR: " + ", ".join(f"{x['year']} {x2(x.get('pbr'))}" for x in r["rows"]))
    summary.append("적정 가격 기준(내재가치·안전마진)은 13~14주차 뒤에 정함. 지금은 비교로 가늠 (경쟁사는 필요하면 그때)")
    items = [{"key": "expensive", "title": "지금 비싼가?",
              "detail": "PER·PBR을 자기 5년과, 필요하면 경쟁사와 비교. 장부 밖 가치는 가격의 단서 (4-①)"}]
    return {"summary": summary, "items": items, "checks": checks, "flags": r["flags"], "data": None, "sources": []}


def final_summary(book: dict) -> list[str]:
    """9 최종 판단: 한 장에 모아 본 것 = 단계마다 확인함·확정한 판단 + 금리·환율 (사는 시점 참고용, 받아 둔 것만)."""
    from . import macro, notebook
    r = notebook.current_round(book)
    out = []
    for no in range(1, 9):
        p = r["steps"].get(str(no))
        if p is None:
            continue
        if p["lane"] == "info":
            out.append(f"{no} {p['name']}: 단순 정보 · {p['summary'][0]}")
            continue
        for it in notebook.live_items(p):
            last = next((e for e in reversed(it["log"]) if e["kind"] == "confirm"), None)
            out.append(f"{no} {p['name']} · {it['title']}: {last['text'] if last else '(확정 없음)'}")
    rows = [m for m in macro.load() if m["points"]]
    if rows:
        out.append("금리·환율 (사는 시점 참고용): " + " / ".join(
            f"{m['name']} {m['last'][1]:,.2f} ({m['last'][0]}, 1년 전 {m['year_ago']:,.2f})" if m["year_ago"] is not None
            else f"{m['name']} {m['last'][1]:,.2f} ({m['last'][0]})" for m in rows))
    else:
        out.append("금리·환율: 받아 둔 자료 없음 (macro --fetch, 승인 필요)")
    return out


def holding_check(book: dict, company: dict) -> tuple[list[str], list[dict], list[dict]]:
    """보유 점검 재료 (외부 요청 없음): 지금 다시 계산해 산 회차와 비교 → 바뀐 단계마다 논의 항목,
    산 뒤(또는 지난 점검 뒤) '바로 확인할 일' 공시가 있으면 분류마다 항목. 받아 둔 자료가 오래됐으면 '확인할 것(자료 받기)'.
    반환: (요약, 논의 항목, 단계 전체 확인할 것)"""
    from datetime import date, datetime as dt
    from . import notebook, prices, service
    h = book.get("holding")
    if not h:
        raise notebook.NotebookError("보유 중인 회사가 아님 (샀다고 기록한 뒤에 점검)")
    r = notebook.current_round(book)
    base = book["rounds"][h["round"] - 1]
    checks_done = [p for k, p in r["steps"].items() if str(k).startswith("h")]
    since = max([h["since"]] + [p["computed_at"][:10] for p in checks_done])
    summary = [f"산 날짜 {h['since']} · 산 이유(그때의 최종 판단): {h['reason'] or '-'}",
               f"비교 기준: {h['round']}회차 분석 · 이번 점검은 {since} 이후의 변화를 본다"]
    px, _, _ = prices.load(company["company_id"])
    if not px.empty:
        a, b = prices.close_on(px, h["since"]), (px.index[-1], float(px.iloc[-1]))
        if a:
            summary.append(f"주가: 산 날 {a[1]:,.2f} → {b[0].date()} {b[1]:,.2f} ({b[1] / a[1] - 1:+.1%})")
    summary.append("파는 이유(매도-①~③): 회사가 바뀌었을 때(숫자가 너무 나빠짐, 영업CF가 최근 5년 규모에서 벗어남, 경쟁사와 비교, "
                   "정성적 이유) · 가격이 너무 올랐을 때(내재가치를 크게 넘거나 경쟁사보다 높음). 나눠서 판다. 더 좋은 기회만으로는 팔지 않는다")
    items, checks = [], []
    now = run(company["company_id"])
    for no, res in now.items():
        old = base["steps"].get(str(no))
        if old is None:
            continue
        old_keys = {it["key"] for it in notebook.live_items(old)}
        new_keys = {i["key"] for i in res["items"]}
        if res["summary"][:1] != old["summary"][:1] or old_keys != new_keys:
            gone, came = old_keys - new_keys, new_keys - old_keys
            items.append({"key": f"step{no}", "title": f"{no} {notebook.STEPS[no]} 바뀜",
                          "detail": f"그때: {old['summary'][0] if old['summary'] else '-'} → 지금: {res['summary'][0] if res['summary'] else '-'}"
                                    + (f" · 새 신호: {', '.join(i['title'] for i in res['items'] if i['key'] in came)}" if came else "")
                                    + (f" · 사라진 신호: {', '.join(it['title'] for it in notebook.live_items(old) if it['key'] in gone)}" if gone else "")})
    for k in IMMEDIATE:
        evs = events.find(company["company_id"], [k], since, include_subsidiary=False)
        if evs:
            items.append({"key": f"event-{k}", "title": f"바로 확인할 일: {k} 공시 {len(evs)}건",
                          "detail": " / ".join(f"{e['filed']} {e['title']}" for e in evs[:5])})
    c = service.get_company(company["company_id"]) or {}
    fetched = str(c.get("fetched_at") or "")[:10]
    if fetched and (date.today() - dt.fromisoformat(fetched).date()).days > 7:
        checks.append({"text": f"공시 목록·재무가 {fetched}에 받은 것: 새 사업보고서·수시공시를 보려면 다시 받기 (get, 요청 필요)",
                       "method": "자료 받기"})
    if not items:
        summary.append("산 회차와 비교해 바뀐 단계 없음 · 산 뒤 바로 확인할 일 공시 없음")
    return summary, items, checks


RUNNERS = {1: step1_promises, 2: step2_cashflow, 3: step3_allocation, 4: step4_quality, 5: step5_safety,
           6: step6_related, 7: step7_qualitative, 8: step8_price}


def run(company_id: str, steps=IMPLEMENTED) -> dict[int, dict]:
    return {no: RUNNERS[no](company_id) for no in steps}
