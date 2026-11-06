"""표준 재무항목 계층:  원본(raw)  →  표준(standard)  →  (나중에) 지표(ratios)

국가·회계기준·회사마다 다른 계정과목을 '정의가 같은' 표준 항목 하나로 매핑한다.
이 파일은 매핑 '장치'만 가지고 있고, 항목 정의(ITEMS)는 필요할 때 하나씩 추가한다.

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

# 표준 항목 정의: 비어 있음. 투자기준에서 지표가 필요해질 때 하나씩 정의해 추가한다.
# 정의는 분석가의 판단이므로, 항목마다 '왜 이렇게 정의했는지'를 note 에 남긴다.
#
# 예시 (실제 데이터로 검증했던 매출액 정의):
#   Item("revenue", "매출액", "flow", PL, ("ifrs-full_Revenue",),
#        r"^(매출액|매출|영업수익|수익|수익\(매출액\))$",
#        ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
#         "us-gaap:SalesRevenueNet", "ifrs-full:Revenue"),
#        note="국내 플랫폼 기업은 '영업수익'으로 표시"),
# 이전에 쓰던 21개 정의 전체는 git 기록(커밋 c9af85b)의 이 파일에서 볼 수 있다.
ITEMS: list[Item] = []
ITEM_BY_KEY = {i.key: i for i in ITEMS}

# ---------------- 일치 수준 ----------------
# exact   정의 일치      : 표준 항목과 같은 개념의 계정/태그
# proxy   대체(조건 확인): 정의는 다르지만, 차이를 만드는 요소가 그 해에 없음을 확인했으므로 값이 같다
# scope   범위 차이 가능 : 정의가 달라 값이 다를 수 있다. 지표 계산 시 주의
# derived 항등식 파생    : 원본에 없어 회계 항등식으로 계산
MATCH_LABEL = {"exact": "정의 일치", "proxy": "대체(조건 확인)", "scope": "범위 차이 가능", "derived": "항등식 파생"}

# 미국 태그 중 정의가 표준과 다른 것: (항목, 태그) → (조건, 조건 불충족 시 처리, 설명)
#   조건 nci    : 그 해 비지배지분이 없거나 0  (MinorityInterest, NetIncomeLossAttributableToNoncontrollingInterest)
#   조건 equity : 그 해 지분법손익이 없거나 0  (IncomeLossFromEquityMethodInvestments)
#   조건 disc   : 그 해 중단영업이 없거나 0
#   조건 None   : 확인할 방법이 없음 → 항상 scope
#   처리 drop   : 값을 쓰지 않음(빈칸) / scope: 쓰되 '범위 차이 가능'으로 표시
US_TAG_RULES: dict[tuple[str, str], tuple[str | None, str, str]] = {
    # 예시: ("net_income", "us-gaap:NetIncomeLoss"):
    #           ("nci", "drop", "지배주주 몫 순이익. 비지배지분이 있으면 연결 순이익과 달라 사용하지 않음"),
}
# 항등식 파생: (만들 항목, 항목 A, 항목 B, 설명) → 원본에 없을 때만 A − B 로 계산
# 예시: ("total_liabilities", "total_assets", "equity_total", "파생: 자산총계 − 자본총계")
DERIVATIONS: list[tuple[str, str, str, str]] = []

NCI_TAGS = ("us-gaap:MinorityInterest", "us-gaap:NetIncomeLossAttributableToNoncontrollingInterest")
EQUITY_METHOD_TAGS = ("us-gaap:IncomeLossFromEquityMethodInvestments",)
DISCONTINUED_TAGS = ("us-gaap:IncomeLossFromDiscontinuedOperationsNetOfTax",
                     "us-gaap:IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity",
                     "us-gaap:CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations",
                     "us-gaap:CashProvidedByUsedInDiscontinuedOperations")

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
    raw["by_code"] = [k if (k := code_map.get(c)) and sj in ITEM_BY_KEY[k].sj else None
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
        "match": "exact", "match_note": "",
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

    # 조건 확인용: 연도별로 비지배지분 / 지분법손익이 0이 아닌 값으로 보고됐는지
    def present(tags) -> set[int]:
        s = df[df["full_tag"].isin(tags) & df["val"].fillna(0).ne(0)]
        return set(s["year"].astype(int))
    has = {"nci": present(NCI_TAGS), "equity": present(EQUITY_METHOD_TAGS), "disc": present(DISCONTINUED_TAGS)}

    out = []
    for it in ITEMS:
        cands = df[df["full_tag"].isin(it.us_tags)].copy()
        if cands.empty:
            continue
        cands = cands[cands["unit"] == (f"{currency}/shares" if it.kind == "per_share" else currency)]
        cands["year"] = cands["year"].astype(int)
        cands["match"], cands["match_note"] = "exact", ""
        keep = pd.Series(True, index=cands.index)
        for (key, tag), (cond, on_fail, note) in US_TAG_RULES.items():
            if key != it.key:
                continue
            m = cands["full_tag"] == tag
            ok = cands["year"].isin(has[cond]).map(lambda b: not b) if cond else pd.Series(False, index=cands.index)
            cands.loc[m & ok, ["match", "match_note"]] = ["proxy", f"{note} → 그 해 해당 요소 없음 확인"]
            cands.loc[m & ~ok, ["match", "match_note"]] = ["scope", note]
            if on_fail == "drop":
                keep &= ~(m & ~ok)
        cands = cands[keep]
        cands["prio"] = cands["full_tag"].map({t: i for i, t in enumerate(it.us_tags)})
        cands["off_anchor"] = cands["accn"] != cands["year"].map(anchor)
        cands["match_rank"] = cands["match"].map({"exact": 0, "proxy": 1, "scope": 2})
        # 같은 공시 안에서는 정의 일치 > 대체 > 범위 차이 순, 그다음 태그 우선순위
        cands = cands.sort_values(["off_anchor", "match_rank", "prio", "filed"]).drop_duplicates("year")
        out.append(pd.DataFrame({
            "item": it.key, "year": cands["year"], "period_end": cands["end"],
            "value": cands["val"], "currency": cands["unit"].str.split("/").str[0],
            "source": cands["full_tag"] + "  (" + cands["label"] + ")",
            "filing": cands["accn"], "method": "tag",
            "match": cands["match"], "match_note": cands["match_note"],
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
            "source": label, "filing": meta.loc[calc.index, "filing"].values, "method": "derived",
            "match": "derived", "match_note": label})],
            ignore_index=True)

    for target, a, b, label in DERIVATIONS:
        derive(target, a, b, label)
    order = {it.key: i for i, it in enumerate(ITEMS)}
    return df.sort_values(["year"]).sort_values("item", key=lambda s: s.map(order), kind="stable")


def checks(df: pd.DataFrame) -> pd.DataFrame:
    """매핑 결과 검증. 실패 = 원본 공시가 이상하거나, 매핑이 잘못됐을 가능성.
    아래 key 로 항목을 정의하면 해당 검증이 자동으로 켜진다 (없으면 건너뜀):
      total_assets, total_liabilities, equity_total  → 자산 = 부채 + 자본
      revenue, cost_of_sales, gross_profit           → 매출 − 매출원가 = 매출총이익, 매출 ≥ 매출총이익
      current_assets, cash                           → 유동자산 ≤ 자산총계, 현금 ≤ 유동자산
      eps_basic, net_income_parent                   → EPS와 지배순이익 부호 일치
    """
    if df.empty:
        return pd.DataFrame(columns=["year", "check", "ok", "detail"])
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


def wide(df: pd.DataFrame, values: str = "value") -> pd.DataFrame:
    """[표준항목 × 연도] 표. values='match' 면 일치 수준 표."""
    t = df.pivot_table(index="item", columns="year", values=values, aggfunc="first")
    t = t.reindex([i.key for i in ITEMS if i.key in t.index])
    t.index = [ITEM_BY_KEY[k].name for k in t.index]
    return t


def match_summary(df: pd.DataFrame) -> pd.DataFrame:
    """항목별 일치 수준 집계 + 정의가 다른 경우의 설명."""
    s = df.groupby(["item", "match"]).agg(years=("year", lambda y: ", ".join(map(str, sorted(y)))),
                                          note=("match_note", "first")).reset_index()
    s = s[s["match"] != "exact"]
    s["item"] = s["item"].map(lambda k: ITEM_BY_KEY[k].name)
    s["match"] = s["match"].map(MATCH_LABEL)
    return s.rename(columns={"item": "항목", "match": "일치 수준", "years": "연도", "note": "내용"})
