"""데이터 조회 도구 (AI와 사람 공용). 기업명만 주면 자동으로 수집 후 원본을 보여준다.

  uv run data.py search 삼성전자            # 기업 검색 (국내·해외)
  uv run data.py get 삼성전자               # 수집(필요 시) + 요약
  uv run data.py get AAPL --refresh         # 강제 재수집
  uv run data.py fin 삼성전자 [계정명]       # 재무제표 원본 (연도별)
  uv run data.py filings 삼성전자 [키워드]   # 공시 목록
  uv run data.py profile 삼성전자           # 기업개황 원본
  uv run data.py std 삼성전자 [--source]    # 표준 재무항목 (국내·해외 비교용) + 검증 결과
  uv run data.py list                      # 수집된 기업 목록

  공시 본문 (요청 시에만 받음, 접수번호는 filings 결과에서 확인)
  uv run data.py doc 삼성전자 20260310002820                      # 본문 받기 + 목차
  uv run data.py doc 삼성전자 20260310002820 --section 사업의 개요 # 절 본문 (목차 번호 또는 제목 일부)
  uv run data.py doc 삼성전자 20260310002820 --grep 자기주식      # 키워드가 나오는 곳 (정규식 가능)
  uv run data.py doc 삼성전자 20260310002820 --part 1             # 첨부 문서(감사보고서 등) 선택
  uv run data.py doc 삼성전자 20260310002820 --full               # 전체 텍스트
  uv run data.py docs 삼성전자                                    # 받아 둔 본문 목록
"""
import argparse
import json
import sys

import pandas as pd

from pipeline import documents, service, standard

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
    p.add_argument("cmd", choices=["search", "get", "fin", "filings", "profile", "std", "doc", "docs", "list"])
    p.add_argument("query", nargs="?")
    p.add_argument("filter", nargs="?", help="fin: 계정명/태그 일부, filings: 공시명 키워드, doc: 접수번호")
    p.add_argument("--pick", type=int, help="검색 후보 번호")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--source", action="store_true", help="std: 값마다 원본 계정·공시번호 표시")
    p.add_argument("--section", help="doc: 목차 번호 또는 제목 일부")
    p.add_argument("--grep", help="doc: 키워드(정규식)")
    p.add_argument("--part", type=int, default=0, help="doc: 문서 번호 (0=본문, 1~=첨부)")
    p.add_argument("--full", action="store_true", help="doc: 전체 텍스트 출력")
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
    if a.refresh and a.cmd != "doc":
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
    elif a.cmd == "std":
        if not standard.ITEMS:
            sys.exit("아직 정의된 표준 항목이 없습니다. pipeline/standard.py 의 ITEMS 에 필요한 항목을 정의하세요.")
        df = standard.standardize(cid)
        if df.empty:
            sys.exit("이 기업에서 정의된 표준 항목에 해당하는 계정을 찾지 못했습니다.")
        if standard.is_financial(c):
            print("[주의] 금융업: 매출·유동자산 등 일반 기업 항목으로 비교하면 안 됩니다.\n")
        cur = "/".join(df["currency"].dropna().unique())
        ends = df.groupby("year")["period_end"].first()
        print(f"통화 {cur} | 기간 종료일: " + ", ".join(f"{y}={e}" for y, e in ends.items()) + "\n")
        print(standard.wide(df).to_string())
        mark = {"exact": "·", "proxy": "P", "scope": "S", "derived": "D"}
        print("\n[일치 수준] ·=정의 일치  P=대체(조건 확인)  S=범위 차이 가능  D=항등식 파생")
        print(standard.wide(df, values="match").map(lambda m: mark.get(m, "-") if isinstance(m, str) else "-").to_string())
        ms = standard.match_summary(df)
        if not ms.empty:
            print(ms.to_string(index=False))
        ch = standard.checks(df)
        bad = ch[~ch["ok"]]
        print(f"\n[검증] {len(ch) - len(bad)}/{len(ch)} 통과")
        for r in bad.itertuples():
            print(f"  ✗ {r.year} {r.check} {r.detail}")
        if a.source:
            print("\n[출처]")
            print(df[["item", "year", "value", "match", "source", "filing", "method"]].to_string(index=False))
        print("\n[method] name+code/name/code=국내 매핑 근거, tag=SEC 태그, derived=항등식 파생, +abs=부호 정규화")
    elif a.cmd == "docs":
        rows = documents.list_docs(cid)
        if not rows:
            print("받아 둔 공시 본문이 없습니다. doc <기업> <접수번호> 로 받으세요.")
        for r in rows:
            print(f"  {r['filed']}  {r['rcept_no']}  {r['title']}  (문서 {r['parts']}개, {r['chars']:,}자)")
    elif a.cmd == "doc":
        doc_cmd(cid, a)
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


def doc_cmd(cid: str, a) -> None:
    if not a.filter:
        sys.exit("접수번호를 입력하세요. (filings 명령으로 확인)")
    try:
        r = documents.fetch(cid, a.filter, force=a.refresh)
    except (ValueError, RuntimeError) as e:
        sys.exit(str(e))
    parts = documents.parts(cid, a.filter)
    if r.get("collected"):
        print("[본문 수집 완료]")
    print(f"공시: {r['title']} | 접수일 {r['filed']} | 접수번호 {r['rcept_no']}")
    print(f"원문: {parts[0]['source_url']}")
    print(f"원본 파일: {parts[0]['raw_path']}  (받은 시각 {parts[0]['fetched_at']})")
    print("문서: " + " / ".join(f"[{p['part']}] {p['part_title']} {p['chars']:,}자" for p in parts), end="\n\n")
    if not 0 <= a.part < len(parts):
        sys.exit(f"--part 는 0~{len(parts) - 1} 사이여야 합니다.")
    p = parts[a.part]
    text = p["text"]
    if a.full:
        print(text)
    elif a.section:
        hit = documents.section(text, a.section)
        if not hit:
            sys.exit(f"'{a.section}' 에 해당하는 절이 없습니다. 목차를 확인하세요.")
        s, body = hit
        print(f"[{p['part_title']}] {s['no']}. {s['title']}  ({len(body):,}자)", end="\n\n")
        print(body)
    elif a.grep:
        hits = documents.grep(text, a.grep)
        more = " (처음 40곳만 표시)" if len(hits) > 40 else ""
        print(f"[{p['part_title']}] '{a.grep}' {len(hits)}곳{more}", end="\n\n")
        for sec, line, ctx in hits[:40]:
            print(f"--- {sec} (줄 {line})")
            print(ctx, end="\n\n")
    else:
        ol = documents.outline(text)
        print(f"[{p['part_title']} 목차] {len(ol)}개 절 · --section 번호|제목 으로 본문 보기", end="\n\n")
        for s in ol:
            print(f"{'  ' * (s['level'] - 1)}{s['no']:>3}. {s['title']}  ({s['end_line'] - s['start_line']}줄)")
        if not ol:
            print(text[:3000] + ("\n..." if len(text) > 3000 else ""))


if __name__ == "__main__":
    main()
