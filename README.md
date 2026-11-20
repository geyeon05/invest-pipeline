# invest-pipeline

투자보고서 수업용 도구. **기업명만 입력하면** 국내·해외 상장사의 공시 원본을 받아 두고, 내가 정한 투자 기준(9단계)으로 분석하며, 판단 과정을 회사마다 공책에 남긴다.

| | 국내 | 해외 |
|---|---|---|
| 출처 | DART (금융감독원 전자공시) | SEC EDGAR (미국 증권거래위원회) |
| 재무제표 | 사업보고서 전체 계정 (최근 10년) | XBRL 재무 팩트 (최근 10년) |
| 공시 | 최근 10년 공시 목록 + 원문 링크, 본문은 요청 시에만 | 같음 |

값은 **가공하지 않고** 원천 그대로 저장하며, 행마다 공시 접수번호가 붙어 원문으로 추적할 수 있다.

## 실행

```bash
cp .env.example .env      # API 키 입력 (.env 는 git에 올리지 않음)
uv sync
uv run data.py fin 삼성전자 매출액   # 재무제표 원본
uv run server.py                   # 분석 진행 화면: http://localhost:8501 (내 컴퓨터에서만)
```

## 분석 흐름

- **투자 분석:** 회사 고르기 → 1~8단계 계산(엔진) → 켜진 신호마다 논의 항목 → 초안 → 피드백 → 확인할 것 → 확정 → 9 최종 판단 → 결과물 3종(분석 보고서·검증표·역할구분) → 보유 중 점검. 단계: `analyses/_투자_분석_단계.md`
- **과제:** 과제 자료 읽기 → 대응표 → 내 9단계로 회사 분석 → 질문별 답 → 주장 → 보고서 → 마무리. 단계: `cases/_과제_진행_단계.md`
- 판단은 사용자가, 자료 수집·계산·피드백은 AI가 한다 (`CLAUDE.md` 6장). 기준과 부품 목록: `criteria/README.md`

## 구조

```
data.py              명령어 도구 (AI·사람 공용): 수집·조회·분석 부품·공책(run, note, case, hold)
server.py, web/      분석 진행 화면 (내 컴퓨터에서만, 시안을 옮긴 HTML)
pipeline/
  dart.py, sec.py, documents.py   수집 (재무·공시 목록·공시 본문)
  standard.py                     국내·해외 표준 재무항목
  cashflow.py, safety.py, …       분석 부품 (criteria/README.md 2장)
  flow.py                         엔진: 부품을 불러 9단계 계산 (외부 요청 없음)
  notebook.py                     공책: 판단 기록 (초안 → 피드백 → 확정, 역할 기록)
  report.py                       결과물: 분석 보고서·검증표·역할구분 (md + PDF)
  case.py, holdings.py            과제 방, 보유 목록
criteria/            투자기준·부품 설명·AI가 정한 값
analyses/, cases/    투자 분석 설명서·과제 설명서 (개인 기록과 reports/ 는 git 제외)
data/                수집 캐시 (git 제외, 언제든 원천에서 다시 받음)
```
