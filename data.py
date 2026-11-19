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

  투자기준 1: 경영진의 약속 이행 기록 (1단계: 한국 자기주식 취득)
  uv run data.py promises 삼성전자                  # 판정 + 아직 받지 않은 공시 목록 (외부 요청 없음)
  uv run data.py promises 삼성전자 --fetch          # 위 목록의 본문을 DART에서 받은 뒤 판정 (사용자 승인 후)
  ※ promises 는 이미 수집된 기업만 대상으로 하고, 기업 재수집·기업목록 갱신을 하지 않는다.

  전체 지도: criteria/README.md (투자기준 = 규칙 / 분석 도구 = 판정 없이 숫자)

  분석 도구: 현금 창출 (결과만 보여줌 + 내 기준 '영업CF가 꾸준히 늘었나', 외부 요청 없음)
  uv run data.py cashflow 삼성전자 [--source]      # 최근 5년 영업CF·FCF·현금 전환율 + 표시

  분석 도구: 자본 배분 (번 돈을 어디에 썼고 결과가 어땠나, 판정 없음, 외부 요청 없음)
  uv run data.py allocation 삼성전자               # 영업CF·설비 재투자·FCF·주주환원·부채 증감·ROE·스프레드 + 의도를 논의할 사실 5가지

  분석 도구: 특수관계자 거래 (한국, 사업보고서 XBRL 주석, 판정 없음)
  uv run data.py related 삼성전자                  # 거래 상대 목록 ('후보'·'?' 표시)
  uv run data.py related 삼성전자 --owner 1,3      # 대주주 쪽으로 판단한 상대를 기록 → 매입 ÷ 매출 계산

  분석 도구: 주주환원 상세 (자본 배분의 상세 화면) (결과만 보여줌, 판정 없음)
  uv run data.py returns 삼성전자 [--source]       # 최근 5년 배당·자사주·소각·환원 비율·주식 수 (외부 요청 없음)
  uv run data.py returns 삼성전자 --fetch          # 한국: DART 주식 수 데이터를 받은 뒤 표시 (사용자 승인 후)

  분석 도구: 이익의 질 · 이익조정 신호 (결과만 보여줌, 판정 없음)
  uv run data.py quality 삼성전자                  # 최근 5년 발생액·매출채권·재고·작은 이익·빅 배스 (외부 요청 없음)
  uv run data.py quality 삼성전자 --fetch          # 대표이사 데이터(한국 DART 임원 현황 / 미국 10-K)를 받은 뒤 표시 (승인 후)

  분석 도구: 재무 안전성 (결과만 보여줌 + 분명한 위험 표시)
  uv run data.py safety 삼성전자                   # 최근 5년 부채비율·유동비율·당좌비율·이자보상비율·부채/영업CF
  uv run data.py safety 삼성전자 --fetch           # 한국: 이자비용용 사업보고서 XBRL을 받은 뒤 표시 (승인 후)

  정성 자료 (그때그때 보고 싶은 것만)
  uv run data.py events 삼성전자 [--kinds 경영진,소송제재사고] [--grep …] [--since YYYY-MM-DD]   # 수시공시 이벤트
  uv run data.py qual 삼성전자 [--topics 해자,수주] [--grep …] [--fetch]   # 사업보고서 정성 부분 원문 발췌
  uv run data.py news 삼성전자 [--fetch] [--grep …]   # 최근 1개월 뉴스 제목·링크 (네이버 API HUB + Google 뉴스)
  uv run data.py macro [--fetch]                   # 금리·환율·유가 (ECOS, FRED)

  분석 도구: 잠정 가격 판단 PER·PBR (판정 없음, 13~14주차 내재가치 계산 전까지의 비교 기준)
  uv run data.py price 삼성전자 --peers SK하이닉스   # 최근 5년·현재 PER(그해 이익/5년 평균)·PBR + 경쟁사 비교
                                                 # inputs/adjustments/<회사>.json 이 있으면 조정 PBR도 표시
  uv run data.py price 삼성전자 --fetch            # 주가(Yahoo Finance)·한국 주식 수(DART)를 받은 뒤 표시 (승인 후)
