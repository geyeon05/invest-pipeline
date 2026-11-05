# invest-pipeline

투자보고서 작성을 위한 데이터 수집 · 저장 · 시각화 파이프라인.

- **수집**: SEC EDGAR (미국) → `data/invest.db` (모든 수치에 공시번호·제출일 출처 기록)
- **시각화**: Streamlit 대시보드 (`dashboard.py`)
- **AI 조회**: `query.py` + `CLAUDE.md` 규칙 (AI는 기억이 아니라 DB를 조회해서 답함)

## 로컬 실행

```bash
uv sync
uv run collect.py AAPL MSFT       # 데이터 수집
uv run streamlit run dashboard.py # 대시보드
```

## 배포 데이터 갱신

배포된 대시보드는 저장소에 포함된 `data/invest.db` 를 읽습니다.
기업을 추가하거나 데이터를 갱신하려면 로컬에서 `collect.py` 를 실행한 뒤 커밋·푸시하면 자동 반영됩니다.

## 데이터 출처

미국 증권거래위원회(SEC) EDGAR 공개 데이터. 투자 권유가 아닌 학습·분석 목적.
