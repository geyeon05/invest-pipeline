"""한국 기업 사업보고서 XBRL 원본 (DART /api/fnlttXbrl.xml) — 주석 숫자 읽기.

손익계산서 본문에 없는 이자비용을 주석 XBRL에서 가져온다 (투자기준 5, 사용자 결정 2026-11-18).
- 받은 zip 은 data/raw/KR/<고유번호>/xbrl/<접수번호>.zip 에 그대로 보관한다. fetch() 는 사용자 승인 후에만 호출한다.
- 주석 XBRL은 2023년분 사업보고서(2024년 제출)부터 있다. 작은 회사는 2024년분부터 (실제 사례: 고영).
  그 이전 보고서는 재무제표 본문 숫자만 있다 → 2021년 이전 이자비용은 빈칸 (사용자 결정).
- 보고서 1건에 당기·전기 2년치가 있으므로 최근 사업보고서와 2년 전 사업보고서면 4년이 채워진다.

이자비용 고르는 규칙 (사용자 결정)
1. 연결 기준 (연결 숫자가 없는 회사는 별도)
2. 다른 축이 없거나 '합계' 축(ReportedAmountMember, FinancialLiabilitiesCategoryMember)인 값만
3. 우선순위: dart:InterestExpenseFinanceExpense (금융비용 주석의 이자비용) → ifrs-full:InterestExpense
   → ifrs-full:InterestRevenueExpense 의 상각후원가 금융부채 몫 ('범위 차이': 리스 이자 등이 빠졌을 수 있음, 현대건설 2022~23)
   같은 태그가 여러 주석에 다른 값으로 나오면 금융비용 주석(ReportedAmountMember) 값을 쓴다 (_parse 참고)
4. 앞의 두 태그가 함께 있고 값이 1% 넘게 다르면 앞의 값을 쓰고 '범위 차이' 표시
5. 퇴직급여 순이자(…DefinedBenefit…)는 빚의 이자가 아니므로 쓰지 않는다
6. 부호는 양수로 통일 (이마트·셀트리온은 음수로 태깅)
7. 같은 연도가 두 보고서에 있으면 그 연도가 당기인 보고서의 값을 쓴다
"""
import re
import sqlite3
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from functools import lru_cache

from .config import DB_PATH, RAW_DIR, dart_key
from .http import get

NS_X = "{http://www.xbrl.org/2003/instance}"
NS_XDI = "{http://xbrl.org/2006/xbrldi}"
CS_AXIS = "ConsolidatedAndSeparateFinancialStatementsAxis"
TOTAL_MEMBERS = {"ReportedAmountMember", "FinancialLiabilitiesCategoryMember"}
PRIMARY = ("dart:InterestExpenseFinanceExpense", "ifrs-full:InterestExpense")
FALLBACK = ("ifrs-full:InterestRevenueExpense",
            {"ClassesOfFinancialInstrumentsAxis": "FinancialLiabilitiesAtAmortisedCostCategoryMember"})


def _dir(company_id: str):
    return RAW_DIR / "KR" / company_id.split(":", 1)[1] / "xbrl"


def _reports(company_id: str) -> list[tuple[int, str, str]]:
    """(사업연도, 접수번호, 제목) — 정정 포함, 제출 순."""
    rows = sqlite3.connect(DB_PATH).execute(
        "SELECT rcept_no, title FROM filings WHERE company_id = ? AND title LIKE '%사업보고서%' ORDER BY filed",
        (company_id,)).fetchall()
    out = []
    for rcept, title in rows:
        if (m := re.search(r"사업보고서\s*\((\d{4})\.\d\d\)", title)):
            out.append((int(m.group(1)), rcept, title))
    return out


def targets(company_id: str) -> list[tuple[int, str]]:
    """받을 보고서: 최근 사업연도와 2년 전 (각각 최초 제출본)."""
    reps = _reports(company_id)
    if not reps:
        return []
    last = max(fy for fy, _, _ in reps)
    out = []
    for fy in (last, last - 2):
        orig = [r for r in reps if r[0] == fy and "정정" not in r[2]]
        if orig:
            out.append((fy, orig[0][1]))
    return out


def _have(company_id: str, fy: int) -> bool:
    d = _dir(company_id)
    return any((d / f"{r}.zip").exists() for y, r, _ in _reports(company_id) if y == fy)


def missing(company_id: str) -> list[tuple[int, str]]:
    d = _dir(company_id)
    return [(fy, r) for fy, r in targets(company_id)
            if not _have(company_id, fy) and not (d / f"{r}.unavailable").exists()]


def fetch(company_id: str, progress=print) -> int:
    """승인 후에만 호출. 최초 제출본에 파일이 없으면(014) 가장 최근 정정본을 시도한다 (실제 사례: 카카오 2023년분)."""
    d = _dir(company_id)
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for fy, rcept in missing(company_id):
        tries = [rcept] + [r for y, r, t in reversed(_reports(company_id)) if y == fy and "정정" in t][:1]
        for r in tries:
            resp = get("https://opendart.fss.or.kr/api/fnlttXbrl.xml",
                       params={"crtfc_key": dart_key(), "rcept_no": r, "reprt_code": "11011"})
            time.sleep(0.3)
            if resp.content[:2] == b"PK":
                (d / f"{r}.zip").write_bytes(resp.content)
                n += 1
                progress(f"  받음 XBRL {fy}년분 {r}")
                break
            m = re.search(rb"<status>(\d+)</status>", resp.content)
            progress(f"  없음 XBRL {fy}년분 {r} ({m.group(1).decode() if m else '?'})")
        else:
            (d / f"{rcept}.unavailable").write_text("DART: 파일 없음", encoding="utf-8")
    return n


