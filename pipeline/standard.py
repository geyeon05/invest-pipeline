"""표준 재무항목 계층:  원본(raw)  →  표준(standard)  →  (나중에) 지표(ratios)

국가·회계기준·회사마다 다른 계정과목을 '정의가 같은' 표준 항목 하나로 매핑한다.
이 파일은 매핑 '장치'만 가지고 있고, 항목 정의(ITEMS)는 필요할 때 하나씩 추가한다.

원칙
1. 값은 바꾸지 않는다. 허용하는 예외는 두 가지뿐이고, 결과에 반드시 표시한다.
   - 부호 정규화: 지출 항목(설비투자, 배당금 지급 등)은 회사마다 +/− 표기가 달라 양수로 통일 (method 에 '+abs')
   - 항등식 파생: 원본에 없을 때만, 회계 항등식으로 계산 (method = 'derived')
2. 모든 값에 출처(원본 계정명/태그, 공시번호)를 붙인다.
3. 매핑 후 검증(재무상태표 항등식 등)을 돌려, 잘못 매핑됐을 가능성을 드러낸다.

매핑 규칙 (국내 DART)
- 회사가 붙인 '계정명'이 명확하면 이름을 우선한다. 계정코드는 회사가 직접 태깅해서 틀린 경우가 있다.
  (실제 사례: 카카오는 2017~2022년 '영업수익'(=매출)에 매출총이익 코드를 붙였다)
- 이름으로 판단할 수 없을 때 표준계정코드를 쓴다.
매핑 규칙 (해외 SEC)
- XBRL 태그 우선순위 목록에서, 그 연도에 값이 있는 첫 태그를 쓴다.
"""
import re
from dataclasses import dataclass

import pandas as pd

from . import service


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    kind: str                      # flow(기간) / stock(시점) / per_share / shares(기간 주식 수) / shares_stock(시점 주식 수)
    sj: tuple[str, ...]            # DART 재무제표 구분
    kr_codes: tuple[str, ...]
    kr_names: str                  # 공백 제거한 계정명에 대한 정규식
    us_tags: tuple[str, ...]       # "taxonomy:tag" 우선순위
    kr_exclude: str = r"(?!x)x"    # 제외 패턴 (기본: 아무것도 제외 안 함)
    kr_code_exclude: str = r"(?!x)x"  # 계정코드 제외 패턴 (예: 이름이 같은 비유동 계정을 코드로 가려냄)
    sign: str = "as_is"            # as_is / abs
    note: str = ""


PL, BS, CF = ("IS", "CIS"), ("BS",), ("CF",)

