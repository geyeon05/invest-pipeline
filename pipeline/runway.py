"""버티는 힘 (사례 3 팩트 1): 연구개발비, 현금 + 단기 금융자산, 1년에 빠져나가는 현금, 몇 년 버티나.

정의 (사용자 결정 2026-11-19):
- 연구개발비 = 비용으로 처리한 연구개발비만 (연결). 한국은 inputs/case3/rnd_expensed.json (주석에서 옮겨 적은 값),
  미국은 SEC ResearchAndDevelopmentExpense.
- 현금 = 현금및현금성자산 + 분명한 단기 금융자산 (단기금융상품, 단기투자, 유동 당기손익-공정가치 금융자산).
  '기타금융자산·기타투자자산'(유동)은 넣지 않고 옆에 따로 표시 (사용자 결정 a).
- 버티는 기간 = 현금 ÷ 1년에 빠져나가는 현금. 빠져나가는 현금 = 영업CF − 유형자산 취득이 마이너스일 때 그 크기.
  플러스면 '남음(+금액)'으로 표시 (사용자 결정 b). 상태 ① 남음 ② 영업CF는 플러스지만 설비투자가 더 큼 ③ 영업CF부터 마이너스.
- Joby는 스팩 합병(2021) 이후만 (사용자 결정).
세부 규칙(줄 이름·코드, 유동 구간 판별)은 AI가 정한 값 → criteria/README.md
"""
import json
import re

from . import service, standard
from .config import ROOT

INPUT = ROOT / "inputs" / "case3" / "rnd_expensed.json"
START_YEAR = {"US:0001819848": 2021}     # Joby: 스팩 합병 이후만

KR_CASH = re.compile(r"^현금및현금성자산$")
KR_SHORT = re.compile(r"^(단기금융상품|단기투자(자산|증권)?|단기매매(금융자산|증권)|(유동)?당기손익.*금융자산)$")
KR_SHORT_CODE = re.compile(r"ShorttermDeposits|ShortTermDeposits|CurrentFinancialAssetsAtFairValueThroughProfitOrLoss")
KR_OTHER = re.compile(r"^기타(유동)?(금융자산|투자자산)$")
US_CASH = ("CashAndCashEquivalentsAtCarryingValue",)
US_SHORT = ("ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent")


def _kr_cash(company_id: str) -> dict:
    df = service.raw_financials(company_id)
    out = {}
    for year, d in df[df["sj_div"] == "BS"].groupby("bsns_year"):
        d = d.sort_values("ord")
        cur, row = False, {"cash": 0.0, "short": 0.0, "other": 0.0, "lines": [], "finance_arm": False}
        for r in d.itertuples():
            n = (r.account_nm or "").replace(" ", "")
            if n.startswith("유동자산"):
                cur = True
                continue
            if n.startswith("비유동자산"):
                break
            if "금융업채권" in n:
                row["finance_arm"] = True
            if not cur or r.thstrm_amount != r.thstrm_amount or r.thstrm_amount is None:
                continue
            v = float(r.thstrm_amount)
            if KR_CASH.match(n):
                row["cash"] += v
                row["lines"].append(r.account_nm)
            elif KR_SHORT.match(n) or KR_SHORT_CODE.search(r.account_id or ""):
                row["short"] += v
                row["lines"].append(r.account_nm)
            elif KR_OTHER.match(n):
                row["other"] += v
        out[int(year)] = row
    return out


def _us_values(company_id: str, tags: tuple, flow: bool) -> dict:
    df = service.raw_financials(company_id)
    df = df[df["form"].isin(["10-K", "10-K/A", "20-F", "20-F/A"]) & df["tag"].isin(tags)]
    out = {}
    for r in df.sort_values("filed").itertuples():
        if flow and (not r.start or (int(r.end[:4]) - int(r.start[:4])) * 12 + int(r.end[5:7]) - int(r.start[5:7]) < 11):
            continue
        y = int(r.end[:4])
        if r.end[5:] != "12-31":
            continue
        out.setdefault(y, {})[r.tag] = float(r.val)      # 나중 제출이 덮어씀 (정정 반영)
    return out


def _us_cash(company_id: str) -> dict:
    vals = _us_values(company_id, US_CASH + US_SHORT, flow=False)
    out = {}
    for y, t in vals.items():
        cash = sum(t.get(k, 0) for k in US_CASH)
        short = next((t[k] for k in US_SHORT if k in t), 0.0)
        out[y] = {"cash": cash, "short": short, "other": 0.0,
                  "lines": [k for k in US_CASH + US_SHORT if k in t], "finance_arm": False}
    return out


