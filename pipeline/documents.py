"""공시 본문 수집 (요청 시에만).

- 국내: DART 공시서류원본  https://opendart.fss.or.kr/api/document.xml  (zip: 본문 XML + 첨부 감사보고서 등)
- 해외: SEC EDGAR 주문서(primary document) HTML  (공시 목록의 원문 URL)

원칙
- 받은 파일은 그대로 data/raw/<시장>/<고유번호>/docs/ 에 보관한다 (증거).
- DB에는 '읽을 수 있는 텍스트'로 바꿔 저장한다. 내용은 바꾸지 않고 형식만 바꾼다:
  장·절 제목은 '#' 줄로, 문단은 빈 줄로, 표는 행마다 ' | ' 로 칸을 나눈다.
- 해외 문서의 숨김 XBRL 데이터(ix:header), 스크립트·스타일은 제외한다 (화면에 보이지 않는 내용).
"""
import io
import re
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser

from .config import RAW_DIR, dart_key
from .http import get
from .store import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS filing_docs (
    company_id TEXT, rcept_no TEXT, part INTEGER, part_name TEXT, part_title TEXT,
    source_url TEXT, raw_path TEXT, fetched_at TEXT, chars INTEGER, text TEXT,
    PRIMARY KEY (company_id, rcept_no, part)
);
"""

BLOCK = {"p", "div", "br", "tr", "li", "table", "tbody", "thead", "pgbrk", "h1", "h2", "h3", "h4", "h5", "h6",
         "library", "table-group", "body"}
CELL = {"td", "th", "te", "tu"}
SKIP = {"script", "style", "ix:header", "head", "summary"}  # summary = DART 기계용 메타데이터
DART_SECTION = re.compile(r"^section-(\d+)$")


class _TextExtractor(HTMLParser):
    """DART XML / SEC HTML → 구조를 살린 텍스트."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.line: list[str] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.skip = 0
        self.section_level = 0
        self.in_title = False
        self.title_buf: list[str] = []
        self.spans: list[bool] = []  # 줄 맨 앞에서 시작한 굵은 글씨(소제목)인지

    # ---- 출력 도우미 ----
    def _flush_line(self):
        # 공백류 통일: 일반 공백, 탭, NBSP, 전각 공백, thin space 등
        s = re.sub(r"[ 	 　   ]+", " ", "".join(self.line)).strip()
        if s:
            self.out.append(s)
        self.line = []

    def _blank(self):
        self._flush_line()
        if self.out and self.out[-1] != "":
            self.out.append("")

    # ---- 파서 콜백 ----
    def handle_starttag(self, tag, attrs):
        if tag in SKIP or (tag == "div" and "display:none" in (dict(attrs).get("style") or "").replace(" ", "")):
            self.skip += 1
            return
        if self.skip:
            if tag in SKIP or tag == "div":
                self.skip += 1
            return
        m = DART_SECTION.match(tag)
        if m:
            self.section_level = int(m.group(1))
        elif tag == "title" and self.section_level:
            self._blank()
            self.in_title, self.title_buf = True, []
        elif tag == "tr":
            self._flush_line()
            self.row = []
        elif tag in CELL and self.row is not None:
            self.cell = []
        elif tag == "span":
            # DART 소제목: 문단 맨 앞의 굵은 글씨 (<SPAN USERMARK="F-14 B">가. 재무위험관리정책</SPAN>본문...)
            bold = "B" in (dict(attrs).get("usermark") or "").split()
            self.spans.append(bold and self.cell is None and not "".join(self.line).strip())
        elif tag in BLOCK:
            self._blank() if tag in {"p", "table", "h1", "h2", "h3", "h4", "pgbrk"} else self._flush_line()

    def handle_endtag(self, tag):
        if self.skip:
            if tag in SKIP or tag == "div":
                self.skip -= 1
            return
        if tag == "title" and self.in_title:
            title = re.sub(r"\s+", " ", "".join(self.title_buf)).strip()
            if title:
                self.out.append("#" * min(self.section_level, 4) + " " + title)
                self.out.append("")
            self.in_title = False
        elif tag in CELL and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            cells = [c for c in self.row]
            if any(cells):
                self.out.append(" | ".join(cells))
            self.row = None
        elif tag == "span" and self.spans:
            if self.spans.pop() and not self.in_title:
                self._flush_line()  # 소제목 뒤 줄바꿈
        elif tag == "table":
            self._blank()
        elif tag in BLOCK:
            self._flush_line()

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title_buf.append(data)
        elif self.cell is not None:
            self.cell.append(data)
        else:
            self.line.append(data)

    def text(self) -> str:
        self._flush_line()
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.out)).strip() + "\n"


# 'Item 1A. Risk Factors'(10-K), 'ITEM 10.ADDITIONAL INFORMATION'(20-F)
# 번호 뒤 마침표 필수 + 대문자로 시작하는 제목 → 표지의 'Item 17 o Item 18 o', 본문 문장 'Item 16G as well as' 제외
SEC_ITEM = re.compile(r"^(?:Item|ITEM)\s+(\d{1,2}[A-K]?)\.\s*([A-Z\[“\"].{2,150})$")