# 표준 항목 정의: 비어 있음. 투자기준에서 지표가 필요해질 때 하나씩 정의해 추가한다.
# 정의는 분석가의 판단이므로, 항목마다 '왜 이렇게 정의했는지'를 note 에 남긴다.
#
# 예시 (실제 데이터로 검증했던 매출액 정의):
#   Item("revenue", "매출액", "flow", PL, ("ifrs-full_Revenue",),
#        r"^(매출액|매출|영업수익|수익|수익\(매출액\))$",
#        ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
#         "us-gaap:SalesRevenueNet", "ifrs-full:Revenue"),
#        note="국내 플랫폼 기업은 '영업수익'으로 표시"),
# 이전에 쓰던 21개 정의 전체는 git 기록(커밋 c9af85b)의 이 파일에서 볼 수 있다.
ITEMS: list[Item] = [
    # ---- 투자기준 2: 꾸준한 현금 창출 (사용자 결정 2026-11-18) ----
    Item("operating_cf", "영업활동현금흐름", "flow", CF, ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
         r"^영업활동(으로인한|으로부터의|에서창출된|으로부터)?(순)?현금(흐름|유입|유출)",
         ("us-gaap:NetCashProvidedByUsedInOperatingActivities",
          "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
          "ifrs-full:CashFlowsFromUsedInOperatingActivities"),
         kr_exclude=r"창출된현금$",
         note="회사가 보고한 값 그대로 (사용자 결정). 국제회계기준은 리스 원금 상환을 재무활동에, 이자 지급을 영업·재무 중 "
              "선택해 적을 수 있어 미국 기준보다 크게 나올 수 있다 — 조정하지 않고 표시만 한다."),
    Item("net_income", "당기순이익(연결)", "flow", PL, ("ifrs-full_ProfitLoss",),
         r"^(연결)?(당기|분기)?순(이익|손익|손실)(\(손실\))?$",
         ("us-gaap:ProfitLoss", "us-gaap:NetIncomeLoss", "ifrs-full:ProfitLoss"),
         kr_exclude=r"계속|중단|귀속|지배|포괄",
         note="비지배지분 몫까지 포함한 연결 순이익 (사용자 결정: 영업현금흐름과 범위를 맞춤)."),
    Item("capex_ppe", "유형자산 취득", "flow", CF,
         ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
          "ifrs-full_PurchaseOfPropertyPlantAndEquipment"),
         r"^유형자산의?취득(액)?$",
         ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:PaymentsToAcquireProductiveAssets",
          "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
         sign="abs", note="지출액을 양수로 통일."),
    Item("capex_intangible", "무형자산 취득", "flow", CF,
         ("ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities", "ifrs-full_PurchaseOfIntangibleAssets"),
         r"^무형자산의?취득(액)?$",
         ("us-gaap:PaymentsToAcquireIntangibleAssets",
          "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities"),
         sign="abs", note="개발비 자산화 등. 국제회계기준 기업은 개발비가 여기로, 미국 기업은 대부분 영업현금흐름에서 이미 빠짐."),
    Item("disposal_ppe", "유형자산 처분", "flow", CF,
         ("ifrs-full_ProceedsFromSalesOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
          "ifrs-full_ProceedsFromSalesOfPropertyPlantAndEquipment"),
         r"^유형자산의?처분(액)?$",
         ("us-gaap:ProceedsFromSaleOfPropertyPlantAndEquipment", "us-gaap:ProceedsFromSaleOfProductiveAssets",
          "ifrs-full:ProceedsFromSalesOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
         sign="abs", note="처분으로 들어온 현금을 양수로 통일."),
    Item("disposal_intangible", "무형자산 처분", "flow", CF,
         ("ifrs-full_ProceedsFromSalesOfIntangibleAssetsClassifiedAsInvestingActivities",
          "ifrs-full_ProceedsFromSalesOfIntangibleAssets"),
         r"^무형자산의?처분(액)?$",
         ("us-gaap:ProceedsFromSaleOfIntangibleAssets",
          "ifrs-full:ProceedsFromSalesOfIntangibleAssetsClassifiedAsInvestingActivities"),
         sign="abs", note="처분으로 들어온 현금을 양수로 통일."),
    # ---- 투자기준 3: 주주환원 기록 (사용자 결정 2026-11-18) ----
    Item("dividends_paid", "배당금 지급(지배기업 주주)", "flow", CF,
         ("ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "ifrs-full_DividendsPaid"),
         r"^(현금)?배당(금)?(의)?지급(액)?$",   # '배당의 지급'(셀트리온 2016~2025)
         ("us-gaap:PaymentsOfDividendsCommonStock", "us-gaap:PaymentsOfDividends",
          "ifrs-full:DividendsPaidClassifiedAsFinancingActivities"),
         kr_exclude=r"비지배", sign="abs",
         note="지배기업이 자기 주주에게 지급한 배당. 소수주주 배당이 별도 줄로 있으면 이 줄은 지배기업 몫으로 보고, "
              "한 줄뿐이면 소수주주 몫이 섞였을 수 있어 '구분 불가'로 표시."),
    Item("dividends_paid_nci", "비지배지분(소수주주) 배당 지급", "flow", CF, (),
         r"비지배(지분|주주).*배당|배당.*비지배", ("us-gaap:PaymentsOfDividendsMinorityInterest",),
         sign="abs", note="자회사가 소수주주에게 준 배당. 주주환원에 넣지 않고 표시만."),
    Item("buyback", "자기주식 취득(현금흐름표)", "flow", CF,
         ("ifrs-full_PurchaseOfTreasuryShares", "dart_AcquisitionOfTreasuryShares",
          "ifrs-full_PaymentsToAcquireOrRedeemEntitysShares"),
         r"^자기주식의?(취득|매입)(액)?$",
         ("us-gaap:PaymentsForRepurchaseOfCommonStock", "ifrs-full:PaymentsToAcquireOrRedeemEntitysShares"),
         sign="abs", note="현금흐름표의 자사주 매입액. 임직원 보상 목적 매입 차감은 pipeline/returns.py 에서 한다."),
    Item("net_income_parent", "지배주주순이익", "flow", PL, ("ifrs-full_ProfitLossAttributableToOwnersOfParent",),
         r"(지배기업|지배회사|지배주주).*(소유주|지분|귀속|순이익)",
         ("us-gaap:NetIncomeLoss", "ifrs-full:ProfitLossAttributableToOwnersOfParent"),
         kr_exclude=r"비지배|포괄"),
    # ---- 투자기준 4: 이익의 질 · 이익조정 신호 (사용자 결정 2026-11-18) ----
    Item("total_assets", "자산총계", "stock", BS, ("ifrs-full_Assets",), r"^자산(총계|합계)$",
         ("us-gaap:Assets", "ifrs-full:Assets")),
    Item("revenue", "매출액", "flow", PL, ("ifrs-full_Revenue",),
         r"^(매출액|매출|영업수익|수익\(매출액\)|매출액\(영업수익\))$",
         ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
          "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax", "us-gaap:SalesRevenueNet", "ifrs-full:Revenue"),
         note="국내 플랫폼·게임 기업은 '영업수익'으로 표시. 총매출 줄 없이 제품·용역·건설 매출로만 나뉜 해는 합산(파생)."),
    Item("receivables", "매출채권(유동)", "stock", BS,
         ("ifrs-full_CurrentTradeReceivables", "dart_ShortTermTradeReceivable", "ifrs-full_TradeReceivables"),
         r"^(단기)?매출채권(\(순\)|\(순액\))?$",
         ("us-gaap:AccountsReceivableNetCurrent", "ifrs-full:CurrentTradeReceivables"),
         kr_exclude=r"장기|비유동", kr_code_exclude=r"(?i)noncurrent|longterm",
         note="매출채권만 (사용자 결정). 매출채권및기타채권으로만 공시한 해는 그 값을 '범위 차이'로 사용."),
    Item("receivables_broad", "매출채권및기타채권(유동)", "stock", BS, (),
         r"^(단기)?매출채권및기타(유동)?(수취)?채권$",
         ("us-gaap:ReceivablesNetCurrent", "us-gaap:AccountsNotesAndLoansReceivableNetCurrent",
          "ifrs-full:TradeAndOtherCurrentReceivables"),
         kr_code_exclude=r"(?i)noncurrent|longterm",
         note="매출채권 줄이 없는 해의 대체용 (기타채권 포함). 이름이 같은 비유동 계정은 코드로 제외 (네이버)."),
    Item("contract_assets", "계약자산(미청구공사)", "stock", BS,
         ("ifrs-full_CurrentContractAssets", "ifrs-full_ContractAssets",
          "dart_ShortTermDueFromCustomersForContractWork", "dart_ShortTermDueFromCustomersForContractWorkNet"),
         r"^(유동)?계약자산$|^(단기)?미청구공사(\(순\)|\(순액\))?$",
         ("us-gaap:ContractWithCustomerAssetNetCurrent", "us-gaap:ContractWithCustomerAssetNet",
          "us-gaap:UnbilledContractsReceivable", "ifrs-full:CurrentContractAssets"),
         kr_exclude=r"확정|장기|비유동", kr_code_exclude=r"(?i)noncurrent|longterm",
         note="공사·건조가 진행된 만큼 매출은 인식했지만 아직 청구하지 않은 금액. 수주산업의 매출채권 성격 (사용자 결정: 별도 표시)."),
    Item("inventory", "재고자산", "stock", BS, ("ifrs-full_Inventories", "ifrs-full_InventoriesTotal", "ifrs-full_CurrentInventories"),
         r"^(유동)?재고자산(\(순\))?$",
         ("us-gaap:InventoryNet", "ifrs-full:Inventories", "us-gaap:InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"),
         kr_exclude=r"비유동|장기"),
    # ---- 투자기준 5: 재무 안전성 (사용자 결정 2026-11-18) ----
    Item("total_liabilities", "부채총계", "stock", BS, ("ifrs-full_Liabilities",), r"^부채(총계|합계)$",
         ("us-gaap:Liabilities", "ifrs-full:Liabilities"),
         note="부채비율·부채÷영업CF의 분자 (사용자 결정: 수업 공식대로 부채총계). 미국에 태그가 없는 해는 자산총계 − 자본총계(파생)."),
    Item("equity_total", "자본총계(비지배지분 포함)", "stock", BS, ("ifrs-full_Equity",), r"^자본(총계|합계)$",
         ("us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "us-gaap:StockholdersEquity",
          "ifrs-full:Equity"),
         note="부채비율의 분모 (사용자 결정: 연결 부채총계와 범위를 맞춰 비지배지분 포함)."),
    Item("current_assets", "유동자산", "stock", BS, ("ifrs-full_CurrentAssets",), r"^유동자산(합계|총계)?$",
         ("us-gaap:AssetsCurrent", "ifrs-full:CurrentAssets")),
    Item("current_liabilities", "유동부채", "stock", BS, ("ifrs-full_CurrentLiabilities",), r"^유동부채(합계|총계)?$",
         ("us-gaap:LiabilitiesCurrent", "ifrs-full:CurrentLiabilities")),
    Item("operating_income", "영업이익", "flow", PL, ("dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"),
         r"^영업(이익|손실|손익)(\(손실\)|\(이익\))?$",
         ("us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities"),
         note="회사가 보고한 값 그대로 (사용자 결정). 국제회계기준에는 영업이익 정의가 없어 기타영업손익 처리가 회사마다 다를 수 있다."),
    Item("interest_expense", "이자비용", "flow", PL, (), r"(?!x)x",
         ("us-gaap:InterestExpense", "us-gaap:InterestExpenseNonoperating", "us-gaap:InterestAndDebtExpense",
          "us-gaap:InterestExpenseDebt", "ifrs-full:FinanceCosts"),
         sign="abs",
         note="한국은 손익계산서 본문에 없어 사업보고서 XBRL 주석에서 읽는다 (pipeline/dart_xbrl.py). 회사가 보고한 그대로: "
              "한국(국제회계기준)은 리스부채 이자 포함, 미국은 대부분 미포함 (사용자 결정: 조정하지 않음)."),
    # ---- 투자기준 6: 수익성과 그 원천 (사용자 결정 2026-11-19) ----
    Item("interest_bearing_debt", "이자부 부채(차입금·사채·리스)", "stock", BS, (), r"(?!x)x", (),
         note="스프레드의 이자율 = 이자비용 ÷ 평균 이자부 부채 (사용자 결정). 한국: 재무상태표의 차입금·사채·리스부채 줄 합산. "
              "미국: 장기 차입금(유동분 포함) + 기업어음·단기차입금 + 금융리스부채. 계산 규칙은 KR_DEBT_RX, US_DEBT."),
    # 미국 주식 수 (한국은 DART '주식의 총수 현황'·'자기주식 취득 및 처분 현황' API 사용: pipeline/dart_shares.py)
    Item("shares_issued", "발행주식 총수(미국)", "shares_stock", BS, (), r"(?!x)x",
         ("us-gaap:CommonStockSharesIssued",), note="자기주식 포함."),
    Item("shares_outstanding", "유통주식 수(미국)", "shares_stock", BS, (), r"(?!x)x",
         ("us-gaap:CommonStockSharesOutstanding",), note="자기주식 제외."),
    Item("shares_retired", "소각 주식 수(미국)", "shares", CF, (), r"(?!x)x",
         ("us-gaap:StockRepurchasedAndRetiredDuringPeriodShares", "us-gaap:TreasuryStockSharesRetired"),
         note="매입 즉시 소각하거나 자기주식을 소각한 수량."),
]
ITEM_BY_KEY = {i.key: i for i in ITEMS}

