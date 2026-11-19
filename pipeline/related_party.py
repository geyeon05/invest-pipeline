"""특수관계자 거래 목록 (7-④) — 사업보고서 XBRL 주석에서 거래 상대별 매출·매입을 꺼낸다 (한국, 2022년 이후)

사용자 결정 (2026-11-19)
- 정의: 대주주 쪽(지배회사·대주주 개인·가족 회사·기업집단 계열사) 회사로부터의 **매입 ÷ 회사 매출**. 관계기업·공동기업 제외.
- 자동 분류는 회사마다 달라 믿기 어려우므로 '분석할 때' 판단: 도구는 목록을 보여주고, 사용자가 대주주 쪽 상대를 고르면
  criteria/judgments/<회사>_related.json 에 기록하고, 그다음부터 비율을 자동으로 계산한다.
- 회사가 붙인 분류(최상위 지배기업, 기업집단 계열사, 유의적 영향력 행사 기업 등)로 '후보' 표시를 붙인다. 확정은 사용자.

AI가 정한 값 (criteria/README.md 'AI가 정한 값'에 기록)
- 매입·비용으로 보는 태그: 이름에 Purchase / Expense / Cost / 매입 이 들어간 것 (자산 매입은 따로: PropertyAndOtherAssets 등)
- 매출·수익으로 보는 태그: Revenue / Sales / Income (이자·배당 수익 포함)
- 비율의 분자는 '매입·비용'만. 자산 매입·매각은 따로 보여준다.
"""
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from . import dart_xbrl
from . import standard as S

NS_X = "{http://www.xbrl.org/2003/instance}"
NS_XDI = "{http://xbrl.org/2006/xbrldi}"
REL_AXIS = "CategoriesOfRelatedPartiesAxis"
CS_AXIS = "ConsolidatedAndSeparateFinancialStatementsAxis"
OWNER_HINT = re.compile(r"UltimateParent|OfParentMember|^ParentMember|LargeBusinessGroup|SignificantInfluence|"
                        r"JointControlOrSignificant|Shareholder|LargestShareholder", re.I)
CATEGORY_KO = [
    (r"UltimateParent", "최상위 지배기업"), (r"^ParentMember|OfParentMember", "지배기업"),
    (r"LargeBusinessGroup", "기업집단 계열사"), (r"SignificantInfluence|JointControlOrSignificant", "유의적 영향력 행사 기업"),
    (r"Shareholder", "주주"), (r"Subsidiar", "종속기업"), (r"JointVenture", "공동기업"), (r"Associate", "관계기업"),
    (r"KeyManagement|Executive|Employee", "주요 경영진·임직원"), (r"OtherRelatedPart", "기타 특수관계자"),
]
ASSET = re.compile(r"PropertyAndOtherAssets|PropertyPlant|IntangibleAssets|SaleOfAssets|DisposalOf|AcquisitionOf", re.I)
BUY = re.compile(r"Purchase|Expense|Cost|매입", re.I)
SELL = re.compile(r"Revenue|Sales|Income|매출", re.I)
SKIP = re.compile(r"Receivable|Payable|Borrowing|Loan|Lending|Guarantee|Collateral|Dividend(s)?Paid|Contribution|"
                  r"OutstandingBalance|Commitment|Allowance|Deposit", re.I)

JUDGE_DIR = Path(__file__).resolve().parent.parent / "criteria" / "judgments"


def _split(member: str) -> tuple[str, str]:
    """멤버 이름 → (거래 상대 부분, 분류 부분). 회사마다 형식이 다르다:
    'HdHyundaiCoLtdMemberOfUltimateParentMemberOfDisclosure…' (HD현대중공업) /
    'LgChemLtdOfAssociatesMemberOfDisclosure…' (LG·셀트리온·네이버) / 'LargeBusinessGroupMember' (범주 합계)."""
    core = re.sub(r"(Member)?OfDisclosure.*$", "", member)
    core = re.sub(r"Member$", "", core)
    best = None
    for rx, _ in CATEGORY_KO:
        for m in re.finditer(rx.replace("^", "(?:^|Of)"), core):
            if best is None or m.start() < best:
                best = m.start()
    if best is None:
        return core, ""
    entity = re.sub(r"(Member)?Of$", "", core[:best])
    return entity, core[best:]


def _category(member: str) -> str:
    _, tail = _split(member)
    for rx, ko in CATEGORY_KO:
        if tail and re.search(rx.replace("^", "(?:^|Of)"), tail):
            return ko
    return "미분류"


