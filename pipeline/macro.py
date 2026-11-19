"""거시 지표 (정성 자료 F) — 2주차 6번: 기업 위주로 판단하고, 큰 흐름은 살 시점을 정할 때 참고한다

- 지표: 7주차에 나온 금리·환율·유가 (사용자 결정 2026-11-19)
- 출처: 한국은행 ECOS, 미국 FRED. 둘 다 공식 API, 사용자가 키를 발급해 .env 에 넣는다 (ECOS_API_KEY, FRED_API_KEY).
- 받은 응답은 data/raw/macro/ 에 그대로 보관한다. fetch() 는 사용자 승인 후에만 호출한다.
- 판정하지 않는다. 최근 값, 1년 전, 최근 5년 범위만 보여준다.

AI가 정한 값 (criteria/README.md): 지표 5개와 통계 코드, 기간 5년
"""
import json
from datetime import date, timedelta

from .config import RAW_DIR, ecos_key, fred_key
from .http import get

DIR = RAW_DIR / "macro"
YEARS = 5

# (이름, 출처, 코드, 주기, ECOS 항목코드, 단위)
SERIES = [
    ("한국 기준금리", "ECOS", "722Y001", "M", "0101000", "%"),
    ("원/달러 환율", "ECOS", "731Y001", "D", "0000001", "원"),
    ("미국 기준금리 (실효 연방기금금리)", "FRED", "FEDFUNDS", "M", None, "%"),
    ("미국 10년 국채 금리", "FRED", "DGS10", "D", None, "%"),
    ("국제 유가 (WTI)", "FRED", "DCOILWTICO", "D", None, "달러/배럴"),
]


def _file(code: str):
    return DIR / f"{code}.json"


def fetch(progress=print) -> dict:
    """승인 후에만 호출. 최근 5년치를 받아 원본 그대로 저장."""
    DIR.mkdir(parents=True, exist_ok=True)
    end = date.today()
    start = end - timedelta(days=365 * YEARS + 10)
    done = {}
    for name, src, code, cyc, item, _ in SERIES:
        try:
            if src == "ECOS":
                k = ecos_key()
                if not k:
                    done[name] = "키 없음 (.env 의 ECOS_API_KEY)"
                    continue
                s, e = (start.strftime("%Y%m"), end.strftime("%Y%m")) if cyc == "M" else \
                    (start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
                r = get(f"https://ecos.bok.or.kr/api/StatisticSearch/{k}/json/kr/1/10000/{code}/{cyc}/{s}/{e}/{item}").json()
                if "StatisticSearch" not in r:
                    done[name] = f"실패: {r.get('RESULT', r)}"
                    continue
            else:
                k = fred_key()
                if not k:
                    done[name] = "키 없음 (.env 의 FRED_API_KEY)"
                    continue
                r = get("https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": code, "api_key": k, "file_type": "json",
                                "observation_start": str(start)}).json()
                if "observations" not in r:
                    done[name] = f"실패: {r.get('error_message', r)}"
                    continue
            _file(code).write_text(json.dumps({"source": src, "code": code, "fetched": str(end), "data": r},
                                              ensure_ascii=False), encoding="utf-8")
            done[name] = "받음"
        except Exception as e:  # noqa: BLE001
            done[name] = f"실패: {e}"
    for k, v in done.items():
        progress(f"  {k}: {v}")
    return done


def load() -> list[dict]:
    """지표별 [(날짜, 값)] 과 요약 (최근, 1년 전, 5년 최저·최고)."""
    out = []
    for name, src, code, cyc, item, unit in SERIES:
        f = _file(code)
        row = {"name": name, "source": src, "code": code, "unit": unit, "points": [], "fetched": None}
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            row["fetched"] = d.get("fetched")
            if src == "ECOS":
                for x in d["data"]["StatisticSearch"]["row"]:
                    t = x["TIME"]
                    day = f"{t[:4]}-{t[4:6]}-{t[6:8] if len(t) == 8 else '01'}"
                    try:
                        row["points"].append((day, float(x["DATA_VALUE"])))
                    except ValueError:
                        pass
            else:
                for x in d["data"]["observations"]:
                    try:
                        row["points"].append((x["date"], float(x["value"])))
                    except ValueError:      # FRED 는 휴일에 '.' 을 넣는다
                        pass
        pts = row["points"]
        if pts:
            last_d, last_v = pts[-1]
            year_ago = str(date.fromisoformat(last_d) - timedelta(days=365))
            prev = [v for d_, v in pts if d_ <= year_ago]
            vals = [v for _, v in pts]
            row.update({"last": (last_d, last_v), "year_ago": prev[-1] if prev else None,
                        "low": min(vals), "high": max(vals), "first": pts[0][0]})
        out.append(row)
    return out
