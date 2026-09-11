"""
네이버 증권 API 후보 테스트 스크립트
────────────────────────────────────
로컬(네이버 접속 차단 없는) 환경에서 실행하세요.
각 후보 URL을 호출해서 상태코드/응답 앞부분을 출력합니다.
어떤 게 살아있는지, 실제 JSON 필드명이 뭔지 눈으로 확인한 뒤
본 앱의 get_market_sum_pages / get_price_data / load_foreign_ratio_all 을
그에 맞게 고치면 됩니다.
"""

import requests
import json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://stock.naver.com/',
}

TEST_CODE = "005930"  # 삼성전자


def show(name, url):
    print("=" * 80)
    print(f"[{name}]")
    print(url)
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        print("status_code:", res.status_code)
        print("final url  :", res.url)
        text = res.text
        print("응답 앞부분 (최대 1000자):")
        print(text[:1000])
        try:
            data = res.json()
            print("→ JSON 파싱 성공. 최상위 타입:", type(data))
            if isinstance(data, list) and data:
                print("→ 첫 항목 키:", list(data[0].keys()) if isinstance(data[0], dict) else data[0])
            elif isinstance(data, dict):
                print("→ 최상위 키:", list(data.keys()))
        except Exception:
            print("→ JSON 파싱 실패 (HTML/XML/기타 형식일 수 있음)")
    except Exception as e:
        print("요청 실패:", e)
    print()


# ── 1) 종목 리스트 (시가총액 순위) 후보 ─────────────────────
show(
    "종목리스트 후보 1: 구 finance.naver.com (혹시 살아있는지 확인)",
    "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
)

show(
    "종목리스트 후보 2: m.stock.naver.com siseListJson",
    "https://m.stock.naver.com/api/json/sise/siseListJson.nhn?menu=market_sum&sosok=0&pageSize=20&page=1",
)

# ── 2) 개별 종목 가격(차트) 후보 ─────────────────────
show(
    "가격 후보 1: 구 fchart.naver.com XML",
    f"https://fchart.naver.com/sise.nhn?symbol={TEST_CODE}&timeframe=day&count=30&requestType=0",
)

show(
    "가격 후보 2: fchart.stock.naver.com (CSV/텍스트, 외국인소진율 포함 가능)",
    f"https://fchart.stock.naver.com/siseJson.naver?symbol={TEST_CODE}&requestType=1"
    f"&startTime=20250101&endTime=20261231&timeframe=day",
)

show(
    "가격 후보 3: m.stock.naver.com front-api 차트",
    f"https://m.stock.naver.com/front-api/external/chart/domestic/info"
    f"?symbol={TEST_CODE}&requestType=1&startTime=20250101&endTime=20261231&timeframe=day",
)

show(
    "가격 후보 4: m.stock.naver.com 일별시세",
    f"https://m.stock.naver.com/api/stock/{TEST_CODE}/price?pageSize=30&page=1",
)

# ── 3) 개별 종목 상세(외국인비율/시총 등) 후보 ─────────────────────
show(
    "상세지표 후보: m.stock.naver.com integration (foreignRate 등)",
    f"https://m.stock.naver.com/api/stock/{TEST_CODE}/integration",
)

# ── 4) 실시간 시세 폴링 API (여러 종목코드를 콤마로 묶어서 요청) ─────────
# Doni님이 브라우저 개발자도구에서 직접 찾은 후보.
# 이미 알고 있는 종목코드들의 "현재 시세"만 갱신해주는 용도로 보임 —
# 시가총액 순위(종목코드 리스트) 자체를 알려주는 API는 아닐 가능성이 큼.
TEST_CODES = "402340,012450,032830,018260,011070"
show(
    "실시간 시세 후보: polling.finance.naver.com (신규 경로)",
    f"https://polling.finance.naver.com/api/realtime/domestic/NXT/stock/{TEST_CODES}",
)
show(
    "실시간 시세 후보(구형 파라미터 방식): polling.finance.naver.com",
    f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{TEST_CODES}",
)

print("=" * 80)
print("완료. 위 결과 중 status_code 200 + JSON 파싱 성공한 것들의")
print("'첫 항목 키' / '응답 앞부분'을 보고 실제 필드명을 확인하세요.")