@lru_cache(maxsize=32)
def _parse(path: str) -> tuple[int, list[dict]]:
    z = zipfile.ZipFile(path)
    names = z.namelist()
    root = ET.fromstring(z.read(next(n for n in names if n.endswith(".xbrl"))))
    lab_name = next((n for n in names if n.endswith("lab-ko.xml")), None)
    labels = {}
    if lab_name:
        lab = z.read(lab_name).decode("utf-8")
        labels = {k: re.sub(r"\s*\[구성요소\]\s*$", "", v).strip()
                  for k, v in re.findall(r'xlink:label="Label_label_([^"]+?)_ko"[^>]*>([^<]*)<', lab)}
    ctx = {}
    for c in root.iter(NS_X + "context"):
        per = c.find(NS_X + "period")
        ctx[c.get("id")] = (per.findtext(NS_X + "startDate"), per.findtext(NS_X + "endDate"),
                            {m.get("dimension").split(":")[-1]: (m.text or "") for m in c.iter(NS_XDI + "explicitMember")})
    rows = []
    for el in root:
        if not el.get("contextRef"):
            continue
        tag = el.tag.split("}")[-1]
        st, en, dims = ctx[el.get("contextRef")]
        if not st or not en or REL_AXIS not in dims:
            continue
        if dims.get(CS_AXIS, "").split(":")[-1] != "ConsolidatedMember":
            continue
        if set(dims) - {REL_AXIS, CS_AXIS}:
            continue
        if SKIP.search(tag):
            continue
        kind = "자산" if ASSET.search(tag) else ("매입" if BUY.search(tag) else ("매출" if SELL.search(tag) else None))
        if not kind:
            continue
        try:
            v = abs(float(el.text))
        except (TypeError, ValueError):
            continue
        member = dims[REL_AXIS]
        mid = member.replace(":", "_")
        local = member.split(":")[-1]
        entity, tail = _split(local)
        is_total = entity == ""                     # 범주 합계 멤버 (예: LargeBusinessGroupMember)
        rows.append({"year": int(en[:4]), "member": local, "name": labels.get(mid, local), "category": _category(local),
                     "kind": kind, "tag": tag, "value": v, "is_total": is_total,
                     "owner_hint": bool(tail and OWNER_HINT.search(tail))})
    fy = max((r["year"] for r in rows), default=0)
    return fy, rows


def table(company_id: str) -> list[dict]:
    """연도·상대·구분별 금액. 같은 연도가 두 보고서에 있으면 그 연도가 당기인 보고서 값."""
    best: dict[tuple, dict] = {}
    for f in sorted(dart_xbrl._dir(company_id).glob("*.zip")):
        fy, rows = _parse(str(f))
        for r in rows:
            key = (r["year"], r["member"], r["kind"], r["tag"])
            cur = r["year"] == fy
            if key in best and (best[key]["_cur"] or not cur):
                continue
            best[key] = {**r, "_cur": cur, "filing": f.stem}
    # 같은 상대·구분에서 태그가 여러 개면 합산 (예: 상품매입 + 기타비용)
    agg = defaultdict(lambda: {"value": 0.0, "tags": set()})
    meta = {}
    for (y, m, k, t), r in best.items():
        a = agg[(y, m, k)]
        a["value"] += r["value"]
        a["tags"].add(t)
        meta[(y, m)] = r
    out = []
    for (y, m, k), a in agg.items():
        r = meta[(y, m)]
        out.append({"year": y, "member": m, "name": r["name"], "category": r["category"], "kind": k,
                    "value": a["value"], "tags": sorted(a["tags"]), "is_total": r["is_total"],
                    "owner_hint": r["owner_hint"], "filing": r["filing"]})
    return sorted(out, key=lambda r: (r["year"], r["is_total"], r["category"], r["name"]))


def judgment_path(company_id: str) -> Path:
    return JUDGE_DIR / f"{company_id.replace(':', '_')}_related.json"


def load_owner_side(company_id: str) -> dict | None:
    p = judgment_path(company_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def counterparties(company_id: str) -> list[dict]:
    """거래 상대 목록 (범주 합계 행 제외). 번호는 이 순서. 최근 연도의 매입·매출·자산 금액."""
    rows = table(company_id)
    if not rows:
        return []
    last = max(r["year"] for r in rows)
    by = {}
    for r in rows:
        if r["is_total"]:
            continue
        c = by.setdefault(r["member"], {"member": r["member"], "name": r["name"], "category": r["category"],
                                        "owner_hint": r["owner_hint"], "years": set(), "last": {}})
        c["years"].add(r["year"])
        if r["year"] == last:
            c["last"][r["kind"]] = c["last"].get(r["kind"], 0) + r["value"]
    order = sorted(by.values(), key=lambda c: (not c["owner_hint"], c["category"], -c["last"].get("매입", 0), c["name"]))
    return [{**c, "years": sorted(c["years"]), "last_year": last} for c in order]


def save_owner_side(company_id: str, picks: list[dict], note: str = "") -> Path:
    """사용자가 고른 대주주 쪽 상대를 기록 (사용자 판단)."""
    from datetime import date
    p = judgment_path(company_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"company_id": company_id, "decided": str(date.today()), "by": "사용자",
            "rule": "대주주 쪽(지배회사·대주주 개인·가족 회사·기업집단 계열사) 회사로부터의 매입 ÷ 매출 (프로필 7-④)",
            "owner_side": [{"member": c["member"], "name": c["name"], "category": c["category"]} for c in picks],
            "note": note}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def ratios(company_id: str, owner_members: list[str]) -> list[dict]:
    """대주주 쪽 매입 ÷ 매출 (연도별)."""
    df = S.standardize(company_id)
    rev = df[df["item"] == "revenue"].set_index("year")["value"].to_dict() if not df.empty else {}
    rows = table(company_id)
    out = []
    for y in sorted({r["year"] for r in rows}):
        buy = sum(r["value"] for r in rows if r["year"] == y and r["kind"] == "매입" and r["member"] in owner_members)
        r_ = rev.get(y)
        out.append({"year": y, "purchase": buy, "revenue": r_, "ratio": buy / r_ if r_ else None})
    return out
