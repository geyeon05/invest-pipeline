"""기업명 → 고유번호 매핑. 상장사 전체 목록을 받아 두고 이름·티커로 검색한다.

- 한국: DART 고유번호 목록 (corpCode.xml, 상장사만 사용)  ※ DART API 키 필요
- 미국: SEC company_tickers_exchange.json (EDGAR 등록 상장사 전체, 해외기업 ADR 포함)
"""
import io
import json
import time
import zipfile
import xml.etree.ElementTree as ET

from .config import REFRESH_DAYS, REGISTRY_DIR, dart_key
from .http import get


def _cached(name: str, loader) -> list[dict]:
    path = REGISTRY_DIR / f"{name}.json"
    if path.exists() and time.time() - path.stat().st_mtime < REFRESH_DAYS * 86400:
        return json.loads(path.read_text(encoding="utf-8"))
    rows = loader()
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def _load_kr() -> list[dict]:
    resp = get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": dart_key()})
    if not resp.content.startswith(b"PK"):  # zip 이 아니면 오류 메시지(JSON/XML)
        raise RuntimeError(f"DART 기업목록 다운로드 실패: {resp.text[:200]}")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    rows = []
    for el in root.iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if not stock:
            continue  # 비상장사 제외
        corp_code = el.findtext("corp_code").strip()
        rows.append({
            "company_id": f"KR:{corp_code}", "market": "KR", "source_key": corp_code,
            "name": el.findtext("corp_name", "").strip(),
            "name_en": (el.findtext("corp_eng_name") or "").strip(),
            "tickers": [stock], "exchange": "",
        })
    return rows


def _load_us() -> list[dict]:
    data = get("https://www.sec.gov/files/company_tickers_exchange.json", sec=True).json()
    by_cik: dict[str, dict] = {}
    for cik, name, ticker, exchange in data["data"]:
        cik10 = f"{int(cik):010d}"
        row = by_cik.setdefault(cik10, {
            "company_id": f"US:{cik10}", "market": "US", "source_key": cik10,
            "name": name, "name_en": name, "tickers": [], "exchange": exchange or "",
        })
        if ticker:
            row["tickers"].append(ticker)
    return list(by_cik.values())


def load_all() -> tuple[list[dict], list[str]]:
    """(전체 기업 목록, 경고 메시지) 반환. 한쪽 시장이 실패해도 다른 쪽은 사용."""
    rows, warnings = [], []
    if dart_key():
        try:
            rows += _cached("kr", _load_kr)
        except Exception as e:
            warnings.append(f"한국(DART) 기업목록을 불러오지 못했습니다: {e}")
    else:
        warnings.append("DART API 키가 없어 국내 기업 검색이 꺼져 있습니다.")
    try:
        rows += _cached("us", _load_us)
    except Exception as e:
        warnings.append(f"미국(SEC) 기업목록을 불러오지 못했습니다: {e}")
    return rows, warnings


def _norm(s: str) -> str:
    return "".join(s.lower().split()).replace(".", "").replace(",", "")


# 공식 등록명과 다른 흔한 약칭·한글명 → 검색어 (필요할 때마다 추가)
ALIASES = {
    "tsmc": "TSM", "애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "구글": "GOOGL",
    "알파벳": "GOOGL", "아마존": "AMZN", "메타": "META", "페이스북": "META", "테슬라": "TSLA",
    "넷플릭스": "NFLX", "버크셔": "BRK-B", "버크셔해서웨이": "BRK-B", "코카콜라": "KO",
    "인텔": "INTC", "에이엠디": "AMD", "브로드컴": "AVGO", "asml": "ASML", "도요타": "TM", "소니": "SONY",
}


def search(query: str, rows: list[dict], limit: int = 20) -> list[dict]:
    q = _norm(ALIASES.get(_norm(query), query))
    if not q:
        return []
    scored = []
    for r in rows:
        names = [_norm(r["name"]), _norm(r["name_en"])]
        tickers = [_norm(t) for t in r["tickers"]]
        if q in tickers or q in names:
            score = 0
        elif any(n.startswith(q) for n in names):
            score = 1
        elif any(q in n for n in names) or any(t.startswith(q) for t in tickers):
            score = 2
        else:
            continue
        scored.append((score, len(r["name"]), r))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [{**r, "exact": s == 0} for s, _, r in scored[:limit]]
