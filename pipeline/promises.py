"""투자기준 1: 경영진의 약속 이행 기록 — 1단계: 한국 A (자기주식 취득)

규칙 문서: criteria/01_경영진_약속이행.md

흐름
1. discover()      공시 목록(DB)에서 약속·결과 공시를 찾는다             (읽기 전용)
2. missing_docs()  판정에 필요한데 아직 본문이 없는 공시 목록            (읽기 전용)
3. fetch_missing() 위 목록의 본문을 DART에서 받는다                     (사용자 승인 후에만 호출)
4. evaluate()      받아 둔 본문으로 약속마다 이행률·등급을 계산한다      (읽기 전용)
5. verdict()       현 대표이사 기준 회사 판정                            (읽기 전용)

사람이 판단하는 부분(불이행의 예외 인정)은 criteria/judgments/<회사>.json 에 사용자가 결정한 것만 기록한다.
"""
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import documents
from .config import DATA_DIR, DB_PATH, ROOT, YEARS

JUDGMENTS_DIR = ROOT / "criteria" / "judgments"

# 공시 제목(공백 제거) 안의 키워드
PLAN_DIRECT = "자기주식취득결정"
PLAN_TRUST = "자기주식취득신탁계약체결결정"
TRUST_END = "자기주식취득신탁계약해지결정"
RESULT_DIRECT = "자기주식취득결과보고서"
RESULT_TRUST = "신탁계약해지결과보고서"
EXCLUDE = ("종속회사", "자회사")  # 자회사의 공시는 이 회사 경영진의 약속이 아니다

GRADES = [(0.99, "완전 이행"), (0.90, "대체로 이행"), (0.0, "불이행")]


# ---------------- 공시 찾기 ----------------
def _ro() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _kind(title: str) -> str | None:
    t = title.replace(" ", "")
    if any(x in t for x in EXCLUDE):
        return None
    for key, kind in ((PLAN_TRUST, "plan_trust"), (TRUST_END, "trust_end"), (RESULT_TRUST, "result_trust"),
                      (RESULT_DIRECT, "result_direct"), (PLAN_DIRECT, "plan_direct")):
        if key in t:
            return kind
    return None


def discover(company_id: str) -> list[dict]:
    """최근 YEARS 년의 자기주식 관련 공시. 정정공시([기재정정] 등)는 correction=True."""
    since = (date.today() - timedelta(days=365 * YEARS)).isoformat()
    rows = _ro().execute("SELECT rcept_no, filed, title FROM filings WHERE company_id = ? AND filed >= ? ORDER BY filed",
                         (company_id, since)).fetchall()
    out = []
    for rcept_no, filed, title in rows:
        kind = _kind(title)
        if kind:
            out.append({"rcept_no": rcept_no, "filed": filed, "title": title, "kind": kind,
                        "correction": title.strip().startswith("[")})
    return out


def _have_doc(company_id: str, rcept_no: str) -> bool:
    try:
        return _ro().execute("SELECT 1 FROM filing_docs WHERE company_id = ? AND rcept_no = ? LIMIT 1",
                             (company_id, rcept_no)).fetchone() is not None
    except sqlite3.OperationalError:  # filing_docs 테이블이 아직 없음
        return False


def missing_docs(company_id: str) -> list[dict]:
    """판정에 필요한데 본문이 아직 없는 공시 (DART 요청이 필요한 목록). DART가 원문을 주지 않는 공시는 제외."""
    skip = unavailable(company_id)
    return [f for f in discover(company_id)
            if not _have_doc(company_id, f["rcept_no"]) and f["rcept_no"] not in skip]


UNAVAILABLE_FILE = DATA_DIR / "unavailable_docs.json"   # DART가 원문을 주지 않는 공시 기록 (캐시, git 제외)


def _unavailable() -> dict:
    return json.loads(UNAVAILABLE_FILE.read_text(encoding="utf-8")) if UNAVAILABLE_FILE.exists() else {}


def unavailable(company_id: str) -> dict:
    """{접수번호: 실패 메시지} — DART가 원문을 제공하지 않은 공시."""
    return _unavailable().get(company_id, {})


def fetch_missing(company_id: str, progress=print) -> dict:
    """missing_docs() 목록의 본문을 받는다. 반드시 사용자 승인 후에만 호출한다."""
    return fetch_docs(company_id, missing_docs(company_id), progress)