"""
import argparse
import json
import sys

import pandas as pd

from pipeline import (capital_allocation, cashflow, dart_officers, dart_shares, dart_xbrl, documents, earnings_quality,
                      events, funding, macro, news, price_level, prices, promises, qualitative, related_party,
                      returns, runway, safety, service, standard, us_promises)

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
    p.add_argument("cmd", choices=["search", "get", "fin", "filings", "profile", "std", "doc", "docs", "promises",
                                   "cashflow", "returns", "quality", "safety", "price", "allocation", "related",
                                   "events", "qual", "news", "macro", "runway", "list"])
    p.add_argument("query", nargs="?")
    p.add_argument("filter", nargs="?", help="fin: 계정명/태그 일부, filings: 공시명 키워드, doc: 접수번호")
    p.add_argument("--pick", type=int, help="검색 후보 번호")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--source", action="store_true", help="std: 값마다 원본 계정·공시번호 표시")
    p.add_argument("--section", help="doc: 목차 번호 또는 제목 일부")
    p.add_argument("--grep", help="doc: 키워드(정규식)")
    p.add_argument("--part", type=int, default=0, help="doc: 문서 번호 (0=본문, 1~=첨부)")
    p.add_argument("--full", action="store_true", help="doc: 전체 텍스트 출력")
    p.add_argument("--fetch", action="store_true", help="promises: 아직 받지 않은 공시 본문을 받는다 (사용자 승인 후)")
    p.add_argument("--peers", help="price: 비교할 경쟁사 (쉼표로 구분, 받아 둔 기업 이름)")
    p.add_argument("--owner", help="related: 대주주 쪽으로 판단한 거래 상대 번호 (쉼표로 구분, 사용자 판단을 기록)")
    p.add_argument("--kinds", help="events: 볼 분류 (쉼표로 구분, 예: 경영진,소송제재사고). 없으면 메뉴와 건수")
    p.add_argument("--topics", help="qual: 볼 주제 (쉼표로 구분, 예: 해자,수주). 없으면 메뉴")
    p.add_argument("--terms", help="news: 산업·경쟁 검색어 (쉼표로 구분, 경쟁사 이름·산업 낱말. 예: SK하이닉스,HBM)")
    p.add_argument("--since", help="events: 시작일 YYYY-MM-DD (기본: 1년 전)")
    p.add_argument("--no-sub", action="store_true", help="events: 자회사·종속회사 공시 빼기")
    p.add_argument("--frequent", action="store_true", help="events: 잦은 지분 변동 공시(최대주주등소유주식변동신고서 등)도 넣기")
    p.add_argument("--attribute", choices=["plan", "result"], default="result",
                   help="promises: 현 대표이사의 기록을 결과 시점(result, 기본·사용자 결정 2026-11-18)/약속 시점(plan) 대표이사로 볼지")
    a = p.parse_args()

    if a.cmd == "list":
        print(service.collected_companies().to_string(index=False))
        return
    if a.cmd == "macro":          # 회사와 상관없는 명령
        macro_cmd(a)
        return
    if not a.query:
        p.error("기업명 또는 티커를 입력하세요.")
    if a.cmd == "promises":
        promises_cmd(a)
        return
    if a.cmd == "cashflow":
        cashflow_cmd(a)
        return
    if a.cmd == "returns":
        returns_cmd(a)
        return
    if a.cmd == "quality":
        quality_cmd(a)
        return
    if a.cmd == "safety":
        safety_cmd(a)
        return
    if a.cmd == "price":
        price_cmd(a)
        return
    if a.cmd == "runway":
        runway_cmd(a)
        return
    if a.cmd == "allocation":
        allocation_cmd(a)
        return
    if a.cmd == "related":
        related_cmd(a)
        return
    if a.cmd == "events":
        events_cmd(a)
        return
    if a.cmd == "qual":
        qual_cmd(a)
        return
    if a.cmd == "news":
        news_cmd(a)
        return
    if a.cmd == "macro":
        macro_cmd(a)
        return
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


def resolve_local(query: str, pick: int | None) -> dict:
    """이미 수집된 기업 중에서만 찾는다 (외부 요청 없음)."""
    from pipeline.registry import ALIASES, _norm
    df = service.collected_companies()
    q = _norm(ALIASES.get(_norm(query), query))   # 'TSMC' → 'TSM', '애플' → 'AAPL' 등 흔한 별칭
    hit = df[df["company_id"].str.lower().eq(q)
             | df["ticker"].fillna("").str.replace(" ", "").str.lower().str.split(",").apply(lambda ts: q in ts)
             | df["name"].str.replace(" ", "").str.lower().str.contains(q, regex=False)]
    if hit.empty:
        sys.exit(f"'{query}' 는 아직 수집되지 않은 기업입니다. 기업 수집(DART/SEC 요청)이 먼저 필요합니다.")
    if len(hit) > 1 and pick is None:
        # 이름이 정확히 같거나 티커가 정확히 같은 후보가 하나뿐이면 그것을 고른다 (예: 'LG' → (주)LG, LG화학 아님)
        bare = hit["name"].str.replace(r"\(주\)|주식회사|\s", "", regex=True).str.lower()
        exact = hit[bare.eq(q) | hit["ticker"].fillna("").str.replace(" ", "").str.lower().str.split(",")
                    .apply(lambda ts: q in ts)]
        if len(exact) == 1:
            return exact.iloc[0].to_dict()
        for i, r in enumerate(hit.itertuples()):
            print(f"  [{i}] {r.name} ({r.ticker}) {r.company_id}")
        sys.exit("후보가 여러 개입니다. --pick 번호 로 선택하세요.")
    return hit.iloc[pick or 0].to_dict()


def _eok(v) -> str:
    return "-" if v is None else f"{v / 1e8:,.0f}억"


def promises_cmd(a) -> None:
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    if cid.startswith("US:"):
        us_promises_cmd(c, a)
        return
    print(f"\n=== {c['name']} | {cid} | 기준 1: 경영진의 약속 이행 기록 (한국 A·B) ===")
    ceos = promises.current_ceos(cid)
    print(f"현 대표이사 (DART 기업개황, 수집 {c['fetched_at']}): {', '.join(ceos) or '확인 불가'}\n")

    def all_missing():
        seen, out = set(), []
        for f in promises.missing_docs(cid) + funding.missing_docs(cid):
            if f["rcept_no"] not in seen:
                seen.add(f["rcept_no"])
                out.append(f)
        return out

    if a.fetch:
        # 사업보고서는 약속 공시를 읽어야 필요한 연도를 알 수 있어, 약속 공시를 받은 뒤 한 번 더 확인한다
        total = {"done": 0, "failed": {}}
        for _ in range(2):
            miss = all_missing()
            if not miss:
                break
            print(f"[본문 수집] {len(miss)}건을 DART에서 받습니다.")
            r = promises.fetch_docs(cid, miss)
            total["done"] += r["done"]
            total["failed"].update(r["failed"])
        print(f"  → 받음 {total['done']}건, 실패 {len(total['failed'])}건\n")

    print("── A. 자기주식 취득 ──")
    ps = promises.evaluate(cid)
    if not ps:
        print("최근 10년간 자기주식 취득 약속(취득결정·신탁계약 체결결정)이 없습니다.")
    for p in ps:
        state = f"{p.grade} ({p.ratio:.1%})" if p.status == "판정" else p.status
        if p.exception:
            state += f" → 예외 인정: {p.exception}"
        print(f"[{p.kind}] 약속 {p.plan_filed} ({p.plan_rcept})  {_eok(p.amount)}  기간 {p.start}~{p.end}  "
              f"대표이사 {'/'.join(p.ceo_plan) or '?'}")
        if p.result_rcept:
            print(f"       결과 {p.result_filed} ({p.result_rcept})  {_eok(p.actual)}  대표이사 {'/'.join(p.ceo_result) or '?'}")
        print(f"       → {state}" + (f"  | 회사가 적은 미달 사유: {p.reason}" if p.reason else ""))
        for n in p.notes:
            print(f"         · {n}")

    print("\n── B. 조달 자금 사용 (공시 단위로 셈) ──")
    evs = funding.evaluate(cid)
    if not evs:
        print("최근 10년간 회사 자신의 자금 조달 공시(유상증자·전환/교환/신주인수권부사채 발행결정)가 없습니다.")
    questions = []
    for ev in evs:
        state = ev.status + (f" {ev.grade}" if ev.grade else "")
        rec = f"  | 기록: {', '.join(dict.fromkeys(ev.records))}" if ev.records else ""
        print(f"[{ev.kind}{' ' + ev.tranche + '회' if ev.tranche else ''}] 약속 {ev.plan_filed} ({ev.plan_rcept})  "
              f"대표이사 {'/'.join(ev.ceo_plan) or '?'} → 결과 시점 {'/'.join(ev.ceo_result) or '-'}")
        print(f"       → {state}{rec}")
        for n in ev.notes:
            print(f"         · {n}")
        for u in ev.units:
            base = u.plan_amount or u.report_amount
            ratio = f" {u.ratio:.1%}" if u.ratio is not None else ""
            print(f"       - {u.cat}: 약속 {_eok(base)} ({u.timing}) / 실제 {_eok(u.actual)}"
                  f"{' (' + str(u.judged_year) + '년 사업보고서)' if u.judged_year else ''} → {u.status}"
                  f"{' ' + u.grade if u.grade else ''}{ratio}" + (f" | 차이 사유: {u.reason}" if u.reason else ""))
            for n in u.notes:
                print(f"           · {n}")
            for k, q in u.questions:
                questions.append((f"{ev.plan_rcept}:{u.cat}", k, q))

    if questions:
        print(f"\n[직접 판단이 필요한 것 {len(questions)}건] 판단은 criteria/judgments/{cid.replace(':', '_')}.json 에 기록")
        for i, (key, k, q) in enumerate(questions, 1):
            print(f"   {i}. [{key}] {q}")

    miss = all_missing()
    if miss:
        print(f"\n[아직 받지 않은 공시 {len(miss)}건] '확인 필요'인 건은 이 본문들이 있어야 판정됩니다.")
        for f in miss:
            print(f"   {f['filed']} {f['rcept_no']} {f['title']}")
        print("   → 받으려면 승인 후: uv run data.py promises <기업> --fetch")
    unav = promises.unavailable(cid)
    if unav:
        print(f"\n[DART가 원문을 제공하지 않는 공시 {len(unav)}건] 다시 요청하지 않습니다.")
        for r_no, msg in unav.items():
            print(f"   {r_no}  {msg[-60:]}")

    print("\n[회사 판정] (한국 A·B 반영. E(사업 전략)는 아직 없음)")
    v = promises.verdict(ps + evs, ceos, a.attribute)
    label = {"plan": "약속 시점 대표이사 기준", "result": "결과 시점 대표이사 기준"}[a.attribute]
    print(f"   {v['verdict']}  ({v['why']})  [{label}]  | 진행 중 {v['pending']}건, 확인·판단 필요 {v['unresolved']}건")


def cashflow_cmd(a) -> None:
    """분석 도구: 현금 창출 — 결과만 보여준다 (판정 없음)."""
    c = resolve_local(a.query, a.pick)
    r = cashflow.analyze(c["company_id"])
    print(f"\n=== {c['name']} | {c['company_id']} | 분석 도구: 현금 창출 (최근 5년, 결과만 표시) ===")
    if not r["rows"]:
        print("표시할 결과가 없습니다.")
    else:
        cur = r["rows"][-1]["currency"]
        unit, div = ("억 원", 1e8) if cur == "KRW" else (f"백만 {cur}", 1e6)
        f = lambda v: "-" if v is None else f"{v / div:,.0f}"  # noqa: E731
        print(f"(금액 단위: {unit})\n")
        print(f"{'연도':>6} {'A 영업CF':>12} {'취득':>10} {'처분':>8} {'순설비투자':>11} {'B FCF':>11} {'연결순이익':>11} {'C 전환율':>8}")
        for x in r["rows"]:
            cv = "-" if x["conversion"] is None else f"{x['conversion']:.2f}"
            print(f"{x['year']:>6} {f(x['operating_cf']):>12} {f(x['acquisitions']):>10} {f(x['disposals']):>8} "
                  f"{f(x['net_capex']):>11} {f(x['fcf']):>11} {f(x['net_income']):>11} {cv:>8}")
        k = r["counts"]
        print(f"\n[5년 중 몇 년] 영업CF > 0: {k['ocf_pos']}/{k['years']}  |  FCF > 0: {k['fcf_pos']}/{k['fcf_known']}"
              f"  |  현금 전환율 ≥ 1.0: {k['conv_ge1']}/{k['conv_known']} (흑자인 해 기준)")
        print("   ※ 통과선이 아닌 참고용 개수 (이 도구는 판정하지 않음)")
        st = r.get("steady") or {}
        if st:
            ok = {True: "충족", False: "미충족", None: "판단 불가"}[st["ok"]]
            cg = "-" if st["cagr"] is None else f"{st['cagr']:+.1%}"
            print(f"\n[내 기준: 영업CF가 꾸준히 늘었나 (프로필 6-①, 성장기 회사의 증거)] {ok}"
                  + (f"  ({st['why']})" if st.get("why") and st["ok"] is None else ""))
            print(f"   전년보다 늘어난 해 {st['ups']}/{st['changes']}번 (기준 3번 이상)  |  5년 연평균 {cg} (기준 0% 초과)")
            if st["decreases"]:
                print("   감소한 해: " + ", ".join(f"{y} {c:+.1%}" for y, c in st["decreases"]))
            if st["negatives"]:
                print(f"   ● 경고: 영업CF가 마이너스인 해 {st['negatives']} → 이유 확인 (6-①)")
        notes = [(x["year"], n) for x in r["rows"] for n in x["notes"]]
        if notes:
            print("\n[연도별 표시]")
            for y, n in notes:
                print(f"   {y}: {n}")
    if r["flags"]:
        print("\n[회사 단위 표시]")
        for fl in r["flags"]:
            print(f"   · {fl}")
    if a.source and not r["sources"].empty:
        s = r["sources"]
        ys = [x["year"] for x in r["rows"]]
        s = s[s["year"].isin(ys)][["item", "year", "value", "match", "source", "filing"]]
        print("\n[출처]")
        print(s.to_string(index=False))


def returns_cmd(a) -> None:
    """분석 도구: 주주환원 상세 (자본 배분의 상세 화면) — 결과만 보여준다 (판정 없음)."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    if a.fetch and cid.startswith("KR:"):
        ys = dart_shares.target_years()
        print(f"[DART 주식 수 데이터] {len(dart_shares.missing(cid, ys))}건을 받습니다.")
        dart_shares.fetch(cid, ys)
    r = returns.analyze(cid)
    print(f"\n=== {c['name']} | {cid} | 분석 도구: 주주환원 상세 (최근 5년, 결과만 표시) ===")
    if r["rows"]:
        cur = r["rows"][-1]["currency"] or ("KRW" if cid.startswith("KR:") else "USD")
        unit, div = ("억 원", 1e8) if cur == "KRW" else (f"백만 {cur}", 1e6)
        f = lambda v: "-" if v is None else f"{v / div:,.0f}"  # noqa: E731
        print(f"(금액 단위: {unit}, 주식 수: 주)\n")
        print(f"{'연도':>5} {'A 배당':>9} {'자사주매입':>10} {'보상차감':>9} {'B 매입(순)':>10} {'지배순이익':>10} {'D 환원비율':>9}"
              f" {'C 소각':>13} {'E 발행주식':>15} {'E 유통주식':>15}")
        sh = lambda v: "-" if v is None else f"{v:,.0f}"  # noqa: E731
        for x in r["rows"]:
            rt = "-" if x["ratio"] is None else f"{x['ratio']:.0%}"
            print(f"{x['year']:>5} {f(x['dividends']):>9} {f(x['buyback']):>10} {f(x['comp'] or None):>9} "
                  f"{f(x['buyback_net']):>10} {f(x['net_income_parent']):>10} {rt:>9} {sh(x['retired']):>13} "
                  f"{sh(x['issued']):>15} {sh(x['outstanding']):>15}")
        first = next((x for x in r["rows"] if x["issued"] is not None), None)
        last = next((x for x in reversed(r["rows"]) if x["issued"] is not None), None)
        if first and last and first is not last:
            ch = lambda k: (f"{(last[k] / first[k] - 1):+.1%}" if first.get(k) and last.get(k) else "-")  # noqa: E731
            print(f"\n[주식 수 변화 {first['year']}→{last['year']}] 발행주식 {ch('issued')}  |  유통주식 {ch('outstanding')}")
        notes = [(x["year"], n) for x in r["rows"] for n in x["notes"]]
        if notes:
            print("\n[연도별 표시]")
            for y, n in notes:
                print(f"   {y}: {n}")
    else:
        print("표시할 결과가 없습니다.")
    if r["comp_detail"]:
        print("\n[보상 목적 자사주 매입의 근거 (취득결정 공시)]")
        for d in r["comp_detail"]:
            yrs = ", ".join(f"{y}년 {v / 1e8:,.0f}억" for y, v in sorted(d.get("years", {}).items()))
            print(f"   {d['filed']} {d['plan']} | 목적: {d.get('purpose', '-')} | {d.get('basis', d.get('note', ''))}"
                  + (f" | {yrs}" if yrs else ""))
    if r["flags"]:
        print("\n[회사 단위 표시]")
        for fl in r["flags"]:
            print(f"   · {fl}")
    print("\n   ※ 이 도구는 판정하지 않는다 (결과만 표시)")