def rnd(company_id: str) -> dict:
    if company_id.startswith("US:"):
        v = _us_values(company_id, ("ResearchAndDevelopmentExpense",), flow=True)
        return {y: {"value": t["ResearchAndDevelopmentExpense"], "src": "SEC 10-K ResearchAndDevelopmentExpense"}
                for y, t in v.items()}
    data = json.loads(INPUT.read_text(encoding="utf-8")).get(company_id, {}) if INPUT.exists() else {}
    out = {}
    for y, r in data.get("years", {}).items():
        out[int(y)] = {"value": None if r.get("value") is None else r["value"] * 1e6,
                       "src": f"{r['rcept_no']} {r['note']}" if r.get("value") is not None else "",
                       "reason": r.get("reason", "")}
    return out


def table(company_id: str, years: int = 5) -> dict:
    std = standard.standardize(company_id)
    w = std.pivot_table(index="item", columns="year", values="value", aggfunc="first")
    cur = std["currency"].dropna().iloc[0] if not std.empty else ""
    cash = _kr_cash(company_id) if company_id.startswith("KR:") else _us_cash(company_id)
    rd = rnd(company_id)
    ys = sorted(int(y) for y in w.columns if not w[y].isna().all())
    start = START_YEAR.get(company_id)
    if start:
        ys = [y for y in ys if y >= start]
    ys = ys[-years:]
    veh = vehicle(company_id)
    rows = []
    for y in ys:
        ocf = w.at["operating_cf", y] if "operating_cf" in w.index and y in w.columns else None
        capex = w.at["capex_ppe", y] if "capex_ppe" in w.index and y in w.columns else None
        c = cash.get(y, {})
        if veh:                      # 금융 자회사를 뺀 차량 부문 (사용자 결정)
            v = veh.get(y, {})
            ocf, capex = v.get("ocf"), v.get("capex_net")
            c = {"cash": v.get("cash"), "short": 0.0 if v.get("cash") is not None else None,
                 "other": v.get("current_fin"), "finance_arm": False,
                 "lines": ["차량 부문 현금및현금성자산 (유동금융자산은 기타금융 칸)"]} if v.get("cash") is not None else {}
        total = (c.get("cash") or 0) + (c.get("short") or 0) if c else None
        fcf = None if ocf is None or ocf != ocf or capex is None or capex != capex else ocf - capex
        burn = -fcf if fcf is not None and fcf < 0 else None
        rows.append({"year": y, "rnd": rd.get(y, {}).get("value"), "rnd_reason": rd.get(y, {}).get("reason", ""),
                     "cash": c.get("cash"), "short": c.get("short"), "total": total, "other": c.get("other"),
                     "ocf": ocf, "capex": capex, "burn": burn,
                     "runway": (total / burn) if burn and total is not None else None,
                     "finance_arm": c.get("finance_arm", False), "lines": c.get("lines", [])})
    return {"currency": cur, "rows": rows, "rnd_src": {y: v.get("src", "") for y, v in rd.items()},
            "vehicle": bool(veh)}


VEHICLE = ROOT / "inputs" / "case3" / "hyundai_vehicle.json"


def vehicle(company_id: str) -> dict:
    """현대차 차량 부문 숫자 {연도: {...}} (원 단위). 해당 회사가 아니면 {}."""
    if not VEHICLE.exists():
        return {}
    d = json.loads(VEHICLE.read_text(encoding="utf-8"))
    if d.get("company_id") != company_id:
        return {}
    return {int(y): {k: (v * 1e6 if isinstance(v, (int, float)) else v) for k, v in r.items()}
            for y, r in d["years"].items()}


# ---------------- 빌릴 능력 · 주식 조달 (사용자 결정 2026-11-19: A·B·C(총 한도만)·E) ----------------
CAPACITY = ROOT / "inputs" / "case3" / "funding_capacity.json"
KR_FIN_CF = re.compile(r"^재무활동(으로인한|으로부터의|에서창출된)?(순)?현금(흐름|유입|유출)")
KR_EQUITY = re.compile(r"^(유상증자|종속기업(의)?(유상)?증자|주식(의)?발행|신주(의)?발행)$")
KR_HYBRID = re.compile(r"^신종자본증권(의)?발행$")
US_EQUITY = ("ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOfPrivatePlacement",
             "ProceedsFromIssuanceOrSaleOfEquity", "ProceedsFromStockOptionsExercised", "ProceedsFromWarrantExercises",
             "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans")