# ---------------- 일치 수준 ----------------
# exact   정의 일치      : 표준 항목과 같은 개념의 계정/태그
# proxy   대체(조건 확인): 정의는 다르지만, 차이를 만드는 요소가 그 해에 없음을 확인했으므로 값이 같다
# scope   범위 차이 가능 : 정의가 달라 값이 다를 수 있다. 지표 계산 시 주의
# derived 파생(계산값)   : 원본에 없어 계산 (항등식, 세부 줄 합산, 같은 값 대체). 계산 방법은 match_note 에
MATCH_LABEL = {"exact": "정의 일치", "proxy": "대체(조건 확인)", "scope": "범위 차이 가능", "derived": "파생(계산값)"}

# 미국 태그 중 정의가 표준과 다른 것: (항목, 태그) → (조건, 조건 불충족 시 처리, 설명)
#   조건 nci    : 그 해 비지배지분이 없거나 0  (MinorityInterest, NetIncomeLossAttributableToNoncontrollingInterest)
#   조건 equity : 그 해 지분법손익이 없거나 0  (IncomeLossFromEquityMethodInvestments)
#   조건 disc   : 그 해 중단영업이 없거나 0
#   조건 None   : 확인할 방법이 없음 → 항상 scope
#   처리 drop   : 값을 쓰지 않음(빈칸) / scope: 쓰되 '범위 차이 가능'으로 표시
US_TAG_RULES: dict[tuple[str, str], tuple[str | None, str, str]] = {
    ("net_income", "us-gaap:NetIncomeLoss"):
        ("nci", "drop", "지배주주 몫 순이익. 비지배지분이 있으면 연결 순이익과 달라 사용하지 않음"),
    ("operating_cf", "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"):
        ("disc", "scope", "계속영업분만 포함 (중단영업 현금흐름 제외)"),
    ("capex_ppe", "us-gaap:PaymentsToAcquireProductiveAssets"):
        (None, "scope", "유형자산 외 생산용 자산(내부용 소프트웨어 등 무형)이 포함될 수 있음 → 무형자산 취득과 겹칠 수 있음"),
    ("disposal_ppe", "us-gaap:ProceedsFromSaleOfProductiveAssets"):
        (None, "scope", "유형자산 외 생산용 자산 처분이 포함될 수 있음"),
    ("dividends_paid", "us-gaap:PaymentsOfDividends"):
        ("nci", "scope", "보통주·우선주 배당 합계일 수 있고, 비지배지분 배당이 섞였을 수 있음"),
    ("inventory", "us-gaap:InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"):
        (None, "scope", "장기 계약 재고에서 고객 선수금·진행청구액을 뺀 값 (예: Boeing)"),
    ("equity_total", "us-gaap:StockholdersEquity"):
        ("nci", "scope", "지배주주 자본만 (비지배지분 제외)"),
    ("interest_expense", "us-gaap:InterestExpenseDebt"):
        (None, "scope", "차입금 이자만 (리스 이자 등 제외될 수 있음, 예: Walmart)"),
    ("interest_expense", "ifrs-full:FinanceCosts"):
        (None, "scope", "금융원가 전체 (이자 외 항목이 섞일 수 있음, 예: TSMC)"),
}
# 항등식 파생: (만들 항목, 항목 A, 항목 B, 설명) → 원본에 없을 때만 A − B 로 계산
# 예시: ("total_liabilities", "total_assets", "equity_total", "파생: 자산총계 − 자본총계")
DERIVATIONS: list[tuple[str, str, str, str]] = [
    ("total_liabilities", "total_assets", "equity_total", "파생: 자산총계 − 자본총계 (부채총계 태그 없음)"),
]
# 대체: (만들 항목, 가져올 항목, 일치 수준, 설명) → 원본에 없는 해에만 다른 항목 값을 그대로 쓴다
FALLBACKS: list[tuple[str, str, str, str]] = [
    ("receivables", "receivables_broad", "scope", "매출채권 줄이 없어 매출채권및기타채권 사용 (기타채권 포함)"),
]
# 이자부 부채 (투자기준 6): 한국은 재무상태표 줄 합산, 미국은 태그 조합 (_us_debt)
#   (실제 사례: LG화학은 유동·비유동 모두 '차입금', NC '유동성사채및차입금', 삼성전자·현대차 '유동성장기부채'.
#    셀트리온은 본문에 차입금 줄이 없어 빈칸)
KR_DEBT_RX = (r"^(단기|장기|유동성장기|유동성|비유동|유동|비유동성)?(차입금|사채|차입부채|리스부채|사채및차입금|차입금및사채|"
              r"장기부채|전환사채|교환사채|신주인수권부사채|기업어음)$|^유동성장기(차입금|부채)$|^유동성사채및차입금$")