def quality_cmd(a) -> None:
    """분석 도구: 이익의 질 · 이익조정 신호 — 결과만 보여준다 (판정 없음)."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    if a.fetch:
        r0 = earnings_quality.analyze(cid)
        ys = [r0["rows"][0]["year"] - 1] + [x["year"] for x in r0["rows"]] if r0["rows"] else []
        miss = earnings_quality.missing_ceo_data(cid, ys)
        if miss and cid.startswith("KR:"):
            print(f"[DART 임원 현황] {len(miss)}건을 받습니다.")
            dart_officers.fetch(cid, miss)
        elif miss:
            print(f"[SEC 10-K 본문] {len(miss)}건을 받습니다.")
            promises.fetch_docs(cid, miss)
    r = earnings_quality.analyze(cid)
    print(f"\n=== {c['name']} | {cid} | 분석 도구: 이익의 질 · 이익조정 신호 (최근 5년, 결과만 표시) ===")
    if not r["rows"]:
        print("표시할 결과가 없습니다.")
    else:
        pct = lambda v: "-" if v is None else f"{v:+.1%}"  # noqa: E731
        mark = lambda b: "-" if b is None else ("●" if b else "·")  # noqa: E731
        print("(● 신호 있음, · 없음, - 계산 불가)\n")
        print(f"{'연도':>5} {'A 발생액/자산':>12} {'매출 증가':>9} {'매출채권':>9} {'B':>2} {'계약자산':>9} {'B*':>2}"
              f" {'재고':>9} {'C':>2} {'순이익/자산':>10} {'D':>2} {'E':>2}  대표이사")
        for x in r["rows"]:
            print(f"{x['year']:>5} {pct(x['accruals']):>12} {pct(x['rev_g']):>9} {pct(x['rec_g']):>9} {mark(x['B']):>2}"
                  f" {pct(x['ca_g']):>9} {mark(x['B_ca']):>2} {pct(x['inv_g']):>9} {mark(x['C']):>2}"
                  f" {pct(x['roa']):>10} {mark(x['D']):>2} {mark(x['E']):>2}  {x['ceo'] or '-'}")
        n = lambda k: sum(1 for x in r["rows"] if x[k])  # noqa: E731
        print(f"\n[5년 중 신호가 켜진 해] B 매출채권 {n('B')} | 계약자산 {n('B_ca')} | C 재고 {n('C')} | "
              f"D 작은 이익 {n('D')} | E 빅 배스 {n('E')}")
        print("   A 발생액/자산이 플러스 = 순이익이 영업CF보다 큼 (현금이 덜 들어온 이익)")
        notes = [(x["year"], t) for x in r["rows"] for t in x["notes"]]
        if notes:
            print("\n[연도별 표시]")
            for y, t in notes:
                print(f"   {y}: {t}")
    if r["flags"]:
        print("\n[회사 단위 표시]")
        for fl in r["flags"]:
            print(f"   · {fl}")
    print("\n   ※ 이 도구는 판정하지 않는다 (결과만 표시). 신호는 의심의 출발점이지 결론이 아니다.")


def safety_cmd(a) -> None:
    """분석 도구: 재무 안전성 — 결과만 보여주고, 분명한 위험 두 가지만 따로 표시."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    if a.fetch and cid.startswith("KR:"):
        miss = dart_xbrl.missing(cid)
        print(f"[DART 사업보고서 XBRL] {len(miss)}건을 받습니다.")
        dart_xbrl.fetch(cid)
    r = safety.analyze(cid)
    print(f"\n=== {c['name']} | {cid} | 분석 도구: 재무 안전성 (최근 5년, 결과만 표시) ===")
    if not r["rows"]:
        print("표시할 결과가 없습니다.")
    else:
        pct = lambda v: "-" if v is None else f"{v:.0%}"  # noqa: E731
        x2 = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
        yrs = lambda v: "-" if v is None else f"{v:.1f}년"  # noqa: E731
        print(f"\n{'연도':>5} {'A 부채비율':>10} {'B 유동비율':>10} {'C 당좌비율':>10} {'D 이자보상':>10} {'E 부채/영업CF':>12}")
        for x in r["rows"]:
            print(f"{x['year']:>5} {pct(x['debt_ratio']):>10} {pct(x['current']):>10} {pct(x['quick']):>10} "
                  f"{x2(x['icr']):>10} {yrs(x['debt_ocf']):>12}")
        print("\n   D 이자보상비율 = 영업이익 ÷ 이자비용 (배수). E = 부채총계를 영업CF로 갚는 데 걸리는 해")
        print("   ※ 이자비용은 보고 그대로: 한국(국제회계기준)은 리스 이자 포함, 미국은 대부분 미포함")
        notes = [(x["year"], t) for x in r["rows"] for t in x["notes"]]
        if notes:
            print("\n[연도별 표시]")
            for y, t in notes:
                print(f"   {y}: {t}")
    print("\n[분명한 위험] (자본잠식, 이자보상비율 1 미만)")
    if r["risks"]:
        for y, t in r["risks"]:
            print(f"   ● {y}: {t}")
    else:
        print("   없음")
    if r.get("spread_warn"):
        print("\n[경고: 스프레드 마이너스 = 빚이 독이 되는 해 (9-②)]  자세한 숫자: uv run data.py allocation <기업>")
        for y, v in r["spread_warn"]:
            print(f"   ● {y}: 스프레드 {v:+.1%} (ROA가 이자율보다 낮음)")
    if r["flags"]:
        print("\n[회사 단위 표시]")
        for fl in r["flags"]:
            print(f"   · {fl}")
    print("\n   ※ 이 도구는 통과선을 두지 않는다 (업종마다 적정 수준이 다름). 같은 업종끼리 비교해서 본다.")


