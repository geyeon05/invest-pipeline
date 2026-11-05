"""표준 재무항목 계층:  원본(raw)  →  표준(standard)  →  (나중에) 지표(ratios)

국가·회계기준·회사마다 다른 계정과목을 '정의가 같은' 표준 항목 하나로 매핑한다.

원칙
1. 값은 바꾸지 않는다. 허용하는 예외는 두 가지뿐이고, 결과에 반드시 표시한다.
   - 부호 정규화: 지출 항목(설비투자, 배당금 지급 등)은 회사마다 +/− 표기가 달라 양수로 통일 (method 에 '+abs')
   - 항등식 파생: 원본에 없을 때만, 회계 항등식으로 계산 (method = 'derived')
2. 모든 값에 출처(원본 계정명/태그, 공시번호)를 붙인다.
3. 매핑 후 검증(재무상태표 항등식 등)을 돌려, 잘못 매핑됐을 가능성을 드러낸다.

매핑 규칙 (국내 DART)
- 회사가 붙인 '계정명'이 명확하면 이름을 우선한다. 계정코드는 회사가 직접 태깅해서 틀린 경우가 있다.
  (실제 사례: 카카오는 2017~2022년 '영업수익'(=매출)에 매출총이익 코드를 붙였다)
- 이름으로 판단할 수 없을 때 표준계정코드를 쓴다.
매핑 규칙 (해외 SEC)
- XBRL 태그 우선순위 목록에서, 그 연도에 값이 있는 첫 태그를 쓴다.
"""
import re
from dataclasses import dataclass

import pandas as pd

from . import service


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    kind: str                      # flow(기간) / stock(시점) / per_share
    sj: tuple[str, ...]            # DART 재무제표 구분
    kr_codes: tuple[str, ...]
    kr_names: str                  # 공백 제거한 계정명에 대한 정규식
    us_tags: tuple[str, ...]       # "taxonomy:tag" 우선순위
    kr_exclude: str = r"(?!x)x"    # 제외 패턴 (기본: 아무것도 제외 안 함)
    sign: str = "as_is"            # as_is / abs
    note: str = ""


PL, BS, CF = ("IS", "CIS"), ("BS",), ("CF",)