@lru_cache(maxsize=64)
def _parse(path: str) -> tuple[int, dict]:
    """한 보고서의 이자비용 후보 → (보고서 사업연도, {연도: {태그: 값}})."""
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith(".xbrl"))))
    ctx = {}
    for c in root.iter(NS_X + "context"):
        per = c.find(NS_X + "period")
        st, en = per.findtext(NS_X + "startDate"), per.findtext(NS_X + "endDate")
        dims = {m.get("dimension").split(":")[-1]: (m.text or "").split(":")[-1]
                for m in c.iter(NS_XDI + "explicitMember")}
        ctx[c.get("id")] = (st, en, dims)
    cands = {}
    has_cons = False
    for el in root:
        if not el.get("contextRef"):
            continue
        uri, tag = el.tag[1:].split("}")
        seg = uri.rstrip("/").rsplit("/", 1)[-1]          # .../dart, .../ifrs-full, .../entity00126380
        full = f"{seg if seg in ('dart', 'ifrs-full') else 'entity'}:{tag}"
        if full not in PRIMARY and full != FALLBACK[0]:
            continue
        st, en, dims = ctx[el.get("contextRef")]
        dims = dict(dims)   # 같은 context 를 여러 사실이 공유하므로 복사해서 쓴다
        if not (st and en) or not 330 <= (date.fromisoformat(en) - date.fromisoformat(st)).days <= 400:
            continue
        basis = dims.pop(CS_AXIS, None)
        has_cons |= basis == "ConsolidatedMember"
        if full == FALLBACK[0]:
            if dims != FALLBACK[1]:
                continue
        elif dims and not set(dims.values()) <= TOTAL_MEMBERS:
            continue
        try:
            v = abs(float(el.text))
        except (TypeError, ValueError):
            continue
        # 같은 태그가 주석마다 다른 값으로 나온다: 'ReportedAmountMember' = 금융비용 주석 합계(리스 이자 포함),
        # 축 없음 = 금융상품 범주별 손익 주석(차입금 이자만일 수 있음). 금융비용 주석 값을 우선 (사용자 결정).
        # (실제 사례: 셀트리온 2024 금융비용 주석 756억 = 범주별 주석 742억 + 리스 이자 14억)
        rank = 0 if "ReportedAmountMember" in dims.values() else (1 if dims else 2)
        slot = cands.setdefault((basis, int(en[:4])), {})
        if full not in slot or rank < slot[full][0]:
            slot[full] = (rank, v)
    want = "ConsolidatedMember" if has_cons else None
    out = {}
    for (basis, y), tags in cands.items():
        if basis == want or (want is None and basis in (None, "SeparateMember")):
            out.setdefault(y, {}).update({t: v for t, (_, v) in tags.items()})
    fy = max(out) if out else 0
    return fy, {"basis": "연결" if has_cons else "별도", "years": out}


def interest_expense(company_id: str) -> list[dict]:
    """연도별 이자비용 (standard 항목 행 형식)."""
    best = {}
    for f in sorted(_dir(company_id).glob("*.zip")):
        fy, res = _parse(str(f))
        for y, tags in res["years"].items():
            current = y == fy
            if y in best and (best[y]["_current"] or not current):
                continue
            p = [tags[t] for t in PRIMARY if t in tags]
            if p:
                v, used = p[0], next(t for t in PRIMARY if t in tags)
                match, note = "exact", ""
                if len(p) == 2 and abs(p[0] - p[1]) > 0.01 * max(p):
                    match = "scope"
                    note = (f"같은 보고서에 이자비용이 두 값: 금융비용 주석 {p[0] / 1e8:,.0f}억, "
                            f"다른 주석 {p[1] / 1e8:,.0f}억 → 금융비용 주석 값 사용")
            elif FALLBACK[0] in tags:
                v, used, match = tags[FALLBACK[0]], FALLBACK[0], "scope"
                note = "이자비용 합계 태그 없음 → 상각후원가 금융부채의 이자 (리스 이자 등이 빠졌을 수 있음)"
            else:
                continue
            if res["basis"] == "별도":
                note = (note + " / " if note else "") + "연결 숫자 없음 → 별도 기준"
            best[y] = {"item": "interest_expense", "year": y, "period_end": f"{y}-12-31", "value": v,
                       "currency": "KRW", "source": f"{used}  (사업보고서 XBRL 주석, {res['basis']})",
                       "filing": f.stem, "method": "xbrl+abs", "match": match, "match_note": note,
                       "_current": current}
    return [{k: v for k, v in r.items() if k != "_current"} for _, r in sorted(best.items())]
