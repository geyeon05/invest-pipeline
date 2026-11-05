"""데이터 조회 도구 (AI와 사람 공용). 기업명만 주면 자동으로 수집 후 원본을 보여준다.

  uv run data.py search 삼성전자            # 기업 검색 (국내·해외)
  uv run data.py get 삼성전자               # 수집(필요 시) + 요약
  uv run data.py get AAPL --refresh         # 강제 재수집
  uv run data.py fin 삼성전자 [계정명]       # 재무제표 원본 (연도별)
  uv run data.py filings 삼성전자 [키워드]   # 공시 목록
  uv run data.py profile 삼성전자           # 기업개황 원본
  uv run data.py list                      # 수집된 기업 목록
"""
import argparse
import json
import sys

import pandas as pd

from pipeline import service

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_rows", 500)
pd.set_option("display.max_colwidth", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.4g}")


def resolve(query: str, pick: int | None) -> dict:
    results, warnings = service.search(query)
    for w in warnings:
        print(f"[경고] {w}")
    if not results:
        sys.exit(f"'{query}' 에 해당하는 상장사를 찾지 못했습니다.")
    exact = [r for r in results if r.get("exact")]
    if pick is None and len(exact) == 1:
        pick = results.index(exact[0])
    if pick is None and len(results) > 1:
        print_candidates(results)
        sys.exit("후보가 여러 개입니다. --pick 번호 로 선택하세요.")
    company = results[pick or 0]
    r = service.ensure(company)
    if r.get("collected"):
        print(f"[수집 완료] {company['name']}: {json.dumps({k: v for k, v in r.items() if k != 'collected'}, ensure_ascii=False)}")
    return company


def print_candidates(results: list[dict]) -> None:
    for i, r in enumerate(results):
        print(f"  [{i}] {r['market']}  {r['name']}  ({', '.join(r['tickers'])})  {r['company_id']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["search", "get", "fin", "filings", "profile", "list"])
    p.add_argument("query", nargs="?")
    p.add_argument("filter", nargs="?", help="fin: 계정명/태그 일부, filings: 공시명 키워드")
    p.add_argument("--pick", type=int, help="검색 후보 번호")
    p.add_argument("--refresh", action="store_true")
    a = p.parse_args()

    if a.cmd == "list":
        print(service.collected_companies().to_string(index=False))
        return
    if not a.query:
        p.error("기업명 또는 티커를 입력하세요.")
    if a.cmd == "search":
        results, warnings = service.search(a.query)
        for w in warnings:
            print(f"[경고] {w}")
        print_candidates(results)
        return

    company = resolve(a.query, a.pick)
    cid = company["company_id"]
    if a.refresh:
        print(service.ensure(company, force=True))
    c = service.get_company(cid)
    src = "DART" if c["market"] == "KR" else "SEC EDGAR"
    print(f"\n=== {c['name']} ({c['ticker']}) | {cid} | 출처 {src} | 수집 {c['fetched_at']} ===\n")

    if a.cmd == "get":
        f = service.filings(cid)
        raw = service.raw_financials(cid)
        print(f"재무 원본 행: {len(raw):,} | 공시: {len(f):,}건")
        print(f.head(10).to_string(index=False))
    elif a.cmd == "profile":
        print(json.dumps(c["profile"], ensure_ascii=False, indent=2))
    elif a.cmd == "filings":
        f = service.filings(cid)
        if a.filter:
            f = f[f["공시명"].str.contains(a.filter, case=False, na=False)]
        print(f.to_string(index=False))
    elif a.cmd == "fin":
        if c["market"] == "KR":
            for name, t in service.kr_statements(cid).items():
                if a.filter:
                    t = t[t.index.str.contains(a.filter, case=False, na=False)]
                if not t.empty:
                    print(f"--- {name} | 단위: 원 | 각 연도 사업보고서 당기금액 ---")
                    print(t.to_string(), "\n")
            print("[출처] DART 단일회사 전체 재무제표. 접수번호(rcept_no)는 raw_financials 에 행마다 기록됨")
        else:
            t = service.us_annual(cid)
            if a.filter:
                t = t[t.index.get_level_values("tag").str.contains(a.filter, case=False)
                      | t.index.get_level_values("label").str.contains(a.filter, case=False)]
            print(t.to_string())
            print("\n[출처] SEC XBRL companyfacts, 10-K/20-F 연간값. 공시번호(accn)는 raw_financials 에 행마다 기록됨")


if __name__ == "__main__":
    main()
