"""투자기준 1: 경영진의 약속 이행 기록 — 3단계: 미국 기업 (10-K의 주주환원 의도 표명)

규칙 문서: criteria/01_경영진_약속이행.md (7. 미국 기업)

사용자 결정 (2026-11-18)
- 자동 판정 패턴: P1 배당 증액 의도("intends to increase its dividend on an annual basis"),
                  P2 배당 지속 의도("intend to continue returning capital ... in the form of dividends")
  P3(금액이 있는 분기 배당 예정)와 그 밖의 의도 문장, 금액·시기가 없는 일반 문장은 '확인해볼 문장'으로만 표시
- 같은 문장이 매년 반복되면 이어지는 약속 1건. 문장이 나온 10-K의 다음 회계연도부터 확인하고,
  문장이 사라지면 그 해까지가 약속 (공식적으로 거둬들인 것으로 보고 문제 삼지 않음)
- 판정은 현 CEO 재임 기간(10-K 서명 기준)으로 한다. 이전 CEO 시절도 확인해서 불이행이 있으면 한 단계 낮춘다
- 전년 대비 비교는 같은 10-K 안의 두 해 값으로 한다 (주식분할 전후 값이 섞이지 않게)
- 연도 결과는 그 해 10-K에 서명한 CEO의 기록으로 본다 (결과 시점 기준)
"""
import re
from datetime import date

from . import documents
from . import promises as P

DPS_TAG = "CommonStockDividendsPerShareDeclared"

PATTERNS = {
    "P1": ("배당 증액 의도",
           re.compile(r"\b(intends?|plans?)\s+to\s+increase\s+(its|our|the\s+company[’']s)\s+(quarterly\s+)?(cash\s+)?"
                      r"dividends?\b[^.]{0,40}\b(on\s+an\s+annual\s+basis|annually|each\s+year|every\s+year)", re.I)),
    "P2": ("배당 지속 의도",
           re.compile(r"\b(intends?|plans?|expects?)\s+to\s+continue\s+(returning\s+capital\b[^.]{0,60}\bdividends?|"
                      r"(to\s+)?pay(ing)?\s+(regular\s+)?(quarterly\s+)?(cash\s+)?dividends?)", re.I)),
}
# 회사가 주어인 의도 문장만 ('We ... expect', 'The Company ... will continue')
INTENT = re.compile(r"\b(We|The\s+Company|Our\s+Board)\b(\s+\S+){0,4}?\s+(intends?|plans?|expects?|anticipates?|"
                    r"(are|is)\s+committed|commits?|will\s+continue|aims?|targets?)\b")
TOPIC = re.compile(r"dividend|repurchas|buyback|capital\s+expenditure|invest|datacenter|data\s+center|"
                   r"return(ing)?\s+.{0,20}(capital|cash)\s+to", re.I)
BOILERPLATE = re.compile(r"RSU|10b5-1|plans?\s+to\s+sell\s+the\s+security|stock\s+plans?|equity\s+incentive|"
                         r"benefit\s+plans?|pension|defined\s+benefit|fair\s+value\s+of\s+stock\s+awards", re.I)


