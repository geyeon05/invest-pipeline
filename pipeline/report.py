"""결과물 3종: 분석 보고서 · 검증표 · 역할구분 (analyses/_투자_분석_단계.md 5단계 7)

- 최종 판단을 확정한 회차에서만 만든다 (화면의 '결과물 만들기' 버튼, 사용자 결정 2026-11-20 '가').
- 공책에 있는 것만 쓴다. 새 주장·새 숫자를 만들지 않는다.
- 분석 보고서 순서 (사용자 결정): 결론 → 단계별 확정 판단(사실 + 내 판단) → 가격 판단 → 금리·환율 → 다시 볼 조건.
- 검증표: 엔진이 쓴 공시 값마다 받아 둔 원본(DART 재무제표 / SEC XBRL)과 다시 대조한다 (일치 / 계산값 / 못 찾음 / 불일치).
  판단 글에 직접 쓴 숫자는 자동 대조가 안 되므로 따로 모아 '확인 필요'로 표시한다.
- 역할구분: 공책의 역할 기록 그대로 (기록에 있는 것만).
- PDF: md → HTML → Edge(headless)로 인쇄. 새로 설치하는 것 없음. 외부 요청 없음.
- 저장 위치: 회사 공책 폴더 (analyses/, GitHub에 올리지 않음).
"""
import html
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from . import dart_xbrl, notebook, service

EDGE = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]
ITEM_KO = {"operating_cf": "영업CF", "net_income": "순이익", "equity_total": "자본총계", "total_liabilities": "부채총계",
           "total_assets": "자산총계", "current_assets": "유동자산", "current_liabilities": "유동부채", "inventory": "재고자산",
           "operating_income": "영업이익", "interest_expense": "이자비용", "revenue": "매출", "receivables": "매출채권",
           "contract_assets": "계약자산"}


def _confirmed(it: dict) -> dict | None:
    return next((e for e in reversed(it["log"]) if e["kind"] == "confirm"), None)


def _fb(it: dict) -> list[str]:
    return [e["text"] for e in it["log"] if e["kind"] == "feedback"]


# ---------------- 분석 보고서 ----------------
def analysis_md(book: dict) -> str:
    r = notebook.current_round(book)
    fin = r.get("final") or {}
    fp = r["steps"].get("9")
    fit = fp["items"][0] if fp else None
    last = _confirmed(fit) if fit else None
    out = [f"# {book['name']} 분석 보고서 ({r['no']}회차, {r['mode']})",
           f"- 회사: {book['name']} ({book['company_id']}) · 확정일 {str(fin.get('at', ''))[:10]} · 공책 기준",
           "- 판단은 모두 사용자가 했다. Claude는 자료 수집·계산·피드백만 했다 (역할구분 문서 참고).", "",
           "## 1. 결론", f"**{fin.get('conclusion', '-')}**", "", (last["text"] if last else "-"), ""]
    if fit and _fb(fit):
        out += ["반박·피드백에 대한 답 (최종 판단 중 받은 피드백):"] + [f"- {t}" for t in _fb(fit)] + [""]
    out += ["## 2. 단계별 확정 판단 (사실 + 내 판단)", ""]
    for no in range(1, 8):
        p = r["steps"].get(str(no))
        if p:
            out += _step_md(p)
    out += ["## 3. 가격 판단", ""]
    if (p8 := r["steps"].get("8")):
        out += _step_md(p8, heading=False)
    macro = [l for l in (fp["summary"] if fp else []) if l.startswith("금리·환율")]
    out += ["## 4. 금리·환율 (사는 시점 참고용)", "", *(macro or ["- 받아 둔 자료 없음"]), ""]
    out += ["## 5. 다시 볼 조건", ""] + ([f"- {c}" for c in fin.get("recheck", [])] or ["- 없음"]) + [""]
    return "\n".join(out)