def _mark_sec_items(text: str) -> str:
    """10-K/10-Q/20-F 본문의 'Item 1A. Risk Factors' 같은 제목 줄을 '## ' 제목으로 표시.
    목차의 Item 줄은 표 행(' | ' 포함)이라 제외된다."""
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if " | " not in ln and SEC_ITEM.match(ln.strip()):
            lines[i] = "## " + ln.strip()
    return "\n".join(lines)


def to_text(markup: str, sec: bool = False) -> str:
    p = _TextExtractor()
    p.feed(markup)
    p.close()
    t = p.text()
    return _mark_sec_items(t) if sec else t


# ---------------- 수집 ----------------
def _filing(conn, company_id: str, rcept_no: str):
    row = conn.execute("SELECT rcept_no, form, title, filed, url FROM filings WHERE company_id = ? AND rcept_no = ?",
                       (company_id, rcept_no)).fetchone()
    if not row:
        raise ValueError(f"{company_id} 의 공시 목록에 접수번호 {rcept_no} 가 없습니다. 공시 목록에서 확인하세요.")
    return dict(zip(["rcept_no", "form", "title", "filed", "url"], row))


def _fetch_kr(company_id: str, f: dict) -> list[dict]:
    corp = company_id.split(":", 1)[1]
    resp = get("https://opendart.fss.or.kr/api/document.xml", params={"crtfc_key": dart_key(), "rcept_no": f["rcept_no"]})
    if not resp.content.startswith(b"PK"):
        raise RuntimeError(f"DART 원문을 받을 수 없습니다: {resp.text[:200]}")
    d = RAW_DIR / "KR" / corp / "docs"
    d.mkdir(parents=True, exist_ok=True)
    raw_path = d / f"{f['rcept_no']}.zip"
    raw_path.write_bytes(resp.content)
    return _parse_kr_zip(resp.content, f, raw_path)


def _decode_xml(data: bytes) -> str:
    """XML 선언의 인코딩을 따라 읽는다. 오래된 DART 문서는 EUC-KR 이다.
    선언이 없거나 틀리면 UTF-8 → CP949(EUC-KR 확장) 순으로 시도."""
    m = re.match(rb'\s*<\?xml[^>]*encoding=["\']([A-Za-z0-9_\-]+)["\']', data)
    tried = []
    for enc in ([m.group(1).decode("ascii")] if m else []) + ["utf-8", "cp949"]:
        enc = "cp949" if enc.lower() in ("euc-kr", "euckr", "ks_c_5601-1987") else enc
        if enc in tried:
            continue
        tried.append(enc)
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _parse_kr_zip(content: bytes, f: dict, raw_path) -> list[dict]:
    parts = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names = sorted(z.namelist(), key=lambda n: (n != f"{f['rcept_no']}.xml", n))  # 본문 먼저, 첨부 뒤
        for i, name in enumerate(names):
            xml = _decode_xml(z.read(name))
            m = re.search(r"<DOCUMENT-NAME[^>]*>([^<]*)</DOCUMENT-NAME>", xml)
            title = m.group(1).strip() if m else (f["title"] if i == 0 else name)
            parts.append({"part": i, "part_name": name, "part_title": title,
                          "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f['rcept_no']}",
                          "raw_path": str(raw_path), "text": to_text(xml)})
    return parts


def _fetch_us(company_id: str, f: dict) -> list[dict]:
    cik = company_id.split(":", 1)[1]
    resp = get(f["url"], sec=True)
    d = RAW_DIR / "US" / cik / "docs"
    d.mkdir(parents=True, exist_ok=True)
    raw_path = d / (f["rcept_no"] + "_" + f["url"].rsplit("/", 1)[-1])
    raw_path.write_bytes(resp.content)
    html = resp.content.decode(resp.encoding or "utf-8", errors="replace")
    return [{"part": 0, "part_name": f["url"].rsplit("/", 1)[-1], "part_title": f["form"] or f["title"],
             "source_url": f["url"], "raw_path": str(raw_path), "text": to_text(html, sec=True)}]


def fetch(company_id: str, rcept_no: str, force: bool = False) -> dict:
    """공시 본문을 받아 저장한다 (이미 있으면 그대로). 요약을 반환."""
    conn = connect()
    conn.executescript(SCHEMA)
    f = _filing(conn, company_id, rcept_no)
    have = conn.execute("SELECT COUNT(*) FROM filing_docs WHERE company_id = ? AND rcept_no = ?",
                        (company_id, rcept_no)).fetchone()[0]
    if have and not force:
        return {"collected": False, **f}
    parts = (_fetch_kr if company_id.startswith("KR:") else _fetch_us)(company_id, f)
    _store(conn, company_id, rcept_no, parts)
    return {"collected": True, **f, "parts": [(p["part_title"], len(p["text"])) for p in parts]}