def allocation_cmd(a) -> None:
    """자본 배분: 번 돈을 어디에 썼고 결과가 어땠나 (기준 3 주주환원을 합친 분석 도구, 판정 없음)."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    r = capital_allocation.analyze(cid)
    print(f"\n=== {c['name']} | {cid} | 자본 배분 (최근 5년, 결과만 표시) ===")
    rows = r["rows"]
    if not rows:
        print("표시할 결과가 없습니다.")
        return
    cur = rows[-1]["currency"] or ("KRW" if cid.startswith("KR:") else "USD")
    unit, dv = ("억 원", 1e8) if cur == "KRW" else (f"백만 {cur}", 1e6)
    f = lambda v: "-" if v is None else f"{v / dv:,.0f}"  # noqa: E731
    pc = lambda v: "-" if v is None else f"{v:+.0%}"  # noqa: E731
    print(f"(단위: {unit})\n")
    print(f"{'연도':>5} {'번 돈(영업CF)':>13} {'설비 재투자':>10} {'FCF':>9} {'주주환원':>9} {'FCF−환원':>9} "
          f"{'이자부부채 증감':>13} {'ROE':>6}")
    for x in rows:
        roe = "-" if x["roe"] is None else f"{x['roe']:.1%}"
        print(f"{x['year']:>5} {f(x['ocf']):>13} {f(x['capex']):>10} {f(x['fcf']):>9} {f(x['payout']):>9} "
              f"{f(x['left']):>9} {f(x['debt_change']):>13} {roe:>6}")
    print("   주주환원 = 배당 + 자사주 매입(임직원 보상 목적 제외). 자세한 내역: uv run data.py returns <기업>")
    print("   ROE = 연결 순이익 ÷ 평균 자본총계. 재투자는 설비만 (인수·지분 투자 제외)")

    fa = r["facts"]
    print("\n[ROE를 인정하나: 스프레드 = ROA − 이자율 (9-②, 플러스일 때만 빚으로 높인 ROE를 인정)]")
    print(f"{'연도':>5} {'ROE':>7} {'ROA(영업)':>10} {'이자율':>7} {'스프레드':>9}")
    p1 = lambda v: "-" if v is None else f"{v:.1%}"  # noqa: E731
    for x in rows:
        mark = "" if x.get("spread") is None else ("  ● 마이너스" if x["spread"] < 0 else "")
        why = f"  ({x['why']})" if x.get("why") else ""
        sp = "-" if x.get("spread") is None else f"{x['spread']:+.1%}"
        print(f"{x['year']:>5} {p1(x['roe']):>7} {p1(x.get('roa_op')):>10} {p1(x.get('rate')):>7} {sp:>9}{mark}{why}")
    print("   ROA = 영업이익 ÷ 평균 총자산, 이자율 = 이자비용 ÷ 평균 이자부 부채 (리스 포함은 회사가 보고한 그대로)")
    print("   이자율이 비정상적으로 낮거나 높으면 이자비용과 부채의 범위가 다를 수 있음 → 분석할 때 판단 (예: 금융 자회사)")
    print("\n[의도를 논의할 때 쓸 사실]")
    pe = fa["persistence"]
    print(f" ① 환원이 이어진 해: {pe['n']}/{pe['of']}년  (배당 {pe['div_years'] or '없음'}, 자사주 매입 {pe['buy_years'] or '없음'})")
    if fa["over_fcf"]:
        print(" ② 환원이 FCF보다 큰 해:")
        for y, p, fc, dc in fa["over_fcf"]:
            print(f"     {y}: 환원 {f(p)} > FCF {f(fc)}  | 이자부 부채 증감 {f(dc)}")
    else:
        print(" ② 환원이 FCF보다 큰 해: 없음")
    print(" ③ 자사주: 연도 | 취득 주식 | 소각 주식 | 처분 주식 | 연말 보유")
    num = lambda v: "-" if v is None else f"{v:,.0f}"  # noqa: E731
    for y, acq, ret_, dis, tr in fa["retire"]:
        print(f"     {y} | {num(acq)} | {num(ret_)} | {num(dis)} | {num(tr)}")
    if fa["timing"]:
        lab = "매입 결정 전 6개월 주가 변화" if cid.startswith("KR:") else "매입한 회계연도의 1년 주가 변화"
        print(f" ④ 매입 시점의 주가 흐름 ({lab}):")
        for t in fa["timing"]:
            tag = f" [보상 목적: {t['comp']}]" if t.get("comp") else ""
            amt = "" if not t.get("amount") else f" {f(t['amount'])}"
            print(f"     {t['date']} {t['kind']}{amt}: {pc(t['change'])}{tag}")
    else:
        print(" ④ 매입 시점의 주가 흐름: 해당 없음")
    pr = fa.get("promise", {})
    gr = ", ".join(f"{k} {v}건" for k, v in pr.get("grades", {}).items())
    print(f" ⑤ 발표한 환원 정책을 지켰나 (기준 1, {pr.get('scope')}): {pr.get('verdict')} ({pr.get('why')})"
          + (f" | {gr}" if gr else ""))
    if r["flags"]:
        print("\n[회사 단위 표시]")
        for fl in r["flags"]:
            print(f"   · {fl}")
    print("\n   ※ 판정하지 않는다. 주주환원의 의도는 회사마다 논의해서 판단한다 (프로필 4-2).")


def events_cmd(a) -> None:
    """수시공시 이벤트: 그때그때 보고 싶은 분류·검색어만 (외부 요청 없음)."""
    from datetime import date, timedelta
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    since = a.since or str(date.today() - timedelta(days=365))
    print(f"\n=== {c['name']} | {cid} | 수시공시 이벤트 ({since} 이후, 받아 둔 공시 목록 기준) ===")
    kinds = [k.strip() for k in (a.kinds or "").split(",") if k.strip()]
    if not kinds and not a.grep:
        print("\n[메뉴] 보고 싶은 분류를 --kinds 로 고르세요 (여러 개는 쉼표). 자유 검색어는 --grep")
        for k, n in events.menu_counts(cid, since).items():
            print(f"   {k:<8} {n:>4}건")
        print("\n   예: uv run data.py events <기업> --kinds 경영진,소송제재사고 --since 2024-01-01")
        print("   옵션: --no-sub (자회사 공시 빼기), --frequent (잦은 지분 변동 공시 넣기)")
        return
    bad = [k for k in kinds if k not in events.MENU]
    if bad:
        print(f"메뉴에 없는 분류: {bad}. 메뉴: {', '.join(events.MENU)}")
    rows = events.find(cid, kinds, since, a.grep, include_subsidiary=not a.no_sub, include_frequent=a.frequent)
    if not rows:
        print("해당하는 공시가 없습니다.")
    for r in rows:
        sub = " [자회사]" if r["subsidiary"] else ""
        print(f"   {r['filed']}  {r['kind']:<10} {r['title']}{sub}")
        print(f"              {r['url']}")
    print(f"\n   {len(rows)}건. 본문은: uv run data.py doc <기업> <접수번호> (받기 전 승인 필요)")
    print("   ※ 공시 목록은 기업 데이터를 받을 때 함께 갱신된다 (data.py get, 7일 지나면 다시 받음)")


def qual_cmd(a) -> None:
    """사업보고서(10-K)의 정성 부분: 그때그때 보고 싶은 주제·낱말만, 원문 그대로."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    f = qualitative.latest_annual(cid)
    print(f"\n=== {c['name']} | {cid} | 사업보고서 정성 부분 (원문 발췌, 요약 없음) ===")
    if not f:
        print("사업보고서(10-K)를 공시 목록에서 찾지 못했습니다.")
        return
    print(f"대상: {f['filed']} {f['title']} (접수번호 {f['rcept_no']})")
    if not qualitative.have(cid, f["rcept_no"]):
        if a.fetch:
            print("본문을 받습니다 (한국 사업보고서는 30초~2분)...")
            documents.fetch(cid, f["rcept_no"])
        else:
            print("본문을 아직 받지 않았습니다. 받으려면 승인 후: uv run data.py qual <기업> --fetch")
            return
    topics = [t.strip() for t in (a.topics or "").split(",") if t.strip()]
    if not topics and not a.grep:
        print("\n[메뉴] 보고 싶은 주제를 --topics 로 고르세요 (여러 개는 쉼표). 자유 검색어는 --grep")
        for t, (kr_rx, us_rx) in qualitative.TOPICS.items():
            print(f"   {t:<6} 찾는 말: {kr_rx if cid.startswith('KR:') else us_rx}")
        return
    hits = qualitative.search(cid, f["rcept_no"], topics, a.grep, limit=0 if a.full else 30)
    if not hits:
        print("해당하는 부분이 없습니다.")
    for h in hits:
        print(f"\n[{h['topic']}] {h['section']}  (문서 {h['part']} {h['part_title'] or ''}, {h['line']}번째 줄)")
        for ln in h["text"].split("\n"):
            print(f"   {ln[:300]}")
    more = "" if a.full else " (최대 30곳. 전부 보려면 --full)"
    print(f"\n   {len(hits)}곳{more}. 출처: {f['title']}, 접수번호 {f['rcept_no']}")
    print("   절 전체를 보려면: uv run data.py doc <기업> <접수번호> --section <제목 일부>")