def fetch_docs(company_id: str, docs: list[dict], progress=print) -> dict:
    """주어진 공시들의 본문을 받는다. 반드시 사용자 승인 후에만 호출한다.
    한 건이 실패해도 멈추지 않고 계속 받는다. DART가 원문을 주지 않는 공시는 기록해 두고 다음부터 다시 요청하지 않는다."""
    done, failed = 0, {}
    skip = unavailable(company_id)
    for f in docs:
        if f["rcept_no"] in skip:
            continue
        try:
            documents.fetch(company_id, f["rcept_no"])
            done += 1
            progress(f"  받음 {f['filed']} {f['rcept_no']} {f['title']}")
        except Exception as e:  # DART 원문 없음(014) 등
            failed[f["rcept_no"]] = str(e)[:200]
            progress(f"  실패 {f['filed']} {f['rcept_no']} {f['title']} → {str(e)[:120]}")
    if failed:
        allu = _unavailable()
        allu.setdefault(company_id, {}).update(failed)
        UNAVAILABLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        UNAVAILABLE_FILE.write_text(json.dumps(allu, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"done": done, "failed": failed}


# ---------------- 본문 읽기 ----------------
def _text(company_id: str, rcept_no: str) -> str | None:
    if not _have_doc(company_id, rcept_no):
        return None
    return documents.parts(company_id, rcept_no)[0]["text"].replace("&cr;", "")


def _num(s: str) -> int:
    s = s.strip().replace(",", "")
    return int(s) if re.fullmatch(r"-?\d+", s) else 0


def _date(s: str) -> str | None:
    m = re.search(r"(\d{4})\s*[년.\-]\s*(\d{1,2})\s*[월.\-]\s*(\d{1,2})", s)
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _names(s: str) -> list[str]:
    """'정의선, 무뇨스 바르셀로 호세 안토니오, 최영일(각자대표이사)' → 이름 목록 (공백·괄호 설명 제거)."""
    s = re.sub(r"\([^)]*\)", "", _nospace(s))
    # '대표이사 윤종규'처럼 직함이 한 번 더 적힌 경우 직함을 뗀다
    names = [re.sub(r"^(대표이사|대표집행임원|대표)", "", n) for n in re.split(r"[,·/]|및", s)]
    return [n for n in names if n]


def parse_ceo(text: str) -> list[str]:
    """공시 머리의 '대 표 이 사 : | 전 영 현' → ['전영현']. 여러 명이면 모두."""
    for line in text.split("\n")[:40]:
        if _nospace(line).startswith("대표이사:"):
            return _names(line.split(":", 1)[1].replace("|", ""))
    return []


def parse_plan(text: str, kind: str) -> dict:
    """약속 공시: 금액(보통+기타), 기간, 대표이사."""
    L = text.split("\n")
    out = {"amount": None, "start": None, "end": None, "ceo": parse_ceo(text)}
    for i, line in enumerate(L):
        s = _nospace(line)
        if kind == "plan_direct" and s.startswith("2.취득예정금액(원)|보통주식|"):
            common = _num(line.split("|")[-1])
            other = _num(L[i + 1].split("|")[-1]) if i + 1 < len(L) and _nospace(L[i + 1]).startswith("기타주식|") else 0
            out["amount"] = common + other
        elif kind == "plan_trust" and re.match(r"^1\.계약금액\(원\)\|", s):
            out["amount"] = _num(line.split("|")[-1])
        elif re.match(r"^\d+\.(취득예상기간|계약기간)\|시작일\|", s):
            out["start"] = _date(line)
            if i + 1 < len(L) and _nospace(L[i + 1]).startswith("종료일|"):
                out["end"] = _date(L[i + 1])
    return out


def parse_trust_end(text: str) -> dict:
    """신탁계약 해지결정: 해지 전 계약기간 시작일 (체결결정과 잇는 데 사용)."""
    for line in text.split("\n"):
        if re.match(r"^\d+\.해지전계약기간\|시작일\|", _nospace(line)):
            return {"start": _date(line)}
    return {"start": None}


def parse_result(text: str) -> dict:
    """결과보고서: 연결 날짜, 약속·실제 금액, 미달 사유, 대표이사.

    1순위: '일치 여부' 표가 금액(원) 기준이면 그 값을 쓴다 (회사와 상관없이 원 단위).
    2순위: 표가 주식 수 기준(오래된 형식)이면, 취득내용의 '계' 행에서 금액을 단위에 맞춰 합산한다.
    """
    L = text.split("\n")
    out = {"link_date": None, "plan_amount": None, "actual": None, "basis": None, "reason": "", "ceo": parse_ceo(text)}
    for i, line in enumerate(L):
        if "주요사항보고서제출일" in _nospace(line):
            for j in range(i, min(i + 4, len(L))):
                if (d := _date(L[j])):
                    out["link_date"] = d
                    break
            break
    hi = next((i for i, l in enumerate(L) if "일치여부" in _nospace(l) and l.lstrip().startswith("#")), None)
    if hi is not None:
        header = next((L[j] for j in range(hi + 1, min(hi + 4, len(L))) if "|" in L[j]), "")
        vals_i = next((j for j in range(hi + 1, min(hi + 8, len(L)))
                       if re.match(r"^[\d,\-]+\s*\|", L[j].strip())), None)
        if vals_i is not None:
            v = [c.strip() for c in L[vals_i].split("|")]
            out["reason"] = v[5] if len(v) > 5 and v[5] not in ("-", "") else ""
            if "금액" in _nospace(header):
                out.update(plan_amount=_num(v[0]) + _num(v[1]), actual=_num(v[2]) + _num(v[3]), basis="일치 여부 표 (원)")
                return out
    # 2순위: '취득내용'(직접) 또는 '취득ㆍ처분 현황'(신탁) 절 안의 '계' 행만 읽는다.
    # 다음 같은 수준의 절(예: '해지후 자기주식등 보유현황')의 합계 행이 섞이지 않게 절 경계에서 멈춘다.
    start = next((i for i, l in enumerate(L) if l.lstrip().startswith("#")
                  and re.search(r"취득내용|취득[ㆍ·]처분현황", _nospace(l))), None)
    if start is None:
        return out
    level = len(L[start].lstrip()) - len(L[start].lstrip().lstrip("#"))
    end = next((j for j in range(start + 1, len(L))
                if (m := re.match(r"^(#+) ", L[j].lstrip())) and len(m.group(1)) <= level), len(L))
    unit, total = 1, 0
    found = False
    for line in L[start:end]:
        s = _nospace(line)
        if "단위:" in s:
            unit = 1_000_000 if "백만원" in s else (1000 if "천원" in s else 1)
        if s.startswith("계|"):
            cells = [c.strip() for c in line.split("|")]
            amounts = [_num(c) for c in cells if re.fullmatch(r"[\d,]+", c)]
            if len(amounts) >= 4:      # 직접취득: 주문수량 | 취득수량 | 평균가 | 취득가액총액
                total += amounts[3] * unit
                found = True
            elif len(amounts) >= 2:    # 신탁: 수량 | 금액
                total += amounts[1] * unit
                found = True
    if found:
        out.update(actual=total, basis="취득내용 합계 행")
    return out


# ---------------- 약속 판정 ----------------
@dataclass
class Promise:
    kind: str                      # 직접 / 신탁
    plan_rcept: str
    plan_filed: str
    amount: int | None = None
    start: str | None = None
    end: str | None = None
    ceo_plan: list = field(default_factory=list)
    corrections: list = field(default_factory=list)   # 정정공시 접수번호
    result_rcept: str | None = None
    result_filed: str | None = None
    ceo_result: list = field(default_factory=list)
    actual: int | None = None
    ratio: float | None = None
    grade: str | None = None
    status: str = "확인 필요"       # 판정 / 진행 중 / 확인 필요
    reason: str = ""               # 회사가 적은 미달 사유
    notes: list = field(default_factory=list)
    exception: str | None = None   # 사용자가 인정한 예외 사유
    # 2단계(B: 조달 자금) 공시 단위 약속에서 쓰는 항목
    units: list = field(default_factory=list)     # 용도별 결과 (funding.Unit)
    records: list = field(default_factory=list)   # 판정하지 않고 기록하는 것: 모호한 약속 / 약속 철회
    tranche: str | None = None


def _grade(ratio: float) -> str:
    return next(g for th, g in GRADES if ratio >= th)


def load_judgments(company_id: str) -> dict:
    p = JUDGMENTS_DIR / f"{company_id.replace(':', '_')}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _nearest(results: dict, kind: str, target: str, used: set, tolerance: int = 3):
    """연결 날짜가 target 과 같거나 ±tolerance 일 안에서 가장 가까운 결과. (결과, 날짜 차이) 반환.
    결과보고서 하나는 약속 하나에만 연결한다 (used)."""
    t = date.fromisoformat(target)
    best, gap = None, None
    for (k, d), r in results.items():
        if k != kind or r["rcept_no"] in used:
            continue
        g = abs((date.fromisoformat(d) - t).days)
        if g <= tolerance and (gap is None or g < gap):
            best, gap = r, g
    return best, (gap or 0)


def evaluate(company_id: str) -> list[Promise]:
    """받아 둔 본문만으로 판정한다 (DART 요청 없음). 본문이 없는 공시는 '확인 필요'로 남는다."""
    fs = discover(company_id)
    by_kind = lambda k: [f for f in fs if f["kind"] == k]  # noqa: E731
    judg = load_judgments(company_id).get("exceptions", {})

    # 결과보고서: 연결 날짜(약속 또는 해지결정의 제출일)로 색인
    results = {}
    for f in by_kind("result_direct") + by_kind("result_trust"):
        t = _text(company_id, f["rcept_no"])
        if t:
            r = parse_result(t)
            r.update(rcept_no=f["rcept_no"], filed=f["filed"], kind=f["kind"])
            if r["link_date"]:
                results[(f["kind"], r["link_date"])] = r   # 같은 날짜면 나중(정정) 결과가 덮어씀
    # 신탁 해지결정: 계약 시작일 → 해지결정 제출일
    trust_end_by_start = {}
    for f in by_kind("trust_end"):
        t = _text(company_id, f["rcept_no"])
        if t and (st := parse_trust_end(t)["start"]):
            trust_end_by_start[st] = f["filed"]

    promises, used = [], set()
    for kind_key, label, res_kind in (("plan_direct", "직접", "result_direct"), ("plan_trust", "신탁", "result_trust")):
        originals = [f for f in by_kind(kind_key) if not f["correction"]]
        corrections = [f for f in by_kind(kind_key) if f["correction"]]
        for o in originals:
            p = Promise(kind=label, plan_rcept=o["rcept_no"], plan_filed=o["filed"])
            # 정정공시: 원 공시 이후, 다음 원 공시 이전에 나온 같은 종류의 정정 → 최종 약속은 마지막 정정본
            nxt = next((x["filed"] for x in originals if x["filed"] > o["filed"]), "9999")
            mine = [c for c in corrections if o["filed"] <= c["filed"] < nxt]
            p.corrections = [c["rcept_no"] for c in mine]
            # 최종 약속 = 마지막 정정본. 정정본 원문을 DART가 주지 않으면, 받을 수 있는 가장 최근 문서로 판정하고 표시한다
            # (사용자 결정 2026-11-18: 원 공시로 판정 + "정정 내용 확인 불가" 표시)
            group = [o] + mine
            src, t = None, None
            for cand in reversed(group):
                if (t := _text(company_id, cand["rcept_no"])):
                    src = cand["rcept_no"]
                    break
            if not t:
                final = group[-1]["rcept_no"]
                why = "DART 원문 없음" if final in unavailable(company_id) else "본문 미수집"
                p.notes.append(f"{why}: {final}")
                promises.append(p)
                continue
            pl = parse_plan(t, kind_key)
            p.amount, p.start, p.end = pl["amount"], pl["start"], pl["end"]
            p.ceo_plan = parse_ceo(_text(company_id, o["rcept_no"]) or t)
            if mine and src == mine[-1]["rcept_no"]:
                p.notes.append(f"정정 {len(mine)}건 → 최종 약속(정정본 {src}) 기준")
            elif mine:
                skipped = [c["rcept_no"] for c in mine if c["rcept_no"] != src and not _have_doc(company_id, c["rcept_no"])]
                p.notes.append(f"정정본 {', '.join(skipped)} 원문 없음 → {src} 기준으로 판정 (정정 내용 확인 불가)")
            # 결과 연결 (회사가 적은 날짜가 실제 공시일과 며칠 다를 수 있어 ±3일 안에서 가장 가까운 것)
            if label == "직접":
                r, gap = _nearest(results, res_kind, o["filed"], used)
            else:
                end_filed = trust_end_by_start.get(p.start) if p.start else None
                r, gap = _nearest(results, res_kind, end_filed, used) if end_filed else (None, 0)
            if r:
                used.add(r["rcept_no"])
            if r and gap:
                p.notes.append(f"결과보고서에 적힌 날짜({r['link_date']})가 공시일과 {gap}일 차이 → 가장 가까운 것으로 연결")
            if r:
                p.result_rcept, p.result_filed, p.ceo_result = r["rcept_no"], r["filed"], r["ceo"]
                p.actual, p.reason = r["actual"], r["reason"]
                if r["plan_amount"] and p.amount and r["plan_amount"] != p.amount:
                    p.notes.append(f"결과보고서의 약속 금액({r['plan_amount']:,})이 약속 공시({p.amount:,})와 다름 → 약속 공시 기준")
                if p.amount and p.actual is not None:
                    p.ratio = p.actual / p.amount
                    p.grade = _grade(p.ratio)
                    p.status = "판정"
                    if r["basis"] != "일치 여부 표 (원)":
                        p.notes.append(f"실제 금액은 {r['basis']}에서 계산")
                else:
                    p.notes.append("금액을 읽지 못함")
            elif p.end and p.end >= date.today().isoformat():
                p.status = "진행 중"
            else:
                p.notes.append("기간이 끝났는데 결과보고서를 찾지 못함 (본문 미수집 또는 연결 실패)")
            if p.plan_rcept in judg:
                p.exception = judg[p.plan_rcept].get("reason", "")
            promises.append(p)
    return sorted(promises, key=lambda x: x.plan_filed)


# ---------------- 회사 판정 ----------------
def current_ceos(company_id: str) -> list[str]:
    row = _ro().execute("SELECT profile_json FROM companies WHERE company_id = ?", (company_id,)).fetchone()
    prof = json.loads(row[0]) if row and row[0] else {}
    return _names(prof.get("ceo_nm") or "")


LEVELS = ["통과", "주의", "탈락"]


def verdict(promises: list[Promise], ceos: list[str], attribute: str = "result") -> dict:
    """attribute: 'result' = 결과 시점 대표이사 기준 (사용자 결정, 2026-11-18), 'plan' = 약속 시점 대표이사 기준.
    결과가 없는 약속은 약속 시점 대표이사로 본다."""
    def is_current(p: Promise) -> bool:
        who = p.ceo_plan if attribute == "plan" else (p.ceo_result or p.ceo_plan)
        return bool(set(who) & set(ceos))

    judged = [p for p in promises if p.status == "판정"]
    cur = [p for p in judged if is_current(p)]
    past = [p for p in judged if not is_current(p)]
    fail = lambda ps: [p for p in ps if p.grade == "불이행" and not p.exception]  # noqa: E731
    # 모호한 약속·약속 철회 기록 (B): 현 대표이사의 기록이면 '주의' 사유
    cur_records = [r for p in promises if p.records and is_current(p) for r in p.records]
    res = {"current_judged": len(cur), "current_fail": len(fail(cur)), "past_fail": len(fail(past)),
           "current_records": len(cur_records),
           "pending": sum(p.status == "진행 중" for p in promises),
           "unresolved": sum(p.status in ("확인 필요", "판단 필요") for p in promises)}
    if len(cur) < 3:
        res["verdict"] = "판정 불가"
        res["why"] = f"현 대표이사의 판정 끝난 약속 {len(cur)}건 (3건 미만)"
        return res
    level = 0 if res["current_fail"] == 0 else (1 if res["current_fail"] == 1 else 2)
    why = [f"현 대표이사 불이행 {res['current_fail']}건"]
    if cur_records and level == 0:
        level = 1
        why.append(f"현 대표이사의 모호한 약속·약속 철회 {len(cur_records)}건 → 주의")
    if res["past_fail"] and level < 2:
        level += 1
        why.append(f"이전 대표이사 시절 불이행 {res['past_fail']}건 → 한 단계 낮춤")
    res["verdict"], res["why"] = LEVELS[level], ", ".join(why)
    return res
