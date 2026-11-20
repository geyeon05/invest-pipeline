"""분석 진행 화면 (내 컴퓨터에서만): uv run server.py  →  http://localhost:8501

- 화면은 web/ 의 HTML (기업분석 진행 화면 시안을 옮긴 것, 2026-11-20).
- 이 프로그램은 화면과 공책(pipeline/notebook.py)을 잇기만 한다. 계산은 엔진(pipeline/flow.py), 판단 규칙은 공책 모듈.
- 외부 요청 없음 (받아 둔 자료만). 127.0.0.1 에만 열고, 다른 주소에서 온 요청은 받지 않는다 (인터넷 공개 금지, API 키 보안).
- 파이썬 기본 기능만 쓴다 (설치 없음).
"""
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pipeline import case, flow, holdings, notebook, prices, report, service

sys.stdout.reconfigure(encoding="utf-8")
HOST, PORT = "127.0.0.1", 8501
WEB = Path(__file__).resolve().parent / "web"
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
WRITE_KINDS = {"draft", "revise", "confirm", "checked", "reopen", "open-final", "bought", "start-check"}   # 화면(사용자)이 적는 것. 피드백은 Claude가 note 명령으로


def companies() -> list[dict]:
    df = service.collected_companies()
    return [{"company_id": r["company_id"], "name": r["name"], "ticker": r["ticker"], "market": r["market"]}
            for r in df.to_dict("records")]


def company(cid: str) -> dict:
    c = next((c for c in companies() if c["company_id"] == cid), None)
    if c is None:
        raise notebook.NotebookError("받아 둔 회사가 아님")
    return c


def book_view(c: dict, base=None, book=None) -> dict:
    """공책 + 화면이 바로 쓸 상태 값 (상태 계산은 공책 모듈의 규칙 그대로). base: 과제용 회사 공책 폴더."""
    book = book or notebook.load(c, base)
    view = {"company": c, "book": book, "steps": notebook.STEPS, "implemented": list(flow.IMPLEMENTED)}
    if book and book["rounds"]:
        r = notebook.current_round(book)
        view["status"] = {k: notebook.status(p) for k, p in r["steps"].items()}
        view["open_checks"] = {k: len(notebook.open_checks(p)) for k, p in r["steps"].items()}   # 단계 전체 것
        # 논의 항목(켜진 신호)마다: 상태, 확정을 막는 확인할 것 수 (단계 전체 것 + 그 항목 것)
        view["items"] = {k: [{"status": notebook.item_status(it), "open": len(notebook.open_checks(p, it))}
                             for it in notebook.live_items(p)] for k, p in r["steps"].items()}
        view["final_lock"] = notebook.final_lock(book) if book.get("kind") != "case" else []
        view["final_choices"] = list(notebook.FINAL_CHOICES)
        view["hold_choices"] = list(notebook.HOLD_CHOICES)
        view["holding"] = book.get("holding") or False
        view["sold"] = book.get("sold")
    return view


def price_view(cid: str) -> dict:
    """주가 칸: 받아 둔 주가만 읽는다 (외부 요청 없음). 1년 = 월말 종가 12개, 5년 = 분기말 종가 20개."""
    px, _, meta = prices.load(cid)
    if px.empty:
        return {"have": False}
    px = px.dropna()
    last_day, last = px.index[-1], float(px.iloc[-1])
    prev = float(px.iloc[-2]) if len(px) > 1 else None

    def series(rule, n, fmt):
        s = px.resample(rule).last().dropna().iloc[-n:]
        return [{"label": d.strftime(fmt), "value": float(v)} for d, v in s.items()]
    return {"have": True, "date": str(last_day.date()), "last": last, "prev": prev,
            "currency": meta.get("currency") or ("KRW" if cid.startswith("KR:") else "USD"),
            "symbol": meta.get("symbol"), "y1": series("ME", 12, "%y.%m"),
            "y5": [{"label": f"{d.strftime('%y')}.{(d.month - 1) // 3 + 1}Q", "value": v["value"]}
                   for d, v in zip(px.resample("QE").last().dropna().index[-20:], series("QE", 20, "%y.%m"))]}