KR_DEBT_EXCLUDE = r"할인|조정|이자|상환할증|보증|충당"
KR_FIN_LIAB_RX = r"^(단기|장기|유동|비유동)?(기타)?(유동|비유동)?금융부채$"
US_DEBT = {
    # 장기 차입금: 유동분 포함 합계가 있으면 그것, 없으면 비유동 + 유동
    "long": (("us-gaap:LongTermDebt",), ("us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebtCurrent"),
             ("us-gaap:LongTermDebtAndCapitalLeaseObligations", "us-gaap:LongTermDebtAndCapitalLeaseObligationsCurrent")),
    # 단기 차입금 (장기 차입금과 겹치지 않음)
    "short": ("us-gaap:CommercialPaper", "us-gaap:ShortTermBorrowings"),
    # 금융리스 부채 (운용리스는 미국 이자비용에 들어가지 않으므로 넣지 않음)
    "lease": ("us-gaap:FinanceLeaseLiability",),
    # 국제회계기준(20-F)
    "ifrs": ("ifrs-full:Borrowings", "ifrs-full:CurrentBorrowings", "ifrs-full:NoncurrentPortionOfNoncurrentBondsIssued",
             "ifrs-full:CurrentPortionOfNoncurrentBondsIssued", "ifrs-full:LeaseLiabilities"),
}


# 국내: 계정명으로 정의 차이가 드러나는 경우 → 범위 차이 표시 (항목, 계정명 정규식, 설명)
KR_SCOPE_RULES: list[tuple[str, str, str]] = [
    ("revenue", r"지분법", "매출에 지분법손익이 포함됨 (지주회사, 예: LG '매출 및 지분법 손익')"),
]
# 국내: 합계 줄이 없고 세부 줄로만 공시한 해에 세부 줄을 합산 (항목, 재무제표, 계정명 정규식, 계정코드 정규식, 설명)
#   (실제 사례: 고영 2021년 유형자산 취득을 토지·건물·건설중인자산 등으로만 공시, LG(지주) 매출을 제품·용역·건설로만 공시)
KR_COMPONENTS: list[tuple[str, tuple[str, ...], str, str, str]] = [
    ("capex_ppe", CF, r"^(토지|건물|구축물|기계장치|차량운반구|공구와기구|공기구비품|비품|집기|시설장치|건설중인(유형)?자산|기타유형자산)의?(취득|증가)$",
     r"(?!x)x", "세부 줄 합산: 토지·건물·기계장치·건설중인자산 등의 취득"),
    ("capex_intangible", CF, r"^(개발비|소프트웨어|산업재산권|회원권|건설중인무형자산|기타무형자산)의?(취득|증가)$",
     r"(?!x)x", "세부 줄 합산: 개발비·소프트웨어·건설중인무형자산 등의 취득"),
    ("revenue", PL, r"(?!x)x", r"^ifrs-full_RevenueFrom(SaleOfGoods|RenderingOfServices|ConstructionContracts)$",
     "세부 줄 합산: 제품·상품 매출 + 용역 매출 + 건설계약 매출"),
]