def news_cmd(a) -> None:
    """뉴스: 최근 1개월 제목·언론사·날짜·링크만 (요약 없음)."""
    import re as _re
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    extra = [t.strip() for t in (a.terms or "").split(",") if t.strip()]
    if a.fetch:
        news.fetch(cid, extra)
        if cid.startswith("KR:"):
            news.fetch_trend(cid)
    g = news.grouped(cid, extra)
    print(f"\n=== {c['name']} | {cid} | 뉴스 (최근 {news.DAYS}일, 제목·링크만, 요약 없음) ===")
    if not g["all_own"] and not g["산업·경쟁"]:
        print("받아 둔 기사가 없습니다. 받으려면 승인 후: uv run data.py news <기업> --fetch [--terms 경쟁사,산업낱말]")
        return
    print(f"회사 검색어 '{news.query_for(cid)}' (제목에 이 이름이 있는 기사만)"
          + (f" | 산업·경쟁 검색어 {extra}" if extra else ""))
    limit = None if a.full else 15

    name = news.query_for(cid)

    def show(title, rows, note, min_sources=news.MIN_SOURCES, drop=None):
        if a.grep:
            rows = [r for r in rows if _re.search(a.grep, r["title"], _re.I)]
        ev = news.events_of(rows, min_sources, drop or {name})
        print(f"\n[{title}] {len(ev)}개 사건 (기사 {len(rows)}건에서)  — {note}")
        for e in ev[:limit]:
            print(f"   {e['date']:%Y-%m-%d}  {len(e['sources'])}곳 {e['n']}건  {e['title'][:80]}")
            print(f"              {e['link']}")
        if limit and len(ev) > limit:
            print(f"   … 처음 {limit}개만. 전부 보려면 --full")

    show("(가) 사건", g["사건"], "공시와 연결되는지 events 로 확인")
    show("(나) 분위기·시황", g["분위기·시황"], "주가·시황 기사 (2곳 규칙 없이 같은 기사만 묶음)", min_sources=1)
    print("   주별 회사 기사 수 (Google / 네이버):  "
          + "  ".join(f"{w} {gg}/{nn}" for w, gg, nn in news.weekly_counts(g["all_own"])))
    print("   ※ 기사 수로는 추세를 판단할 수 없음: 네이버는 최대 1,000건(큰 회사는 최근 며칠), Google RSS는 관련도 순 약 100건")
    tr = news.load_trend(cid) if cid.startswith("KR:") else None
    if tr and tr.get("week"):
        from datetime import date as _date, timedelta as _td
        wk = tr["week"]
        fetched = _date(int(tr["fetched"][:4]), int(tr["fetched"][4:6]), int(tr["fetched"][6:8]))
        # 받은 날 기준으로 아직 끝나지 않은 주는 값이 낮게 나오므로 평균·최대에서 빼고 '진행 중'으로 표시
        full = [(p, v) for p, v in wk if _date.fromisoformat(p) + _td(days=7) <= fetched]
        partial = [(p, v) for p, v in wk if (p, v) not in full]
        avg = sum(v for _, v in full) / len(full) if full else 0
        print(f"   네이버 검색어 트렌드 '{news.query_for(cid)}' (받은 날 {tr['fetched']}, 최근 1년 중 최대 = 100인 상대값)")
        print("     최근 4주: " + "  ".join(f"{p[5:]} {v:.0f}" for p, v in full[-4:])
              + "".join(f"  ({p[5:]} 주는 진행 중 {v:.0f})" for p, v in partial)
              + f"  | 1년 평균 {avg:.0f}, 1년 최대 주 {max(full, key=lambda x: x[1])[0] if full else '-'}")
        if tr.get("date"):
            print("     최근 7일 (일 단위, 30일 중 최대 = 100): " + "  ".join(f"{p[5:]} {v:.0f}" for p, v in tr["date"][-7:]))
    elif cid.startswith("KR:"):
        print("   네이버 검색어 트렌드: 받지 않음 (애플리케이션에 '검색어 트렌드' API를 켠 뒤 --fetch)")
    if extra:
        show("(다) 산업·경쟁", g["산업·경쟁"], "경쟁사 이름·산업 낱말이 제목에 있는 기사", drop=set(extra))
    else:
        print("\n[(다) 산업·경쟁] 검색어 없음. 경쟁사 이름·산업 낱말을 주면 따로 받음 (승인 후): "
              "--fetch --terms \"SK하이닉스,HBM,메모리 가격\"")
    print(f"\n   ※ 줄이기: 광고·홍보성 기사 뺌, 제목 낱말 {news.SAME_EVENT:.0%} 이상 겹치고 {news.SAME_DAYS}일 안이면 한 사건, "
          f"{news.MIN_SOURCES}곳 이상 언론사가 다룬 사건만 (시황은 묶기만). 언론사는 주소로 통일")
    print("   ※ 판단은 공시로 한다 (프로필 2번). 뉴스는 시야를 넓히는 데 쓴다")


