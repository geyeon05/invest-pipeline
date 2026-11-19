"""잠정 가격 판단: PER·PBR (13~14주차의 내재가치 계산을 배우기 전까지 쓰는 비교 기준)

사용자 결정 (2026-11-19)
- 12주차까지 배운 범위로 가격 수준을 '비교'로 가늠한다. 내재가치 계산(닻)은 13~14주차 이후에 더한다.
- PER = 보통주 주가 ÷ 기본주당순이익 (공시 값). **그해 이익 기준과 최근 5년 평균 이익 기준을 함께** 본다
  (5주차 PER, 11주차 평균 회귀: 이익이 출렁이는 회사는 그해 이익만으로 싸다고 착각할 수 있음).
- PBR = 보통주 주가 ÷ 주당 장부가치. 주당 장부가치 = 지배주주 자본 ÷ 유통주식 수 (4주차).
  수치화되는 장부 밖 가치를 더한 '조정 장부가치'는 분석할 때 입력한다 (아직 미구현).
- 주가는 자동 수집 (Yahoo Finance). 시점은 현재 + 최근 5개 회계연도 말.
- 비교는 경쟁사 우선, 자기 과거는 보조. 경쟁사는 분석할 때 직접 고른다.
- 판정하지 않는다. 숫자와 사실만 보여준다.
"""
import sqlite3
from functools import lru_cache

import pandas as pd

from . import dart_shares, prices, service
from . import standard as S
from .config import DB_PATH

YEARS = 5


@lru_cache(maxsize=4096)
def _us_filed(accn: str) -> str | None:
    r = sqlite3.connect(DB_PATH).execute("SELECT MIN(filed) FROM sec_facts WHERE accn = ?", (accn,)).fetchone()
    return r[0] if r else None


def _filed(company_id: str, filing) -> str | None:
    """공시 제출일. 한국: 접수번호 앞 8자리, 미국: accn 의 제출일."""
    if not filing or pd.isna(filing):
        return None
    f = str(filing)
    if company_id.startswith("KR:"):
        return f"{f[:4]}-{f[4:6]}-{f[6:8]}" if f[:8].isdigit() else None
    return _us_filed(f)