def _step_md(p: dict, heading: bool = True) -> list[str]:
    out = [f"### {p['no']}. {p['name']}"] if heading else []
    out += ["사실:"] + [f"- {l}" for l in p["summary"]]
    if p["lane"] == "info":
        when = next((e["at"][:10] for e in p["log"] if e["kind"] == "checked"), "-")
        out += ["", f"내 판단: 켜진 신호 없음 → 확인함 ({when})", ""]
        return out
    out.append("")
    for it in notebook.live_items(p):
        c = _confirmed(it)
        out += [f"**{it['title']}** — {it['detail']}", "", f"- 내 판단: {c['text'] if c else '(확정 없음)'}"]
        done = [x for x in it["checks"] + p["checks"] if x["status"] == "done"]
        out += [f"- 확인한 것: {x['text']} → {x['result']}" + (f" [{x['source']}]" if x["source"] else "") for x in done]
        out.append("")
    return out


# ---------------- 검증표 ----------------
def _check_value(company_id: str, raw, s: dict) -> tuple[str, str]:
    """엔진이 쓴 공시 값 하나를 받아 둔 원본과 다시 대조한다."""
    if s["match"] == "derived":
        return "계산값", f"계산식: {s['account']}"
    v = s["value"]
    if v is None:
        return "못 찾음", "값 없음"
    if "XBRL 주석" in s["account"]:            # 한국 이자비용: 재무제표 표가 아니라 사업보고서 XBRL 주석 원본 파일
        z = dart_xbrl._dir(company_id) / f"{s['filing']}.zip"
        if not z.exists():
            return "못 찾음", "XBRL 원본 파일 없음 → 확인 필요"
        tag = s["account"].split()[0]
        x = dart_xbrl._parse(str(z))[1]["years"].get(int(s["year"]), {}).get(tag)
        if x is None:
            return "못 찾음", "XBRL 원본에서 같은 연도·태그를 찾지 못함 → 확인 필요"
        ok = abs(float(x) - float(v)) <= max(1.0, abs(float(v)) * 1e-9)
        return ("일치", "XBRL 주석 원본 파일을 다시 읽어 대조") if ok else ("불일치", f"원본 값 {float(x):,.0f}")
    if company_id.startswith("KR:"):
        name = s["account"].split("  [")[0].strip()
        rows = raw[(raw["rcept_no"] == s["filing"]) & (raw["account_nm"].str.strip() == name)]
        vals = [x for col in ("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount") for x in rows[col].dropna()]
    else:
        tag = s["account"].split()[0].split(":")[-1]
        rows = raw[(raw["accn"] == s["filing"]) & (raw["tag"] == tag)]
        vals = list(rows["val"].dropna())
    if not vals:
        return "못 찾음", "원본에서 같은 공시·계정을 찾지 못함 → 확인 필요"
    if any(abs(float(x) - float(v)) <= max(1.0, abs(float(v)) * 1e-9) for x in vals):
        return "일치", ""
    return "불일치", f"원본 값 {', '.join(f'{float(x):,.0f}' for x in vals[:3])}"


NUM = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?\s?(?:%p|%|배|억|조|원|년|건|USD|달러)?")


def verify_md(book: dict) -> tuple[str, dict]:
    r = notebook.current_round(book)
    cid = book["company_id"]
    raw = service.raw_financials(cid)
    rows, seen = [], set()
    for no in range(1, 9):
        p = r["steps"].get(str(no))
        for s in (p or {}).get("sources", []):
            k = (s["item"], s["year"], s["filing"])
            if k in seen:
                continue
            seen.add(k)
            res, note = _check_value(cid, raw, s)
            rows.append((no, s, res, note))
    count = {}
    for *_, res, _ in rows:
        count[res] = count.get(res, 0) + 1
    out = [f"# {book['name']} 검증표 ({r['no']}회차)",
           f"- 만든 때: {datetime.now():%Y-%m-%d %H:%M} · 대상: 엔진이 공시에서 가져와 결론의 사실로 쓴 값",
           "- 방법: 공책의 값마다 받아 둔 원본(한국 DART 재무제표, 미국 SEC XBRL)에서 같은 공시(접수번호)·같은 계정을 다시 찾아 값이 같은지 본다",
           "- 결과: " + " · ".join(f"{k} {v}건" for k, v in count.items()), "",
           "| 단계 | 항목 | 연도 | 값 | 출처 (공시 번호 · 계정) | 정의 일치 | 대조 결과 | 메모 |", "|---|---|---|---|---|---|---|---|"]
    for no, s, res, note in rows:
        v = "-" if s["value"] is None else f"{s['value']:,.0f}"
        out.append(f"| {no} | {ITEM_KO.get(s['item'], s['item'])} | {s['year']} | {v} | {s['filing']} · {s['account']} | "
                   f"{s['match']} | {res} | {note} |")
    out += ["", "- 비율(부채비율, 이자보상비율, 발생액 등)은 위 값으로 계산한 것이다. 계산식은 `criteria/` 각 기준 문서.",
            "- 공시 본문(주석)에서 옮겨 적은 값은 각 단계의 '확인한 것' 출처를 따른다.", "",
            "## 판단 글에 직접 쓴 숫자 (자동 대조 안 됨 → 확인 필요)", ""]
    typed = []
    for no in range(1, 10):
        p = r["steps"].get(str(no))
        for it in (notebook.live_items(p) if p else []):
            c = _confirmed(it)
            nums = [m.strip() for m in NUM.findall(c["text"]) if re.search(r"\d", m) and len(m.strip()) > 1] if c else []
            if nums:
                typed.append(f"- {no} {p['name']} · {it['title']}: {', '.join(dict.fromkeys(nums))}")
    out += typed or ["- 없음"]
    return "\n".join(out), count