NCI_TAGS = ("us-gaap:MinorityInterest", "us-gaap:NetIncomeLossAttributableToNoncontrollingInterest")
EQUITY_METHOD_TAGS = ("us-gaap:IncomeLossFromEquityMethodInvestments",)
DISCONTINUED_TAGS = ("us-gaap:IncomeLossFromDiscontinuedOperationsNetOfTax",
                     "us-gaap:IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity",
                     "us-gaap:CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations",
                     "us-gaap:CashProvidedByUsedInDiscontinuedOperations")

# 회계기준 차이 중 숫자 매핑으로 해결되지 않는 것들 (해석할 때 반드시 고려)
STANDARD_GAPS = [
    ("리스 (IFRS16 vs ASC842)", "IFRS: 모든 리스를 자산·부채로 인식하고 비용은 감가상각+이자로 나뉨 → 영업이익·EBITDA·영업현금흐름이 "
     "US GAAP 운용리스 기업보다 크게 나온다. 부채비율도 IFRS 쪽이 높게 나온다."),
    ("현금흐름 분류", "IFRS는 이자·배당의 수취·지급을 영업/투자/재무 중 선택 가능. US GAAP은 이자지급=영업, 배당지급=재무로 고정. "
     "FCF 비교 시 각 회사의 분류를 확인해야 한다."),
    ("개발비 자산화", "IFRS는 요건 충족 시 개발비를 무형자산으로 자산화할 수 있고, US GAAP은 대부분 비용 처리. "
     "IFRS 기업의 영업이익이 높게, 자산이 크게 나올 수 있다 (예: 바이오·게임·자동차)."),
    ("영업이익 정의", "IFRS에는 영업이익 정의가 없다. K-IFRS는 '매출총이익 − 판관비' 방식 표시를 요구하지만 "
     "기타영업수익·비용 처리는 회사마다 다를 수 있다."),
    ("재고자산 LIFO", "US GAAP만 후입선출법(LIFO) 허용. 물가 상승기에 LIFO 기업은 매출원가가 크고 재고자산이 작게 나온다."),
    ("회계연도", "국내는 대부분 12월 결산, 미국은 회사마다 다름(Apple 9월, NVIDIA 1월). 표준 연도는 "
     "'기간 종료월이 6월 이후면 그 해, 1~5월이면 전년'으로 맞춘다 (Compustat 방식). 기간 종료일을 함께 표시한다."),
    ("통화", "국내 KRW, 미국 USD, 해외 20-F 기업은 현지통화(TSMC는 TWD). 비율은 그대로 비교 가능하지만 금액 비교는 환산이 필요하다."),
    ("금융업", "은행·보험·증권은 매출·매출원가·유동자산 개념이 없어 일반 기업 지표로 비교하면 안 된다. "
     "또 DART API는 금융업 재무제표를 2023년 이후만 제공한다."),
]