def rebuild_from_raw(company_id: str, rcept_no: str) -> dict:
    """보관된 원본 파일에서 텍스트를 다시 만든다 (DART/SEC 요청 없음). 변환 규칙을 고쳤을 때 사용."""
    conn = connect()
    conn.executescript(SCHEMA)
    f = _filing(conn, company_id, rcept_no)
    row = conn.execute("SELECT raw_path FROM filing_docs WHERE company_id = ? AND rcept_no = ? AND part = 0",
                       (company_id, rcept_no)).fetchone()
    if not row:
        raise ValueError(f"받아 둔 본문이 없습니다: {company_id} {rcept_no}")
    from pathlib import Path
    raw_path = Path(row[0])
    if company_id.startswith("KR:"):
        parts = _parse_kr_zip(raw_path.read_bytes(), f, raw_path)
    else:
        html = raw_path.read_bytes().decode("utf-8", errors="replace")
        parts = [{"part": 0, "part_name": f["url"].rsplit("/", 1)[-1], "part_title": f["form"] or f["title"],
                  "source_url": f["url"], "raw_path": str(raw_path), "text": to_text(html, sec=True)}]
    _store(conn, company_id, rcept_no, parts)
    return {**f, "parts": [(p["part_title"], len(p["text"])) for p in parts]}


def _store(conn, company_id: str, rcept_no: str, parts: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute("DELETE FROM filing_docs WHERE company_id = ? AND rcept_no = ?", (company_id, rcept_no))
        conn.executemany("INSERT INTO filing_docs VALUES (?,?,?,?,?,?,?,?,?,?)",
                         [(company_id, rcept_no, p["part"], p["part_name"], p["part_title"], p["source_url"],
                           p["raw_path"], now, len(p["text"]), p["text"]) for p in parts])


# ---------------- 조회 ----------------
def list_docs(company_id: str) -> list[dict]:
    conn = connect()
    conn.executescript(SCHEMA)
    rows = conn.execute(
        "SELECT d.rcept_no, f.filed, f.title, COUNT(*), SUM(d.chars), MAX(d.fetched_at) FROM filing_docs d "
        "LEFT JOIN filings f ON f.company_id = d.company_id AND f.rcept_no = d.rcept_no "
        "WHERE d.company_id = ? GROUP BY d.rcept_no ORDER BY f.filed DESC", (company_id,)).fetchall()
    return [dict(zip(["rcept_no", "filed", "title", "parts", "chars", "fetched_at"], r)) for r in rows]


def parts(company_id: str, rcept_no: str) -> list[dict]:
    conn = connect()
    conn.executescript(SCHEMA)
    rows = conn.execute("SELECT part, part_name, part_title, source_url, raw_path, fetched_at, chars, text "
                        "FROM filing_docs WHERE company_id = ? AND rcept_no = ? ORDER BY part",
                        (company_id, rcept_no)).fetchall()
    keys = ["part", "part_name", "part_title", "source_url", "raw_path", "fetched_at", "chars", "text"]
    return [dict(zip(keys, r)) for r in rows]


def outline(text: str) -> list[dict]:
    """'#' 제목 줄로 목차를 만든다: [{no, level, title, start_line, end_line}]"""
    lines = text.split("\n")
    heads = [(i, len(m.group(1)), m.group(2)) for i, ln in enumerate(lines)
             if (m := re.match(r"^(#{1,4}) (.+)$", ln))]
    out = []
    for n, (i, lvl, title) in enumerate(heads):
        end = next((j for j, l2, _ in heads[n + 1:] if l2 <= lvl), len(lines))
        out.append({"no": n + 1, "level": lvl, "title": title, "start_line": i, "end_line": end})
    return out


def section(text: str, key: str) -> tuple[dict, str] | None:
    """목차 번호(예: '12') 또는 제목 일부(예: '사업의 내용', 'Risk Factors')로 절 본문을 꺼낸다."""
    ol = outline(text)
    hit = next((s for s in ol if key.isdigit() and s["no"] == int(key)), None) \
        or next((s for s in ol if key.lower() in s["title"].lower()), None)
    if not hit:
        return None
    lines = text.split("\n")
    return hit, "\n".join(lines[hit["start_line"]:hit["end_line"]])


def grep(text: str, pattern: str, context: int = 1) -> list[tuple[str, int, str]]:
    """키워드가 나오는 줄과 앞뒤 문맥: [(속한 절 제목, 줄 번호, 문맥)]"""
    lines = text.split("\n")
    ol = outline(text)
    rx = re.compile(pattern, re.IGNORECASE)
    hits = []
    for i, ln in enumerate(lines):
        if rx.search(ln) and not ln.startswith("#"):
            sec = next((s["title"] for s in reversed(ol) if s["start_line"] <= i), "(제목 없음)")
            ctx = "\n".join(lines[max(0, i - context): i + context + 1])
            hits.append((sec, i, ctx))
    return hits
