"""주가 (Yahoo Finance, yfinance) — 잠정 가격 판단(PER·PBR)용 (사용자 결정 2026-11-19: 자동 수집)

- 공식 API가 아니어서 막히거나 바뀔 수 있다. 그러면 다른 출처로 바꾼다.
- 받은 일별 시세와 분할 기록을 data/raw/<KR|US>/<id>/prices/ 에 그대로 보관한다 (언제·어디서 받았는지 함께).
- fetch() 는 사용자 승인 후에만 호출한다.

주식 분할 맞추기
- Yahoo 의 과거 종가는 '오늘 기준'으로 분할을 반영해 고친 값이다.
- 공시된 주당순이익·주식 수는 그 보고서를 낸 날 기준이다 (실제 사례: Walmart 는 FY2023 이 끝난 뒤
  2024년 2월에 3:1 분할했고, FY2023 10-K 의 주당순이익은 분할 후 기준이다).
- 그래서 공시 값을 '오늘 기준'으로 바꾼다: 보고서 제출일 '이후'에 있었던 분할 비율만큼 나누거나(주당 값) 곱한다(주식 수).
"""
import json
from datetime import datetime

import pandas as pd

from . import service
from .config import RAW_DIR


def _dir(company_id: str):
    market, key = company_id.split(":", 1)
    return RAW_DIR / market / key / "prices"


# 해외 기업(20-F)은 미국 상장 ADR 이 달러로 거래되지만 재무제표는 현지 통화다 → 현지 상장 주가를 쓴다.
#   (실제 사례: TSMC 재무제표는 대만 달러, 미국 ADR 'TSM'은 미국 달러이고 1 ADR = 5주)
LOCAL_LISTING = {"US:0001046179": "2330.TW"}


def symbol(company_id: str) -> str | None:
    """Yahoo 종목 기호. 한국: 종목코드 + .KS(유가증권) / .KQ(코스닥), 미국: 첫 번째 티커, 해외 기업: 현지 상장."""
    if company_id in LOCAL_LISTING:
        return LOCAL_LISTING[company_id]
    c = service.get_company(company_id) or {}
    ticker = (c.get("ticker") or "").split(",")[0].strip()
    if not ticker:
        return None
    if company_id.startswith("KR:"):
        cls = (c.get("profile") or {}).get("corp_cls")
        return f"{ticker}.{'KQ' if cls == 'K' else 'KS'}"
    return ticker


def have(company_id: str) -> bool:
    return (_dir(company_id) / "daily.csv").exists()


def fetch(company_id: str, years: int = 7, progress=print) -> bool:
    """승인 후에만 호출. 최근 years년 일별 시세(수정 전 종가 포함)와 분할 기록을 받아 저장."""
    import yfinance as yf
    sym = symbol(company_id)
    if not sym:
        progress(f"  {company_id}: 종목 기호를 알 수 없음")
        return False
    t = yf.Ticker(sym)
    h = t.history(period=f"{years}y", interval="1d", auto_adjust=False)
    if h.empty:
        progress(f"  {company_id} ({sym}): 시세 없음")
        return False
    d = _dir(company_id)
    d.mkdir(parents=True, exist_ok=True)
    h.index = h.index.tz_localize(None) if h.index.tz is not None else h.index
    h[["Close", "Adj Close", "Volume"]].to_csv(d / "daily.csv", encoding="utf-8")
    splits = t.splits
    splits.index = splits.index.tz_localize(None) if len(splits) and splits.index.tz is not None else splits.index
    splits.to_csv(d / "splits.csv", header=["ratio"], encoding="utf-8")
    try:
        currency = t.fast_info.get("currency")
    except Exception:  # noqa: BLE001
        currency = None
    meta = {"source": "Yahoo Finance (yfinance)", "symbol": sym, "currency": currency,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "first": str(h.index[0].date()), "last": str(h.index[-1].date()),
            "note": "Close = 분할 반영(오늘 기준), 배당 미반영 종가"}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    progress(f"  받음 {sym} {meta['first']}~{meta['last']} ({currency})")
    return True


def load(company_id: str) -> tuple[pd.Series, pd.Series, dict]:
    """(일별 종가, 분할 비율, 메타). 없으면 빈 Series."""
    d = _dir(company_id)
    if not (d / "daily.csv").exists():
        return pd.Series(dtype=float), pd.Series(dtype=float), {}
    px = pd.read_csv(d / "daily.csv", index_col=0, parse_dates=True)["Close"]
    sp = pd.read_csv(d / "splits.csv", index_col=0, parse_dates=True)["ratio"] if (d / "splits.csv").exists() \
        else pd.Series(dtype=float)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
    return px, sp[sp > 0], meta


def close_on(px: pd.Series, day) -> tuple[pd.Timestamp, float] | None:
    """그날 또는 그 직전 거래일의 종가 (최대 10일 전까지)."""
    day = pd.Timestamp(day)
    s = px[(px.index <= day) & (px.index > day - pd.Timedelta(days=10))]
    return (s.index[-1], float(s.iloc[-1])) if len(s) else None


def split_factor_after(splits: pd.Series, day) -> float:
    """day '이후' 분할 비율의 곱. 공시 주당 값 ÷ 이 값 = 오늘 기준 주당 값."""
    if splits.empty or day is None:
        return 1.0
    s = splits[splits.index > pd.Timestamp(day)]
    f = 1.0
    for r in s:
        f *= float(r)
    return f
