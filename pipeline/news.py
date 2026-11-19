"""뉴스 (정성 자료 C) — 제목·언론사·날짜·링크만 모은다 (사용자 결정 2026-11-19)

- 출처: 네이버 뉴스 검색 API(키 필요) + Google 뉴스 RSS(키 없음, 공식 API 아님) — 둘 다 (사용자 결정)
- 기간: 최근 1개월 (사용자 결정)
- 요약하지 않는다. 기사 본문도 받지 않는다. 프로필 2번: 뉴스는 시야를 넓히고 공시와 연결하는 데 쓴다 (판단은 공시로).
- 받은 응답은 data/raw/<KR|US>/<id>/news/ 에 그대로 보관한다. fetch() 는 사용자 승인 후에만 호출한다.
"""
import email.utils
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from . import service
from .config import RAW_DIR, naver_keys
from .http import get

DAYS = 30


def _dir(company_id: str):
    market, key = company_id.split(":", 1)
    return RAW_DIR / market / key / "news"


def query_for(company_id: str) -> str:
    """검색어: 한국은 '(주)' 등을 뺀 회사 이름, 미국은 영문 이름에서 'INC', 'CORP' 등을 뺀 것."""
    c = service.get_company(company_id) or {}
    name = c.get("name") or ""
    if company_id.startswith("KR:"):
        return re.sub(r"\(주\)|주식회사|㈜|\s", "", name)
    name = re.sub(r"[,.]", "", name)
    return re.sub(r"\b(INC|CORP|CORPORATION|CO|LTD|COMPANY|PLC|HOLDINGS?)\b", "", name, flags=re.I).strip()


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def fetch(company_id: str, progress=print) -> dict:
    """승인 후에만 호출. 두 출처에서 최근 1개월 기사 목록을 받아 원본 그대로 저장."""
    d = _dir(company_id)
    d.mkdir(parents=True, exist_ok=True)
    q = query_for(company_id)
    kr = company_id.startswith("KR:")
    stamp = datetime.now().strftime("%Y%m%d")
    done = {}
    # Google 뉴스 RSS
    loc = {"hl": "ko", "gl": "KR", "ceid": "KR:ko"} if kr else {"hl": "en-US", "gl": "US", "ceid": "US:en"}
    try:
        r = get("https://news.google.com/rss/search", params={"q": f"{q} when:{DAYS}d", **loc})
        (d / f"google_{stamp}.xml").write_text(r.text, encoding="utf-8")
        done["google"] = "받음"
    except Exception as e:  # noqa: BLE001
        done["google"] = f"실패: {e}"
    # 네이버 뉴스 검색 API (한국어 기사)
    cid_, sec = naver_keys()
    if not (cid_ and sec):
        done["naver"] = "키 없음 (.env 의 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)"
    else:
        items, cutoff = [], datetime.now(timezone.utc) - timedelta(days=DAYS)
        # 키 종류에 따라 주소·머리말이 다르다 (2026-11-19 확인):
        #  - 네이버 클라우드 플랫폼 'NAVER API HUB': naverapihub.apigw.ntruss.com/search/v1/news, X-NCP-APIGW-API-KEY(-ID)
        #  - 네이버 개발자센터: openapi.naver.com/v1/search/news.json, X-Naver-Client-Id/Secret
        #  API HUB를 먼저 시도하고, 인증이 안 되면 개발자센터 방식으로.
        modes = [("https://naverapihub.apigw.ntruss.com/search/v1/news",
                  {"X-NCP-APIGW-API-KEY-ID": cid_, "X-NCP-APIGW-API-KEY": sec}),
                 ("https://openapi.naver.com/v1/search/news.json",
                  {"X-Naver-Client-Id": cid_, "X-Naver-Client-Secret": sec})]
        url, hdr = modes[0]
        try:
            get(url, params={"query": q, "display": 1}, headers=hdr)
        except Exception:  # noqa: BLE001
            url, hdr = modes[1]
        try:
            for start in range(1, 1001, 100):
                r = get(url, params={"query": q, "display": 100, "start": start, "sort": "date"}, headers=hdr).json()
                batch = r.get("items", [])
                items += batch
                if not batch or email.utils.parsedate_to_datetime(batch[-1]["pubDate"]) < cutoff:
                    break
            (d / f"naver_{stamp}.json").write_text(json.dumps({"query": q, "items": items}, ensure_ascii=False),
                                                   encoding="utf-8")
            done["naver"] = f"받음 {len(items)}건"
        except Exception as e:  # noqa: BLE001
            done["naver"] = f"실패: {e}"
    progress(f"  뉴스 '{q}': " + ", ".join(f"{k} {v}" for k, v in done.items()))
    return done


def load(company_id: str) -> list[dict]:
    """가장 최근에 받은 두 출처의 기사 목록 → 최근 1개월, 같은 제목은 하나로, 최신순."""
    d = _dir(company_id)
    out = []
    g = sorted(d.glob("google_*.xml"))
    if g:
        root = ET.fromstring(g[-1].read_text(encoding="utf-8"))
        for it in root.iter("item"):
            title = _strip(it.findtext("title"))
            src = it.find("source")
            source = src.text if src is not None else ""
            if source and title.endswith(f" - {source}"):
                title = title[: -len(source) - 3]
            out.append({"date": email.utils.parsedate_to_datetime(it.findtext("pubDate")), "title": title,
                        "source": source, "link": it.findtext("link"), "from": "Google", "fetched": g[-1].stem[-8:]})
    n = sorted(d.glob("naver_*.json"))
    if n:
        for it in json.loads(n[-1].read_text(encoding="utf-8")).get("items", []):
            link = it.get("originallink") or it.get("link")
            host = re.sub(r"^https?://(www\.)?", "", link or "").split("/")[0]
            out.append({"date": email.utils.parsedate_to_datetime(it["pubDate"]), "title": _strip(it.get("title")),
                        "source": host, "link": link, "from": "네이버", "fetched": n[-1].stem[-8:]})
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)
    seen, uniq = set(), []
    for a in sorted(out, key=lambda a: a["date"], reverse=True):
        key = re.sub(r"\W", "", a["title"])[:40]
        if a["date"] < cutoff or key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    return uniq