ITEMS: list[Item] = [
    Item("revenue", "매출액", "flow", PL, ("ifrs-full_Revenue",),
         r"^(매출액|매출|영업수익|수익|수익\(매출액\)|매출액\(영업수익\)|영업수익\(매출액\))$",
         ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
          "us-gaap:SalesRevenueNet", "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
          "ifrs-full:Revenue"),
         note="국내 플랫폼·서비스 기업은 '영업수익'으로 표시. 금융업은 매출 개념이 달라 비교 부적합."),
    Item("cost_of_sales", "매출원가", "flow", PL, ("ifrs-full_CostOfSales",), r"^매출원가$",
         ("us-gaap:CostOfRevenue", "us-gaap:CostOfGoodsAndServicesSold", "us-gaap:CostOfGoodsSold",
          "ifrs-full:CostOfSales"),
         sign="abs", note="비용을 성격별로 표시하는 기업(플랫폼 등)은 매출원가가 없다."),
    Item("gross_profit", "매출총이익", "flow", PL, ("ifrs-full_GrossProfit",), r"^매출총(이익|손익)(\(손실\))?$",
         ("us-gaap:GrossProfit", "ifrs-full:GrossProfit")),
    Item("operating_income", "영업이익", "flow", PL, ("dart_OperatingIncomeLoss",),
         r"^영업(이익|손익|손실)(\(손실\))?$",
         ("us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities"),
         note="IFRS는 영업이익을 정의하지 않는다. K-IFRS는 표시를 의무화했고, US GAAP은 관행적으로 표시. "
              "기타영업수익·비용 포함 범위가 회사마다 다를 수 있다."),
    Item("pretax_income", "법인세차감전순이익", "flow", PL, ("ifrs-full_ProfitLossBeforeTax",),
         r"^(연결)?법인세(비용)?차감전(계속영업)?(순)?(이익|손익|손실)",
         ("us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
          "ifrs-full:ProfitLossBeforeTax")),
    Item("income_tax", "법인세비용", "flow", PL, ("ifrs-full_IncomeTaxExpenseContinuingOperations",),
         r"^(계속영업)?법인세(비용|수익|비용\(수익\)|수익\(비용\)|비용\(이익\))?$",
         ("us-gaap:IncomeTaxExpenseBenefit", "ifrs-full:IncomeTaxExpenseContinuingOperations")),
    Item("net_income", "당기순이익(연결)", "flow", PL, ("ifrs-full_ProfitLoss",),
         r"^(연결)?(당기|분기)?순(이익|손익|손실)(\(손실\))?$",
         ("us-gaap:ProfitLoss", "us-gaap:NetIncomeLoss", "ifrs-full:ProfitLoss"),
         kr_exclude=r"계속|중단|귀속|지배|포괄",
         note="비지배지분 몫까지 포함한 연결 순이익. ROE·EPS 에는 '지배주주순이익'을 쓴다."),
    Item("net_income_parent", "지배주주순이익", "flow", PL, ("ifrs-full_ProfitLossAttributableToOwnersOfParent",),
         r"(지배기업|지배회사|지배주주).*(소유주|지분|귀속|순이익)",
         ("us-gaap:NetIncomeLoss", "ifrs-full:ProfitLossAttributableToOwnersOfParent"),
         kr_exclude=r"비지배|포괄"),
    Item("eps_basic", "기본주당이익(보통주)", "per_share", PL, ("ifrs-full_BasicEarningsLossPerShare",),
         r"^(보통주)?기본주당(순)?(이익|손익|손실)",
         ("us-gaap:EarningsPerShareBasic", "ifrs-full:BasicEarningsLossPerShare"),
         kr_exclude=r"우선주|계속|중단|희석",
         note="주식분할 이전 연도의 EPS는 분할이 반영되지 않은 원본값일 수 있다."),
    Item("total_assets", "자산총계", "stock", BS, ("ifrs-full_Assets",), r"^자산총계$",
         ("us-gaap:Assets", "ifrs-full:Assets")),
    Item("current_assets", "유동자산", "stock", BS, ("ifrs-full_CurrentAssets",), r"^유동자산$",
         ("us-gaap:AssetsCurrent", "ifrs-full:CurrentAssets")),
    Item("cash", "현금및현금성자산", "stock", BS, ("ifrs-full_CashAndCashEquivalents",), r"^현금및현금성자산$",
         ("us-gaap:CashAndCashEquivalentsAtCarryingValue", "ifrs-full:CashAndCashEquivalents")),
    Item("total_liabilities", "부채총계", "stock", BS, ("ifrs-full_Liabilities",), r"^부채총계$",
         ("us-gaap:Liabilities", "ifrs-full:Liabilities"),
         note="미국 기업 일부는 부채총계를 따로 보고하지 않는다 → 자산총계 − 자본총계로 파생(derived)."),
    Item("current_liabilities", "유동부채", "stock", BS, ("ifrs-full_CurrentLiabilities",), r"^유동부채$",
         ("us-gaap:LiabilitiesCurrent", "ifrs-full:CurrentLiabilities")),
    Item("equity_total", "자본총계(비지배 포함)", "stock", BS, ("ifrs-full_Equity",), r"^자본총계$",
         ("us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
          "us-gaap:StockholdersEquity", "ifrs-full:Equity")),
    Item("equity_parent", "지배주주지분", "stock", BS, ("ifrs-full_EquityAttributableToOwnersOfParent",),
         r"(지배기업|지배회사|지배주주).*(소유주|지분)",
         ("us-gaap:StockholdersEquity", "ifrs-full:EquityAttributableToOwnersOfParent"),
         kr_exclude=r"비지배"),
    Item("operating_cf", "영업활동현금흐름", "flow", CF, ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
         r"^영업활동(으로인한|으로부터의|에서창출된|으로부터)?(순)?현금(흐름|유입|유출)",
         ("us-gaap:NetCashProvidedByUsedInOperatingActivities",
          "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
          "ifrs-full:CashFlowsFromUsedInOperatingActivities"),
         kr_exclude=r"창출된현금$",
         note="IFRS는 이자·배당의 수취·지급을 영업/투자/재무 중 선택해 분류할 수 있고, US GAAP은 이자 지급을 "
              "영업활동으로 고정한다. 또 IFRS16 리스는 원금 상환이 재무활동이라 IFRS 기업의 영업현금흐름이 상대적으로 크게 나온다."),
    Item("investing_cf", "투자활동현금흐름", "flow", CF, ("ifrs-full_CashFlowsFromUsedInInvestingActivities",),
         r"^투자활동(으로인한|으로부터의|으로부터)?(순)?현금(흐름|유입|유출)",
         ("us-gaap:NetCashProvidedByUsedInInvestingActivities",
          "us-gaap:NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
          "ifrs-full:CashFlowsFromUsedInInvestingActivities")),
    Item("financing_cf", "재무활동현금흐름", "flow", CF, ("ifrs-full_CashFlowsFromUsedInFinancingActivities",),
         r"^재무활동(으로인한|으로부터의|으로부터)?(순)?현금(흐름|유입|유출)",
         ("us-gaap:NetCashProvidedByUsedInFinancingActivities",
          "us-gaap:NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
          "ifrs-full:CashFlowsFromUsedInFinancingActivities")),
    Item("capex", "유형자산 취득(설비투자)", "flow", CF,
         ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
          "ifrs-full_PurchaseOfPropertyPlantAndEquipment"),
         r"^유형자산의?취득$",
         ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:PaymentsToAcquireProductiveAssets",
          "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
         sign="abs", note="지출액을 양수로 통일. 무형자산 취득은 포함하지 않는다."),
    Item("dividends_paid", "배당금 지급", "flow", CF, ("ifrs-full_DividendsPaidClassifiedAsFinancingActivities",
                                                     "ifrs-full_DividendsPaid"),
         r"^(현금)?배당금(의)?지급(액)?$",
         ("us-gaap:PaymentsOfDividends", "us-gaap:PaymentsOfDividendsCommonStock",
          "ifrs-full:DividendsPaidClassifiedAsFinancingActivities"),
         sign="abs", note="지출액을 양수로 통일. 비지배주주 배당 포함 여부는 회사마다 다를 수 있다."),
]
ITEM_BY_KEY = {i.key: i for i in ITEMS}

