"""사람이 직접 보는 대시보드.  실행:  uv run streamlit run dashboard.py"""
import plotly.express as px
import streamlit as st

from pipeline import analysis

st.set_page_config(page_title="투자분석 대시보드", layout="wide")
st.title("투자분석 대시보드")

companies = analysis.list_companies()
if companies.empty:
    st.info("수집된 기업이 없습니다. 터미널에서 `uv run collect.py AAPL` 을 먼저 실행하세요.")
    st.stop()

labels = {r.company_id: f"{r.name} ({r.company_id})" for r in companies.itertuples()}
cid = st.sidebar.selectbox("기업 선택", list(labels), format_func=labels.get)
unit_div = st.sidebar.radio("금액 단위", ["백만", "십억"], horizontal=True)
div = 1e6 if unit_div == "백만" else 1e9

t = analysis.metrics_table(cid)
if t.empty:
    st.warning("재무 데이터가 없습니다.")
    st.stop()
t.index = t.index.astype(str)
latest = t.iloc[-1]

st.subheader(labels[cid])
c = st.columns(5)
c[0].metric("매출 (최근연도)", f"{latest.get('revenue', float('nan')) / div:,.0f} {unit_div}$",
            f"{latest.get('revenue_growth_%', float('nan')):.1f}% YoY")
c[1].metric("영업이익률", f"{latest.get('operating_margin_%', float('nan')):.1f}%")
c[2].metric("순이익률", f"{latest.get('net_margin_%', float('nan')):.1f}%")
c[3].metric("ROE", f"{latest.get('roe_%', float('nan')):.1f}%")
c[4].metric("부채/자본", f"{latest.get('debt_to_equity', float('nan')):.2f}x")

tab1, tab2, tab3, tab4 = st.tabs(["실적 추세", "수익성·재무건전성", "공시 타임라인", "원본 데이터·출처"])

with tab1:
    money = [m for m in ["revenue", "operating_income", "net_income", "free_cash_flow"] if m in t]
    df = (t[money] / div).reset_index().melt(id_vars="fiscal_year", var_name="지표", value_name=unit_div)
    st.plotly_chart(px.bar(df, x="fiscal_year", y=unit_div, color="지표", barmode="group",
                           title=f"매출·이익·FCF ({unit_div} USD)"), width="stretch")

with tab2:
    pct = [m for m in ["gross_margin_%", "operating_margin_%", "net_margin_%", "roe_%", "fcf_margin_%"] if m in t]
    df = t[pct].reset_index().melt(id_vars="fiscal_year", var_name="지표", value_name="%")
    st.plotly_chart(px.line(df, x="fiscal_year", y="%", color="지표", markers=True,
                            title="마진·ROE 추세 (%)"), width="stretch")
    if "debt_to_equity" in t:
        st.plotly_chart(px.bar(t.reset_index(), x="fiscal_year", y="debt_to_equity",
                               title="부채/자본 비율 (x)"), width="stretch")

with tab3:
    forms = st.multiselect("공시 유형", ["10-K", "10-Q", "8-K", "DEF 14A", "20-F", "6-K"],
                           default=["10-K", "8-K"])
    f = analysis.filings(cid, forms)
    st.caption(f"{len(f)}건 · 링크를 누르면 SEC 원문으로 이동합니다")
    st.dataframe(f, width="stretch", hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("원문")})

with tab4:
    st.markdown("**연도별 지표표** (파생지표는 `pipeline/analysis.py` 에서 계산)")
    st.dataframe(t.T.style.format("{:,.2f}"), width="stretch")
    st.markdown("**원본 수치와 출처** — 모든 값은 공시 접수번호(accession)로 원문 추적 가능")
    st.dataframe(analysis.raw_financials(cid), width="stretch", hide_index=True)