def macro_cmd(a) -> None:
    """거시 지표: 금리·환율·유가 (판정 없음, 살 시점 참고용)."""
    if a.fetch:
        macro.fetch()
    print("\n=== 거시 지표 (2주차 6번: 살 시점 참고용, 판정 없음) ===\n")
    print(f"   {'지표':<26} {'최근':>18} {'1년 전':>9} {'5년 최저~최고':>18}  출처")
    for r in macro.load():
        if not r["points"]:
            print(f"   {r['name']:<26} {'받지 않음':>18}  ({r['source']} {r['code']})")
            continue
        d, v = r["last"]
        ya = "-" if r["year_ago"] is None else f"{r['year_ago']:,.2f}"
        last = f"{v:,.2f} ({d})"
        rng = f"{r['low']:,.2f}~{r['high']:,.2f}"
        print(f"   {r['name']:<26} {last:>18} {ya:>9} {rng:>18}  {r['source']} {r['code']} ({r['unit']})")
    print("\n   받으려면 승인 후: uv run data.py macro --fetch  (키: .env 의 ECOS_API_KEY, FRED_API_KEY)")


def related_cmd(a) -> None:
    """특수관계자 거래 목록 (7-④): 대주주 쪽 매입 ÷ 매출. 대주주 쪽인지는 사용자가 고른다."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    print(f"\n=== {c['name']} | {cid} | 특수관계자 거래 (사업보고서 XBRL 주석, 연결, 판정 없음) ===")
    if not cid.startswith("KR:"):
        print("한국 기업만 지원합니다 (미국 10-K는 특수관계자 거래가 구조화된 숫자로 거의 없음).")
        return
    cps = related_party.counterparties(cid)
    if not cps:
        print("특수관계자 거래 숫자가 없습니다. 사업보고서 XBRL(2022년 이후)을 받았는지 확인하세요: "
              "uv run data.py safety <기업> --fetch (승인 필요)")
        return
    if a.owner:
        idx = [int(x) for x in a.owner.split(",") if x.strip().isdigit()]
        picks = [cps[i - 1] for i in idx if 1 <= i <= len(cps)]
        p = related_party.save_owner_side(cid, picks)
        print(f"[기록] 대주주 쪽으로 고른 상대 {len(picks)}곳을 저장했습니다: {p}")
    saved = related_party.load_owner_side(cid) or {}
    chosen = {x["member"] for x in saved.get("owner_side", [])}
    ly = cps[0]["last_year"]
    eok = lambda v: "-" if not v else f"{v / 1e8:,.0f}"  # noqa: E731
    print(f"(금액: {ly}년, 억 원. '후보' = 회사가 지배기업·기업집단 계열사·유의적 영향력 행사 기업으로 분류, "
          f"'?' = 회사가 분류를 붙이지 않음 (지배회사일 수도 있음). 확정은 직접)\n")
    print(f"{'번호':>4}  {'':4} {'분류':<14} {'거래 상대':<28} {'매입·비용':>10} {'매출·수익':>10} {'자산 거래':>9}")
    for i, x in enumerate(cps, 1):
        mark = "선택" if x["member"] in chosen else ("후보" if x["owner_hint"] else ("?" if x["category"] == "미분류" else ""))
        lst = x["last"]
        print(f"{i:>4}  {mark:4} {x['category'][:12]:<14} {x['name'][:26]:<28} {eok(lst.get('매입')):>10} "
              f"{eok(lst.get('매출')):>10} {eok(lst.get('자산')):>9}")
    if chosen:
        print(f"\n[대주주 쪽 매입 ÷ 매출]  (기록: {saved.get('decided')}, {len(chosen)}곳)")
        for r in related_party.ratios(cid, list(chosen)):
            rt = "-" if r["ratio"] is None else f"{r['ratio']:.2%}"
            print(f"   {r['year']}: 매입 {eok(r['purchase'])}억 ÷ 매출 {eok(r['revenue'])}억 = {rt}")
    else:
        print("\n대주주 쪽 상대를 고르면 비율이 계산됩니다: uv run data.py related <기업> --owner 1,3,5")
    print("\n   ※ 주의 기준(%)은 분석할 때 판단한다 (숫자 기준 3). '기타'로 묶인 상대는 구성을 알 수 없다.")


def runway_cmd(a) -> None:
    """버티는 힘: 연구개발비(비용 처리분), 현금 + 단기 금융자산, 1년에 빠져나가는 현금, 몇 년 버티나 (판정 없음)."""
    c = resolve_local(a.query, a.pick)
    peers = [resolve_local(p.strip(), None) for p in (a.peers or "").split(",") if p.strip()]
    for t in [c] + peers:
        cid = t["company_id"]
        r = runway.table(cid)
        cur = r["currency"]
        unit, div = ("억원", 1e8) if cur == "KRW" else (f"백만 {cur}", 1e6)

        def f(v):
            return "-" if v is None or v != v else f"{v / div:,.0f}"

        start = runway.START_YEAR.get(cid)
        print(f"\n=== {t['name']} | {cid} | 버티는 힘 (단위: {unit}, 연결)"
              + (f" — {start}년부터 (사용자 결정)" if start else "") + " ===")
        print(f"   {'연도':<6}{'연구개발비':>10}{'현금':>10}{'단기금융':>10}{'합계':>10}{'(기타금융)':>11}"
              f"{'영업CF':>10}{'설비투자':>10}{'빠져나감':>10}{'버티는 해':>9}")
        for x in r["rows"]:
            ok = x["ocf"] is not None and x["ocf"] == x["ocf"] and x["capex"] is not None and x["capex"] == x["capex"]
            if ok and x["burn"] is None:
                rw = f"남음(+{f(x['ocf'] - x['capex'])})"      # 사용자 결정 b: 남은 금액 표시
            else:
                rw = "-" if x["runway"] is None else f"{x['runway']:.1f}년"
            state = "" if not ok else ("①" if x["burn"] is None else ("②" if x["ocf"] >= 0 else "③"))
            print(f"   {x['year']:<6}{f(x['rnd']):>10}{f(x['cash']):>10}{f(x['short']):>10}{f(x['total']):>10}"
                  f"{'(' + f(x['other']) + ')':>11}{f(x['ocf']):>10}{f(x['capex']):>10}{f(x['burn']):>10}{rw:>13} {state}")
        blanks = [f"{x['year']}: {x['rnd_reason'][:60]}" for x in r["rows"] if x["rnd"] is None and x["rnd_reason"]]
        last = r["rows"][-1] if r["rows"] else {}
        print(f"   현금에 넣은 줄 ({last.get('year', '')}): {', '.join(last.get('lines', [])) or '-'}")
        print("   연구개발비 출처: " + ("SEC 10-K ResearchAndDevelopmentExpense" if cid.startswith("US:")
                                    else "inputs/case3/rnd_expensed.json (연결 주석에서 옮겨 적음, 접수번호 포함)"))
        for b in blanks[:1]:
            print(f"   연구개발비 빈칸 — {b}…")
        if any(x["finance_arm"] for x in r["rows"]):
            print("   ※ 연결에 금융 자회사(금융업채권)가 있음: 현금·영업CF에 금융업이 섞여 있어 자동차 사업만의 숫자가 아님")

        # 빌릴 능력 (A 이미 빌린 정도, B 이자 감당) · 주식 조달 (E) — 버티는 해 계산에는 넣지 않음
        ys = [x["year"] for x in r["rows"]]
        b = runway.borrowing(cid, ys)

        def g(v, p=2):
            return "-" if v is None or v != v else f"{v:.{p}f}"
        print(f"\n   [빌릴 능력·주식 조달] (단위: {unit})")
        print(f"   {'연도':<6}{'부채비율':>9}{'이자보상':>9}{'이자부부채':>11}{'순차입금':>11}{'재무활동CF':>11}{'주식발행':>10}"
              + ("" if cid.startswith("US:") else f"{'신종자본증권':>11}"))
        for x in b:
            print(f"   {x['year']:<6}{g(x['debt_ratio']):>9}{g(x['icr'], 1):>9}{f(x['debt']):>11}{f(x['net_debt']):>11}"
                  f"{f(x['fin_net']):>11}{f(x['equity']):>10}" + ("" if cid.startswith("US:") else f"{f(x['hybrid']):>11}"))
        wb = runway.with_borrowing(cid, r["rows"])
        print(f"\n   [빌린 돈까지 쓸 때 버티는 해] ① 부채비율 상한 = 최근 5년 최고치  ④ 이자보상 1배까지 (단위: {unit})")
        print(f"   {'연도':<6}{'①상한':>8}{'①더빌림':>11}{'①버티는해':>11}{'이자율':>8}{'④더빌림':>11}{'④버티는해':>11}")
        for x in wb:
            def yy(v, room):
                if x["burn"] is None and x["ocf"] is not None and x["ocf"] == x["ocf"]:
                    return "남음"
                return "-" if v is None else f"{v:.1f}년"
            r4 = f(x["room4"]) if x["room4"] is not None else (x["why4"] or "-")
            print(f"   {x['year']:<6}{g(x['dr_cap']):>8}{f(x['room1']):>11}{yy(x['runway1'], x['room1']):>11}"
                  f"{('-' if not x['rate'] else f'{x[chr(114)+chr(97)+chr(116)+chr(101)]:.1%}'):>8}{r4:>11}{yy(x['runway4'], x['room4']):>11}")
        if wb:
            print(f"   이자율 출처: {wb[-1]['rate_src']}. 영업손실인 해는 ④ 더 빌림 = 0")
        sp_ = runway.supernal(cid)
        if sp_:
            print(f"\n   [공동기업 슈퍼널 (지분 {sp_['stake']:.2%}, 지분법 — 현대차 연결에 들어 있지 않음)] (단위: {unit})")
            print(f"   {'연도':<6}{'매출':>8}{'순손실':>10}{'현대차 몫':>10}{'유동자산':>10}{'자산':>10}{'부채':>9}{'자본':>10}{'현대차 장부가':>13}")
            for y in sorted(sp_["rows"]):
                s_ = sp_["rows"][y]
                print(f"   {y:<6}{f(s_['revenue']):>8}{f(s_['net_income']):>10}{f(s_['parent_share_loss']):>10}"
                      f"{f(s_['current_assets']):>10}{f(s_['assets']):>10}{f(s_['liabilities']):>9}{f(s_['equity']):>10}"
                      f"{f(s_['book_value']):>13}")
            print("   ※ 현금·영업CF 미공시 → 버티는 해 계산 불가. 출처: 현대차 연결 주석 공동기업 요약재무정보"
                  " (inputs/case3/supernal.json). 현대차 몫 = 순손실 × 지분율 (단순 계산)")
        if r.get("vehicle"):
            print("   ※ 현대차는 차량 부문 기준 (금융 자회사 제외, 사용자 결정): 현금·영업CF·투자·부채·자본·영업이익·차입금은 부문정보 주석"
                  " (inputs/case3/hyundai_vehicle.json). 투자는 '유형ㆍ무형자산 취득 및 처분' 순액 → 정의 차이. 연구개발비·이자비용·재무활동CF·주식발행은 연결")
        cap = runway.capacity_facts(cid)
        cl = cap.get("credit_lines")
        if cl:
            print(f"   차입 약정 (총 한도, {cl['as_of']}): {cl['summary']}")
            print(f"     [출처: {cl['rcept_no']}, {cl['note']}]")
        if cap.get("caution"):
            print(f"   ※ {cap['caution']}")
        for e in cap.get("equity_events", []):
            amt = "-" if e.get("usd_m") is None else f"${e['usd_m']:,.1f}M"
            print(f"   · {e['when']:<16} {e['what']}  {amt}")
        if cap.get("equity_events"):
            print(f"     [출처: SEC 10-K FY2025, accn {cl['rcept_no'] if cl else ''}, Liquidity and Capital Resources]")
            print("   ※ 주식발행 열은 표준 태그로 잡히는 것만 (공모 증자·ATM은 회사 고유 태그라 빠짐 → 위 목록)")
    print("\n   ※ 빠져나감 = 영업CF − 설비투자가 마이너스일 때 그 크기. 버티는 해 = 합계 ÷ 빠져나감")
    print("   ※ 상태: ① 번 돈으로 설비투자까지 하고 남음 (남은 금액 표시)  ② 영업CF는 플러스지만 설비투자가 더 큼"
          " (버티는 해 = 이 속도로 투자하며 자기 돈만 쓸 때)  ③ 영업CF부터 마이너스")
    print("   ※ (기타금융)은 기타금융자산·기타투자자산(유동). 합계에 넣지 않음 (사용자 결정)")
    print("   ※ 버티는 해에는 차입 여력·증자·정부 지원을 넣지 않음. 빌릴 능력은 아래 표로 따로 봄")
    print("   ※ 부채비율·이자보상비율은 safety 도구 값 그대로. 순차입금 = 이자부 부채 − (현금 + 단기 금융자산)")
    print("   ※ 차입 약정은 총 한도만 (이미 빌린 금액이 섞여 있고, 사용 금액이 공시되지 않아 안 쓴 한도는 알 수 없음)")


def price_cmd(a) -> None:
    """잠정 가격 판단: PER·PBR — 숫자와 경쟁사 비교만 보여준다 (판정 없음)."""
    c = resolve_local(a.query, a.pick)
    peers = [resolve_local(p.strip(), None) for p in (a.peers or "").split(",") if p.strip()]
    targets = [c] + peers
    if a.fetch:
        for t in targets:
            cid = t["company_id"]
            print(f"[{t['name']}]")
            prices.fetch(cid)
            if cid.startswith("KR:"):
                ys = dart_shares.target_years()
                miss = [m for m in dart_shares.missing(cid, ys) if m[0] == "stockTotqySttus"]
                if miss:
                    print(f"  [DART 주식 수] {len(miss)}건")
                    dart_shares.fetch(cid, ys)
    r = price_level.analyze(c["company_id"])
    print(f"\n=== {c['name']} | {c['company_id']} | 잠정 가격 판단: PER·PBR (판정 없음) ===")
    m = r.get("meta") or {}
    if m:
        print(f"주가 출처: {m.get('source')} {m.get('symbol')} ({m.get('currency')}), 받은 시각 {m.get('fetched_at')}")
    x = lambda v: "-" if v is None else f"{v:.1f}배"  # noqa: E731
    num = lambda v: "-" if v is None else f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"  # noqa: E731
    if r["rows"]:
        print(f"\n{'회계연도':>7} {'날짜':>11} {'주가':>11} {'PER(그해)':>10} {'PER(5년평균)':>12} {'PBR':>7}  "
              f"{'주당순이익':>10} {'5년평균':>10} {'주당장부가치':>12}")
        for w in r["rows"]:
            print(f"{w['year']:>7} {str(w['date'] or '-'):>11} {num(w['price']):>11} {x(w['per']):>10} {x(w['per_avg']):>12} "
                  f"{x(w['pbr']):>7}  {num(w['eps']):>10} {num(w['eps_avg']):>10} {num(w['bps']):>12}")
        cur = r["current"]
        if cur:
            print(f"{'현재':>7} {str(cur['date']):>11} {num(cur['price']):>11} {x(cur['per']):>10} {x(cur['per_avg']):>12} "
                  f"{x(cur['pbr']):>7}  ({cur['basis_year']}회계연도 이익·장부가치 기준)")
        adj = r.get("adjustments") or {}
        if adj.get("error"):
            print(f"\n[조정 장부가치] {adj['error']} ({adj['path']})")
        elif adj.get("items") and cur and cur.get("adj_pbr") is not None:
            print(f"\n[조정 장부가치 (4-①, 직접 입력한 항목)]  {adj['path']}")
            for it in adj["items"]:
                print(f"   {'+' if it['signed'] >= 0 else '−'} {num(abs(it['signed']))}  {it.get('name', '')}"
                      f"  | 이유: {it.get('reason', '-')} | 출처: {it.get('source', '-')} | 기준일: {it.get('as_of', '-')}")
            print(f"   주당 장부가치 {num(cur['bps'])} → {num(cur['adj_bps'])}  |  PBR {x(cur['pbr'])} → 조정 PBR {x(cur['adj_pbr'])}")
            print("   ※ 세금 효과는 반영하지 않음 (입력한 금액 그대로)")
        elif cur:
            print(f"\n[조정 장부가치] 입력 없음. 수치화되는 장부 밖 가치가 있으면 {adj.get('path')} 에 적으면 조정 PBR이 계산됨")
        notes = [(w["year"], t) for w in r["rows"] for t in w["notes"]]
        if notes:
            print("\n[연도별 표시]")
            for y, t in notes:
                print(f"   {y}: {t}")
    if peers:
        print("\n[경쟁사 비교: 현재]")
        print(f"   {'기업':<16} {'PER(그해)':>10} {'PER(5년평균)':>12} {'PBR':>7}  기준 회계연도")
        for t in targets:
            rr = r if t is c else price_level.analyze(t["company_id"])
            cu = rr.get("current")
            if cu:
                print(f"   {t['name'][:14]:<16} {x(cu['per']):>10} {x(cu['per_avg']):>12} {x(cu['pbr']):>7}  {cu['basis_year']}")
            else:
                print(f"   {t['name'][:14]:<16} 계산 안 됨: {'; '.join(rr['flags'])[:80]}")
    if r["flags"]:
        print("\n[회사 단위 표시]")
        for fl in r["flags"]:
            print(f"   · {fl}")
    print("\n   ※ 판정하지 않는다. 경쟁사 비교가 우선, 자기 과거는 보조. 내재가치 계산은 13~14주차 이후에 더한다.")


def us_promises_cmd(c: dict, a) -> None:
    """미국 기업: 10-K의 주주환원 의도 표명 (P1 배당 증액, P2 배당 지속)."""
    cid = c["company_id"]
    print(f"\n=== {c['name']} | {cid} | 기준 1: 경영진의 약속 이행 기록 (미국: 10-K 주주환원 의도) ===")
    if a.fetch:
        miss = us_promises.missing_docs(cid)
        print(f"[본문 수집] 10-K {len(miss)}건을 SEC에서 받습니다.")
        r = promises.fetch_docs(cid, miss)
        print(f"  → 받음 {r['done']}건, 실패 {len(r['failed'])}건\n")
    r = us_promises.evaluate(cid)
    print(f"현 CEO (FY{r['latest_fy']} 10-K 서명): {r['current_ceo'] or '확인 불가'}")
    ceos_seen = list(dict.fromkeys(v for v in r["ceo_by_fy"].values() if v))
    print(f"10-K 서명 CEO: " + ", ".join(f"{n} (FY{min(y for y, v in r['ceo_by_fy'].items() if v == n)}~"
                                          f"{max(y for y, v in r['ceo_by_fy'].items() if v == n)})" for n in ceos_seen) + "\n")
    if not r["promises"]:
        print("자동 판정 대상인 주주환원 의도 문장(P1 배당 증액, P2 배당 지속)이 10-K에 없습니다.")
    for p in r["promises"]:
        state = p.status + (f" {p.grade}" if p.grade else "")
        print(f"[{p.kind}] CEO {p.result_filed} 시기 → {state}")
        for n in p.notes:
            print(f"       · {n}")
        for ck in p.units:
            print(f"       - FY{ck['fy']}: {ck['result']}  ({ck['detail']})")
    if r["references"]:
        print(f"\n[확인해볼 문장 {len(r['references'])}건] 자동 판정하지 않음 (P3 금액 있는 배당 예정, 설비투자 계획, 일반 문장 등)")
        for x in r["references"][:12]:
            yrs = f"FY{x['years'][0]}" + (f"~FY{x['years'][-1]}" if x['years'][-1] != x['years'][0] else "")
            print(f"   {yrs} ({len(x['years'])}회) {x['text'][:170]}")
        if len(r["references"]) > 12:
            print(f"   … 외 {len(r['references']) - 12}건")
    miss = us_promises.missing_docs(cid)
    if miss:
        print(f"\n[아직 받지 않은 10-K {len(miss)}건]")
        for f in miss:
            print(f"   {f['filed']} {f['rcept_no']} {f['title']}")
        print("   → 받으려면 승인 후: uv run data.py promises <기업> --fetch")
    print("\n[회사 판정] (현 CEO 재임 기간으로 판정, 이전 CEO 시절 불이행은 한 단계 낮춤)")
    cur = [us_promises._norm_person(r["current_ceo"] or "")]
    v = promises.verdict(r["promises"], cur, "result")
    print(f"   {v['verdict']}  ({v['why']})  | 진행 중 {v['pending']}건, 확인 필요 {v['unresolved']}건")
    print("   ※ 미국 기업은 같은 의도 문장을 약속 1건으로 세므로 대부분 '판정 불가'가 된다 (기준 문서 7. 미국 기업)")


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