# 회계기준 차이 중 숫자 매핑으로 해결되지 않는 것들 (해석할 때 반드시 고려)
STANDARD_GAPS = [
    ("리스 (IFRS16 vs ASC842)", "IFRS: 모든 리스를 자산·부채로 인식하고 비용은 감가상각+이자로 나뉨 → 영업이익·EBITDA·영업현금흐름이 "
     "US GAAP 운용리스 기업보다 크게 나온다. 부채비율도 IFRS 쪽이 높게 나온다."),
    ("현금흐름 분류", "IFRS는 이자·배당의 수취·지급을 영업/투자/재무 중 선택 가능. US GAAP은 이자지급=영업, 배당지급=재무로 고정. "
     "FCF 비교 시 각 회사의 분류를 확인해야 한다."),
    ("개발비 자산화", "IFRS는 요건 충족 시 개발비를 무형자산으로 자산화할 수 있고, US GAAP은 대부분 비용 처리. "
     "IFRS 기업의 영업이익이 높게, 자산이 크게 나올 수 있다 (예: 바이오·게임·자동차)."),
    ("영업이익 정의", "IFRS에는 영업이익 정의가 없다. K-IFRS는 '매출총이익 − 판관비' 방식 표시를 요구하지만 "
     "기타영업수익·비용 처리는 회사마다 다를 수 있다."),
    ("재고자산 LIFO", "US GAAP만 후입선출법(LIFO) 허용. 물가 상승기에 LIFO 기업은 매출원가가 크고 재고자산이 작게 나온다."),
    ("회계연도", "국내는 대부분 12월 결산, 미국은 회사마다 다름(Apple 9월, NVIDIA 1월). 표준 연도는 "
     "'기간 종료월이 6월 이후면 그 해, 1~5월이면 전년'으로 맞춘다 (Compustat 방식). 기간 종료일을 함께 표시한다."),
    ("통화", "국내 KRW, 미국 USD, 해외 20-F 기업은 현지통화(TSMC는 TWD). 비율은 그대로 비교 가능하지만 금액 비교는 환산이 필요하다."),
    ("금융업", "은행·보험·증권은 매출·매출원가·유동자산 개념이 없어 일반 기업 지표로 비교하면 안 된다. "
     "또 DART API는 금융업 재무제표를 2023년 이후만 제공한다."),
]