def analyze(company_id: str, years: int = YEARS) -> dict:
    out = {"company_id": company_id, "rows": [], "current": None, "flags": [], "meta": {}}
    df = S.standardize(company_id)
    if df.empty:
        out["flags"].append("재무 데이터가 없음")
        return out
    px, sp, meta = prices.load(company_id)
    out["meta"] = meta
    if px.empty:
        out["flags"].append("주가 미수집 (data.py price <기업> --fetch, 승인 필요)")
        return out
    rows = {(r.item, r.year): r for r in df.itertuples()}
    g = lambda k, y: rows.get((k, y))  # noqa: E731
    fin_cur = next((r.currency for r in df.itertuples() if r.item in ("eps_basic", "equity_parent") and r.currency), None)
    if meta.get("currency") and fin_cur and meta["currency"] != fin_cur:
        out["flags"].append(f"주가 통화({meta['currency']})와 재무제표 통화({fin_cur})가 다름 → 계산 안 함 "
                            f"(예: 해외 상장 ADR). 현지 상장 주가가 필요")
        return out
    fys = sorted({y for (k, y) in rows if k in ("eps_basic", "equity_parent")})[-years:]
    kr = company_id.startswith("KR:")
    shares_kr = dart_shares.load(company_id, fys) if kr else {}

    # 검증: 주당순이익 × 주식 수 ≈ 지배주주 순이익 이어야 한다. 크게 어긋나면 원본 오류로 보고 쓰지 않는다.
    #   (실제 사례: LG화학 2016~2017년 DART 원본의 주당이익이 174억·254억 원 — 단위가 잘못 곱해진 것으로 보임)
    any_shares = next((v.get("issued") for v in dart_shares.load(company_id, list(range(min(fys or [0]) - 5,
                       max(fys or [0]) + 1))).values() if v.get("issued")), None) if kr else None
    bad_eps = set()

    def eps_adj(y):
        r = g("eps_basic", y)
        if r is None or pd.isna(r.value):
            return None
        ni = g("net_income_parent", y)
        n = any_shares if kr else (g("shares_outstanding", y).value if g("shares_outstanding", y) is not None else None)
        if ni is not None and pd.notna(ni.value) and n and r.value and ni.value:
            implied = ni.value / r.value          # 순이익 ÷ 주당이익 = 주식 수
            if not 0.1 < implied / n < 10:
                bad_eps.add(y)
                return None
        return r.value / prices.split_factor_after(sp, _filed(company_id, r.filing))

    def bps_adj(y):
        eq = g("equity_parent", y)
        if eq is None or pd.isna(eq.value):
            return None, "지배주주 자본 없음"
        if kr:
            sh = shares_kr.get(y, {})
            n, filed = sh.get("outstanding"), _filed(company_id, sh.get("rcept_no"))
        else:
            s = g("shares_outstanding", y)
            n, filed = (s.value, _filed(company_id, s.filing)) if s is not None and pd.notna(s.value) else (None, None)
        if not n:
            return None, "유통주식 수 없음" + (" (DART 주식 수 미수집)" if kr and not shares_kr.get(y, {}).get("status") else "")
        return eq.value / (n * prices.split_factor_after(sp, filed)), None

    def per_pair(price, y):
        e = eps_adj(y)
        window = [eps_adj(t) for t in range(y - 4, y + 1)]
        window = [v for v in window if v is not None]
        avg = sum(window) / len(window) if window else None
        return (price / e if e and e > 0 else None, e, price / avg if avg and avg > 0 else None, avg, len(window))

    for y in fys:
        pe = g("eps_basic", y) or g("equity_parent", y)
        day = pd.Timestamp(pe.period_end) if pe is not None and pe.period_end else pd.Timestamp(f"{y}-12-31")
        c = prices.close_on(px, day)
        row = {"year": y, "date": None, "price": None, "per": None, "eps": None, "per_avg": None, "eps_avg": None,
               "n_avg": 0, "pbr": None, "bps": None, "notes": []}
        if c is None:
            row["notes"].append(f"{day.date()} 무렵 주가 없음")
            out["rows"].append(row)
            continue
        row["date"], row["price"] = c[0].date(), c[1]
        row["per"], row["eps"], row["per_avg"], row["eps_avg"], row["n_avg"] = per_pair(c[1], y)
        bps, why = bps_adj(y)
        row["bps"] = bps
        row["pbr"] = c[1] / bps if bps and bps > 0 else None
        if row["eps"] is None:
            row["notes"].append("주당순이익 없음")
        elif row["eps"] <= 0:
            row["notes"].append("주당순이익 0 이하 → 그해 이익 PER 계산 안 함")
        if row["n_avg"] and row["n_avg"] < 5:
            row["notes"].append(f"5년 평균에 쓸 주당순이익이 {row['n_avg']}개뿐 (있는 해만 평균)")
        if row["eps_avg"] is not None and row["eps_avg"] <= 0:
            row["notes"].append("5년 평균 주당순이익 0 이하 → 평균 이익 PER 계산 안 함")
        if why:
            row["notes"].append(why)
        elif bps is not None and bps <= 0:
            row["notes"].append("주당 장부가치 0 이하 (자본잠식) → PBR 계산 안 함")
        for k in ("eps_basic", "equity_parent", "shares_outstanding"):
            r = g(k, y)
            if r is not None and r.match not in ("exact",):
                row["notes"].append(f"{S.ITEM_BY_KEY[k].name}={S.MATCH_LABEL.get(r.match, r.match)}")
        out["rows"].append(row)

    # 현재: 마지막 거래일 종가 + 가장 최근 회계연도의 이익·장부가치
    last_day, last_px = px.index[-1], float(px.iloc[-1])
    if fys:
        y = fys[-1]
        per, e, per_avg, avg, n = per_pair(last_px, y)
        bps, why = bps_adj(y)
        out["current"] = {"date": last_day.date(), "price": last_px, "basis_year": y, "per": per, "eps": e,
                          "per_avg": per_avg, "eps_avg": avg, "n_avg": n, "bps": bps,
                          "pbr": last_px / bps if bps and bps > 0 else None, "why": why}
    if bad_eps:
        out["flags"].append(f"주당순이익 검증 실패로 제외한 해: {sorted(bad_eps)} "
                            "(주당순이익 × 주식 수가 지배주주 순이익과 10배 넘게 어긋남 → 원본 단위 오류 등)")
    if not sp.empty:
        recent = sp[sp.index >= pd.Timestamp(f"{fys[0] - 4}-01-01")] if fys else sp
        if len(recent):
            out["flags"].append("주식 수 변동 반영 (Yahoo 기준 분할·주식배당·인적분할): "
                                + ", ".join(f"{d.date()} {r:g}:1" for d, r in recent.items())
                                + " → 공시 주당 값을 주가와 같은 기준으로 맞춤")
    if S.is_financial(service.get_company(company_id) or {}):
        out["flags"].append("금융업: PBR은 쓸 수 있지만, 업종 특성상 일반 기업과 비교하면 안 됨")
    return out
