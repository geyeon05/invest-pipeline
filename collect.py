"""데이터 수집 실행.

예)  uv run collect.py AAPL MSFT NVDA
     uv run collect.py AAPL --years 15
"""
import argparse

from pipeline import sec_edgar


def main() -> None:
    p = argparse.ArgumentParser(description="기업 데이터 수집")
    p.add_argument("tickers", nargs="+", help="미국 티커 (예: AAPL). 국내 종목은 2단계(DART)에서 지원")
    p.add_argument("--years", type=int, default=10)
    args = p.parse_args()

    for t in args.tickers:
        try:
            sec_edgar.collect(t, years=args.years)
        except Exception as e:  # 한 종목 실패가 전체를 멈추지 않도록
            print(f"[실패] {t}: {e}")


if __name__ == "__main__":
    main()
