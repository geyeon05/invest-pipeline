"""AI(Claude Code)와 사람이 함께 쓰는 조회 도구. 모든 출력에 출처가 붙는다.

예)  uv run query.py companies                 # 수집된 기업 목록
     uv run query.py metrics US:AAPL           # 연도별 지표 + 파생지표
     uv run query.py source US:AAPL revenue    # 지표별 원본 출처(공시번호·제출일)
     uv run query.py filings US:AAPL 10-K 8-K  # 공시 목록
"""
import sys

import pandas as pd

from pipeline import analysis

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_rows", 200)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]

    if cmd == "companies":
        print(analysis.list_companies().to_string(index=False))
    elif cmd == "metrics":
        print(analysis.metrics_table(args[0]).T.to_string())
        print("\n[출처] SEC EDGAR XBRL companyfacts. 원본 출처는: query.py source <기업> <지표>")
    elif cmd == "source":
        df = analysis.raw_financials(args[0])
        if len(args) > 1:
            df = df[df["metric"] == args[1]]
        print(df[["metric", "fiscal_year", "period_end", "value", "unit",
                  "source_tag", "form", "accession", "filed"]].to_string(index=False))
    elif cmd == "filings":
        print(analysis.filings(args[0], args[1:] or None).to_string(index=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
