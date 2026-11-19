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

  투자기준 2: 꾸준한 현금 창출 (결과만 보여줌, 판정 없음, 외부 요청 없음)
  uv run data.py cashflow 삼성전자 [--source]      # 최근 5년 영업CF·FCF·현금 전환율 + 표시

  투자기준 3: 주주환원 기록 (결과만 보여줌, 판정 없음)
  uv run data.py returns 삼성전자 [--source]       # 최근 5년 배당·자사주·소각·환원 비율·주식 수 (외부 요청 없음)
  uv run data.py returns 삼성전자 --fetch          # 한국: DART 주식 수 데이터를 받은 뒤 표시 (사용자 승인 후)

  투자기준 4: 이익의 질 · 이익조정 신호 (결과만 보여줌, 판정 없음)
  uv run data.py quality 삼성전자                  # 최근 5년 발생액·매출채권·재고·작은 이익·빅 배스 (외부 요청 없음)
  uv run data.py quality 삼성전자 --fetch          # 대표이사 데이터(한국 DART 임원 현황 / 미국 10-K)를 받은 뒤 표시 (승인 후)

  투자기준 5: 재무 안전성 (결과만 보여줌 + 분명한 위험 표시)
  uv run data.py safety 삼성전자                   # 최근 5년 부채비율·유동비율·당좌비율·이자보상비율·부채/영업CF
  uv run data.py safety 삼성전자 --fetch           # 한국: 이자비용용 사업보고서 XBRL을 받은 뒤 표시 (승인 후)

  잠정 가격 판단: PER·PBR (판정 없음, 13~14주차 내재가치 계산 전까지의 비교 기준)
  uv run data.py price 삼성전자 --peers SK하이닉스   # 최근 5년·현재 PER(그해 이익/5년 평균)·PBR + 경쟁사 비교
  uv run data.py price 삼성전자 --fetch            # 주가(Yahoo Finance)·한국 주식 수(DART)를 받은 뒤 표시 (승인 후)
"""
import argparse
import json
import sys

import pandas as pd

from pipeline import (capital_allocation, cashflow, dart_officers, dart_shares, dart_xbrl, documents, earnings_quality,
                      funding, price_level, prices, promises, returns, safety, service, standard, us_promises)

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
                                   "cashflow", "returns", "quality", "safety", "price", "allocation", "list"])
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
    p.add_argument("--attribute", choices=["plan", "result"], default="result",
                   help="promises: 현 대표이사의 기록을 결과 시점(result, 기본·사용자 결정 2026-11-18)/약속 시점(plan) 대표이사로 볼지")
    a = p.parse_args()

    if a.cmd == "list":
        print(service.collected_companies().to_string(index=False))
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
    if a.cmd == "allocation":
        allocation_cmd(a)
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
    """투자기준 2: 꾸준한 현금 창출 — 결과만 보여준다 (판정 없음)."""
    c = resolve_local(a.query, a.pick)
    r = cashflow.analyze(c["company_id"])
    print(f"\n=== {c['name']} | {c['company_id']} | 기준 2: 꾸준한 현금 창출 (최근 5년, 결과만 표시) ===")
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
        print("   ※ 통과선이 아닌 참고용 개수 (기준 2는 판정하지 않음)")
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
    """투자기준 3: 주주환원 기록 — 결과만 보여준다 (판정 없음)."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    if a.fetch and cid.startswith("KR:"):
        ys = dart_shares.target_years()
        print(f"[DART 주식 수 데이터] {len(dart_shares.missing(cid, ys))}건을 받습니다.")
        dart_shares.fetch(cid, ys)
    r = returns.analyze(cid)
    print(f"\n=== {c['name']} | {cid} | 기준 3: 주주환원 기록 (최근 5년, 결과만 표시) ===")
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
    print("\n   ※ 기준 3은 판정하지 않는다 (결과만 표시)")


def quality_cmd(a) -> None:
    """투자기준 4: 이익의 질 · 이익조정 신호 — 결과만 보여준다 (판정 없음)."""
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
    print(f"\n=== {c['name']} | {cid} | 기준 4: 이익의 질 · 이익조정 신호 (최근 5년, 결과만 표시) ===")
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
    print("\n   ※ 기준 4는 판정하지 않는다 (결과만 표시). 신호는 의심의 출발점이지 결론이 아니다.")


def safety_cmd(a) -> None:
    """투자기준 5: 재무 안전성 — 결과만 보여주고, 분명한 위험 두 가지만 따로 표시."""
    c = resolve_local(a.query, a.pick)
    cid = c["company_id"]
    if a.fetch and cid.startswith("KR:"):
        miss = dart_xbrl.missing(cid)
        print(f"[DART 사업보고서 XBRL] {len(miss)}건을 받습니다.")
        dart_xbrl.fetch(cid)
    r = safety.analyze(cid)
    print(f"\n=== {c['name']} | {cid} | 기준 5: 재무 안전성 (최근 5년, 결과만 표시) ===")
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
    if r["flags"]:
        print("\n[회사 단위 표시]")
        for fl in r["flags"]:
            print(f"   · {fl}")
    print("\n   ※ 기준 5는 통과선을 두지 않는다 (업종마다 적정 수준이 다름). 같은 업종끼리 비교해서 본다.")


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
