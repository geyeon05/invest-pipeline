"""뉴스 (정성 자료 C) — 제목·언론사·날짜·링크만 모은다 (사용자 결정 2026-11-19)

- 출처: 네이버 뉴스 검색 API(키 필요) + Google 뉴스 RSS(키 없음, 공식 API 아님) — 둘 다 (사용자 결정)
- 기간: 최근 1개월 (사용자 결정)
- 목적 (사용자 결정): (가) 공시와 연결되는 사건, (나) 시장 분위기·열광 정도, (다) 산업·경쟁 흐름.
  범위는 제목에 회사 이름이 있는 기사만. 주가·시황 기사는 따로 묶는다. 산업·경쟁은 경쟁사 이름과 산업 낱말로 따로 받는다.
  언론사는 전부. 네이버 1,000건 한도는 그대로 둔다. 목적별로 묶어 보여준다.
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


def _slug(q: str) -> str:
    return re.sub(r"[^\w가-힣]+", "_", q).strip("_")[:40] or "q"


def _naver_endpoint(cid_: str, sec: str, q: str):
    # 키 종류에 따라 주소·머리말이 다르다 (2026-11-19 확인):
    #  - 네이버 클라우드 플랫폼 'NAVER API HUB': naverapihub.apigw.ntruss.com/search/v1/news, X-NCP-APIGW-API-KEY(-ID)
    #  - 네이버 개발자센터: openapi.naver.com/v1/search/news.json, X-Naver-Client-Id/Secret
    #  API HUB를 먼저 시도하고, 인증이 안 되면 개발자센터 방식으로.
    modes = [("https://naverapihub.apigw.ntruss.com/search/v1/news",
              {"X-NCP-APIGW-API-KEY-ID": cid_, "X-NCP-APIGW-API-KEY": sec}),
             ("https://openapi.naver.com/v1/search/news.json",
              {"X-Naver-Client-Id": cid_, "X-Naver-Client-Secret": sec})]
    try:
        get(modes[0][0], params={"query": q, "display": 1}, headers=modes[0][1])
        return modes[0]
    except Exception:  # noqa: BLE001
        return modes[1]


def fetch_query(company_id: str, q: str, kr: bool, progress=print) -> dict:
    """한 검색어로 두 출처에서 최근 1개월 기사 목록을 받아 원본 그대로 저장 (승인 후에만 호출)."""
    d = _dir(company_id)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    slug = _slug(q)
    done = {}
    loc = {"hl": "ko", "gl": "KR", "ceid": "KR:ko"} if kr else {"hl": "en-US", "gl": "US", "ceid": "US:en"}
    try:
        r = get("https://news.google.com/rss/search", params={"q": f"{q} when:{DAYS}d", **loc})
        (d / f"google__{slug}__{stamp}.xml").write_text(r.text, encoding="utf-8")
        done["google"] = "받음"
    except Exception as e:  # noqa: BLE001
        done["google"] = f"실패: {e}"
    cid_, sec = naver_keys()
    if not (cid_ and sec):
        done["naver"] = "키 없음 (.env 의 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)"
    else:
        items, cutoff = [], datetime.now(timezone.utc) - timedelta(days=DAYS)
        url, hdr = _naver_endpoint(cid_, sec, q)
        try:
            for start in range(1, 1001, 100):
                r = get(url, params={"query": q, "display": 100, "start": start, "sort": "date"}, headers=hdr).json()
                batch = r.get("items", [])
                items += batch
                if not batch or email.utils.parsedate_to_datetime(batch[-1]["pubDate"]) < cutoff:
                    break
            (d / f"naver__{slug}__{stamp}.json").write_text(json.dumps({"query": q, "items": items}, ensure_ascii=False),
                                                           encoding="utf-8")
            done["naver"] = f"받음 {len(items)}건"
        except Exception as e:  # noqa: BLE001
            done["naver"] = f"실패: {e}"
    progress(f"  뉴스 '{q}': " + ", ".join(f"{k} {v}" for k, v in done.items()))
    return done


def fetch(company_id: str, extra: list[str] | None = None, progress=print) -> dict:
    """회사 이름 + (산업·경쟁용) 경쟁사 이름·산업 낱말. 승인 후에만 호출."""
    kr = company_id.startswith("KR:")
    out = {query_for(company_id): fetch_query(company_id, query_for(company_id), kr, progress)}
    for q in extra or []:
        out[q] = fetch_query(company_id, q, kr, progress)
    return out


def _latest(d, src: str, slug: str):
    files = sorted(d.glob(f"{src}__{slug}__*"))
    if not files and slug == "__legacy__":
        return None
    return files[-1] if files else None


def load_query(company_id: str, q: str) -> list[dict]:
    """한 검색어의 가장 최근 수집분 → 최근 1개월, 같은 제목은 하나로, 최신순."""
    d = _dir(company_id)
    slug = _slug(q)
    out = []
    g = _latest(d, "google", slug)
    if g is None and q == query_for(company_id):          # 이전 형식 파일 (google_YYYYMMDD.xml)
        old = sorted(d.glob("google_[0-9]*.xml"))
        g = old[-1] if old else None
    if g:
        root = ET.fromstring(g.read_text(encoding="utf-8"))
        for it in root.iter("item"):
            title = _strip(it.findtext("title"))
            src = it.find("source")
            source = src.text if src is not None else ""
            if source and title.endswith(f" - {source}"):
                title = title[: -len(source) - 3]
            # 언론사는 Google이 주는 언론사 주소(source url)로 → 네이버 기사 주소와 같은 기준으로 맞춤
            outlet = _outlet(src.get("url")) if src is not None and src.get("url") else source
            out.append({"date": email.utils.parsedate_to_datetime(it.findtext("pubDate")), "title": title,
                        "source": source, "outlet": outlet, "link": it.findtext("link"), "from": "Google",
                        "fetched": g.stem[-8:], "query": q})
    n = _latest(d, "naver", slug)
    if n is None and q == query_for(company_id):
        old = sorted(d.glob("naver_[0-9]*.json"))
        n = old[-1] if old else None
    if n:
        for it in json.loads(n.read_text(encoding="utf-8")).get("items", []):
            link = it.get("originallink") or it.get("link")
            host = re.sub(r"^https?://(www\.)?", "", link or "").split("/")[0]
            out.append({"date": email.utils.parsedate_to_datetime(it["pubDate"]), "title": _strip(it.get("title")),
                        "source": host, "outlet": _outlet(link), "link": link, "from": "네이버",
                        "fetched": n.stem[-8:], "query": q})
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)
    seen, uniq = set(), []
    for a in sorted(out, key=lambda a: a["date"], reverse=True):
        key = re.sub(r"\W", "", a["title"])[:40]
        if a["date"] < cutoff or key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    return uniq


def load(company_id: str) -> list[dict]:
    return load_query(company_id, query_for(company_id))


def _in_title(title: str, q: str) -> bool:
    """제목에 검색어가 들어 있나 (띄어쓰기·대소문자 무시). 검색어가 여러 낱말이면 모두 들어 있어야 함."""
    t = re.sub(r"\s", "", title).lower()
    return all(re.sub(r"\s", "", w).lower() in t for w in q.split())


def grouped(company_id: str, extra: list[str] | None = None) -> dict:
    """목적별 묶음 (사용자 결정 2026-11-19).
    - 사건 (가): 제목에 회사 이름이 있는 기사 중 시황이 아닌 것
    - 분위기·시황 (나): 제목에 회사 이름이 있는 기사 중 주가·시황 기사
    - 산업·경쟁 (다): 경쟁사 이름·산업 낱말로 받은 기사 중 제목에 그 낱말이 있는 것
    """
    name = query_for(company_id)
    own = [a for a in load(company_id) if _in_title(a["title"], name)]
    event = [a for a in own if not MARKET.search(a["title"])]
    mood = [a for a in own if MARKET.search(a["title"])]
    industry = []
    for q in extra or []:
        industry += [a for a in load_query(company_id, q) if _in_title(a["title"], q)]
    seen, ind = set(), []
    for a in sorted(industry, key=lambda a: a["date"], reverse=True):
        k = re.sub(r"\W", "", a["title"])[:40]
        if k not in seen:
            seen.add(k)
            ind.append(a)
    return {"사건": event, "분위기·시황": mood, "산업·경쟁": ind, "all_own": own}


def weekly_counts(articles: list[dict]) -> list[tuple[str, int, int]]:
    """최근 4주 주별 기사 수 (Google, 네이버 따로). 네이버는 1,000건 한도로 큰 회사는 최근 며칠만 있음."""
    now = datetime.now(timezone.utc)
    out = []
    for w in range(4):
        hi, lo = now - timedelta(days=7 * w), now - timedelta(days=7 * (w + 1))
        g = sum(1 for a in articles if a["from"] == "Google" and lo < a["date"] <= hi)
        n = sum(1 for a in articles if a["from"] == "네이버" and lo < a["date"] <= hi)
        out.append((f"{lo:%m-%d}~{hi:%m-%d}", g, n))
    return out


# 주가·시황 기사 (AI가 정한 값: criteria/README.md)
MARKET = re.compile(r"주가|특징주|코스피|코스닥|외국인|기관|순매수|순매도|시총|시가총액|급등|급락|상승세|하락세|강세|약세|"
                    r"장중|마감|목표주가|52주|신고가|신저가|공매도|ETF|보합|내려|올라|하락|상승|\d+(\.\d+)?\s*%\s*(상승|하락|올|내|↑|↓|급)|\bshares?\b|\bstock\b|rall(y|ies)|tumbl|soar|slump|"
                    r"price target", re.I)


# ---------------- 네이버 데이터랩 검색어 트렌드 (분위기 (나), 사용자 결정 2026-11-19) ----------------
# 사람들이 그 회사를 얼마나 '검색'했는지의 추세. 값은 요청한 기간 안에서 가장 많이 검색된 때를 100으로 둔 상대값이다.
# 그래서 최근 1년(주 단위)을 함께 받아야 '지금이 평소보다 높은지'를 볼 수 있다 (AI가 정한 값: 1년 주 단위 + 30일 일 단위).
TREND_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"


def fetch_trend(company_id: str, progress=print) -> str:
    """승인 후에만 호출. 회사 이름의 검색어 트렌드 (1년 주 단위, 30일 일 단위)."""
    from datetime import date
    from .http import post_json
    cid_, sec = naver_keys()
    if not (cid_ and sec):
        return "키 없음"
    q = query_for(company_id)
    d = _dir(company_id)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out = {}
    for unit, days in (("week", 365), ("date", DAYS)):
        body = {"startDate": str(date.today() - timedelta(days=days)), "endDate": str(date.today()), "timeUnit": unit,
                "keywordGroups": [{"groupName": q, "keywords": [q]}]}
        try:
            r = post_json(TREND_URL, body, {"X-NCP-APIGW-API-KEY-ID": cid_, "X-NCP-APIGW-API-KEY": sec})
            out[unit] = r.json()
        except Exception as e:  # noqa: BLE001
            msg = getattr(getattr(e, "response", None), "text", "") or str(e)
            progress(f"  검색어 트렌드 '{q}' 실패: {msg[:120]}")
            return "실패"
    (d / f"trend__{_slug(q)}__{stamp}.json").write_text(json.dumps({"query": q, **out}, ensure_ascii=False),
                                                       encoding="utf-8")
    progress(f"  검색어 트렌드 '{q}': 받음")
    return "받음"


def load_trend(company_id: str) -> dict | None:
    """{'week': [(기간 시작, 값)], 'date': [...], 'fetched': ...}"""
    files = sorted(_dir(company_id).glob(f"trend__{_slug(query_for(company_id))}__*.json"))
    if not files:
        return None
    raw = json.loads(files[-1].read_text(encoding="utf-8"))
    out = {"fetched": files[-1].stem[-8:]}
    for unit in ("week", "date"):
        res = (raw.get(unit) or {}).get("results") or [{}]
        out[unit] = [(x["period"], float(x["ratio"])) for x in res[0].get("data", [])]
    return out


# ---------------- 줄이기 (사용자 결정 2026-11-19) ----------------
# 1) 광고성 기사 빼기 (b): 노골적인 광고 + 신제품·행사 홍보성 기사.
#    '공개'·'페스티벌'은 빼고, '[단독]' 기사는 낱말에 걸려도 남김 (사용자 결정 a)
# 2) 같은 사건 기사 묶기: 제목 낱말이 35% 이상 겹치고 2일 안이면 한 사건 (중간)
#    + 같은 날 제목에 '고유한 낱말'이 2개 이상 겹치면 한 사건 (사용자 결정 b)
# 3) 2곳 이상의 언론사가 다룬 사건만. 단 (나) 분위기·시황은 이 규칙 없이 묶기만 (사용자 결정 b), [단독] 기사는 1곳이어도 남김
# 4) 언론사는 주소(도메인)로 통일 (Google 언론사 주소 = 네이버 기사 주소)
# 낱말 목록, 고유한 낱말 판단, 조사 떼기, 도메인 통일 방식은 AI가 정한 값 (criteria/README.md)
AD = re.compile(r"\[(광고|AD|PR|협찬|후원|홍보)\]|광고\)|이벤트|경품|할인|특가|프로모션|쿠폰|증정|사은품|체험단|기획전|"
                r"얼리버드|최대\s*\d+%\s*(할인|혜택)|무료\s*(종목|추천|상담)|리딩방|급등주|"
                r"출시|사전\s*예약|캠페인|수상|기념|론칭|런칭|행사|팝업|전시회|박람회|오픈|선보|신제품|"
                r"Sponsored|Promo|discount|giveaway|launch|unveil", re.I)
KEEP = re.compile(r"\[단독\]|\bexclusive\b", re.I)
SAME_EVENT = 0.35
SAME_DAYS = 2
MIN_SOURCES = 2
DISTINCT_SHARE = 0.10   # 전체 제목의 10% 이하에만 나오는 낱말 = 고유한 낱말
DISTINCT_MIN = 2
_JOSA = re.compile(r"(으로|에서|에게|까지|부터|이다|이며|은|는|이|가|을|를|의|에|도|로|와|과|만)$")
_SLD = {"co", "or", "go", "ne", "ac", "re", "pe", "com", "net", "org"}


def _outlet(url: str | None) -> str:
    """언론사 주소 → 등록 도메인 (news.hankyung.com, www.hankyung.com → hankyung.com; biz.chosun.com → chosun.com)."""
    host = re.sub(r"^https?://", "", url or "").split("/")[0].split(":")[0].lower()
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and parts[-2] in _SLD and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_ad(title: str) -> bool:
    return bool(AD.search(title)) and not KEEP.search(title)


def _tokens(t: str) -> set[str]:
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|[“”\"'‘’…·,.!?:;~/]", " ", t)
    out = set()
    for w in re.split(r"\s+", t):
        w = _JOSA.sub("", w) if len(w) >= 3 else w
        if len(w) >= 2:
            out.add(w.lower())
    return out


def events_of(rows: list[dict], min_sources: int = MIN_SOURCES, drop: set[str] | None = None) -> list[dict]:
    """광고성 기사를 빼고 같은 사건을 묶은 뒤, min_sources곳 이상이 다룬 사건만.
    drop: 고유한 낱말에서 뺄 낱말 (회사 이름 등)."""
    rows = [r for r in rows if not is_ad(r["title"])]
    toks = [_tokens(r["title"]) for r in rows]
    df = {}
    for tk in toks:
        for w in tk:
            df[w] = df.get(w, 0) + 1
    cap = max(2, int(len(rows) * DISTINCT_SHARE))
    drop = {w.lower() for w in (drop or set())}
    groups = []
    for a, tk in sorted(zip(rows, toks), key=lambda x: x[0]["date"]):
        distinct = {w for w in tk if df[w] <= cap and w not in drop and not any(d in w for d in drop)}

        def same(g):
            if abs((a["date"] - g["date"]).days) > SAME_DAYS:
                return False
            if len(tk & g["tk"]) / max(1, len(tk | g["tk"])) >= SAME_EVENT:
                return True
            return a["date"].date() == g["day"] and len(distinct & g["distinct"]) >= DISTINCT_MIN

        hit = next((g for g in groups if same(g)), None)
        if hit:
            hit["articles"].append(a)
        else:
            groups.append({"title": a["title"], "date": a["date"], "day": a["date"].date(), "link": a["link"],
                           "tk": tk, "distinct": distinct, "articles": [a]})
    out = []
    for g in groups:
        srcs = {x.get("outlet") or x["source"] for x in g["articles"] if x.get("outlet") or x["source"]}
        if len(srcs) >= min_sources or any(KEEP.search(x["title"]) for x in g["articles"]):
            out.append({"title": g["title"], "date": g["date"], "link": g["link"], "sources": sorted(srcs),
                        "n": len(g["articles"]), "last": max(x["date"] for x in g["articles"])})
    return sorted(out, key=lambda e: e["last"], reverse=True)
