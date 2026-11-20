"""과제 방: 과제마다 cases/<과제ID>/ 폴더 하나 (cases/_과제_진행_단계.md)

- case.json      과제 정보·대응표·분석할 회사·지금 몇 단계 (1~2단계는 대화창에서 Claude가 사용자와 정해 적는다)
- notebook.json  과제 공책: 4단계 질문별 답('q1'…), 5단계 주장('claim') — 초안 → 피드백 → 확인할 것 → 확정
- companies/     과제용 회사 공책 (3단계 내 9단계 분석). 실제 투자 공책(analyses/)과 따로 둔다
                 (사용자 결정 2026-11-20: 과제의 피드백은 과제 방으로)
- 진행.md        새 창에서 이어 하기 위한 요약 (case.json + 공책에서 저절로 만든다)
공책 쓰기 규칙은 pipeline/notebook.py 와 같다.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import flow, notebook

ROOT = Path(__file__).resolve().parent.parent
STAGES = {1: "과제 자료 읽고 이해하기", 2: "대응표 만들기", 3: "내 9단계로 회사 분석", 4: "과제 질문에 답하기",
          5: "주장 정하기", 6: "보고서", 7: "마무리"}
ID_RE = re.compile(r"^[0-9A-Za-z가-힣_\-]{2,60}$")


def cases_dir() -> Path:
    """과제 폴더들. 시험할 때는 환경변수 CASES_DIR."""
    return Path(os.environ.get("CASES_DIR") or ROOT / "cases")


def _dir(cid: str) -> Path:
    if not ID_RE.match(cid):
        raise notebook.NotebookError("과제 ID는 한글·영문·숫자·_- 만 (예: 5주차_사례2)")
    return cases_dir() / cid


def companies_base(cid: str) -> Path:
    return _dir(cid) / "companies"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def list_cases() -> list[dict]:
    out = []
    for f in sorted(cases_dir().glob("*/case.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        out.append({"id": c["id"], "title": c["title"], "week": c.get("week"), "stage": c["stage"]})
    return out


def load(cid: str) -> dict:
    f = _dir(cid) / "case.json"
    if not f.exists():
        raise notebook.NotebookError(f"과제 '{cid}' 없음")
    return json.loads(f.read_text(encoding="utf-8"))


def save(case: dict) -> None:
    d = _dir(case["id"])
    d.mkdir(parents=True, exist_ok=True)
    case["updated"] = _now()
    tmp = d / "case.tmp"
    tmp.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(d / "case.json")
    write_progress(case)


def new(cid: str, title: str, week: int | None = None, in_file: str = "", pre_file: str = "") -> dict:
    if (_dir(cid) / "case.json").exists():
        raise notebook.NotebookError(f"과제 '{cid}'가 이미 있음")
    case = {"id": cid, "title": title, "week": week, "in_file": in_file, "pre_file": pre_file, "stage": 1,
            "stage_log": [{"at": _now(), "stage": 1}], "summary": "", "alternatives": [], "deliver": "",
            "pre_concepts": [], "questions": [], "companies": [], "approved": None, "outputs": [], "wrapup": [],
            "created": _now()}
    save(case)
    return case


def set_stage(case: dict, stage: int) -> None:
    if stage not in STAGES:
        raise notebook.NotebookError("단계는 1~7")
    case["stage"] = stage
    case["stage_log"].append({"at": _now(), "stage": stage})


def set_table(case: dict, table: dict) -> None:
    """대응표 (2단계, 대화창에서 사용자와 정한 것): summary, alternatives, deliver, pre_concepts[{name, desc}],
    questions[{q, pre, need, parts, missing}]. 승인은 approve()로 따로."""
    for k in ("summary", "alternatives", "deliver", "pre_concepts"):
        if k in table:
            case[k] = table[k]
    if "questions" in table:
        case["questions"] = [{"no": i, **{k: q.get(k, "") for k in ("q", "pre", "need", "parts", "missing")}}
                             for i, q in enumerate(table["questions"], 1)]
        case["approved"] = None              # 대응표가 바뀌면 다시 승인
    if "companies" in table:
        case["companies"] = table["companies"]


def approve(case: dict) -> None:
    if not case["questions"]:
        raise notebook.NotebookError("대응표에 질문이 없음")
    case["approved"] = _now()


# ---------------- 과제 공책 (질문·주장) ----------------
def book_company(case: dict) -> dict:
    """과제 공책을 notebook 모듈로 다루기 위한 가짜 '회사' (폴더 이름만 씀)."""
    return {"company_id": "CASE:" + case["id"], "name": "과제"}


def load_book(case: dict) -> dict:
    c = book_company(case)
    base = _dir(case["id"]) / "_book"
    book = notebook.load(c, base)
    if book is None:
        book = notebook.new_book(c)
        book["kind"] = "case"
        notebook.new_round(book, "처음부터")
    # 대응표의 질문 → 쪽, 주장 → 쪽 (판단 기록은 그대로)
    for q in case["questions"]:
        notebook.put_page(book, f"q{q['no']}", f"질문 {q['no']}",
                          [f"과제 질문: {q['q']}", f"PRE 관점: {q['pre'] or '-'}", f"필요한 재료: {q['need'] or '-'}",
                           f"쓸 부품: {q['parts'] or '-'}"] + ([f"없으면: {q['missing']}"] if q["missing"] else []),
                          [{"key": "answer", "title": "이 질문에 대한 내 답", "detail": q["q"]}])
    notebook.put_page(book, "claim", "주장",
                      ["대안: " + (" / ".join(case["alternatives"]) or "-"),
                       "PRE 관점: " + (", ".join(p["name"] for p in case["pre_concepts"]) or "-"),
                       "순서: 대안별 유리·불리 → 고르고 이유(초안) → 피드백·반박해야 할 주장 → PRE 관점으로 근거 → 확정"],
                      [{"key": "claim", "title": "내 주장 (고른 대안과 이유)", "detail": "대안을 고른 뒤 PRE 관점으로 근거를 정리한다"}])
    return book


def save_book(case: dict, book: dict) -> None:
    notebook.save(book_company(case), book, _dir(case["id"]) / "_book")
    write_progress(case, book)


# ---------------- 3단계: 과제용 회사 공책 ----------------
def run_companies(case: dict, companies: list[dict]) -> dict:
    """과제에 나온 회사를 내 9단계로 계산 (외부 요청 없음). 이미 있으면 같은 회차에 계산 결과만 새로."""
    base = companies_base(case["id"])
    done = {}
    for c in companies:
        b = notebook.load(c, base) or notebook.new_book(c)
        if not b["rounds"]:
            notebook.new_round(b, "처음부터")
        for no, res in flow.run(c["company_id"]).items():
            notebook.put_result(b, no, res)
        notebook.save(c, b, base)
        done[c["company_id"]] = c["name"]
    case["companies"] = [{"company_id": k, "name": v} for k, v in
                         {**{x["company_id"]: x["name"] for x in case["companies"]}, **done}.items()]
    return done


def grid(case: dict) -> list[dict]:
    """회사 × 단계 상태표 (단계별 보기·회사별 보기 공용)."""
    base = companies_base(case["id"])
    out = []
    for c in case["companies"]:
        b = notebook.load(c, base)
        row = {"company_id": c["company_id"], "name": c["name"], "steps": {}}
        if b and b["rounds"]:
            r = notebook.current_round(b)
            for k, p in r["steps"].items():
                if k == "9":
                    continue
                row["steps"][k] = {"status": notebook.status(p), "lane": p["lane"],
                                   "titles": [it["title"] for it in notebook.live_items(p)],
                                   "first": p["summary"][0] if p["summary"] else ""}
        out.append(row)
    return out


# ---------------- 진행.md (새 창에서 이어 하기) ----------------
def write_progress(case: dict, book: dict | None = None) -> None:
    lines = [f"# {case['id']} 진행 기록 (저절로 만들어짐, 고치지 말 것)", "",
             f"- 과제: {case['title']} · 지금 {case['stage']}단계 ({STAGES[case['stage']]})",
             f"- 자료: IN {case['in_file'] or '-'} / PRE {case['pre_file'] or '-'}",
             f"- 대응표: 질문 {len(case['questions'])}개 · " + (f"승인 {case['approved'][:10]}" if case["approved"] else "승인 전"),
             f"- 분석할 회사: " + (", ".join(c["name"] for c in case["companies"]) or "-"), ""]
    if book:
        r = notebook.current_round(book)
        keys = sorted(r["steps"], key=lambda k: (k == "claim", int(k[1:]) if k.startswith("q") else 0))
        lines += ["## 질문·주장"] + [f"- {r['steps'][k]['name']}: {notebook.status(r['steps'][k])}" for k in keys] + [""]
        lines += ["## 역할 기록 (최근 20개)"] + [f"- {x['at'][:16]} · {'사용자' if x['by'] == 'user' else 'AI'} · {x['what']}"
                                             for x in book["roles"][-20:]]
    (_dir(case["id"]) / "진행.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
