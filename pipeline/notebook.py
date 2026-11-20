"""공책: 회사마다 한 권. 엔진·화면·Claude Code가 같은 파일을 읽고 쓴다.

양식(사용자 결정 2026-11-20): analyses/_투자_분석_단계.md '공책 양식'
- 표지 / 회차(다시 분석하면 새 회차, 지난 회차는 그대로) / 단계 쪽 / 최종 판단 쪽 / 보유 점검 쪽 / 역할 기록 쪽
- **논의 단위는 '켜진 신호 하나하나'** (사용자 결정 2026-11-20 '다'): 신호가 없는 단계는 단순 정보,
  신호가 있으면 신호마다 논의 항목이 생기고 항목마다 초안 → 피드백 → 확인할 것 → 확정.
- 확인할 것이 남으면 확정하지 않는다. 단순 정보도 '확인함 + 날짜'를 남긴다.
- 확인할 것은 항목에 붙거나(피드백에서 나온 것), 단계 전체에 붙는다(엔진이 남긴 덜 받은 자료 등).
  단계 전체의 확인할 것이 남으면 그 단계의 어떤 항목도 확정할 수 없고 '확인함'도 남길 수 없다.

파일 형식(AI가 정한 값, criteria/README.md 4장): analyses/<회사이름>_<회사ID>/notebook.json (UTF-8 JSON)
공책은 이 모듈의 함수로만 고친다 (손으로 고치면 깨지기 쉬움). 항목은 단계 안에서 1부터 번호로 부른다.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = 2

STEPS = {1: "약속 이행", 2: "현금 창출", 3: "자본 배분", 4: "이익의 질", 5: "재무 안전성",
         6: "특수관계자", 7: "정성 자료", 8: "가격 판단", 9: "최종 판단"}
METHODS = ("기존 부품", "자료 받기", "새 도구")
# 기록 종류 → 누가 했나 (역할 기록 쪽에 자동으로 남는다)
KINDS = {"draft": ("user", "초안"), "feedback": ("ai", "피드백"), "revise": ("user", "고친 판단"),
         "confirm": ("user", "확정"), "checked": ("user", "확인함"), "reopen": ("user", "다시 열기")}
ITEM_KINDS = ("draft", "feedback", "revise", "confirm", "reopen")


class NotebookError(Exception):
    pass


def base_dir() -> Path:
    """공책을 두는 폴더. 시험할 때는 환경변수 NOTEBOOK_DIR 로 다른 폴더를 쓴다."""
    return Path(os.environ.get("NOTEBOOK_DIR") or ROOT / "analyses")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def folder_name(company: dict) -> str:
    name = re.sub(r"\(주\)|주식회사|[\\/:*?\"<>|]", "", company["name"]).strip()
    name = re.sub(r"\s+", "_", name)
    return f"{name}_{company['company_id'].replace(':', '-')}"


def path_for(company: dict, base: Path | None = None) -> Path:
    """base: 공책 폴더 (없으면 analyses/). 과제용 회사 공책은 cases/<과제>/companies/ 를 준다."""
    return (base or base_dir()) / folder_name(company) / "notebook.json"


def load(company: dict, base: Path | None = None) -> dict | None:
    p = path_for(company, base)
    if not p.exists():
        return None
    book = json.loads(p.read_text(encoding="utf-8"))
    if book.get("version") != VERSION:
        raise NotebookError(f"공책 형식이 다름 (v{book.get('version')}, 지금 v{VERSION}): {p}")
    return book


def save(company: dict, book: dict, base: Path | None = None) -> Path:
    p = path_for(company, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    book["updated"] = _now()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)          # 쓰다가 끊겨도 공책이 반쯤 깨지지 않게
    return p


def new_book(company: dict) -> dict:
    return {"version": VERSION, "company_id": company["company_id"], "name": company["name"],
            "market": company.get("market"), "created": _now(), "updated": None,
            "holding": False, "current": {"round": 0, "stage": None},
            "rounds": [], "holding_checks": [], "roles": []}


def new_round(book: dict, mode: str) -> dict:
    """회차를 새로 연다. mode: '처음부터' / '바뀐 부분만' (사용자가 그때마다 고름)."""
    if mode not in ("처음부터", "바뀐 부분만"):
        raise NotebookError("mode는 '처음부터' 또는 '바뀐 부분만'")
    r = {"no": len(book["rounds"]) + 1, "started": _now(), "mode": mode, "steps": {},
         "final": None, "recheck_conditions": []}
    book["rounds"].append(r)
    book["current"] = {"round": r["no"], "stage": "2단계 계산"}
    return r


def current_round(book: dict) -> dict:
    if not book["rounds"]:
        raise NotebookError("아직 회차가 없음 (run 으로 먼저 계산)")
    return book["rounds"][book["current"]["round"] - 1]


def put_result(book: dict, no: int, result: dict) -> dict:
    """엔진이 단계 계산 결과를 적는다.
    result: summary, sources, flags, data, items[{key, title, detail}], checks[{text, method}](단계 전체)
    - 신호(items)가 없으면 단순 정보, 있으면 논의할 부분.
    - 다시 계산해도 같은 key의 항목은 판단 기록을 그대로 둔다. 사라진 신호의 항목은 지우지 않고 '다시 계산하니 없음' 표시."""
    r = current_round(book)
    page = r["steps"].get(str(no)) or {"no": no, "name": STEPS[no], "log": [], "checks": [], "items": []}
    old = {it["key"]: it for it in page["items"]}
    new_keys = [i["key"] for i in result.get("items", [])]
    items = []
    for i in result.get("items", []):
        it = old.get(i["key"]) or {"key": i["key"], "log": [], "checks": []}
        it.update({"title": i["title"], "detail": i.get("detail", ""), "gone": False})
        items.append(it)
    for k, it in old.items():
        if k not in new_keys:
            it["gone"] = True
            items.append(it)
    page.update({"computed_at": _now(), "summary": result["summary"], "data": result.get("data"),
                 "sources": result.get("sources", []), "flags": result.get("flags", []), "items": items,
                 "lane": "discuss" if any(not it["gone"] for it in items) else "info",
                 "lane_reason": result.get("lane_reason", [])})
    r["steps"][str(no)] = page
    n = sum(1 for it in items if not it["gone"])
    _role(book, no, "ai", f"{no} {STEPS[no]} 계산 · " + (f"논의 항목 {n}개" if n else "신호 없음 → 단순 정보"))
    for c in result.get("checks", []):          # 엔진이 남기는 단계 전체의 '확인할 것' (예: 덜 받은 자료)
        if not any(x["text"] == c["text"] for x in page["checks"]):
            add_check(book, no, c["text"], c["method"])
    return page


def page(book: dict, no: int) -> dict:
    p = current_round(book)["steps"].get(str(no))
    if p is None:
        raise NotebookError(f"{no} 쪽이 아직 없음")
    return p


def item(p: dict, n: int) -> dict:
    live = live_items(p)
    if not 1 <= n <= len(live):
        raise NotebookError(f"{p['no']}단계에 논의 항목 {n}번이 없음 (1~{len(live)})")
    return live[n - 1]


def live_items(p: dict) -> list[dict]:
    return [it for it in p["items"] if not it.get("gone")]


def item_status(it: dict) -> str:
    kinds = [e["kind"] for e in it["log"]]
    if kinds and kinds[-1] == "reopen":
        return "피드백 도착"
    last = kinds[-1] if kinds else None
    return {None: "초안 전", "draft": "피드백 기다림", "feedback": "피드백 도착", "revise": "피드백 기다림",
            "confirm": "확정"}.get(last, "초안 전")


def status(p: dict) -> str:
    """단계의 지금 상태."""
    if p["lane"] == "info":
        return "확인함" if any(e["kind"] == "checked" for e in p["log"]) else "확인 전"
    live = live_items(p)
    done = sum(1 for it in live if item_status(it) == "확정")
    return "확정" if done == len(live) else f"{done}/{len(live)} 확정"


def open_checks(p: dict, it: dict | None = None) -> list[dict]:
    """확정을 막는 확인할 것: 단계 전체 것 + (항목이면) 그 항목 것."""
    cs = list(p["checks"]) + (list(it["checks"]) if it else [])
    return [c for c in cs if c["status"] == "open"]


def add_log(book: dict, no: int, kind: str, text: str = "", item_no: int | None = None,
            conclusion: str | None = None, recheck: list[str] | None = None) -> dict:
    """conclusion·recheck 는 9 최종 판단을 확정할 때만 (산다/기다린다/사지 않는다, 기다린다면 다시 볼 조건)."""
    if kind not in KINDS:
        raise NotebookError(f"모르는 기록 종류: {kind}")
    p = page(book, no)
    if kind == "checked":
        if p["lane"] != "info":
            raise NotebookError("'확인함'은 단순 정보에만 남긴다. 논의 항목은 초안 → 피드백 → 확정")
        if (oc := open_checks(p)):
            raise NotebookError(f"확인할 것 {len(oc)}건이 남아 있어 '확인함'을 남길 수 없음: "
                                + ", ".join(f"#{c['id']} {c['text']}" for c in oc))
        e = {"at": _now(), "kind": kind, "by": "user", "text": ""}
        p["log"].append(e)
        _role(book, no, "user", f"{no} {p['name']} 확인함")
        return e
    if p["lane"] == "info":
        raise NotebookError("단순 정보 단계에는 '확인함'만 남긴다")
    if item_no is None:
        raise NotebookError("논의 항목 번호를 정해야 한다 (--item)")
    it = item(p, item_no)
    st = item_status(it)
    if kind == "feedback" and st != "피드백 기다림":
        raise NotebookError(f"피드백할 초안이 없음 (지금 상태: {st})")
    if kind == "confirm":
        if st != "피드백 도착":
            raise NotebookError(f"확정은 피드백을 받은 뒤에 한다 (지금 상태: {st})")
        if (oc := open_checks(p, it)):
            raise NotebookError(f"확인할 것 {len(oc)}건이 남아 있어 확정할 수 없음: "
                                + ", ".join(f"#{c['id']} {c['text']}" for c in oc))
        if not text:
            raise NotebookError("확정할 판단 내용을 적어야 한다")
    if kind == "reopen" and st != "확정":
        raise NotebookError("확정한 판단만 다시 열 수 있음")
    if kind in ("draft", "revise") and not text:
        raise NotebookError("판단 내용을 적어야 한다")
    is_hold = str(no).startswith("h") and it["key"] == "decision"
    if no == 9 and kind == "confirm":
        _final_confirm(book, it, conclusion, recheck)
    elif no == 9 and kind == "reopen":
        current_round(book)["final"] = None
    elif is_hold and kind == "confirm":
        _hold_confirm(book, p, it, conclusion)
    elif is_hold and kind == "reopen":
        raise NotebookError("보유 점검의 결론은 다시 열지 않는다 (새 점검을 시작한다)")
    if kind in ("draft",) and st != "초안 전":
        raise NotebookError(f"초안은 처음에만 쓴다 (지금 상태: {st}). 피드백 뒤에는 '고친 판단'")
    if kind == "revise" and st != "피드백 도착":
        raise NotebookError(f"고친 판단은 피드백을 받은 뒤에 쓴다 (지금 상태: {st})")
    who, label = KINDS[kind]
    e = {"at": _now(), "kind": kind, "by": who, "text": text}
    if (no == 9 or is_hold) and kind == "confirm":
        e.update({"conclusion": conclusion, "recheck": it.get("recheck", [])})
        text = f"[{conclusion}] {text}"
    it["log"].append(e)
    _role(book, no, who, f"{no} {p['name']} · {it['title']} · {label}" + (f": {text[:60]}" if text else ""))
    return e


def put_page(book: dict, key: str, name: str, summary: list[str], items: list[dict]) -> dict:
    """계산 없는 쪽 (과제 공책의 질문·주장). 다시 넣어도 같은 key의 항목 판단 기록은 그대로 둔다."""
    r = current_round(book)
    page = r["steps"].get(key) or {"no": key, "name": name, "log": [], "checks": [], "items": [], "lane": "discuss",
                                   "lane_reason": [], "sources": [], "flags": [], "data": None}
    old = {it["key"]: it for it in page["items"]}
    page["items"] = [{**(old.get(i["key"]) or {"key": i["key"], "log": [], "checks": []}),
                      "title": i["title"], "detail": i.get("detail", ""), "gone": False} for i in items]
    page.update({"name": name, "summary": summary, "computed_at": _now()})
    r["steps"][key] = page
    return page


# ---------------- 9 최종 판단 (analyses/_투자_분석_단계.md 5단계) ----------------
FINAL_CHOICES = ("산다", "기다린다", "사지 않는다")


def final_lock(book: dict) -> list[str]:
    """최종 판단을 막는 이유. 빈 목록이면 열 수 있다 (1~8단계가 모두 끝나야 함: 단순 정보는 확인함, 논의 항목은 모두 확정)."""
    r = current_round(book)
    left = []
    for no in range(1, 9):
        p = r["steps"].get(str(no))
        if p is None:
            left.append(f"{no} {STEPS[no]}: 계산 안 됨")
        elif (st := status(p)) not in ("확인함", "확정"):
            left.append(f"{no} {STEPS[no]}: {st}")
    return left


def open_final(book: dict, summary: list[str]) -> dict:
    """최종 판단 쪽을 연다 (잠금이 풀렸을 때만). summary = 한 장에 모아 본 것 (엔진이 만듦)."""
    if (left := final_lock(book)):
        raise NotebookError("아직 잠김: " + " / ".join(left))
    r = current_round(book)
    p = r["steps"].get("9")
    if p is None:
        p = {"no": 9, "name": STEPS[9], "log": [], "checks": [], "lane": "discuss", "lane_reason": [],
             "items": [{"key": "final", "title": "최종 판단", "detail": "산다 / 기다린다 / 사지 않는다와 그 이유",
                        "log": [], "checks": [], "gone": False}],
             "sources": [], "flags": [], "data": None}
        r["steps"]["9"] = p
        _role(book, 9, "ai", "9 최종 판단 열기 (1~8단계 끝)")
    p.update({"computed_at": _now(), "summary": summary})
    return p


def _final_confirm(book: dict, it: dict, conclusion: str | None, recheck: list[str] | None) -> None:
    if conclusion not in FINAL_CHOICES:
        raise NotebookError(f"결론은 {' / '.join(FINAL_CHOICES)} 중 하나")
    recheck = [x.strip() for x in (recheck or []) if x.strip()]
    if conclusion == "기다린다" and not recheck:
        raise NotebookError("'기다린다'면 다시 볼 조건을 적어야 한다 (예: PER이 ○배 아래로 오면)")
    r = current_round(book)
    it["conclusion"], it["recheck"] = conclusion, recheck
    r["final"] = {"conclusion": conclusion, "recheck": recheck, "at": _now()}
    r["recheck_conditions"] = recheck
    book["current"]["stage"] = "최종 판단 확정"


# ---------------- 보유 중 점검 (analyses/_투자_분석_단계.md 6단계, 보유-①, 매도-①~③) ----------------
HOLD_CHOICES = ("계속 보유", "일부 판다", "판다")


def mark_bought(book: dict, day: str, note: str = "") -> dict:
    """사용자가 샀다고 할 때만. 산 이유 = 그때의 최종 판단 (확정한 '산다' 결론이 있어야 함)."""
    r = current_round(book)
    fin = r.get("final") or {}
    if fin.get("conclusion") != "산다":
        raise NotebookError("최종 판단이 '산다'로 확정된 회차에서만 기록한다")
    fp = r["steps"].get("9")
    last = next((e for e in reversed(fp["items"][0]["log"]) if e["kind"] == "confirm"), None) if fp else None
    book["holding"] = {"since": day, "round": r["no"], "reason": last["text"] if last else "", "note": note,
                       "recorded": _now()}
    book.setdefault("trades", []).append({"at": _now(), "day": day, "kind": "샀다", "note": note})
    _role(book, None, "user", f"샀다 ({day}) → 보유 목록에 추가")
    return book["holding"]


def start_check(book: dict, reason: str, summary: list[str], items: list[dict], checks: list[dict]) -> dict:
    """보유 점검 쪽을 연다 (h1, h2 …). items = 바뀐 것마다 논의 항목, 마지막에 결론 항목을 붙인다."""
    if not book.get("holding"):
        raise NotebookError("보유 중인 회사가 아님 (샀다고 기록한 뒤에 점검)")
    r = current_round(book)
    n = 1 + sum(1 for k in r["steps"] if str(k).startswith("h"))
    key = f"h{n}"
    page = put_page(book, key, f"보유 점검 {n} ({reason}, {_now()[:10]})", summary,
                    items + [{"key": "decision", "title": "결론: 계속 보유 / 일부 판다 / 판다",
                              "detail": "산 이유가 여전한가? 파는 이유는 회사가 바뀌었을 때와 가격이 너무 올랐을 때. 나눠서 판다. 더 좋은 기회만으로는 팔지 않는다"}])
    page["reason"] = reason
    for c in checks:
        add_check(book, key, c["text"], c["method"])
    _role(book, key, "ai", f"보유 점검 {n} 시작 ({reason}) · 논의 항목 {len(items) + 1}개")
    return page


def _hold_confirm(book: dict, p: dict, it: dict, conclusion: str | None) -> None:
    if conclusion not in HOLD_CHOICES:
        raise NotebookError(f"결론은 {' / '.join(HOLD_CHOICES)} 중 하나")
    left = [x["title"] for x in live_items(p) if x is not it and item_status(x) != "확정"]
    if left:
        raise NotebookError("앞의 논의 항목을 먼저 확정한다: " + ", ".join(left))
    it["conclusion"] = conclusion
    book.setdefault("trades", [])
    if conclusion in ("일부 판다", "판다"):
        book["trades"].append({"at": _now(), "day": _now()[:10], "kind": conclusion, "note": p["name"]})
    if conclusion == "판다":
        book["sold"] = {**book["holding"], "sold": _now()[:10], "check": p["no"]}
        book["holding"] = False


def _container(p: dict, item_no: int | None) -> dict:
    return item(p, item_no) if item_no is not None else p


def add_check(book: dict, no: int, text: str, method: str, item_no: int | None = None) -> dict:
    if method not in METHODS:
        raise NotebookError(f"처리 방법은 {', '.join(METHODS)} 중 하나")
    p = page(book, no)
    box = _container(p, item_no)
    c = {"id": len(box["checks"]) + 1, "text": text, "method": method, "status": "open",
         "result": None, "source": None, "added": _now(), "done": None}
    box["checks"].append(c)
    where = f" · {box['title']}" if item_no is not None else ""
    _role(book, no, "ai", f"{no} {p['name']}{where} 확인할 것 추가 #{c['id']} ({method}): {text[:60]}")
    return c


def done_check(book: dict, no: int, cid: int, result: str, source: str = "", item_no: int | None = None) -> dict:
    p = page(book, no)
    box = _container(p, item_no)
    c = next((c for c in box["checks"] if c["id"] == cid), None)
    if c is None:
        raise NotebookError(f"확인할 것 #{cid} 없음" + (f" (항목 {item_no})" if item_no else " (단계 전체)"))
    if not result:
        raise NotebookError("확인한 결과를 적어야 한다")
    c.update({"status": "done", "result": result, "source": source or None, "done": _now()})
    _role(book, no, "ai", f"{no} {p['name']} 확인할 것 #{cid} 확인: {result[:60]}")
    return c


def _role(book: dict, no: int | None, who: str, what: str) -> None:
    book["roles"].append({"at": _now(), "round": book["current"]["round"], "step": no, "by": who, "what": what})