# ---------------- 역할구분 ----------------
def roles_md(book: dict) -> str:
    r = notebook.current_round(book)
    rs = [x for x in book["roles"] if x["round"] == r["no"]]
    n = {"user": sum(x["by"] == "user" for x in rs), "ai": sum(x["by"] == "ai" for x in rs)}
    out = [f"# {book['name']} 역할구분 ({r['no']}회차)",
           "- 공책의 역할 기록 그대로 (자동 기록, 기록에 있는 것만). 원칙: 사용자는 정하고 판단한다. AI는 재료를 모으고 계산하고 피드백한다.",
           f"- 사용자 {n['user']}건 · AI {n['ai']}건", "",
           "| 때 | 단계 | 누가 | 한 일 |", "|---|---|---|---|"]
    for x in rs:
        step = "-" if x["step"] is None else f"{x['step']} {notebook.STEPS.get(x['step'], '')}"
        who = "사용자" if x["by"] == "user" else "AI"
        out.append(f"| {x['at'][:16].replace('T', ' ')} | {step} | {who} | {x['what'].replace('|', '/')} |")
    return "\n".join(out)


# ---------------- md → HTML → PDF ----------------
CSS = """body{font-family:'Malgun Gothic',sans-serif;font-size:10.5pt;line-height:1.55;color:#1F2933;margin:0}
h1{font-size:17pt;color:#0B3D63;margin:0 0 8px}h2{font-size:13pt;color:#0B3D63;border-bottom:2px solid #0B3D63;padding-bottom:2px;margin:18px 0 6px}
h3{font-size:11.5pt;margin:12px 0 4px}table{border-collapse:collapse;width:100%;font-size:8.5pt;margin:6px 0}
th,td{border:1px solid #C9D4DF;padding:3px 5px;vertical-align:top}th{background:#EAF1F8}ul{margin:2px 0 6px;padding-left:18px}
p{margin:4px 0}@page{size:A4;margin:14mm}"""