def capacity_facts(company_id: str) -> dict:
    return json.loads(CAPACITY.read_text(encoding="utf-8")).get(company_id, {}) if CAPACITY.exists() else {}


def financing(company_id: str) -> dict:
    """연도별 {net: 재무활동 순현금흐름, equity: 주식 발행 유입(잡히는 것만), hybrid: 신종자본증권 발행}"""
    out = {}
    if company_id.startswith("US:"):
        v = _us_values(company_id, ("NetCashProvidedByUsedInFinancingActivities",) + US_EQUITY, flow=True)
        for y, t in v.items():
            out[y] = {"net": t.get("NetCashProvidedByUsedInFinancingActivities"),
                      "equity": sum(t.get(k, 0) for k in US_EQUITY), "hybrid": 0.0}
        return out
    df = service.raw_financials(company_id)
    for y, d in df[df["sj_div"] == "CF"].groupby("bsns_year"):
        row = {"net": None, "equity": 0.0, "hybrid": 0.0}
        for r in d.itertuples():
            n = (r.account_nm or "").replace(" ", "")
            v = r.thstrm_amount
            if v is None or v != v:
                continue
            if row["net"] is None and (KR_FIN_CF.match(n) or r.account_id == "ifrs-full_CashFlowsFromUsedInFinancingActivities"):
                row["net"] = float(v)
            elif KR_EQUITY.match(n):
                row["equity"] += abs(float(v))
            elif KR_HYBRID.match(n):
                row["hybrid"] += abs(float(v))
        out[int(y)] = row
    return out


def borrowing(company_id: str, years: list[int]) -> list[dict]:
    """A 부채비율·순차입금, B 이자보상비율 (safety 도구 값 그대로), E 재무활동."""
    from . import safety
    s = {r["year"]: r for r in safety.analyze(company_id)["rows"]}
    std = standard.standardize(company_id)
    debt = std[std["item"] == "interest_bearing_debt"].set_index("year")["value"].to_dict()
    cash = _kr_cash(company_id) if company_id.startswith("KR:") else _us_cash(company_id)
    fin = financing(company_id)
    veh = vehicle(company_id)
    ie_all = std[std["item"] == "interest_expense"].set_index("year")["value"].to_dict()
    rows = []
    for y in years:
        c = cash.get(y, {})
        total = (c.get("cash") or 0) + (c.get("short") or 0) if c else None
        d = debt.get(y)
        dr_, icr_ = s.get(y, {}).get("debt_ratio"), s.get(y, {}).get("icr")
        if veh:                      # 차량 부문 (사용자 결정): 부채비율·이자보상·차입금·순차입금
            v = veh.get(y, {})
            d = v.get("borrowings")
            total = v.get("cash")
            dr_ = v["liabilities"] / v["equity"] if v.get("liabilities") and v.get("equity") else None
            ie = ie_all.get(y)
            icr_ = v["operating_income"] / ie if v.get("operating_income") is not None and ie else None
        rows.append({"year": y, "debt_ratio": dr_, "icr": icr_,
                     "debt": d, "net_debt": (d - total) if d is not None and d == d and total is not None else None,
                     "fin_net": fin.get(y, {}).get("net"), "equity": fin.get(y, {}).get("equity"),
                     "hybrid": fin.get(y, {}).get("hybrid")})
    return rows


# ---------------- 빌린 돈까지 쓸 때 버티는 해 (사용자 결정 2026-11-19: ①, ④) ----------------
# ① 부채비율 상한 = 그 회사의 최근 5년(그 해 포함) 중 가장 높았던 부채비율. 더 빌릴 수 있는 돈 = 상한 × 자본 − 부채
# ④ 이자보상 하한 1배 (= safety의 '분명한 위험' 경계). 더 빌릴 수 있는 돈 = (영업이익 − 이자비용) ÷ 이자율
#    이자율 = 회사 이자율(이자비용 ÷ 평균 이자부 부채, spread 도구와 같음). 영업이익 ≤ 0 이면 0.
#    현대차만 시장 금리(ECOS 회사채 3년 AA- 연평균): 금융 자회사 때문에 회사 이자율이 왜곡됨 (사용자 결정)
MARKET_RATE_FOR: set = set()   # 현대차는 이후 '차량 부문으로 따로 보기'로 바뀌어 차량 부문 이자율을 씀 (사용자 결정)
MARKET_RATE_FILE = ROOT / "data" / "raw" / "macro" / "721Y001_A_7020000.json"
ICR_FLOOR = 1.0
DR_WINDOW = 5