def case_view(cid: str) -> dict:
    cs = case.load(cid)
    return {"case": cs, "stages": case.STAGES, "book": book_view(case.book_company(cs), book=case.load_book(cs)),
            "grid": case.grid(cs)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):     # 조용히 (요청마다 줄을 찍지 않음)
        pass

    def _ok_host(self) -> bool:
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self.send_error(HTTPStatus.FORBIDDEN, "localhost only")
            return False
        return True

    def _json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._ok_host():
            return
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/companies":
                return self._json(companies())
            if u.path == "/api/book":
                return self._json(book_view(company(q.get("cid", ""))))
            if u.path == "/api/cases":
                return self._json(case.list_cases())
            if u.path == "/api/case":
                return self._json(case_view(q.get("id", "")))
            if u.path == "/api/case/company":
                return self._json(book_view(company(q.get("cid", "")), case.companies_base(case.load(q.get("id", ""))["id"])))
            if u.path == "/out-case":                       # 과제 결과물 열기: case.json 에 등록된 파일만
                cs = case.load(q.get("id", ""))
                name = q.get("name", "")
                allowed = {x for o in cs.get("outputs", []) for x in (o.get("path"), o.get("pdf")) if x}
                if name not in allowed:
                    return self.send_error(HTTPStatus.NOT_FOUND)
                f = (case.ROOT / name).resolve()
                if f.suffix not in (".pdf", ".md") or not f.is_file():
                    return self.send_error(HTTPStatus.NOT_FOUND)
                body = f.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/pdf" if f.suffix == ".pdf" else "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/out":                            # 결과물 열기: 그 회사 공책 폴더의 pdf·md 만
                c = company(q.get("cid", ""))
                folder = notebook.path_for(c).parent.resolve()
                f = (folder / q.get("name", "")).resolve()
                if f.parent != folder or f.suffix not in (".pdf", ".md") or not f.is_file():
                    return self.send_error(HTTPStatus.NOT_FOUND)
                body = f.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/pdf" if f.suffix == ".pdf" else "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/api/price":
                return self._json(price_view(company(q.get("cid", ""))["company_id"]))
        except notebook.NotebookError as e:
            return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        name = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        f = (WEB / name).resolve()
        if WEB not in f.parents or not f.is_file() or f.suffix not in TYPES:
            return self.send_error(HTTPStatus.NOT_FOUND)
        body = f.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", TYPES[f.suffix])
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._ok_host():
            return
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            c = company(data.get("cid", "")) if not self.path.startswith("/api/case/") else None
            if self.path == "/api/run":                    # 공책이 없을 때만: 계산해서 공책 만들기
                if notebook.load(c):
                    raise notebook.NotebookError("공책이 이미 있음 (다시 분석은 대화창에서 회차를 정해 run)")
                b = notebook.new_book(c)
                notebook.new_round(b, "처음부터")
                for no, res in flow.run(c["company_id"]).items():
                    notebook.put_result(b, no, res)
                notebook.save(c, b)
            elif self.path == "/api/outputs":              # 결과물 3종 (최종 판단을 확정한 뒤에만)
                report.make_all(c)
            elif self.path == "/api/case/outputs":          # 과제 6단계: 검증표·역할구분 + 보고서 PDF
                cs = case.load(data.get("id", ""))
                report.make_case(cs)
                case.save(cs)
                return self._json(case_view(cs["id"]))
            elif self.path == "/api/case/note":             # 과제: 회사 공책(cid 있음) 또는 과제 공책(질문·주장)
                cs = case.load(data.get("id", ""))
                kind = data.get("kind")
                if kind not in WRITE_KINDS - {"open-final"}:
                    raise notebook.NotebookError("화면에서 적을 수 없는 종류")
                step = data.get("step")
                step = int(step) if str(step).isdigit() else step
                item_no = None if data.get("item") in (None, "") else int(data["item"])
                text = (data.get("text") or "").strip()
                if data.get("cid"):
                    cc, base = company(data["cid"]), case.companies_base(cs["id"])
                    b = notebook.load(cc, base)
                    notebook.add_log(b, step, kind, text, item_no)
                    notebook.save(cc, b, base)
                else:
                    b = case.load_book(cs)
                    notebook.add_log(b, step, kind, text, item_no)
                    case.save_book(cs, b)
                return self._json(case_view(cs["id"]))
            elif self.path == "/api/note":
                kind = data.get("kind")
                if kind not in WRITE_KINDS:
                    raise notebook.NotebookError("화면에서 적을 수 없는 종류")
                b = notebook.load(c)
                if b is None:
                    raise notebook.NotebookError("공책이 아직 없음")
                if kind == "open-final":
                    notebook.open_final(b, flow.final_summary(b))
                elif kind == "bought":                       # 사용자가 화면에서 '샀다'를 누름
                    notebook.mark_bought(b, str(data.get("day") or "")[:10] or notebook._now()[:10], (data.get("text") or "").strip())
                elif kind == "start-check":                  # 보유 점검 시작 (외부 요청 없음)
                    reason = data.get("reason") if data.get("reason") in ("정기", "바로") else "정기"
                    summary, items, checks = flow.holding_check(b, c)
                    notebook.start_check(b, reason, summary, items, checks)
                else:
                    item_no = data.get("item")
                    step = data.get("step")
                    notebook.add_log(b, int(step) if str(step).isdigit() else str(step), kind, (data.get("text") or "").strip(),
                                     None if item_no in (None, "") else int(item_no),
                                     data.get("conclusion"), data.get("recheck"))
                notebook.save(c, b)
                holdings.write()                             # 보유 목록(보기용)도 다시
            else:
                return self.send_error(HTTPStatus.NOT_FOUND)
        except notebook.NotebookError as e:
            return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        except (ValueError, TypeError) as e:
            return self._json({"error": f"요청 형식 오류: {e}"}, HTTPStatus.BAD_REQUEST)
        return self._json(book_view(c))


if __name__ == "__main__":
    print(f"분석 진행 화면: http://localhost:{PORT}  (끄려면 Ctrl+C)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
