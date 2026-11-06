"""기업 원본 데이터 탐색기.  실행:  uv run streamlit run dashboard.py

기업명(국내·해외)을 입력하면 → 데이터가 없거나 오래됐을 때 자동 수집 → 원본 그대로 표시.
"""
import io
import json

import pandas as pd
import streamlit as st

from pipeline import service
from pipeline.config import REFRESH_DAYS, YEARS, dart_key

st.set_page_config(page_title="기업 원본 데이터 탐색기", layout="wide")


@st.cache_data(ttl=3600, show_spinner="기업 목록을 불러오는 중...")
def search(q: str):
    return service.search(q)


def label(c: dict) -> str:
    market = "국내" if c["market"] == "KR" else "해외"
    tick = ", ".join(c.get("tickers", [])) or c.get("ticker", "")
    extra = f" · {c['exchange']}" if c.get("exchange") else ""
    return f"[{market}] {c['name']} ({tick}{extra})"


def to_csv(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf)
    return buf.getvalue().encode("utf-8-sig")  # 엑셀에서 한글이 깨지지 않도록 BOM


# ---------------- 사이드바: 검색 ----------------
with st.sidebar:
    st.header("기업 검색")
    q = st.text_input("기업명 또는 종목코드/티커", placeholder="삼성전자, 005930, Apple, AAPL, TSMC")
    selected = None
    if q:
        results, warnings = search(q)
        for w in warnings:
            st.caption(f"⚠️ {w}")
        if results:
            idx = st.radio("검색 결과", range(len(results)), format_func=lambda i: label(results[i]))
            selected = results[idx]
        else:
            st.warning("검색 결과가 없습니다. 해외 기업은 영문명이나 티커로 검색해 보세요.")

    done = service.collected_companies()
    if not done.empty:
        st.divider()
        st.caption("이미 수집된 기업")
        pick = st.selectbox("바로 열기", ["-"] + done["company_id"].tolist(),
                            format_func=lambda cid: "-" if cid == "-" else
                            f"{done.set_index('company_id').loc[cid, 'name']} ({done.set_index('company_id').loc[cid, 'ticker']})")
        if pick != "-" and selected is None:
            row = done.set_index("company_id").loc[pick]
            selected = {"company_id": pick, "market": row["market"], "name": row["name"],
                        "source_key": pick.split(":", 1)[1], "tickers": [row["ticker"]], "name_en": ""}

    st.divider()
    st.caption(f"수집 범위: 최근 {YEARS}년 · {REFRESH_DAYS}일이 지나면 자동 재수집\n\n"
               "출처: 국내 DART(금융감독원), 해외 SEC EDGAR(미국 증권거래위원회)")

st.title("기업 원본 데이터 탐색기")

if selected is None:
    st.markdown(
        "왼쪽에 **기업명**을 입력하세요. 처음 보는 기업이면 공식 공시 시스템에서 바로 수집합니다.\n\n"
        "- **국내 상장사**: DART 사업보고서 재무제표 전체 계정, 공시 목록, 기업개황\n"
        "- **해외 상장사**: SEC EDGAR에 공시하는 기업(미국 상장사 + ADR 상장 해외기업). XBRL 재무 팩트 전체, 공시 목록\n\n"
        "이 화면의 모든 값은 원천 데이터를 **가공 없이** 보여줍니다 (연도별로 표 배열만 함)."
    )
    if not dart_key():
        st.info("현재 DART API 키가 설정되지 않아 국내 기업 검색이 꺼져 있습니다.")
    st.stop()

if selected["market"] == "KR" and not dart_key():
    st.error("DART API 키가 없어 국내 기업을 수집할 수 없습니다.")
    st.stop()

cid = selected["company_id"]
col1, col2 = st.columns([5, 1])
force = col2.button("🔄 다시 수집", help="원천에서 최신 데이터를 다시 받습니다")
try:
    with st.spinner(f"{selected['name']} 데이터를 확인하는 중... (처음 수집은 10~60초)"):
        result = service.ensure(selected, force=force)
    if result.get("collected"):
        st.toast("수집 완료: " + ", ".join(f"{k} {v:,}" for k, v in result.items() if k != "collected"))
except Exception as e:
    st.error(f"수집 실패: {e}")
    st.stop()

c = service.get_company(cid)
src = "DART (금융감독원 전자공시)" if c["market"] == "KR" else "SEC EDGAR"
col1.subheader(f"{c['name']}  ·  {c['ticker']}")
col1.caption(f"출처: {src} · 고유번호 {cid.split(':')[1]} · 마지막 수집 {c['fetched_at']} (UTC)")