def _norm_name(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    return re.sub(r"^([IVXⅠ-Ⅹ]+|\d+|[가-하])[.)]", "", s)  # 'Ⅰ.매출액', '1.매출액', '가.매출액'


def _norm_code(s: str) -> str:
    return re.sub(r"^ifrs_", "ifrs-full_", s or "")


def standard_year(period_end: pd.Series) -> pd.Series:
    """회계연도 라벨 통일: 종료월 6~12월 → 그 해, 1~5월 → 전년 (예: NVIDIA 2026-01 종료 → 2025)."""
    d = pd.to_datetime(period_end)
    return d.dt.year.where(d.dt.month >= 6, d.dt.year - 1)


# ---------------- 국내 ----------------
def _kr(company_id: str) -> pd.DataFrame:
    raw = service.raw_financials(company_id)
    if raw.empty:
        return pd.DataFrame()
    raw = raw.assign(nm=raw["account_nm"].map(_norm_name), code=raw["account_id"].map(_norm_code))
    full = raw

    def by_name(row) -> str | None:
        for it in ITEMS:
            if row.sj_div in it.sj and re.search(it.kr_names, row.nm) and not re.search(it.kr_exclude, row.nm)                     and not re.search(it.kr_code_exclude, row.code):
                return it.key
        return None

    code_map = {c: it.key for it in ITEMS for c in it.kr_codes}
    raw["by_name"] = raw.apply(by_name, axis=1)
    # 계정코드가 '다른 개념'임을 분명히 말하면 이름 매칭을 버린다.
    # (실제 사례: 네이버 2021년 '지배기업 소유주지분'은 순이익이 아니라 총포괄이익 귀속분이었다)
    veto = raw["code"].str.contains(r"Comprehensive|Discontinued|ContinuingOperations|Noncontrolling", na=False) \
        & ~raw["code"].isin(code_map)
    raw.loc[veto, "by_name"] = None
    raw["by_code"] = [k if (k := code_map.get(c)) and sj in ITEM_BY_KEY[k].sj else None
                      for c, sj in zip(raw["code"], raw["sj_div"])]
    # 이름이 다른 항목을 가리키면 코드는 무시 (코드 오태깅 방지)
    raw["item"] = raw["by_name"].fillna(raw["by_code"].where(raw["by_name"].isna()))
    raw = raw[raw["item"].notna()].copy()
    raw["method"] = ["name+code" if n == c else ("name" if n else "code")
                     for n, c in zip(raw["by_name"], raw["by_code"])]
    raw["rank"] = raw["method"].map({"name+code": 0, "name": 1, "code": 2})
    raw["sj_rank"] = (raw["sj_div"] != "IS").astype(int)  # 손익계산서를 포괄손익계산서보다 우선
    raw = raw.sort_values(["rank", "sj_rank", "ord"]).drop_duplicates(["item", "bsns_year"])

    company = service.get_company(company_id) or {}
    acc_mt = str((company.get("profile") or {}).get("acc_mt") or "12").zfill(2)  # 결산월

    def pend(years: pd.Series) -> pd.Series:
        return (pd.to_datetime(years.astype(str) + "-" + acc_mt + "-01") + pd.offsets.MonthEnd(0)).dt.strftime("%Y-%m-%d")

    out = pd.DataFrame({
        "item": raw["item"], "year": raw["bsns_year"].astype(int),
        "period_end": pend(raw["bsns_year"]),
        "value": raw["thstrm_amount"], "currency": raw["currency"].fillna("KRW"),
        "source": raw["account_nm"] + "  [" + raw["account_id"].fillna("") + "]  (" + raw["sj_nm"] + ", " + raw["fs_div"] + ")",
        "filing": raw["rcept_no"], "method": raw["method"],
        "match": "exact", "match_note": "",
    })
    for key, rx, note in KR_SCOPE_RULES:
        m = (out["item"] == key) & raw["account_nm"].map(_norm_name).str.contains(rx).values
        out.loc[m, ["match", "match_note"]] = ["scope", note]
    extra = []
    have = set(zip(out["item"], out["year"]))
    # 세부 줄 합산: 합계 줄이 없는 해에만
    for key, sj, name_rx, code_rx, label in KR_COMPONENTS:
        it = ITEM_BY_KEY[key]
        parts = full[full["sj_div"].isin(sj) & (full["nm"].str.match(name_rx) | full["code"].str.match(code_rx))
                     & full["thstrm_amount"].notna()]
        for y, g in parts.groupby("bsns_year"):
            if (key, int(y)) in have:
                continue
            g = g.drop_duplicates("nm")
            vals = g["thstrm_amount"].abs() if it.sign == "abs" else g["thstrm_amount"]
            extra.append({"item": key, "year": int(y), "period_end": pend(pd.Series([y])).iat[0], "value": vals.sum(),
                          "currency": g["currency"].fillna("KRW").iat[0],
                          "source": " + ".join(g["account_nm"]), "filing": g["rcept_no"].iat[0], "method": "derived",
                          "match": "derived", "match_note": label})
    # 지배주주 순이익: 귀속 구분 줄이 없고 비지배지분도 없는 해 → 연결 순이익과 같은 값
    #   (실제 사례: HD현대중공업 2021~2022년은 비지배지분이 없어 손익계산서에 귀속 구분이 없다)
    pl = full[full["sj_div"].isin(PL)]
    nci_years = set(pl.loc[pl["nm"].str.contains("비지배") | pl["code"].str.contains("(?i)noncontrolling"), "bsns_year"].astype(int))
    ni = out[out["item"] == "net_income"]
    for r in ni.itertuples():
        if ("net_income_parent", r.year) not in have and r.year not in nci_years and pd.notna(r.value):
            extra.append({**r._asdict(), "item": "net_income_parent", "method": "derived", "match": "derived",
                          "match_note": "비지배지분이 없어 손익 귀속 구분이 없음 → 연결 순이익 = 지배주주 순이익"})
    # 이자부 부채: 재무상태표의 차입금·사채·리스부채 줄을 합산 (투자기준 6, 파생)
    bs = full[(full["sj_div"] == "BS") & full["nm"].str.match(KR_DEBT_RX) & ~full["nm"].str.contains(KR_DEBT_EXCLUDE)
              & full["thstrm_amount"].notna()]
    fin_liab = full[(full["sj_div"] == "BS") & full["nm"].str.match(KR_FIN_LIAB_RX)]
    # 차입금·리스 줄이 하나도 없고 금융부채 줄만 있는 해도 같은 규칙 (실제 사례: 셀트리온)
    years = sorted(set(bs["bsns_year"]) | set(fin_liab["bsns_year"]))
    for y in years:
        g = bs[bs["bsns_year"] == y].drop_duplicates(["nm", "code", "thstrm_amount"])
        if g.empty and not (fin_liab["bsns_year"] == y).any():
            continue
        if g.empty:
            g = fin_liab[fin_liab["bsns_year"] == y].head(1)   # 빈칸 행의 공시번호용
        # 차입금·사채 줄 없이 리스부채만 있고 '금융부채' 줄이 있으면, 차입금이 금융부채에 묶인 것 → 빈칸 (사용자 결정)
        #   (실제 사례: HD현대중공업은 리스부채만 잡혀 이자율 449%로 나왔다)
        if not g["nm"].str.contains(r"차입|사채|장기부채|기업어음").any() \
                and (fin_liab["bsns_year"] == y).any():
            extra.append({"item": "interest_bearing_debt", "year": int(y), "period_end": pend(pd.Series([y])).iat[0],
                          "value": float("nan"), "currency": "KRW",
                          "source": "차입금 줄 없음 (" + ", ".join(fin_liab.loc[fin_liab["bsns_year"] == y, "account_nm"]
                                                          .str.replace(" ", "").unique()) + ")",
                          "filing": g["rcept_no"].iat[0], "method": "derived", "match": "derived",
                          "match_note": "재무상태표에 차입금·사채 줄이 없음 (금융부채에 포함됐을 수 있음) → 빈칸"})
            continue
        extra.append({"item": "interest_bearing_debt", "year": int(y), "period_end": pend(pd.Series([y])).iat[0],
                      "value": g["thstrm_amount"].sum(), "currency": g["currency"].fillna("KRW").iat[0],
                      "source": " + ".join(g["account_nm"].str.replace(" ", "")), "filing": g["rcept_no"].iat[0],
                      "method": "derived", "match": "derived",
                      "match_note": "재무상태표 본문의 차입금·사채·리스부채 줄 합산 (본문에 없는 차입금은 빠짐)"})
    # 이자비용: 손익계산서 본문에 없어 사업보고서 XBRL 주석에서 (투자기준 5)
    from . import dart_xbrl
    extra += dart_xbrl.interest_expense(company_id)
    if extra:
        out = pd.concat([out, pd.DataFrame(extra).drop(columns=["Index"], errors="ignore")], ignore_index=True)
    return out


# ---------------- 해외 ----------------
def _us(company_id: str) -> pd.DataFrame:
    df = service.raw_financials(company_id)
    if df.empty:
        return pd.DataFrame()
    df = df[df["form"].isin(service.ANNUAL_FORMS) & (df["fp"] == "FY")].copy()
    start, end = pd.to_datetime(df["start"], errors="coerce"), pd.to_datetime(df["end"], errors="coerce")
    dur = (end - start).dt.days
    df = df[dur.isna() | dur.between(330, 400)].copy()
    df["year"] = standard_year(df["end"])
    df["full_tag"] = df["taxonomy"] + ":" + df["tag"]
    # 각 연도 '최초 연차보고서' 값 사용 (as reported). 국내(각 연도 사업보고서 당기금액)와 같은 원칙이고,
    # 서로 다른 시점의 정정·재작성 값이 섞여 재무상태표 항등식이 깨지는 것을 막는다.
    df = df.sort_values("filed").drop_duplicates(["full_tag", "unit", "year"], keep="first")

    # 보고통화 고정: 20-F 기업은 현지통화와 USD 편의환산을 함께 보고하는 경우가 있다 (예: TSMC TWD+USD)
    money = df[df["full_tag"].isin(["us-gaap:Assets", "ifrs-full:Assets"])]
    currency = money["unit"].mode().iat[0] if not money.empty else "USD"

    # 연도별 기준 공시 = 그 회계연도를 처음 보고한 연차보고서. 태그 우선순위는 이 공시 '안에서' 적용한다.
    # (태그별로 따로 고르면, 예컨대 Microsoft 2016년 매출은 2018년 재작성 공시에서, 매출원가는 2016년 원 공시에서
    #  가져오는 식으로 시점이 섞인다)
    first = df.sort_values("filed").groupby("year").head(1)
    anchor = dict(zip(first["year"], first["accn"]))

    # 조건 확인용: 연도별로 비지배지분 / 지분법손익이 0이 아닌 값으로 보고됐는지
    def present(tags) -> set[int]:
        s = df[df["full_tag"].isin(tags) & df["val"].fillna(0).ne(0)]
        return set(s["year"].astype(int))
    has = {"nci": present(NCI_TAGS), "equity": present(EQUITY_METHOD_TAGS), "disc": present(DISCONTINUED_TAGS)}

    out = []
    for it in ITEMS:
        cands = df[df["full_tag"].isin(it.us_tags)].copy()
        if cands.empty:
            continue
        want = {"per_share": f"{currency}/shares", "shares": "shares", "shares_stock": "shares"}.get(it.kind, currency)
        cands = cands[cands["unit"] == want]
        cands["year"] = cands["year"].astype(int)
        cands["match"], cands["match_note"] = "exact", ""
        keep = pd.Series(True, index=cands.index)
        for (key, tag), (cond, on_fail, note) in US_TAG_RULES.items():
            if key != it.key:
                continue
            m = cands["full_tag"] == tag
            ok = cands["year"].isin(has[cond]).map(lambda b: not b) if cond else pd.Series(False, index=cands.index)
            cands.loc[m & ok, ["match", "match_note"]] = ["proxy", f"{note} → 그 해 해당 요소 없음 확인"]
            cands.loc[m & ~ok, ["match", "match_note"]] = ["scope", note]
            if on_fail == "drop":
                keep &= ~(m & ~ok)
        cands = cands[keep]
        cands["prio"] = cands["full_tag"].map({t: i for i, t in enumerate(it.us_tags)})
        cands["off_anchor"] = cands["accn"] != cands["year"].map(anchor)
        cands["match_rank"] = cands["match"].map({"exact": 0, "proxy": 1, "scope": 2})
        # 같은 공시 안에서는 정의 일치 > 대체 > 범위 차이 순, 그다음 태그 우선순위
        cands = cands.sort_values(["off_anchor", "match_rank", "prio", "filed"]).drop_duplicates("year")
        out.append(pd.DataFrame({
            "item": it.key, "year": cands["year"], "period_end": cands["end"],
            "value": cands["val"], "currency": cands["unit"].str.split("/").str[0],
            "source": cands["full_tag"] + "  (" + cands["label"] + ")",
            "filing": cands["accn"], "method": "tag",
            "match": cands["match"], "match_note": cands["match_note"],
        }))
    # 이자부 부채 (투자기준 6): 태그 조합 → 파생. 같은 해 값은 위에서 고른 '최초 연차보고서' 값.
    v = df[df["unit"] == currency].pivot_table(index="year", columns="full_tag", values="val", aggfunc="first")
    meta = df.drop_duplicates("year").set_index("year")
    for y in v.index:
        g = lambda t: v.at[y, t] if t in v and pd.notna(v.at[y, t]) else None  # noqa: E731
        parts = []
        long = next((grp for grp in US_DEBT["long"] if all(g(t) is not None for t in grp[:1])), None)
        if long:
            parts += [t for t in long if g(t) is not None]
        parts += [t for t in US_DEBT["short"] + US_DEBT["lease"] if g(t) is not None]
        if not long:
            parts += [t for t in US_DEBT["ifrs"] if g(t) is not None]
        if not parts:
            continue
        ifrs = not long
        out.append(pd.DataFrame([{
            "item": "interest_bearing_debt", "year": int(y), "period_end": meta.at[y, "end"] if y in meta.index else None,
            "value": sum(g(t) for t in parts), "currency": currency.split("/")[0],
            "source": " + ".join(t.split(":")[1] for t in parts), "filing": anchor.get(y), "method": "derived",
            "match": "scope" if ifrs else "derived",
            "match_note": ("국제회계기준 태그 조합 (일부 차입금이 빠졌을 수 있음)" if ifrs else
                           "장기 차입금(유동분 포함) + 기업어음·단기차입금 + 금융리스부채 합산. 운용리스 부채는 미국 이자비용에 "
                           "들어가지 않으므로 제외")}]))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ---------------- 공통: 부호 · 파생 · 검증 ----------------
def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    for it in ITEMS:
        if it.sign == "abs":
            m = (df["item"] == it.key) & df["value"].notna()
            df.loc[m & (df["value"] < 0), "method"] += "+abs"
            df.loc[m, "value"] = df.loc[m, "value"].abs()

    def derive(target: str, a: str, b: str, label: str):
        nonlocal df
        w = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
        if a not in w or b not in w:
            return
        have = set(df.loc[df["item"] == target, "year"])
        calc = (w[a] - w[b]).dropna()
        calc = calc[~calc.index.isin(have)]
        if calc.empty:
            return
        meta = df[df["item"] == a].set_index("year")
        df = pd.concat([df, pd.DataFrame({
            "item": target, "year": calc.index, "period_end": meta.loc[calc.index, "period_end"].values,
            "value": calc.values, "currency": meta.loc[calc.index, "currency"].values,
            "source": label, "filing": meta.loc[calc.index, "filing"].values, "method": "derived",
            "match": "derived", "match_note": label})],
            ignore_index=True)

    for target, a, b, label in DERIVATIONS:
        derive(target, a, b, label)
    for target, src, match, label in FALLBACKS:
        have = set(df.loc[(df["item"] == target) & df["value"].notna(), "year"])
        add = df[(df["item"] == src) & ~df["year"].isin(have) & df["value"].notna()].copy()
        if not add.empty:
            add["item"], add["match"], add["match_note"] = target, match, label
            df = pd.concat([df[~((df["item"] == target) & df["year"].isin(add["year"]))], add], ignore_index=True)
    order = {it.key: i for i, it in enumerate(ITEMS)}
    return df.sort_values(["year"]).sort_values("item", key=lambda s: s.map(order), kind="stable")


def checks(df: pd.DataFrame) -> pd.DataFrame:
    """매핑 결과 검증. 실패 = 원본 공시가 이상하거나, 매핑이 잘못됐을 가능성.
    아래 key 로 항목을 정의하면 해당 검증이 자동으로 켜진다 (없으면 건너뜀):
      total_assets, total_liabilities, equity_total  → 자산 = 부채 + 자본
      revenue, cost_of_sales, gross_profit           → 매출 − 매출원가 = 매출총이익, 매출 ≥ 매출총이익
      current_assets, cash                           → 유동자산 ≤ 자산총계, 현금 ≤ 유동자산
      eps_basic, net_income_parent                   → EPS와 지배순이익 부호 일치
    """
    if df.empty:
        return pd.DataFrame(columns=["year", "check", "ok", "detail"])
    w = df.pivot_table(index="year", columns="item", values="value", aggfunc="first")
    g = lambda k: w[k] if k in w else pd.Series(float("nan"), index=w.index)  # noqa: E731
    rows = []

    def add(name, ok, detail):
        for y in w.index:
            if pd.notna(ok.get(y)):
                rows.append({"year": y, "check": name, "ok": bool(ok[y]), "detail": detail.get(y, "")})

    a, l, e = g("total_assets"), g("total_liabilities"), g("equity_total")
    gap = (a - (l + e)) / a
    add("자산 = 부채 + 자본", gap.abs().lt(0.005).where(gap.notna()), gap.map(lambda v: f"차이 {v:.2%}"))
    add("매출 ≥ 매출총이익", (g("revenue") >= g("gross_profit")).where(g("revenue").notna() & g("gross_profit").notna()), {})
    gp = (g("revenue") - g("cost_of_sales") - g("gross_profit")) / g("revenue")
    add("매출 − 매출원가 = 매출총이익", gp.abs().lt(0.01).where(gp.notna()), gp.map(lambda v: f"차이 {v:.2%}"))
    add("유동자산 ≤ 자산총계", (g("current_assets") <= a).where(g("current_assets").notna() & a.notna()), {})
    add("현금 ≤ 유동자산", (g("cash") <= g("current_assets")).where(g("cash").notna() & g("current_assets").notna()), {})
    s1, s2 = g("eps_basic"), g("net_income_parent")
    add("EPS와 지배순이익 부호 일치", ((s1 >= 0) == (s2 >= 0)).where(s1.notna() & s2.notna()), {})
    return pd.DataFrame(rows, columns=["year", "check", "ok", "detail"])


def is_financial(company: dict) -> bool:
    p = company.get("profile") or {}
    if company["market"] == "KR":
        return str(p.get("induty_code", "")).startswith(("64", "65", "66"))
    try:
        return 6000 <= int(p.get("sic") or 0) <= 6799
    except ValueError:
        return False


def standardize(company_id: str) -> pd.DataFrame:
    """표준 항목 (long 형식): item, year, period_end, value, currency, source, filing, method"""
    df = _kr(company_id) if company_id.startswith("KR:") else _us(company_id)
    if df.empty:
        return df
    return _finalize(df).reset_index(drop=True)


def wide(df: pd.DataFrame, values: str = "value") -> pd.DataFrame:
    """[표준항목 × 연도] 표. values='match' 면 일치 수준 표."""
    t = df.pivot_table(index="item", columns="year", values=values, aggfunc="first")
    t = t.reindex([i.key for i in ITEMS if i.key in t.index])
    t.index = [ITEM_BY_KEY[k].name for k in t.index]
    return t


def match_summary(df: pd.DataFrame) -> pd.DataFrame:
    """항목별 일치 수준 집계 + 정의가 다른 경우의 설명."""
    s = df.groupby(["item", "match"]).agg(years=("year", lambda y: ", ".join(map(str, sorted(y)))),
                                          note=("match_note", "first")).reset_index()
    s = s[s["match"] != "exact"]
    s["item"] = s["item"].map(lambda k: ITEM_BY_KEY[k].name)
    s["match"] = s["match"].map(MATCH_LABEL)
    return s.rename(columns={"item": "항목", "match": "일치 수준", "years": "연도", "note": "내용"})