def _norm_person(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _display(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    # 서명과 활자 이름이 한 줄에 겹친 경우: 'SATYA NADELLA Satya Nadella' → 'Satya Nadella'
    w = s.split()
    if len(w) % 2 == 0 and [x.lower() for x in w[:len(w) // 2]] == [x.lower() for x in w[len(w) // 2:]]:
        s = " ".join(w[len(w) // 2:])
    return s.title() if s.isupper() else s


def parse_ceo(text: str) -> str | None:
    """10-K 서명란의 '/s/ 이름 | ... Chief Executive Officer (Principal Executive Officer)'.
    없으면 경영진 표의 '이름 | 나이 | Chief Executive Officer' 행."""
    L = text.split("\n")
    for i, line in enumerate(L):
        if "Principal Executive Officer" in line and "Chief Executive Officer" in line:
            for cand in (line, L[i - 1] if i else ""):
                if (m := re.search(r"/s/\s*([^|]{3,60}?)\s*(\||$)", cand)):
                    return _display(m.group(1))
    for line in L:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2 and re.fullmatch(r"(Chairman( of the Board)? and )?Chief Executive Officer( and Director)?", cells[-1]) \
                and re.fullmatch(r"[A-Z][A-Za-z.\- ]{3,40}", cells[0]):
            return _display(cells[0])
    return None


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text.replace("|", " "))
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", flat) if 20 < len(s) < 400]


# ---------------- 데이터 ----------------
def ten_ks(company_id: str) -> list[dict]:
    rows = P._ro().execute("SELECT filed, rcept_no, report_date FROM filings WHERE company_id = ? AND form = '10-K' "
                           "ORDER BY filed", (company_id,)).fetchall()
    out = []
    for filed, rcept, rep in rows:
        fy = int(rep[:4]) if rep else int(filed[:4])
        out.append({"filed": filed, "rcept_no": rcept, "fy": fy, "title": f"10-K FY{fy}"})
    return out


def missing_docs(company_id: str) -> list[dict]:
    unav = P.unavailable(company_id)
    return [k for k in ten_ks(company_id) if not P._have_doc(company_id, k["rcept_no"]) and k["rcept_no"] not in unav]


def dps_pair(company_id: str, accn: str) -> dict[int, float]:
    """한 10-K(accn) 안의 연간 주당배당금 {회계연도 종료 연도: 값}. 같은 보고서 안의 값이라 분할 기준이 같다."""
    rows = P._ro().execute(
        'SELECT start, "end", val FROM sec_facts WHERE company_id = ? AND tag = ? AND accn = ? AND form = \'10-K\'',
        (company_id, DPS_TAG, accn)).fetchall()
    out = {}
    for start, end, val in rows:
        if start and end:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            if 330 <= days <= 400:
                out[int(end[:4])] = val
    return out


# ---------------- 판정 ----------------
def evaluate(company_id: str) -> dict:
    ks = ten_ks(company_id)
    by_fy, ceo_by_fy, refs = {}, {}, {}
    for k in ks:
        t = P._text(company_id, k["rcept_no"])
        if not t:
            continue
        by_fy[k["fy"]] = k
        ceo_by_fy[k["fy"]] = parse_ceo(t)
        k["found"] = {}
        for s in _sentences(t):
            hit = next((pid for pid, (_, rx) in PATTERNS.items() if rx.search(s)), None)
            if hit:
                k["found"].setdefault(hit, s)
            elif INTENT.search(s) and TOPIC.search(s) and not BOILERPLATE.search(s):
                key = re.sub(r"\d", "#", s.lower())[:160]     # 해마다 숫자만 바뀌는 문장은 하나로
                refs.setdefault(key, {"text": s, "years": []})["years"].append(k["fy"])
    years = sorted(by_fy)
    latest = years[-1] if years else None
    current = ceo_by_fy.get(latest)

    promises_out = []
    for pid, (label, _) in PATTERNS.items():
        stmt_years = [y for y in years if pid in by_fy[y].get("found", {})]
        # 문장이 이어서 나온 구간마다 약속 1건 (사라졌다 다시 나오면 별개의 약속)
        runs, cur_run = [], []
        for y in stmt_years:
            if cur_run and y != cur_run[-1] + 1:
                runs.append(cur_run)
                cur_run = []
            cur_run.append(y)
        if cur_run:
            runs.append(cur_run)
        for run in runs:
            checks = []
            for fy in range(run[0] + 1, run[-1] + 2):          # 문장이 나온 다음 해부터, 마지막 문장의 다음 해까지
                k = by_fy.get(fy)
                if not k:
                    filed = any(x["fy"] == fy for x in ks)
                    checks.append({"fy": fy, "result": "확인 필요" if filed else "진행 중",
                                   "ceo": None, "detail": "10-K 본문 미수집" if filed else "아직 10-K가 나오지 않음"})
                    continue
                d = dps_pair(company_id, k["rcept_no"])
                cur, prev = d.get(fy), d.get(fy - 1)
                if pid == "P1":
                    ok = None if cur is None or prev is None else cur > prev
                    detail = f"FY{fy} {cur} vs FY{fy - 1} {prev} (같은 10-K)"
                else:
                    ok = None if cur is None else cur > 0
                    detail = f"FY{fy} 주당배당금 {cur}"
                checks.append({"fy": fy, "result": "확인 필요" if ok is None else ("지킴" if ok else "못 지킴"),
                               "ceo": ceo_by_fy.get(fy), "detail": detail, "accn": k["rcept_no"]})
            # CEO별로 나눠 약속 기록을 만든다 (결과 시점 CEO 기준)
            for who in dict.fromkeys(c["ceo"] or current for c in checks):
                seg = [c for c in checks if (c["ceo"] or current) == who]
                p = P.Promise(kind=f"{pid} {label}", plan_rcept=by_fy[run[0]]["rcept_no"], plan_filed=by_fy[run[0]]["filed"])
                p.ceo_plan = [_norm_person(ceo_by_fy.get(run[0]) or "")]
                p.ceo_result = [_norm_person(who or "")]
                p.units = seg
                p.notes.append(f"문장이 나온 10-K: FY{run[0]}~FY{run[-1]} → 확인 기간 FY{run[0] + 1}~FY{run[-1] + 1}")
                p.notes.append(f"문장: \"{by_fy[run[0]]['found'][pid][:160]}\"")
                judged = [c for c in seg if c["result"] in ("지킴", "못 지킴")]
                if any(c["result"] == "못 지킴" for c in judged):
                    p.status, p.grade = "판정", "불이행"
                elif judged:
                    p.status, p.grade = "판정", "완전 이행"
                elif any(c["result"] == "확인 필요" for c in seg):
                    p.status = "확인 필요"
                else:
                    p.status = "진행 중"
                p.result_filed = who
                promises_out.append(p)
    ref_list = sorted(refs.values(), key=lambda r: (-len(r["years"]), r["years"][0]))
    return {"promises": promises_out, "current_ceo": current, "latest_fy": latest,
            "ceo_by_fy": ceo_by_fy, "references": ref_list}
