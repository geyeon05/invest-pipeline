"""DB에서 읽어 파생지표를 계산한다. 계산은 AI가 아니라 이 코드가 한다."""
import pandas as pd

from .db import connect


def list_companies() -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM companies ORDER BY company_id", connect())


def raw_financials(company_id: str) -> pd.DataFrame:
    """출처 정보까지 포함한 원본 수치 (long 형식)."""
    return pd.read_sql(
        "SELECT * FROM financials WHERE company_id = ? ORDER BY metric, fiscal_year",
        connect(), params=(company_id,),
    )


def filings(company_id: str, forms: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT form, filed, report_date, description, accession, url FROM filings "
        "WHERE company_id = ? ORDER BY filed DESC",
        connect(), params=(company_id,),
    )
    return df[df["form"].isin(forms)] if forms else df


def metrics_table(company_id: str) -> pd.DataFrame:
    """연도 × 지표 표 + 파생지표."""
    raw = raw_financials(company_id)
    if raw.empty:
        return raw
    t = raw.pivot(index="fiscal_year", columns="metric", values="value").sort_index()

    def col(name: str) -> pd.Series:
        return t[name] if name in t else pd.Series(float("nan"), index=t.index)

    rev = col("revenue")
    t["revenue_growth_%"] = rev.pct_change() * 100
    t["gross_margin_%"] = col("gross_profit") / rev * 100
    t["operating_margin_%"] = col("operating_income") / rev * 100
    t["net_margin_%"] = col("net_income") / rev * 100
    avg_equity = (col("equity") + col("equity").shift(1)) / 2
    t["roe_%"] = col("net_income") / avg_equity * 100
    t["debt_to_equity"] = col("total_liabilities") / col("equity")
    t["free_cash_flow"] = col("operating_cash_flow") - col("capex")
    t["fcf_margin_%"] = t["free_cash_flow"] / rev * 100
    return t