tab_fin, tab_fil, tab_prof, tab_raw = st.tabs(["재무제표 원본", "공시 목록", "기업 개황", "원본 데이터 다운로드"])

# ---------------- 재무제표 ----------------
with tab_fin:
    if c["market"] == "KR":
        merge = st.toggle("연도별 계정 자동 맞추기", value=True,
                          help="회사가 연도마다 계정명이나 계정코드를 바꿔도(예: 수익(매출액)→영업수익→매출액) 같은 항목을 "
                               "한 행에 놓습니다. 끄면 회사가 쓴 계정명 그대로 행을 나눕니다. 어느 쪽이든 금액은 원본 그대로입니다.")
        stmts = service.kr_statements(cid, merge=merge)
        if not stmts:
            st.warning("DART에 사업보고서 재무제표 데이터가 없습니다 (2015년 이후 공시분만 API 제공).")
        else:
            st.caption("단위: 원 · 각 연도 사업보고서의 '당기' 금액 · CFS=연결, OFS=별도 · 행 이름은 최근 연도 계정명")
            name = st.selectbox("재무제표", list(stmts))
            flt = st.text_input("계정과목 검색", key="kr_flt")
            t = stmts[name]
            if flt:
                t = t[t.index.str.contains(flt, case=False, na=False)]
            st.dataframe(t.style.format("{:,.0f}", na_rep=""), width="stretch", height=600)
    else:
        t = service.us_annual(cid)
        if t.empty:
            st.warning("이 기업은 SEC에 XBRL 재무 데이터를 제출하지 않았습니다.")
        else:
            st.caption("SEC XBRL 연간값 (10-K/20-F) · 행 = 회사가 보고한 태그 · 열 = 회계기간 종료 연도 · "
                       "같은 기간이 여러 번 보고되면 가장 최근 제출본(정정 반영)")
            flt = st.text_input("태그/항목 검색 (예: Revenue, NetIncome, Assets)", key="us_flt")
            if flt:
                m = (t.index.get_level_values("tag").str.contains(flt, case=False)
                     | t.index.get_level_values("label").str.contains(flt, case=False))
                t = t[m]
            st.caption(f"{len(t):,}개 항목")
            st.dataframe(t.reset_index().set_index(["tag", "label", "unit"]).drop(columns="taxonomy")
                         .style.format("{:,.2f}", na_rep=""), width="stretch", height=600)

# ---------------- 공시 목록 ----------------
with tab_fil:
    f = service.filings(cid)
    a, b = st.columns([3, 2])
    kw = a.text_input("공시명 검색", placeholder="사업보고서, 10-K, 8-K, 주요사항...")
    if c["market"] == "US":
        forms = sorted(f["유형"].dropna().unique())
        default = [x for x in ["10-K", "10-Q", "8-K", "20-F", "6-K"] if x in forms]
        chosen = b.multiselect("유형", forms, default=default)
        if chosen:
            f = f[f["유형"].isin(chosen)]
    else:
        f = f.drop(columns="유형")
    if kw:
        f = f[f["공시명"].str.contains(kw, case=False, na=False)]
    st.caption(f"{len(f):,}건 · '원문'을 누르면 공시 원문으로 이동")
    st.dataframe(f, width="stretch", hide_index=True, height=600,
                 column_config={"원문": st.column_config.LinkColumn("원문", display_text="열기")})

# ---------------- 기업 개황 ----------------
with tab_prof:
    st.json(c["profile"])

# ---------------- 원본 다운로드 ----------------
with tab_raw:
    raw = service.raw_financials(cid)
    st.markdown(f"**재무 원본 행 {len(raw):,}개** · 원천 API 응답의 모든 필드 (공시 접수번호 포함)")
    st.dataframe(raw.head(500), width="stretch", hide_index=True)
    d1, d2, d3 = st.columns(3)
    d1.download_button("재무 원본 CSV", to_csv(raw.set_index("company_id")), f"{cid.replace(':', '_')}_financials.csv")
    d2.download_button("공시 목록 CSV", to_csv(service.filings(cid).set_index("접수일")), f"{cid.replace(':', '_')}_filings.csv")
    d3.download_button("기업개황 JSON", json.dumps(c["profile"], ensure_ascii=False, indent=2).encode("utf-8"),
                       f"{cid.replace(':', '_')}_profile.json")
