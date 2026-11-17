"""투자기준 1: 경영진의 약속 이행 기록 — 2단계: 한국 B (조달 자금의 사용 계획)

규칙 문서: criteria/01_경영진_약속이행.md (3. 판정 방법 B)

약속   : 주요사항보고서의 유상증자·전환사채·교환사채·신주인수권부사채 발행결정 (자회사 공시 제외)
         - 용도별 금액: "자금조달의 목적"
         - 사용 시기: "조달자금의 구체적 사용 목적" (시설자금 투자기간, 운영자금 연도별 금액)
결과   : 사업보고서의 "증권의 발행을 통해 조달된 자금의 사용실적" 표 (예전 보고서는 "직접금융 자금의 사용")
한 건  : 공시 단위 (사용자 결정 2026-11-18). 화면에는 용도별 결과를 모두 보여준다.

사용자 결정으로 정한 판정 규칙
- 약속 공시에 용도별 금액이 없으면 → 사업보고서 표의 "계획" 칸을 약속으로 쓴다
- 사용 시기가 없으면 → 납입 후 3년이 지난 해의 사업보고서로 판정 (그 전에 전액 썼으면 그때)
- 기한이 남았는데 전액 썼으면 → 그때 판정
- 약속 공시와 사업보고서의 계획 금액이 다르면 → 둘 다 표시하고 사용자가 판단
- 실제 용도가 약속과 같은지 → AI가 다르게 보이는 것을 표시하고 사용자가 판단
- 대상이 없는 타법인 증권 취득 약속 → 모호한 약속 (판정하지 않고 기록)
- 쓰기 전에 사채를 되사 소각하는 등 → 약속 철회 (판정하지 않고 기록)
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import promises as P
from .config import YEARS

PLAN_KINDS = {"유상증자결정": "유상증자", "전환사채권발행결정": "전환사채", "교환사채권발행결정": "교환사채",
              "신주인수권부사채권발행결정": "신주인수권부사채"}
CAT_ORDER = ["시설", "영업양수", "운영", "채무상환", "타법인", "기타"]
FULL_USE = 0.99            # 이 비율 이상 쓰면 "전액 사용"으로 보고 바로 판정
NO_TIMING_YEARS = 3        # 사용 시기가 없는 약속: 납입 후 3년
WITHDRAW_RX = re.compile(r"만기\s*전\s*상환|만기전상환|소각\s*완료|조기\s*상환|만기\s*전\s*(사채\s*)?취득")


# ---------------- 공시 찾기 ----------------
def _plan_kind(title: str) -> str | None:
    t = title.replace(" ", "")
    if any(x in t for x in P.EXCLUDE):
        return None
    return next((v for k, v in PLAN_KINDS.items() if k in t), None)


def discover(company_id: str) -> dict:
    since = (date.today() - timedelta(days=365 * YEARS)).isoformat()
    rows = P._ro().execute("SELECT rcept_no, filed, title FROM filings WHERE company_id = ? AND filed >= ? ORDER BY filed",
                           (company_id, since)).fetchall()
    plans, reports = [], {}
    for rcept_no, filed, title in rows:
        if (k := _plan_kind(title)):
            plans.append({"rcept_no": rcept_no, "filed": filed, "title": title, "kind": k,
                          "correction": title.strip().startswith("[")})
        m = re.search(r"사업보고서\s*\((\d{4})\.(\d{2})\)", title)
        if m:
            reports.setdefault(int(m.group(1)), []).append({"rcept_no": rcept_no, "filed": filed, "title": title})
    return {"plans": plans, "reports": reports}


# ---------------- 약속 공시 읽기 ----------------
def _cat(text: str) -> str:
    s = P._nospace(text or "")
    if "시설" in s:
        return "시설"
    if "영업양수" in s:
        return "영업양수"
    if "운영" in s:
        return "운영"
    if "채무" in s or "차입금" in s:
        return "채무상환"
    if any(k in s for k in ("타법인", "M&A", "출자", "증권취득")):
        return "타법인"
    return "기타"


def _body(text: str) -> list[str]:
    """정정공시는 정정 전/후 표 뒤에 정정된 공시 전체가 다시 실린다 → 마지막 '...결정' 제목 이후만 쓴다."""
    L = text.replace("&cr;", " ").split("\n")
    heads = [i for i, l in enumerate(L) if l.startswith("# ") and "결정" in P._nospace(l)]
    return L[heads[-1]:] if heads else L


def _year2(s: str) -> int:
    y = int(s)
    return 2000 + y if y < 100 else y


def parse_plan(text: str) -> dict:
    """{'tranche', 'amounts': {분류: 원}, 'end_year': {분류: 연도}, 'target_known': {분류: bool}, 'ceo'}"""
    L = _body(text)
    out = {"tranche": None, "amounts": {}, "end_year": {}, "target_known": {}, "ceo": P.parse_ceo(text), "notes": []}
    for i, line in enumerate(L):
        s = P._nospace(line)
        if out["tranche"] is None and "|회차|" in s:
            cells = [c.strip() for c in line.split("|")]
            out["tranche"] = cells[cells.index("회차") + 1] if "회차" in cells else None
        if "자금조달의목적|" in s:
            j = i
            while j < len(L):
                cells = [c.strip() for c in L[j].split("|")]
                lab = next((c for c in cells if re.search(r"자금\s*\(원\)", c)), None)
                if not lab:
                    break
                amt = P._num(cells[cells.index(lab) + 1]) if cells.index(lab) + 1 < len(cells) else 0
                if amt:
                    c = _cat(lab)
                    out["amounts"][c] = out["amounts"].get(c, 0) + amt
                j += 1
            break
    # 구체적 사용 목적: 시설자금 투자기간, 운영·기타자금 연도별 금액, 타법인 대상
    sec = None
    year_cols: list = []      # 연도(int) / "이후"("'25년 이후" 칸) / None(합계·기타 칸)
    for line in L:
        s = P._nospace(line)
        if s.startswith("【시설자금"):
            sec = "시설"
        elif s.startswith("【운영자금") or s.startswith("【운영"):
            sec = "운영"
        elif s.startswith("【타법인") or s.startswith("【영업양수"):
            sec = "타법인"
        elif s.startswith("【채무상환"):
            sec = "채무상환"
        elif s.startswith("【"):
            sec = None
        if sec == "시설" and (m := re.search(r"'?(\d{2,4})\s*[~∼-]\s*'?(\d{2,4})", line)) and "|" in line:
            out["end_year"]["시설"] = max(out["end_year"].get("시설", 0), _year2(m.group(2)))
        if sec == "운영":
            if re.search(r"'?\d{2,4}\s*년", line) and "|" in line and not re.search(r"\d{3},\d{3}", line):
                year_cols = []
                for c in [c.strip() for c in line.split("|")]:
                    m = re.match(r"^['’‘]?(\d{2,4})\s*년(\s*이후)?$", c)
                    year_cols.append(None if not m else ("이후" if m.group(2) else _year2(m.group(1))))
            elif year_cols and "|" in line and re.match(r"^(운영|기타)", s):
                cells = [c.strip() for c in line.split("|")]
                vals = cells[2:2 + len(year_cols)]
                ys = [y for y, v in zip(year_cols, vals) if isinstance(y, int) and P._num(v)]
                later = any(y == "이후" and P._num(v) for y, v in zip(year_cols, vals))   # 'N년 이후'에 금액 → 끝나는 해 불명
                c = _cat(cells[0])
                if ys and not later:
                    out["end_year"][c] = max(ys)
        if sec in ("타법인", "채무상환") and "|" in line and not s.startswith("자금용도") and not s.startswith("종목"):
            cells = [c.strip() for c in line.split("|")]
            if sec == "타법인" and _cat(cells[0]) in ("타법인", "영업양수"):
                c = _cat(cells[0])
                out["target_known"][c] = out["target_known"].get(c, False) or any(x not in ("-", "") for x in cells[1:3])
            if sec == "채무상환" and len(cells) > 2:
                out["target_known"]["채무상환"] = True
    full = "\n".join(L)
    if re.search(r"투자\s*대상[^.\n]{0,20}결정되지\s*않", full):
        out["target_known"]["타법인"] = False
    if (m := re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(인수|취득)\s*예정", full)) and "타법인" in out["amounts"]:
        out["end_year"].setdefault("타법인", int(m.group(1)))
        out["target_known"]["타법인"] = True
    if "타법인" in out["amounts"] and "타법인" not in out["target_known"]:
        if re.search(r"타법인\s*주식\s*및\s*출자증권\s*취득\s*결정", full):
            out["target_known"]["타법인"] = True
            out["notes"].append("대상: '타법인 주식 및 출자증권 취득결정' 공시를 참조")
    return out


# ---------------- 사업보고서 사용실적 표 읽기 ----------------
_DATE = re.compile(r"(\d{4})\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})\s*일?\.?")   # 2018.04.16 / 2018년 04월 16일


def parse_usage(text: str) -> list[dict]:
    """사용실적 표의 증권 발행 행: kind, label(회차 포함), paid(납입일), plan_use, plan_amt, act_use, act_amt, reason (원)."""
    L = text.replace("&cr;", " ").split("\n")
    rows, unit, in_tbl = [], 1_000_000, False
    for line in L:
        s = P._nospace(line)
        if re.search(r"(공모|사모)자금의사용내역", s):
            in_tbl, unit = True, 1_000_000
            continue
        if in_tbl and (re.search(r"미사용자금", s) or re.match(r"^#{1,3} \d", line.strip())):
            in_tbl = False
        if not in_tbl:
            continue
        if "단위:" in s:
            unit = 1 if "단위:원" in s else (1_000 if "천원" in s else 1_000_000)
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        d = next((i for i, c in enumerate(cells) if _DATE.fullmatch(c.replace(" ", "")) or _DATE.fullmatch(c)), None)
        if d is None or d + 4 >= len(cells):
            continue
        label = " ".join(cells[:d])
        kind = next((v for k, v in (("유상증자", "유상증자"), ("GDR", "유상증자"), ("전환사채", "전환사채"),
                                    ("교환사채", "교환사채"), ("신주인수권", "신주인수권부사채")) if k in label), None)
        if not kind:
            continue
        m = _DATE.search(cells[d])
        rows.append({"kind": kind, "label": label, "paid": f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}",
                     "plan_use": cells[d + 1], "plan_amt": P._num(cells[d + 2]) * unit,
                     "act_use": cells[d + 3], "act_amt": P._num(cells[d + 4]) * unit,
                     "reason": " ".join(c for c in cells[d + 5:] if c not in ("-", "")).strip()})
    return rows


# ---------------- 판정 ----------------
@dataclass
class Unit:
    cat: str
    plan_amount: int | None = None        # 약속 공시 금액 (원)
    report_amount: int | None = None      # 사업보고서 계획 칸 금액 (원)
    plan_use: str = ""
    end_year: int | None = None
    timing: str = ""                      # 약속 기간 / 시기 없음(3년) 등
    status: str = "확인 필요"             # 판정 / 진행 중 / 확인 필요 / 판단 필요 / 모호한 약속 / 약속 철회
    judged_year: int | None = None
    report_rcept: str | None = None
    actual: int | None = None
    act_use: str = ""
    ratio: float | None = None
    grade: str | None = None
    reason: str = ""
    questions: list = field(default_factory=list)   # 사용자에게 물을 것 (key, 질문)
    notes: list = field(default_factory=list)


def _key(plan_rcept: str, cat: str) -> str:
    return f"{plan_rcept}:{cat}"


def evaluate(company_id: str) -> list:
    d = discover(company_id)
    judg = P.load_judgments(company_id).get("funding", {})
    unav = P.unavailable(company_id)
    # 사업보고서: 연도별로 받아 둔 것 중 가장 최근 제출본
    reports = {}
    for y, docs in d["reports"].items():
        for doc in sorted(docs, key=lambda x: x["filed"], reverse=True):
            if (t := P._text(company_id, doc["rcept_no"])):
                reports[y] = {"rcept_no": doc["rcept_no"], "rows": parse_usage(t), "ceo": P.parse_ceo(t)}
                break
    latest_possible = date.today().year - 1 if date.today().month >= 4 else date.today().year - 2  # 제출됐을 최근 사업연도

    # 약속 묶기: 원 공시 + 정정공시 (같은 종류·같은 회차, 없으면 날짜 순)
    originals = [p for p in d["plans"] if not p["correction"]]
    corrections = [p for p in d["plans"] if p["correction"]]
    parsed = {p["rcept_no"]: parse_plan(t) for p in d["plans"] if (t := P._text(company_id, p["rcept_no"]))}
    groups = {o["rcept_no"]: [o] for o in originals}
    for c in corrections:
        tr = parsed.get(c["rcept_no"], {}).get("tranche")
        cands = [o for o in originals if o["kind"] == c["kind"] and o["filed"] <= c["filed"]]
        same = [o for o in cands if tr and parsed.get(o["rcept_no"], {}).get("tranche") == tr]
        target = (same or cands)[-1] if (same or cands) else None
        if target is None:
            groups[c["rcept_no"]] = [c]          # 원 공시가 기간 밖이거나 없음 → 정정공시만으로 하나의 약속
        else:
            groups[target["rcept_no"]].append(c)

    events = []
    used_rows = set()
    for key0, grp in sorted(groups.items(), key=lambda kv: kv[1][0]["filed"]):
        o = grp[0]
        ev = P.Promise(kind=f"자금({o['kind']})", plan_rcept=o["rcept_no"], plan_filed=o["filed"])
        ev.corrections = [c["rcept_no"] for c in grp[1:]]
        avail = [g for g in grp if g["rcept_no"] in parsed]
        if not avail:
            final = grp[-1]["rcept_no"]
            ev.notes.append(f"{'DART 원문 없음' if final in unav else '본문 미수집'}: {final}")
            ev.units = []
            events.append(ev)
            continue
        src = avail[-1]
        pl = parsed[src["rcept_no"]]
        ev.ceo_plan = parsed[avail[0]["rcept_no"]]["ceo"] or pl["ceo"]
        if len(avail) < len(grp):
            missing = [g["rcept_no"] for g in grp if g["rcept_no"] not in parsed]
            ev.notes.append(f"정정본 {', '.join(missing)} 원문 없음 → {src['rcept_no']} 기준 (정정 내용 확인 불가)")
        elif len(grp) > 1:
            ev.notes.append(f"정정 {len(grp) - 1}건 → 최종 약속(정정본 {src['rcept_no']}) 기준")
        ev.notes += pl["notes"]
        ev.tranche = pl["tranche"]

        # 사업보고서 표에서 이 공시의 행 찾기: 같은 종류, 납입일이 결정일 -7일 ~ +150일, 회차가 있으면 회차 일치
        lo = (date.fromisoformat(o["filed"]) - timedelta(days=7)).isoformat()
        hi = (date.fromisoformat(o["filed"]) + timedelta(days=150)).isoformat()
        by_year = {}
        for y, rep in reports.items():
            rs = [r for r in rep["rows"] if r["kind"] == o["kind"] and lo <= r["paid"] <= hi]
            if pl["tranche"]:
                tr = re.sub(r"\s", "", pl["tranche"])
                rs_t = [r for r in rs if re.search(rf"(제|^){re.escape(tr)}(회|$)", re.sub(r"\s", "", r["label"]))
                        or re.sub(r"\s", "", r["label"]).endswith(tr)]
                rs = rs_t or [r for r in rs if not re.search(r"제?\d+(-\d+)?회", r["label"])]
            if rs:
                by_year[y] = rs
        paid = min((r["paid"] for rs in by_year.values() for r in rs), default=None)

        # 용도 단위 만들기: 약속 공시 금액이 있으면 그것, 없으면 사업보고서 계획 칸 (사용자 결정)
        cats = list(pl["amounts"])
        if not cats:
            first = by_year[min(by_year)] if by_year else []
            cats = list(dict.fromkeys(_cat(r["plan_use"]) for r in first))
            if cats:
                ev.notes.append("약속 공시에 용도별 금액이 없어 사업보고서 표의 계획 칸을 약속으로 사용")
        units = []
        for c in sorted(cats, key=CAT_ORDER.index):
            u = Unit(cat=c, plan_amount=pl["amounts"].get(c))
            # 시기
            if c in pl["end_year"]:
                u.end_year, u.timing = pl["end_year"][c], f"{pl['end_year'][c]}년까지"
            elif paid:
                u.end_year, u.timing = int(paid[:4]) + NO_TIMING_YEARS, f"시기 없음 → 납입({paid}) 후 {NO_TIMING_YEARS}년"
            else:
                u.end_year, u.timing = int(o["filed"][:4]) + NO_TIMING_YEARS, f"시기 없음 → 결정일 후 {NO_TIMING_YEARS}년 (납입일 미확인)"
            # 모호한 약속: 대상이 없는 타법인 증권·영업양수 (사용자 결정: 대상이나 시기가 없는 약속)
            if c in ("타법인", "영업양수") and pl["target_known"].get(c) is False:
                u.status = "모호한 약속"
                u.notes.append("약속 공시에 취득 대상이 없음")
            units.append(u)

        # 연도별 사업보고서로 판정
        for u in units:
            if u.status == "모호한 약속":
                continue
            jk = judg.get(_key(o["rcept_no"], u.cat), {})
            for y in sorted(by_year):
                if y > (u.end_year or 9999):
                    break
                row = next((r for r in by_year[y] if _cat(r["plan_use"]) == u.cat), None)
                if row is None and len(by_year[y]) == 1 and len(units) == 1:
                    row = by_year[y][0]
                if row is None:
                    continue
                u.report_amount, u.plan_use = row["plan_amt"], row["plan_use"]
                u.actual, u.act_use, u.reason = row["act_amt"], row["act_use"], row["reason"]
                u.report_rcept, u.judged_year = reports[y]["rcept_no"], y
                ev.ceo_result = reports[y]["ceo"]
                base = u.plan_amount or u.report_amount
                if WITHDRAW_RX.search(row["reason"]) and base and u.actual < base * FULL_USE:
                    u.status = "약속 철회"
                    u.notes.append(f"{y}년 사업보고서: \"{row['reason'][:40]}\"")
                    break
                if base and u.actual >= base * FULL_USE:
                    break          # 전액 사용 → 그 해에 판정 (기한 전이어도)
            if u.status == "약속 철회":
                continue
            if u.judged_year is None:
                if (u.end_year or 0) > latest_possible:
                    u.status = "진행 중"
                else:
                    u.notes.append(f"{u.end_year}년 사업보고서가 필요 (미수집)" if u.end_year not in reports
                                   else "사업보고서 표에서 이 약속의 행을 찾지 못함")
                continue
            base = u.plan_amount or u.report_amount
            done = u.actual >= base * FULL_USE or u.judged_year >= (u.end_year or 0)
            if not done:
                u.status = "진행 중" if (u.end_year or 0) > latest_possible else "확인 필요"
                if u.status == "확인 필요":
                    u.notes.append(f"{u.end_year}년 사업보고서가 필요 (미수집)")
                continue
            # 사용자 판단이 필요한 것
            if u.plan_amount and u.report_amount and abs(u.plan_amount - u.report_amount) > 1_000_000:
                if "amount_basis" not in jk:
                    u.questions.append(("amount_basis", f"약속 공시 {u.plan_amount/1e8:,.0f}억 vs 사업보고서 계획 {u.report_amount/1e8:,.0f}억 — 어느 금액을 약속으로 볼까요? (plan_doc / report)"))
                else:
                    base = u.plan_amount if jk["amount_basis"] == "plan_doc" else u.report_amount
            same_text = P._nospace(u.plan_use) == P._nospace(u.act_use)
            if not same_text and not (_cat(u.act_use) == u.cat and u.cat != "기타"):
                if "same_purpose" not in jk:
                    u.questions.append(("same_purpose", f"약속 용도 \"{u.plan_use}\" → 실제 \"{u.act_use}\" — 같은 용도인가요? (true / false)"))
                elif jk["same_purpose"] is False:
                    u.notes.append("사용자 판단: 약속과 다른 용도 → 그 금액은 불이행으로 계산")
                    u.actual = 0
            if u.questions:
                u.status = "판단 필요"
                continue
            u.ratio = u.actual / base if base else None
            u.grade = P._grade(u.ratio) if u.ratio is not None else None
            if u.grade == "불이행" and jk.get("grade_override"):
                u.notes.append(f"사용자 판단: 미달 사유 정당 → {jk['grade_override']} ({jk.get('reason', '')})")
                u.grade = jk["grade_override"]
            u.status = "판정"
        ev.units = units
        _aggregate(ev)
        events.append(ev)
    return events


def _aggregate(ev) -> None:
    """공시 단위 판정 (사용자 결정): 용도 중 하나라도 불이행이면 불이행, 아니면 판정된 용도 중 가장 낮은 등급."""
    us = ev.units
    ev.records = [u.status for u in us if u.status in ("모호한 약속", "약속 철회")]
    judged = [u for u in us if u.status == "판정"]
    pending = [u for u in us if u.status in ("확인 필요", "판단 필요")]
    ongoing = [u for u in us if u.status == "진행 중"]
    if any(u.grade == "불이행" for u in judged):
        ev.status, ev.grade = "판정", "불이행"
    elif pending:
        ev.status = "판단 필요" if any(u.status == "판단 필요" for u in pending) else "확인 필요"
    elif ongoing:
        ev.status = "진행 중"
    elif judged:
        ev.status = "판정"
        order = [g for _, g in P.GRADES]
        ev.grade = max((u.grade for u in judged), key=order.index)
    elif "약속 철회" in ev.records:
        ev.status = "약속 철회"
    elif ev.records:
        ev.status = "모호한 약속"


def missing_docs(company_id: str) -> list[dict]:
    """B 판정에 필요한데 본문이 없는 공시: 약속 공시 전부 + 판정에 필요한 연도의 사업보고서."""
    d = discover(company_id)
    unav = P.unavailable(company_id)
    out = [p for p in d["plans"] if not P._have_doc(company_id, p["rcept_no"]) and p["rcept_no"] not in unav]
    need_years = set()
    for ev in evaluate(company_id):
        for u in getattr(ev, "units", []):
            if u.status == "확인 필요" and u.end_year:
                need_years.add(u.end_year)
    for y in sorted(need_years):
        docs = d["reports"].get(y, [])
        if docs and not any(P._have_doc(company_id, x["rcept_no"]) for x in docs):
            doc = [x for x in docs if not x["title"].startswith("[")] or docs
            if doc[0]["rcept_no"] not in unav:
                out.append(doc[0])
    return out