def _market_rate() -> dict:
    if not MARKET_RATE_FILE.exists():
        return {}
    rows = json.loads(MARKET_RATE_FILE.read_text(encoding="utf-8"))["StatisticSearch"]["row"]
    return {int(r["TIME"]): float(r["DATA_VALUE"]) / 100 for r in rows}


def with_borrowing(company_id: str, rows: list[dict]) -> list[dict]:
    from . import spread
    std = standard.standardize(company_id)
    w = std.pivot_table(index="item", columns="year", values="value", aggfunc="first")

    def g(k, y):
        v = w.at[k, y] if k in w.index and y in w.columns else None
        return None if v is None or v != v else float(v)
    ys = sorted(int(y) for y in w.columns)
    start = START_YEAR.get(company_id, ys[0] if ys else 0)
    veh = vehicle(company_id)
    if veh:   # 차량 부문 값으로 바꿔 끼움 (부채·자본·영업이익). 이자비용은 연결 주석 값(금융 부문 이자는 매출원가에 있어 빠짐)
        for y, v in veh.items():
            for k, vk in (("total_liabilities", "liabilities"), ("equity_total", "equity"), ("operating_income", "operating_income")):
                if v.get(vk) is not None:
                    if y not in w.columns:
                        w[y] = float("nan")
                    w.loc[k, y] = v[vk]
        ys = sorted(veh)            # 부채비율 창도 차량 부문 연도만 (연결 연도와 섞지 않음)
    dr = {y: g("total_liabilities", y) / g("equity_total", y) for y in ys
          if y >= start and g("total_liabilities", y) is not None and g("equity_total", y)}
    sp = spread.by_year(std, [r["year"] for r in rows])
    mkt = _market_rate() if company_id in MARKET_RATE_FOR else {}
    out = []
    for r in rows:
        y = r["year"]
        L, E, oi, ie = g("total_liabilities", y), g("equity_total", y), g("operating_income", y), g("interest_expense", y)
        past = [dr[k] for k in range(y - DR_WINDOW + 1, y + 1) if k in dr]
        cap = max(past) if past else None
        room1 = max(0.0, cap * E - L) if cap is not None and E is not None and L is not None else None
        if company_id in MARKET_RATE_FOR:
            rate, rate_src = mkt.get(y), "시장(회사채 AA-)"
        elif veh:
            b0, b1 = (veh.get(y - 1) or {}).get("borrowings"), (veh.get(y) or {}).get("borrowings")
            avg = (b0 + b1) / 2 if b0 and b1 else b1
            rate, rate_src = ((ie / avg) if ie and avg else None), "차량 부문(이자비용 ÷ 평균 차입금)"
        else:
            rate, rate_src = (sp.get(y) or {}).get("rate"), "회사"
        if oi is None:
            room4, why4 = None, "영업이익 없음"
        elif oi <= 0:
            room4, why4 = 0.0, "영업손실"
        elif not rate or ie is None:
            room4, why4 = None, "이자율·이자비용 없음"
        else:
            room4, why4 = max(0.0, (oi / ICR_FLOOR - ie) / rate), ""
        total, burn = r.get("total"), r.get("burn")

        def yrs(room):
            return (total + room) / burn if burn and total is not None and room is not None else None
        out.append({**r, "dr_cap": cap, "room1": room1, "runway1": yrs(room1),
                     "room4": room4, "runway4": yrs(room4), "why4": why4, "rate": rate, "rate_src": rate_src})
    return out


# ---------------- 슈퍼널 (현대차 공동기업 44.44%, 사용자 결정 2026-11-19: 표에 따로 넣음) ----------------
SUPERNAL = ROOT / "inputs" / "case3" / "supernal.json"


def supernal(parent_id: str) -> dict:
    if not SUPERNAL.exists():
        return {}
    d = json.loads(SUPERNAL.read_text(encoding="utf-8"))
    if d.get("parent") != parent_id:
        return {}
    rows = {}
    for y, r in d["years"].items():
        ca, na = r["current_assets"], r["noncurrent_assets"]
        cl, nl = r["current_liabilities"], r["noncurrent_liabilities"]
        rows[int(y)] = {"current_assets": ca * 1e6, "assets": (ca + na) * 1e6, "liabilities": (cl + nl) * 1e6,
                        "equity": (ca + na - cl - nl) * 1e6, "net_income": r["net_income"] * 1e6,
                        "revenue": r["revenue"] * 1e6, "parent_share_loss": r["net_income"] * d["stake"] * 1e6,
                        "book_value": None if r.get("book_value") is None else r["book_value"] * 1e6}
    return {"stake": d["stake"], "rows": rows}
