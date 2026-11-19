"""스프레드 = ROA − 이자율 (9주차: 레버리지의 마법과 독)

사용자 결정
- 9-②: 빚으로 높인 ROE는 스프레드가 플러스일 때만 인정한다.
- ROA = 영업이익 ÷ 평균 총자산 (2026-11-19, (나): 이자를 내기 전의 이익을 이자율과 같은 선에서 비교)
- 이자율 = 이자비용 ÷ 평균 이자부 부채 (숫자 기준 7). 차입금이 금융부채에 묶인 회사는 이자부 부채가 빈칸 → 계산 안 함.
  이자비용과 부채의 범위가 어긋나는 회사(예: 현대차 금융 자회사)는 숫자를 그대로 보여주고 분석할 때 판단한다.
- 보여주는 곳: 숫자는 자본 배분 화면(ROE 옆), 재무 안전성 화면에는 마이너스인 해만 경고로.
"""
import pandas as pd


def by_year(df: pd.DataFrame, years: list[int]) -> dict[int, dict]:
    """표준 항목 표(df)에서 연도별 {roa_op, rate, spread, why}."""
    if df.empty:
        return {}
    val = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    g = lambda y, k: val.at[y, k] if (k in val and y in val.index and pd.notna(val.at[y, k])) else None  # noqa: E731

    def avg(k, y):
        a, b = g(y, k), g(y - 1, k)
        return (a + b) / 2 if a is not None and b is not None else None

    out = {}
    for y in years:
        oi, ta, ie, debt = g(y, "operating_income"), avg("total_assets", y), g(y, "interest_expense"), \
            avg("interest_bearing_debt", y)
        roa = oi / ta if oi is not None and ta else None
        rate = ie / debt if ie is not None and debt and debt > 0 else None
        why = None
        if roa is None:
            why = "영업이익 또는 전년 총자산 없음"
        elif ie is None:
            why = "이자비용 없음"
        elif debt is None:
            why = "이자부 부채 없음 (전년 값이 없거나, 차입금이 금융부채에 묶여 빈칸)"
        elif debt <= 0:
            why = "이자부 부채 0"
        out[y] = {"roa_op": roa, "rate": rate, "spread": roa - rate if roa is not None and rate is not None else None,
                  "why": why}
    return out