def _inline(t: str) -> str:
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def md_to_html(md: str, title: str) -> str:
    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[-|\s]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.append("<table>" + "".join("<tr>" + "".join(f"<{'th' if k == 0 else 'td'}>{_inline(c)}</{'th' if k == 0 else 'td'}>"
                                                              for c in row) + "</tr>" for k, row in enumerate(rows)) + "</table>")
            continue
        if ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{_inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        m = re.match(r"^(#{1,3}) (.*)", ln)
        if m:
            out.append(f"<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>")
        elif ln.strip():
            out.append(f"<p>{_inline(ln)}</p>")
        i += 1
    return f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{CSS}</style></head><body>{''.join(out)}</body></html>"


def to_pdf(md: str, pdf: Path, title: str) -> bool:
    edge = next((e for e in EDGE if e.exists()), None)
    if edge is None:
        return False
    with tempfile.TemporaryDirectory() as d:
        h = Path(d) / "page.html"
        h.write_text(md_to_html(md, title), encoding="utf-8")
        subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", h.as_uri()], capture_output=True, timeout=120)
    return pdf.exists()


# ---------------- 과제 (cases/_과제_진행_단계.md 6단계) ----------------
def case_verify_md(cs: dict) -> tuple[str, dict]:
    """과제 검증표: 3단계 회사 공책의 공시 값을 원본과 대조 + 보고서·확정 판단에 직접 쓴 숫자는 '확인 필요'."""
    from . import case as K
    base = K.companies_base(cs["id"])
    rows, count = [], {}
    for c in cs["companies"]:
        b = notebook.load(c, base)
        if not b:
            continue
        raw, seen = service.raw_financials(c["company_id"]), set()
        for no in range(1, 9):
            for s in notebook.current_round(b)["steps"].get(str(no), {}).get("sources", []):
                k = (s["item"], s["year"], s["filing"])
                if k in seen:
                    continue
                seen.add(k)
                res, note = _check_value(c["company_id"], raw, s)
                count[res] = count.get(res, 0) + 1
                rows.append((c["name"], no, s, res, note))
    out = [f"# {cs['id']} 검증표", f"- 과제: {cs['title']} · 만든 때 {datetime.now():%Y-%m-%d %H:%M}",
           "- 방법: 3단계(내 9단계 분석)에서 엔진이 공시에서 가져온 값마다 받아 둔 원본(DART 재무제표·SEC XBRL·XBRL 주석)을 다시 찾아 대조",
           "- 결과: " + (" · ".join(f"{k} {v}건" for k, v in count.items()) or "대조할 값 없음"), "",
           "| 회사 | 단계 | 항목 | 연도 | 값 | 출처 (공시 번호 · 계정) | 정의 일치 | 대조 결과 | 메모 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for name, no, s, res, note in rows:
        v = "-" if s["value"] is None else f"{s['value']:,.0f}"
        out.append(f"| {name} | {no} | {ITEM_KO.get(s['item'], s['item'])} | {s['year']} | {v} | {s['filing']} · {s['account']} | "
                   f"{s['match']} | {res} | {note} |")
    out += ["", "## 보고서·확정 판단에 직접 쓴 숫자 (자동 대조 안 됨 → Claude가 원문과 대조해 결과를 적는다)", ""]
    typed = []
    rep = next((o for o in cs.get("outputs", []) if o.get("kind") == "보고서"), None)
    if rep and (K.ROOT / rep["path"]).exists():   # 절대 경로면 / 연산이 그 경로를 그대로 씀
        for ln in (K.ROOT / rep["path"]).read_text(encoding="utf-8").splitlines():
            nums = [m.strip() for m in NUM.findall(ln) if re.search(r"\d", m) and len(m.strip()) > 1]
            if nums and not ln.startswith("|---"):
                typed.append(f"- 보고서: {ln.strip()[:120]}")
    book = K.load_book(cs)
    for k, p in notebook.current_round(book)["steps"].items():
        for it in notebook.live_items(p):
            c = _confirmed(it)
            nums = [m.strip() for m in NUM.findall(c["text"]) if re.search(r"\d", m) and len(m.strip()) > 1] if c else []
            if nums:
                typed.append(f"- {p['name']} 확정 판단: {', '.join(dict.fromkeys(nums))}")
    out += typed or ["- 없음"]
    return "\n".join(out), count


def case_roles_md(cs: dict) -> str:
    """과제 역할구분: 과제 공책 + 과제용 회사 공책의 역할 기록을 시간 순서로 (기록에 있는 것만)."""
    from . import case as K
    rs = [(x, "질문·주장") for x in K.load_book(cs)["roles"]]
    for c in cs["companies"]:
        b = notebook.load(c, K.companies_base(cs["id"]))
        rs += [(x, c["name"]) for x in (b["roles"] if b else [])]
    rs.sort(key=lambda t: t[0]["at"])
    n = {"user": sum(x["by"] == "user" for x, _ in rs), "ai": sum(x["by"] == "ai" for x, _ in rs)}
    out = [f"# {cs['id']} 역할구분", f"- 과제: {cs['title']}",
           "- 공책의 역할 기록 그대로 (자동, 기록에 있는 것만). 원칙: 사용자는 정하고 판단한다. AI는 재료를 모으고 계산하고 피드백한다.",
           f"- 사용자 {n['user']}건 · AI {n['ai']}건", "",
           "## 과제 단계 기록", ""] + [f"- {s['at'][:16].replace('T', ' ')} · {s['stage']}단계 ({K.STAGES[s['stage']]})"
                                      for s in cs.get("stage_log", [])] + [
           f"- 대응표 승인: {cs['approved'][:16].replace('T', ' ') if cs.get('approved') else '-'} (사용자)", "",
           "## 판단 기록", "", "| 때 | 대상 | 누가 | 한 일 |", "|---|---|---|---|"]
    for x, where in rs:
        out.append(f"| {x['at'][:16].replace('T', ' ')} | {where} | {'사용자' if x['by'] == 'user' else 'AI'} | "
                   f"{x['what'].replace('|', '/')} |")
    return "\n".join(out)


def make_case(cs: dict) -> list[dict]:
    """reports/에 과제ID_검증표·역할구분(md+PDF)을 만들고, 보고서(Claude가 뼈대대로 쓴 md)가 있으면 PDF도 만든다."""
    import os
    from . import case as K
    rdir = Path(os.environ.get("REPORTS_DIR") or K.ROOT / "reports")     # 시험할 때는 REPORTS_DIR
    rdir.mkdir(parents=True, exist_ok=True)
    rel = lambda f: str(f.relative_to(K.ROOT)).replace("\\", "/") if K.ROOT in f.parents else str(f)  # noqa: E731
    verify, count = case_verify_md(cs)
    docs = {"검증표": verify, "역할구분": case_roles_md(cs)}
    rep = next((o for o in cs.get("outputs", []) if o.get("kind") == "보고서"), None)
    outs = [rep] if rep else []
    if rep and (K.ROOT / rep["path"]).exists():
        md = (K.ROOT / rep["path"]).read_text(encoding="utf-8")
        pdf = (K.ROOT / rep["path"]).with_suffix(".pdf")
        rep["pdf"] = rel(pdf) if to_pdf(md, pdf, pdf.stem) else None
    for kind, md in docs.items():
        stem = f"{cs['id']}_{kind}"
        (rdir / f"{stem}.md").write_text(md, encoding="utf-8")
        pdf = rdir / f"{stem}.pdf"
        if pdf.exists():
            pdf.unlink()
        outs.append({"kind": kind, "name": kind, "path": rel(rdir / f"{stem}.md"),
                     "pdf": rel(pdf) if to_pdf(md, pdf, stem) else None})
    cs["outputs"] = outs
    cs["verify"] = count
    return outs


def make_all(company: dict) -> dict:
    """세 문서를 md + PDF로 만들고 공책에 위치를 적는다. 최종 판단을 확정한 회차에서만."""
    book = notebook.load(company)
    if book is None:
        raise notebook.NotebookError("공책이 없음")
    r = notebook.current_round(book)
    if not r.get("final"):
        raise notebook.NotebookError("최종 판단을 확정한 뒤에 만든다")
    folder = notebook.path_for(company).parent
    base = notebook.folder_name(company).rsplit("_", 1)[0]
    verify, count = verify_md(book)
    docs = {"분석보고서": analysis_md(book), "검증표": verify, "역할구분": roles_md(book)}
    made = {}
    for kind, md in docs.items():
        stem = f"{base}_{kind}_{r['no']}회차"
        (folder / f"{stem}.md").write_text(md, encoding="utf-8")
        pdf = folder / f"{stem}.pdf"
        if pdf.exists():
            pdf.unlink()
        made[kind] = {"md": f"{stem}.md", "pdf": f"{stem}.pdf" if to_pdf(md, pdf, stem) else None}
    r["outputs"] = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "files": made, "verify": count}
    notebook._role(book, 9, "ai", "결과물 3종 만들기 (분석 보고서·검증표·역할구분), 검증표 "
                   + ", ".join(f"{k} {v}건" for k, v in count.items()))
    notebook.save(company, book)
    return r["outputs"]