def _norm_name(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    return re.sub(r"^([IVXⅠ-Ⅹ]+|\d+|[가-하])[.)]", "", s)  # 'Ⅰ.매출액', '1.매출액', '가.매출액'


def _norm_code(s: str) -> str:
    return re.sub(r"^ifrs_", "ifrs-full_", s or "")


def standard_year(period_end: pd.Series) -> pd.Series:
    """회계연도 라벨 통일: 종료월 6~12월 → 그 해, 1~5월 → 전년 (예: NVIDIA 2026-01 종료 → 2025)."""
    d = pd.to_datetime(period_end)
    return d.dt.year.where(d.dt.month >= 6, d.dt.year - 1)


# ---------------- 국내 ----------------
def _kr(company_id: str) -> pd.DataFrame:
    raw = service.raw_financials(company_id)
    if raw.empty:
        return pd.DataFrame()
    raw = raw.assign(nm=raw["account_nm"].map(_norm_name), code=raw["account_id"].map(_norm_code))

    def by_name(row) -> str | None:
        for it in ITEMS:
            if row.sj_div in it.sj and re.search(it.kr_names, row.nm) and not re.search(it.kr_exclude, row.nm):
                return it.key
        return None

    code_map = {c: it.key for it in ITEMS for c in it.kr_codes}
    raw["by_name"] = raw.apply(by_name, axis=1)
    # 계정코드가 '다른 개념'임을 분명히 말하면 이름 매칭을 버린다.
    # (실제 사례: 네이버 2021년 '지배기업 소유주지분'은 순이익이 아니라 총포괄이익 귀속분이었다)
    veto = raw["code"].str.contains(r"Comprehensive|Discontinued|ContinuingOperations|Noncontrolling", na=False) \
        & ~raw["code"].isin(code_map)
    raw.loc[veto, "by_name"] = None
    raw["by_code"] = [code_map.get(c) if sj in ITEM_BY_KEY.get(code_map.get(c, ""), ITEMS[0]).sj else None
                      for c, sj in zip(raw["code"], raw["sj_div"])]
    # 이름이 다른 항목을 가리키면 코드는 무시 (코드 오태깅 방지)
    raw["item"] = raw["by_name"].fillna(raw["by_code"].where(raw["by_name"].isna()))
    raw = raw[raw["item"].notna()].copy()
    raw["method"] = ["name+code" if n == c else ("name" if n else "code")
                     for n, c in zip(raw["by_name"], raw["by_code"])]
    raw["rank"] = raw["method"].map({"name+code": 0, "name": 1, "code": 2})
    raw["sj_rank"] = (raw["sj_div"] != "IS").astype(int)  # 손익계산서를 포괄손익계산서보다 우선
    raw = raw.sort_values(["rank", "sj_rank", "ord"]).drop_duplicates(["item", "bsns_year"])

    company = service.get_company(company_id) or {}
    acc_mt = str((company.get("profile") or {}).get("acc_mt") or "12").zfill(2)  # 결산월
    period_end = pd.to_datetime(raw["bsns_year"].astype(str) + "-" + acc_mt + "-01") + pd.offsets.MonthEnd(0)

    return pd.DataFrame({
        "item": raw["item"], "year": raw["bsns_year"].astype(int),
        "period_end": period_end.dt.strftime("%Y-%m-%d"),
        "value": raw["thstrm_amount"], "currency": raw["currency"].fillna("KRW"),
        "source": raw["account_nm"] + "  [" + raw["account_id"].fillna("") + "]  (" + raw["sj_nm"] + ", " + raw["fs_div"] + ")",
        "filing": raw["rcept_no"], "method": raw["method"],
    })


# ---------------- 해외 ----------------
def _us(company_id: str) -> pd.DataFrame:
    df = service.raw_financials(company_id)
    if df.empty:
        return pd.DataFrame()
    df = df[df["form"].isin(service.ANNUAL_FORMS) & (df["fp"] == "FY")].copy()
    start, end = pd.to_datetime(df["start"], errors="coerce"), pd.to_datetime(df["end"], errors="coerce")
    dur = (end - start).dt.days
    df = df[dur.isna() | dur.between(330, 400)].copy()
    df["year"] = standard_year(df["end"])
    df["full_tag"] = df["taxonomy"] + ":" + df["tag"]
    # 각 연도 '최초 연차보고서' 값 사용 (as reported). 국내(각 연도 사업보고서 당기금액)와 같은 원칙이고,
    # 서로 다른 시점의 정정·재작성 값이 섞여 재무상태표 항등식이 깨지는 것을 막는다.
    df = df.sort_values("filed").drop_duplicates(["full_tag", "unit", "year"], keep="first")

    # 보고통화 고정: 20-F 기업은 현지통화와 USD 편의환산을 함께 보고하는 경우가 있다 (예: TSMC TWD+USD)
    money = df[df["full_tag"].isin(["us-gaap:Assets", "ifrs-full:Assets"])]
    currency = money["unit"].mode().iat[0] if not money.empty else "USD"

    # 연도별 기준 공시 = 그 회계연도를 처음 보고한 연차보고서. 태그 우선순위는 이 공시 '안에서' 적용한다.
    # (태그별로 따로 고르면, 예컨대 Microsoft 2016년 매출은 2018년 재작성 공시에서, 매출원가는 2016년 원 공시에서
    #  가져오는 식으로 시점이 섞인다)
    first = df.sort_values("filed").groupby("year").head(1)
    anchor = dict(zip(first["year"], first["accn"]))

    out = []
    for it in ITEMS:
        cands = df[df["full_tag"].isin(it.us_tags)].copy()
        if cands.empty:
            continue
        cands = cands[cands["unit"] == (f"{currency}/shares" if it.kind == "per_share" else currency)]
        cands["prio"] = cands["full_tag"].map({t: i for i, t in enumerate(it.us_tags)})
        cands["off_anchor"] = cands["accn"] != cands["year"].map(anchor)
        cands = cands.sort_values(["off_anchor", "prio", "filed"]).drop_duplicates("year")
        out.append(pd.DataFrame({
            "item": it.key, "year": cands["year"].astype(int), "period_end": cands["end"],
            "value": cands["val"], "currency": cands["unit"].str.split("/").str[0],
            "source": cands["full_tag"] + "  (" + cands["label"] + ")",
            "filing": cands["accn"], "method": "tag",
        }))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ---------------- 공통: 부호 · 파생 · 검증 ----------------
def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    for it in ITEMS:
        if it.sign == "abs":
            m = (df["item"] == it.key) & df["value"].notna()
            df.loc[m & (df["value"] < 0), "method"] += "+abs"
            df.loc[m, "value"] = df.loc[m, "value"].abs()

    def derive(target: str, a: str, b: str, label: str):
        nonlocal df
        w = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
        if a not in w or b not in w:
            return
        have = set(df.loc[df["item"] == target, "year"])
        calc = (w[a] - w[b]).dropna()
        calc = calc[~calc.index.isin(have)]
        if calc.empty:
            return
        meta = df[df["item"] == a].set_index("year")
        df = pd.concat([df, pd.DataFrame({
            "item": target, "year": calc.index, "period_end": meta.loc[calc.index, "period_end"].values,
            "value": calc.values, "currency": meta.loc[calc.index, "currency"].values,
            "source": label, "filing": meta.loc[calc.index, "filing"].values, "method": "derived"})],
            ignore_index=True)

    derive("total_liabilities", "total_assets", "equity_total", "파생: 자산총계 − 자본총계")
    derive("gross_profit", "revenue", "cost_of_sales", "파생: 매출액 − 매출원가")
    order = {it.key: i for i, it in enumerate(ITEMS)}
    return df.sort_values(["year"]).sort_values("item", key=lambda s: s.map(order), kind="stable")


def checks(df: pd.DataFrame) -> pd.DataFrame:
    """매핑 결과 검증. 실패 = 원본 공시가 이상하거나, 매핑이 잘못됐을 가능성."""
    w = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    g = lambda k: w[k] if k in w else pd.Series(float("nan"), index=w.index)  # noqa: E731
    rows = []

    def add(name, ok, detail):
        for y in w.index:
            if pd.notna(ok.get(y)):
                rows.append({"year": y, "check": name, "ok": bool(ok[y]), "detail": detail.get(y, "")})

    a, l, e = g("total_assets"), g("total_liabilities"), g("equity_total")
    gap = (a - (l + e)) / a
    add("자산 = 부채 + 자본", gap.abs().lt(0.005).where(gap.notna()), gap.map(lambda v: f"차이 {v:.2%}"))
    add("매출 ≥ 매출총이익", (g("revenue") >= g("gross_profit")).where(g("revenue").notna() & g("gross_profit").notna()), {})
    gp = (g("revenue") - g("cost_of_sales") - g("gross_profit")) / g("revenue")
    add("매출 − 매출원가 = 매출총이익", gp.abs().lt(0.01).where(gp.notna()), gp.map(lambda v: f"차이 {v:.2%}"))
    add("유동자산 ≤ 자산총계", (g("current_assets") <= a).where(g("current_assets").notna() & a.notna()), {})
    add("현금 ≤ 유동자산", (g("cash") <= g("current_assets")).where(g("cash").notna() & g("current_assets").notna()), {})
    s1, s2 = g("eps_basic"), g("net_income_parent")
    add("EPS와 지배순이익 부호 일치", ((s1 >= 0) == (s2 >= 0)).where(s1.notna() & s2.notna()), {})
    return pd.DataFrame(rows, columns=["year", "check", "ok", "detail"])


def is_financial(company: dict) -> bool:
    p = company.get("profile") or {}
    if company["market"] == "KR":
        return str(p.get("induty_code", "")).startswith(("64", "65", "66"))
    try:
        return 6000 <= int(p.get("sic") or 0) <= 6799
    except ValueError:
        return False


def standardize(company_id: str) -> pd.DataFrame:
    """표준 항목 (long 형식): item, year, period_end, value, currency, source, filing, method"""
    df = _kr(company_id) if company_id.startswith("KR:") else _us(company_id)
    if df.empty:
        return df
    return _finalize(df).reset_index(drop=True)


def wide(df: pd.DataFrame) -> pd.DataFrame:
    """[표준항목 × 연도] 표 (값만)."""
    t = df.pivot_table(index="item", columns="year", values="value", aggfunc="first")
    t = t.reindex([i.key for i in ITEMS if i.key in t.index])
    t.index = [ITEM_BY_KEY[k].name for k in t.index]
    return t
