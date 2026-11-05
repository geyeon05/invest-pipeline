"""기업명 입력 → (없거나 오래됐으면) 자동 수집 → DB 에서 원본 그대로 조회."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import dart, registry, sec
from .config import REFRESH_DAYS
from .store import clear_company, connect

ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")


# ---------- 검색 · 수집 ----------
def search(query: str, limit: int = 20) -> tuple[list[dict], list[str]]:
    rows, warnings = registry.load_all()
    return registry.search(query, rows, limit), warnings


def get_company(company_id: str) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT company_id, market, name, name_en, ticker, profile_json, fetched_at "
                       "FROM companies WHERE company_id = ?", (company_id,)).fetchone()
    if not row:
        return None
    keys = ["company_id", "market", "name", "name_en", "ticker", "profile", "fetched_at"]
    c = dict(zip(keys, row))
    c["profile"] = json.loads(c["profile"] or "{}")
    return c


def is_fresh(company_id: str) -> bool:
    c = get_company(company_id)
    if not c or not c["fetched_at"]:
        return False
    return datetime.fromisoformat(c["fetched_at"]) > datetime.now(timezone.utc) - timedelta(days=REFRESH_DAYS)


def ensure(company: dict, force: bool = False) -> dict:
    """DB에 최신 데이터가 있으면 그대로, 없으면 원천에서 수집한다. 수집 결과 요약을 반환."""
    cid = company["company_id"]
    if not force and is_fresh(cid):
        return {"collected": False}
    collector = dart if company["market"] == "KR" else sec
    conn = connect()
    with conn:  # 한 트랜잭션: 실패하면 기존 데이터 유지
        clear_company(conn, cid)
        result = collector.fetch(conn, company)
        conn.execute("INSERT OR REPLACE INTO companies VALUES (?,?,?,?,?,?,?)",
                     (cid, company["market"], result["name"], result["name_en"], result["ticker"],
                      json.dumps(result["profile"], ensure_ascii=False),
                      datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return {"collected": True, **result["counts"]}


def collected_companies() -> pd.DataFrame:
    return pd.read_sql("SELECT company_id, market, name, ticker, fetched_at FROM companies ORDER BY name", connect())


# ---------- 조회 (원본 값 그대로, 배열만 바꿈) ----------
def filings(company_id: str) -> pd.DataFrame:
    return pd.read_sql("SELECT filed AS 접수일, form AS 유형, title AS 공시명, filer AS 제출인, "
                       "rcept_no AS 접수번호, url AS 원문 FROM filings WHERE company_id = ? ORDER BY filed DESC",
                       connect(), params=(company_id,))


def raw_financials(company_id: str) -> pd.DataFrame:
    table = "dart_fin" if company_id.startswith("KR:") else "sec_facts"
    return pd.read_sql(f"SELECT * FROM {table} WHERE company_id = ?", connect(), params=(company_id,))


SJ_ORDER = ["BS", "IS", "CIS", "CF", "SCE"]


def _row_key(g: pd.DataFrame, merge: bool) -> pd.Series:
    """한 재무제표 안에서 표의 행 기준을 정한다.

    merge=False: 회사가 쓴 계정명 그대로 (연도마다 이름이 바뀌면 다른 행).
    merge=True : 같은 표준계정코드 '또는' 같은 계정명을 가진 행을 하나로 잇는다.
        회사는 계정명을 바꾸기도 하고(수익(매출액)→영업수익→매출액), 같은 이름에 다른 코드를
        쓰기도 해서 어느 한쪽만으로는 연도가 맞지 않기 때문.
        단, 이어 붙였더니 한 연도에 값이 둘 이상 생기면 잘못 이은 것이므로 그 묶음은 계정명 기준으로 되돌린다.
    """
    detail = g["account_detail"].fillna("").replace("-", "")
    sce = g["sj_div"] == "SCE"  # 자본변동표는 자본 구성요소(account_detail)별로 같은 계정이 반복됨
    name = g["account_nm"].where(~sce, g["account_nm"] + " | " + detail)
    if not merge:
        return name
    code = g["account_id"].fillna("").str.replace(r"^ifrs_", "ifrs-full_", regex=True)
    code = code.where(~sce, code + " | " + detail)
    standard = g["account_id"].fillna("").str.match(r"^(ifrs-full|ifrs|dart)_")

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for n, c, s in zip(name, code, standard):
        a = find("n:" + n)
        if s:
            parent[find("c:" + c)] = a
    key = pd.Series([find("n:" + n) for n in name], index=g.index)

    conflict = g.assign(key=key).groupby(["key", "bsns_year"]).size()
    bad = set(conflict[conflict > 1].index.get_level_values("key"))
    return key.where(~key.isin(bad), "n:" + name)


def kr_statements(company_id: str, merge: bool = True) -> dict[str, pd.DataFrame]:
    """DART 재무제표를 종류별 [계정 × 사업연도] 표로 배열. 값은 각 연도 사업보고서의 '당기' 금액 그대로.
    행 이름은 가장 최근 연도에 회사가 쓴 계정명."""
    df = raw_financials(company_id)
    if df.empty:
        return {}
    out = {}
    for sj in sorted(df["sj_div"].unique(), key=lambda s: SJ_ORDER.index(s) if s in SJ_ORDER else 99):
        g = df[df["sj_div"] == sj].sort_values("bsns_year")
        g = g.assign(key=_row_key(g, merge))
        last = g.groupby("key").last()  # 최근 연도의 계정명·순서
        names = last["account_nm"] + last["account_detail"].fillna("").replace("-", "").map(
            lambda d: f" [{d}]" if d and sj == "SCE" else "")
        t = g.pivot_table(index="key", columns="bsns_year", values="thstrm_amount", aggfunc="first")
        t = t.reindex(last.sort_values(["bsns_year", "ord"], ascending=[False, True]).index)
        t.index = names.reindex(t.index).values
        t.index.name = "계정과목"
        sj_nm = g["sj_nm"].iloc[-1]
        fs = "/".join(sorted(g["fs_div"].unique()))
        out[f"{sj_nm} ({fs})"] = t
    return out


def us_annual(company_id: str) -> pd.DataFrame:
    """SEC XBRL 팩트 중 연차보고서(10-K/20-F)의 연간 값만 [태그 × 회계연도] 표로 배열.
    같은 기간이 여러 공시에 나오면 가장 최근 제출본(정정 반영) 값을 사용. 회계연도 = 기간 종료일의 연도."""
    df = raw_financials(company_id)
    if df.empty:
        return df
    df = df[df["form"].isin(ANNUAL_FORMS) & (df["fp"] == "FY")].copy()
    start = pd.to_datetime(df["start"], errors="coerce")
    end = pd.to_datetime(df["end"], errors="coerce")
    dur = (end - start).dt.days
    df = df[dur.isna() | dur.between(330, 400)]  # 시점 값(재무상태표) 또는 1년 기간 값만
    df["year"] = end[df.index].dt.year
    df = df.sort_values("filed").drop_duplicates(["taxonomy", "tag", "unit", "year"], keep="last")
    t = df.pivot_table(index=["taxonomy", "tag", "label", "unit"], columns="year", values="val", aggfunc="first")
    return t.sort_index()
