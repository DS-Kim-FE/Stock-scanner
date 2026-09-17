import requests
import pandas as pd
from datetime import datetime

# 헬퍼 함수는 기존 코드와 동일하게 사용
def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://finance.naver.com/'
    }

def get_market_sum_pages(page_list, market="KOSPI"):
    """
    [REVISED] Naver Finance API를 사용하여 시가총액 순위 데이터를 가져오는 함수
    """
    all_stocks = []
    # page_list는 이제 API의 'page' 파라미터로 직접 사용됩니다.
    for page in page_list:
        try:
            page_size = 50 # API가 한 페이지에 50개 종목을 반환
            url = f"https://m.stock.naver.com/api/stock/marketValue/{market}?page={page}&pageSize={page_size}"
            res = requests.get(url, headers=get_headers(), timeout=10)
            res.raise_for_status() # HTTP 에러가 발생하면 예외를 발생시킴
            data = res.json()
            
            for item in data.get('stocks', []):
                all_stocks.append({
                    '종목코드': item.get('itemCode'),
                    '종목명': item.get('stockName'),
                    '등락률': item.get('compareToPreviousClosePrice', {}).get('text')
                })
        except Exception as e:
            print(f"Error fetching market sum for page {page}: {e}")
            continue
            
    if not all_stocks:
        return pd.DataFrame()

    return pd.DataFrame(all_stocks)


def get_price_data(code, max_pages=60):
    """
    [REVISED] Naver Finance API를 사용하여 일별 시세 데이터를 가져오는 함수
    """
    dfs = []
    page_size = 10 # API가 한 페이지에 기본 10개 데이터를 반환
    
    # max_pages 만큼 API 페이지를 순회하며 데이터 수집
    for page in range(1, max_pages + 1):
        try:
            url = f"https://api.stock.naver.com/chart/basics/day/{code}?page_size={page_size}&page={page}"
            res = requests.get(url, headers=get_headers(), timeout=10)
            res.raise_for_status()
            data = res.json()
            
            if not data: # 데이터가 더 이상 없으면 중단
                break
            
            dfs.append(pd.DataFrame(data))
            
        except Exception as e:
            # 에러 발생 시 진행 상황을 잃지 않도록 중단
            break
            
    if not dfs:
        return pd.DataFrame()

    full_df = pd.concat(dfs, ignore_index=True)
    
    # 원본 코드의 컬럼명 및 데이터 타입과 호환되도록 변환
    full_df = full_df.rename(columns={
        'localDate': '날짜',
        'closePrice': '종가',
        'openPrice': '시가',
        'highPrice': '고가',
        'lowPrice': '저가',
        'accumulatedTradingVolume': '거래량'
    })
    
    full_df['날짜'] = pd.to_datetime(full_df['날짜'], format='%Y%m%d')
    
    num_cols = ['종가', '시가', '고가', '저가', '거래량']
    for col in num_cols:
        # API에서 오는 값은 이미 숫자형이므로, 쉼표 제거 로직이 필요 없을 수 있으나 호환성을 위해 유지
        full_df[col] = pd.to_numeric(full_df[col].astype(str).str.replace(',', ''), errors='coerce')
        
    return full_df[['날짜', '종가', '시가', '고가', '저가', '거래량']].sort_values('날짜').reset_index(drop=True)

