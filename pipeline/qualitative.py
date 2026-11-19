"""사업보고서·10-K의 정성 부분 찾기 (정성 자료 B) — 그때그때 보고 싶은 주제·낱말만 원문 그대로 보여준다

사용자 결정 (2026-11-19)
- 고정된 절 목록을 두지 않는다. 주제 메뉴는 고르기 쉽게 둔 것이고, 자유 검색어도 쓸 수 있다.
- 원문 발췌만 보여준다 (AI 요약 없음). 요약이 필요하면 대화에서 요청한다.
- 본문은 분석할 회사의 최신 사업보고서(10-K) 1건만, 그때 승인받고 받는다 (`--fetch`).

주제 메뉴의 출처 (프로필 답): 7-② 해자(대중성·기술 독점성), 4-① 장부 밖 가치(수주잔고), 4-② 잠재적 부채(소송·보증), 위험
"""
import re
import sqlite3

from . import documents
from . import promises as P
from .config import DB_PATH

TOPICS = {
    "해자": (r"시장\s*점유율|점유율|경쟁\s*(상황|요소|우위)|경쟁사|브랜드", r"market share|competitive position|competition|brand"),
    "기술": (r"특허|연구\s*개발|R&D|지식재산|원천기술", r"patent|research and development|intellectual property|proprietary"),
    "수주": (r"수주\s*잔고|수주\s*잔량|수주\s*총액|계약\s*잔액", r"backlog|remaining performance obligation"),
    "우발부채": (r"우발\s*부채|지급\s*보증|소송|피소|담보\s*제공", r"contingenc|legal proceedings|litigation|guarantee"),
    "위험": (r"위험\s*요인|위험\s*관리|리스크", r"risk factors"),
}


def latest_annual(company_id: str) -> dict | None:
    """가장 최근 사업보고서(10-K/20-F)의 접수번호. 한국은 정정본이 있으면 가장 최근 정정본."""
    c = sqlite3.connect(DB_PATH)
    if company_id.startswith("KR:"):
        rows = c.execute("SELECT filed, rcept_no, title FROM filings WHERE company_id = ? AND title LIKE '%사업보고서 (%' "
                         "ORDER BY filed DESC", (company_id,)).fetchall()
        if not rows:
            return None
        m = re.search(r"\((\d{4}\.\d\d)\)", rows[0][2])
        same = [r for r in rows if m and m.group(1) in r[2]]
        f = same[0] if same else rows[0]
    else:
        f = c.execute("SELECT filed, rcept_no, form FROM filings WHERE company_id = ? AND form IN ('10-K', '20-F') "
                      "ORDER BY filed DESC LIMIT 1", (company_id,)).fetchone()
        if not f:
            return None
    return {"filed": f[0], "rcept_no": f[1], "title": f[2]}


def have(company_id: str, rcept_no: str) -> bool:
    return P._have_doc(company_id, rcept_no)


def search(company_id: str, rcept_no: str, topics: list[str], keyword: str | None, context: int = 2,
           limit: int = 30) -> list[dict]:
    """[{topic, part, section, line, text}] — 원문 그대로."""
    kr = company_id.startswith("KR:")
    pats = [(t, TOPICS[t][0 if kr else 1]) for t in topics if t in TOPICS]
    if keyword:
        pats.append(("검색어", keyword))
    out = []
    toc = re.compile(r"\|\s*\d{1,3}\s*$|^\s*(Item|ITEM)\s+\d+[A-K]?\.\s*\|")   # 목차 줄 ('Item 3. | Legal Proceedings | 20')
    for p in documents.parts(company_id, rcept_no):
        lines = (p["text"] or "").split("\n")
        for topic, pat in pats:
            for sec, i, ctx in documents.grep(p["text"] or "", pat, context):
                if toc.search(lines[i]):
                    continue
                out.append({"topic": topic, "part": p["part"], "part_title": p["part_title"], "section": sec,
                            "line": i, "text": ctx})
    # 같은 줄이 여러 주제에 걸리면 한 번만
    seen, uniq = set(), []
    for h in out:
        k = (h["part"], h["line"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)
    return uniq[:limit] if limit else uniq
