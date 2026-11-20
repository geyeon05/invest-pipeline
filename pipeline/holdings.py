"""보유 목록: analyses/_보유목록.md 를 회사 공책들에서 다시 만든다 (공책이 원본, 이 파일은 보기용).
개인 투자 정보라 GitHub에 올리지 않는다 (.gitignore)."""
import json

from . import notebook


def scan() -> tuple[list[dict], list[dict]]:
    held, trades = [], []
    for f in sorted(notebook.base_dir().glob("*/notebook.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        for t in b.get("trades", []):
            trades.append({"name": b["name"], **t})
        if b.get("holding"):
            r = b["rounds"][-1]
            checks = [p for k, p in r["steps"].items() if str(k).startswith("h")]
            last = max((p["computed_at"][:10] for p in checks), default="-")
            held.append({"name": b["name"], "company_id": b["company_id"], **b["holding"], "last_check": last,
                         "folder": f.parent.name})
    return held, trades


def write() -> None:
    held, trades = scan()
    lines = ["# 보유 목록", "",
             "개인 투자 정보라 GitHub에 올리지 않는다 (`.gitignore`). 회사 공책에서 저절로 만든다 (고치지 말 것).",
             "사용자가 샀다고 할 때만 추가된다 (`analyses/_투자_분석_단계.md` 6단계).", "",
             "| 회사 | 산 날짜 | 산 이유 (그때의 최종 판단) | 분석 기록 | 마지막 점검 |", "|---|---|---|---|---|"]
    lines += [f"| {h['name']} | {h['since']} | {h['reason'][:80]} | {h['folder']} ({h['round']}회차) | {h['last_check']} |" for h in held]
    lines += ["", "## 사고판 기록", "", "| 회사 | 날짜 | 무엇 | 메모 |", "|---|---|---|---|"]
    lines += [f"| {t['name']} | {t['day']} | {t['kind']} | {t.get('note', '')} |" for t in sorted(trades, key=lambda t: t["at"])]
    (notebook.base_dir() / "_보유목록.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
