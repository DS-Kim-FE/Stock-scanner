# ============================================================
# 스캐너 패치 (기존 app 파일에 아래 블록을 순서대로 반영)
#  0. import 줄 교체
#  1. get_price_data 마지막 return 교체
#  2. 상수/헬퍼/지수 데이터/get_market_trend 추가·교체
#  3. calc_relative_strength 추가
#  4. calc_signal_score 전체 교체
#  5. classify_cloud_status 추가 + analyze_stock 전체 교체
#  6. COLUMNS / 스타일 / 사이드바 / 작업 스레드 / 시작 버튼 부분 교체 (맨 아래 주석 참고)
# ============================================================
import time
import numpy as np
import pandas as pd
import requests
from datetime import datetime, date, timedelta, timezone   # [0] 기존 datetime import 교체


# ------------------------------------------------------------
# [1] get_price_data 의 마지막 return 줄을 아래로 교체
#     (페이지 경계 중복 날짜 제거)
# ------------------------------------------------------------
#   return (full_df.dropna(subset=['날짜', '종가'])
#           .drop_duplicates(subset='날짜', keep='last')
#           .sort_values('날짜').reset_index(drop=True))


# ------------------------------------------------------------
# [2] 상수 / 장중 판별 / 지수 데이터 / 시장 추세
# ------------------------------------------------------------
WEEKLY_MIN_BARS = 80     # 선행스팬B(52주) + 26주 이동 = 78주 이상 필요
TREND_CAP = 5            # 추세 그룹(일목·20일선·2주양봉·삼역) 점수 상한/하한
DISP_HIGH_ATR = 4.0      # (종가-20MA)/ATR14 가 이 값 초과면 과열
DISP_LOW_ATR = -3.0      # 이 값 미만이면 과매도권
DISP_ENTRY_ATR = 2.0     # 진입준비 허용 최대 이격
DOWN_VOL_DROP = -0.03    # 하락거래량급증: 당일 -3% 이하 + 거래량 2배


def is_market_open_now():
    """한국 정규장(평일 09:00~15:30) 여부. 서버 타임존과 무관하게 UTC+9로 계산."""
    now = datetime.now(timezone.utc) + timedelta(hours=9)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 <= minutes < 15 * 60 + 30


def get_index_price_data(market, max_pages=10, page_size=60):
    """KOSPI/KOSDAQ 지수 일별 시세. 실패 시 빈 DataFrame.
    ※ 엔드포인트는 네이버 모바일 증권 기준 추정값 -> 처음 실행 시 지수 데이터가 오는지 확인 필요."""
    index_name = "KOSPI" if market == "KOSPI" else "KOSDAQ"
    dfs = []
    for page in range(1, max_pages + 1):
        url = f"https://m.stock.naver.com/api/index/{index_name}/price?pageSize={page_size}&page={page}"
        try:
            res = requests.get(url, headers=get_headers(), timeout=10, verify=False)
            if res.status_code != 200:
                break
            data = res.json()
            if not data or not isinstance(data, list):
                break
            dfs.append(pd.DataFrame(data))
            time.sleep(0.05)
        except Exception:
            break
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True).rename(columns={
        'localTradedAt': '날짜', 'closePrice': '종가'})
    if '날짜' not in df.columns or '종가' not in df.columns:
        return pd.DataFrame()
    df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
    df['종가'] = pd.to_numeric(df['종가'].astype(str).str.replace(',', ''), errors='coerce')
    return (df.dropna(subset=['날짜', '종가'])[['날짜', '종가']]
            .drop_duplicates(subset='날짜', keep='last')
            .sort_values('날짜').reset_index(drop=True))


def get_market_trend(market, index_df=None):
    """기존 get_market_trend 교체. 종목용 엔드포인트 대신 지수 전용 데이터를 사용."""
    index_name = "코스피" if market == "KOSPI" else "코스닥"
    df = index_df if index_df is not None else get_index_price_data(market, max_pages=3)
    if df is None or len(df) < 60:
        return f"{index_name} 추세: 데이터 부족 (지수 API 확인 필요)"
    close = df['종가']
    current = close.iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    change_20 = (current / close.iloc[-21] - 1) * 100
    if current > ma20 and ma20 > ma60:
        status = "상승 추세"
    elif current < ma20 and ma20 < ma60:
        status = "하락 추세"
    else:
        status = "혼조/횡보"
    return f"{index_name} 추세: {status} | 현재가 {current:,.0f} | 20일 {change_20:+.1f}%"


# ------------------------------------------------------------
# [3] 상대강도 (지수 대비)
# ------------------------------------------------------------
def calc_relative_strength(price_df, index_df, lookback=60):
    """RS = 종목 종가 / 지수 종가. 최근 lookback일 초과수익률 + RS선 방향으로 판정.
    반환: (rs_level[-1/0/1], 표시문자열)"""
    if index_df is None or index_df.empty or price_df is None or price_df.empty:
        return 0, "-"
    m = pd.merge(price_df[['날짜', '종가']], index_df[['날짜', '종가']],
                 on='날짜', suffixes=('_s', '_i')).sort_values('날짜')
    if len(m) < lookback + 21:
        return 0, "-"
    rs = (m['종가_s'] / m['종가_i']).reset_index(drop=True)
    excess = (rs.iloc[-1] / rs.iloc[-1 - lookback] - 1) * 100
    rs_ma20 = rs.rolling(20).mean()
    rising = rs.iloc[-1] > rs_ma20.iloc[-1] and rs_ma20.iloc[-1] > rs_ma20.iloc[-6]
    if excess >= 5 and rising:
        return 1, f"{excess:+.1f}% 💪"
    if excess <= -5 and not rising:
        return -1, f"{excess:+.1f}% 🥶"
    return 0, f"{excess:+.1f}% ➖"


# ------------------------------------------------------------
# [4] calc_signal_score 전체 교체
# ------------------------------------------------------------
# 주봉이 구름 아래일 때 매수 계열 신호를 한 단계씩 낮춘다.
WEEKLY_BEAR_DOWNGRADE = {
    "🎯 매집후돌파": "📈 매수관심",
    "🔥 적극매수": "📈 매수관심",
    "📈 매수관심": "🌱 진입준비",
    "🌱 진입준비": "🔄 바닥탐색",
}


def calc_signal_score(last, prev, ichimoku_status, w_ichimoku_status,
                      cci_now, cci_prev, weekly_two_bullish=False,
                      ma20_breakout=False, dual_cloud_breakout=False,
                      accum_level=0, triple_bull=False, triple_bear=False,
                      rs_level=0):
    detail = {}

    # 1. 일목 (일봉)
    if '상향돌파' in ichimoku_status: s_ichi = 3
    elif '하향이탈' in ichimoku_status: s_ichi = -3
    elif '상승진입' in ichimoku_status: s_ichi = 1
    elif '하락진입' in ichimoku_status: s_ichi = -2
    else: s_ichi = 0
    detail['구름대(일)'] = s_ichi

    # 2. 일목 (주봉)
    if '상향돌파' in w_ichimoku_status: s_w_ichi = 4
    elif '하향이탈' in w_ichimoku_status: s_w_ichi = -4
    elif '구름대 위' in w_ichimoku_status: s_w_ichi = 2
    elif '구름대 아래' in w_ichimoku_status: s_w_ichi = -2
    elif '상승진입' in w_ichimoku_status: s_w_ichi = 1
    elif '하락진입' in w_ichimoku_status: s_w_ichi = -2
    else: s_w_ichi = 0
    detail['구름대(주)'] = s_w_ichi

    # 3. MACD (주) + CCI (보조)
    hist_now, hist_prev = last['MACD_hist'], prev['MACD_hist']
    macd_slope = hist_now - hist_prev
    if hist_now > 0 and hist_prev <= 0: s_macd = 2
    elif hist_now < 0 and hist_prev >= 0: s_macd = -2
    elif hist_now < 0 and macd_slope > 0: s_macd = 1
    elif hist_now > 0 and macd_slope < 0: s_macd = -1
    else: s_macd = 0

    if cci_prev < -100 and cci_now >= -100: s_cci = 2
    elif cci_prev < 0 and cci_now >= 0: s_cci = 1
    elif cci_prev > 0 and cci_now <= 0: s_cci = -1
    elif cci_prev > 100 and cci_now <= 100: s_cci = -2
    else: s_cci = 0

    s_momentum = s_macd if s_macd != 0 else s_cci
    detail['모멘텀'] = s_momentum

    # 4. 구름대 상태 플래그 (판정은 일봉 기준, 주봉은 상위 필터로 별도 사용)
    d_above = '구름대 위' in ichimoku_status or '상향돌파' in ichimoku_status
    d_below = '구름대 아래' in ichimoku_status or '하향이탈' in ichimoku_status
    w_bear = '구름대 아래' in w_ichimoku_status or '하향이탈' in w_ichimoku_status
    is_falling_entry = ('하락진입' in ichimoku_status) or ('하락진입' in w_ichimoku_status)

    cloud_breakout = '상향돌파' in ichimoku_status or '상향돌파' in w_ichimoku_status
    cloud_breakdown = '하향이탈' in ichimoku_status or '하향이탈' in w_ichimoku_status
    momentum_up = s_momentum >= 1
    momentum_down = s_momentum <= -1
    has_turn = cloud_breakout or cloud_breakdown or momentum_up or momentum_down

    # 5. 거래량 위험: 거래량 2배 + 당일 -3% 이하일 때만
    vol_ratio = last['vol_ratio'] if not pd.isna(last['vol_ratio']) else 1.0
    pct_chg = (last['종가'] / prev['종가'] - 1) if prev['종가'] else 0.0
    down_volume_surge = pct_chg <= DOWN_VOL_DROP and vol_ratio >= 2.0
    low_volume_breakout = cloud_breakout and vol_ratio < 1.0
    s_vol = -2 if down_volume_surge else 0
    detail['거래량위험'] = s_vol

    # 6. 추세 그룹: 서로 상관 높은 항목은 합산 후 상한(캡)을 둔다.
    s_2w = 1 if weekly_two_bullish else 0
    s_ma20 = 1 if ma20_breakout else 0
    s_triple = 1 if triple_bull else (-1 if triple_bear else 0)
    trend_raw = s_ichi + s_w_ichi + s_2w + s_ma20 + s_triple
    trend_score = max(-TREND_CAP, min(TREND_CAP, trend_raw))
    detail['2주양봉'] = s_2w
    detail['20일선돌파'] = s_ma20
    detail['삼역'] = s_triple
    detail['추세그룹(캡적용)'] = trend_score

    # 7. 매집 / 상대강도
    s_accum = {2: 2, 1: 1, -1: -2}.get(accum_level, 0)
    detail['매집'] = s_accum
    s_rs = rs_level  # -1 / 0 / +1
    detail['RS'] = s_rs

    score = trend_score + s_momentum + s_vol + s_accum + s_rs

    is_distributing = accum_level == -1
    accum_breakout = accum_level == 2 and (cloud_breakout or ma20_breakout)

    # 8. 이격: ATR 정규화 (ATR 없으면 기존 % 기준으로 대체)
    atr = last.get('ATR14', np.nan)
    disparity_pct = ((last['종가'] / last['20MA']) - 1) * 100 if last['20MA'] > 0 else 0
    if pd.notna(atr) and atr > 0:
        disp_atr = (last['종가'] - last['20MA']) / atr
        is_high_disp = disp_atr > DISP_HIGH_ATR
        is_low_disp = disp_atr < DISP_LOW_ATR
        entry_disp_ok = disp_atr <= DISP_ENTRY_ATR
    else:
        is_high_disp = disparity_pct > 15
        is_low_disp = disparity_pct < -10
        entry_disp_ok = disparity_pct <= 6
    is_weekly_breakout = '상향돌파' in w_ichimoku_status

    # 9. 신호 결정 (우선순위 순)
    if down_volume_surge: signal = "🚨 하락거래량급증"
    elif is_distributing and momentum_down: signal = "🚨 분산의심"
    elif low_volume_breakout: signal = "⚠️ 거래량없는돌파"
    elif is_falling_entry: signal = "⚠️ 구름대주의"
    elif accum_breakout and momentum_up: signal = "🎯 매집후돌파"
    elif (dual_cloud_breakout and weekly_two_bullish and ma20_breakout
          and vol_ratio >= 1.0): signal = "🔥 양·주봉 동시돌파"
    elif is_weekly_breakout and momentum_up: signal = "🚀 주간돌파!"
    elif score >= 5 and cloud_breakout and momentum_up: signal = "🔥 적극매수"
    elif score >= 3 and not is_high_disp and (cloud_breakout or momentum_up): signal = "📈 매수관심"
    elif accum_level == 2 and not is_high_disp and score >= 1: signal = "🧺 매집진행"
    elif score >= 1 and entry_disp_ok and has_turn and not is_falling_entry: signal = "🌱 진입준비"
    elif d_below and momentum_up and score >= 0: signal = "🔄 바닥탐색"
    elif d_below and momentum_down: signal = "🔻 하락가속"
    elif score <= -5 and cloud_breakdown and momentum_down: signal = "🧊 적극매도"
    elif score <= -3: signal = "📉 매도관심"
    elif d_below and is_low_disp: signal = "🔽 추세하락"
    elif d_above and is_high_disp: signal = "🔼 추세상승"
    elif d_above and not has_turn: signal = "🛡️ 홀딩유지"
    elif '내부' in ichimoku_status or '내부' in w_ichimoku_status: signal = "🌫️ 구름대내부"
    else: signal = "⏸️ 관망"

    # 10. 주봉 상위 필터: 주봉이 구름 아래면 매수 계열을 한 단계 낮춘다.
    if w_bear:
        signal = WEEKLY_BEAR_DOWNGRADE.get(signal, signal)

    return score, signal, detail


# ------------------------------------------------------------
# [5] 구름대 상태 판정 공통 함수 + analyze_stock 전체 교체
# ------------------------------------------------------------
def classify_cloud_status(frame, now_label, unit):
    """일봉/주봉 공통. frame에 종가, senkou_a, senkou_b 필요."""
    last = frame.iloc[-1]
    top_now = max(last['senkou_a'], last['senkou_b'])
    bot_now = min(last['senkou_a'], last['senkou_b'])
    price = last['종가']
    if price > top_now:
        up = find_recent_cloud_cross(frame, "up")
        if up is None:
            return "📈 구름대 위"
        age = now_label if up == 0 else f"{up}{unit}전"
        return f"🔥 상향돌파({age})"
    if price < bot_now:
        down = find_recent_cloud_cross(frame, "down")
        if down is None:
            return "📉 구름대 아래"
        age = now_label if down == 0 else f"{down}{unit}전"
        return f"🧊 하향이탈({age})"
    prior = frame.iloc[-5:-1]
    p_top = prior[['senkou_a', 'senkou_b']].max(axis=1)
    p_bot = prior[['senkou_a', 'senkou_b']].min(axis=1)
    was_above = bool((prior['종가'] > p_top).any())
    was_below = bool((prior['종가'] < p_bot).any())
    if was_above and not was_below: return "⚠️ 구름대하락진입"
    if was_below and not was_above: return "🌱 구름대상승진입"
    return "🌫️ 구름대 내부"


def analyze_stock(code, name, current_change, drop_last=False, index_df=None):
    """drop_last=True: 장중 분석용. 마지막 일봉(미완성)과 미완성 주봉을 제외한다."""
    try:
        df_price = get_price_data(code, max_pages=10, page_size=60)
        if df_price is None or len(df_price) < 80:
            return None
        if drop_last:
            df_price = df_price.iloc[:-1].reset_index(drop=True)
            if len(df_price) < 80:
                return None

        # ─── 1. 일봉 지표 ───
        df = df_price.set_index('날짜').copy()
        df['5MA'] = df['종가'].rolling(5).mean()
        df['20MA'] = df['종가'].rolling(20).mean()
        df['60MA'] = df['종가'].rolling(60).mean()

        high_9, low_9 = df['고가'].rolling(9).max(), df['저가'].rolling(9).min()
        df['tenkan_sen'] = (high_9 + low_9) / 2
        high_26, low_26 = df['고가'].rolling(26).max(), df['저가'].rolling(26).min()
        df['kijun_sen'] = (high_26 + low_26) / 2
        high_52, low_52 = df['고가'].rolling(52).max(), df['저가'].rolling(52).min()
        df['senkou_b_base'] = (high_52 + low_52) / 2

        # 삼역호전용: 전환선/기준선, 후행스팬(현재 종가 vs 26일 전 종가)
        df['tk_gt_kj'] = df['tenkan_sen'] > df['kijun_sen']
        df['chikou_up'] = df['종가'] > df['종가'].shift(26)
        df['chikou_down'] = df['종가'] < df['종가'].shift(26)

        ema12 = df['종가'].ewm(span=12, adjust=False).mean()
        ema26 = df['종가'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_Signal']

        df['CCI'] = calc_cci(df)
        df['vol_ratio'] = df['거래량'] / df['거래량'].rolling(20).mean()

        vol_sum20 = df['거래량'].rolling(20).sum()
        df['vol_surge20'] = vol_sum20 / vol_sum20.shift(20).replace(0, np.nan)
        df['chg20'] = df['종가'] / df['종가'].shift(20) - 1
        low20 = df['저가'].rolling(20).min()
        df['box20'] = (df['고가'].rolling(20).max() - low20) / low20.replace(0, np.nan)

        true_range = pd.concat([
            df['고가'] - df['저가'],
            (df['고가'] - df['종가'].shift(1)).abs(),
            (df['저가'] - df['종가'].shift(1)).abs()
        ], axis=1).max(axis=1)
        df['ATR14'] = true_range.rolling(14).mean()

        df_future = pd.DataFrame(index=df.index)
        df_future['senkou_a'] = (df['tenkan_sen'] + df['kijun_sen']) / 2
        df_future['senkou_b'] = df['senkou_b_base']
        df_future = df_future.shift(26)

        df_merged = pd.merge(df, df_future, left_index=True, right_index=True, how='left')
        df_final = df_merged.dropna(subset=['senkou_a', 'senkou_b', 'CCI']).copy()
        if len(df_final) < 6:
            return None

        last, prev = df_final.iloc[-1], df_final.iloc[-2]
        ichimoku_status = classify_cloud_status(df_final, "당일", "일")

        cloud_top_now = max(last['senkou_a'], last['senkou_b'])
        cloud_bot_now = min(last['senkou_a'], last['senkou_b'])
        triple_bull = bool(last['종가'] > cloud_top_now and last['tk_gt_kj'] and last['chikou_up'])
        triple_bear = bool(last['종가'] < cloud_bot_now and (not last['tk_gt_kj']) and last['chikou_down'])
        sam_display = "✅호전" if triple_bull else "❌역전" if triple_bear else "-"

        # ─── 2. 주봉 ───
        w_ichimoku_status = "-"
        weekly_two_bullish = False

        df_w = df_price.resample('W', on='날짜').agg({
            '시가': 'first', '종가': 'last', '고가': 'max', '저가': 'min', '거래량': 'sum'
        }).dropna()

        # 마지막 일봉이 금요일 이전이면 이번 주 주봉은 미완성
        last_date = df_price['날짜'].iloc[-1]
        partial_week_present = last_date.weekday() < 4
        if partial_week_present and drop_last and len(df_w) > 0:
            df_w = df_w.iloc[:-1]
            partial_week_present = False

        if len(df_w) >= WEEKLY_MIN_BARS:
            w_high_9, w_low_9 = df_w['고가'].rolling(9).max(), df_w['저가'].rolling(9).min()
            df_w['tenkan_sen'] = (w_high_9 + w_low_9) / 2
            w_high_26, w_low_26 = df_w['고가'].rolling(26).max(), df_w['저가'].rolling(26).min()
            df_w['kijun_sen'] = (w_high_26 + w_low_26) / 2
            w_high_52, w_low_52 = df_w['고가'].rolling(52).max(), df_w['저가'].rolling(52).min()
            df_w['senkou_b_base'] = (w_high_52 + w_low_52) / 2

            df_w_future = pd.DataFrame(index=df_w.index)
            df_w_future['senkou_a'] = (df_w['tenkan_sen'] + df_w['kijun_sen']) / 2
            df_w_future['senkou_b'] = df_w['senkou_b_base']
            df_w_future = df_w_future.shift(26)

            df_w_merged = pd.merge(df_w, df_w_future, left_index=True, right_index=True, how='left')
            df_w_final = df_w_merged.dropna(subset=['senkou_a', 'senkou_b']).copy()

            if len(df_w_final) >= 5:
                # 2주 연속 양봉은 '완성된' 주봉만 사용
                completed = df_w_final.iloc[:-1] if partial_week_present else df_w_final
                if len(completed) >= 2:
                    c1, c2 = completed.iloc[-1], completed.iloc[-2]
                    weekly_two_bullish = bool(c1['종가'] > c1['시가'] and c2['종가'] > c2['시가'])
                w_label = "직전주" if drop_last else "이번주"
                w_ichimoku_status = classify_cloud_status(df_w_final, w_label, "주")
            else:
                w_ichimoku_status = "데이터부족"
        else:
            w_ichimoku_status = "데이터부족"

        # ─── 3. 기타 보조지표 ───
        def ma_cross(l, p, ma_col):
            if p['종가'] <= p[ma_col] and l['종가'] > l[ma_col]: return "🔥GC"
            if p['종가'] >= p[ma_col] and l['종가'] < l[ma_col]: return "🧊DC"
            return "📈↑" if l['종가'] > l[ma_col] else "📉↓"

        ma_text = f"5:{ma_cross(last, prev, '5MA')} 20:{ma_cross(last, prev, '20MA')} 60:{ma_cross(last, prev, '60MA')}"

        cci_now, cci_prev = last['CCI'], prev['CCI']
        cci_val = round(cci_now, 1)
        if cci_prev < -100 and cci_now >= -100: cci_display = f"{cci_val} 🟢과매도탈출"
        elif cci_prev < 0 and cci_now >= 0: cci_display = f"{cci_val} 🔵제로크로스"
        elif cci_prev > 100 and cci_now <= 100: cci_display = f"{cci_val} 🟡과매수탈출"
        elif cci_prev > 0 and cci_now <= 0: cci_display = f"{cci_val} 🔴제로데드"
        elif cci_now > 100: cci_display = f"{cci_val} ⚡과매수"
        elif cci_now < -100: cci_display = f"{cci_val} 💧과매도"
        else: cci_display = f"{cci_val} ➖중립"

        vol_r = round(last['vol_ratio'], 1) if not pd.isna(last['vol_ratio']) else 1.0
        vol_display = f"{vol_r}배 📈" if vol_r >= 2.0 else f"{vol_r}배 📉" if vol_r < 0.5 else f"{vol_r}배"

        disparity = ((last['종가'] / last['20MA']) - 1) * 100 if last['20MA'] > 0 else 0
        disparity_fmt = f"{'+' if disparity >= 0 else ''}{round(disparity, 2)}%"

        ma20_breakout = prev['종가'] <= prev['20MA'] and last['종가'] > last['20MA']
        dual_cloud_breakout = ('상향돌파' in ichimoku_status and '상향돌파' in w_ichimoku_status)

        accum_level, accum_display = calc_accumulation(last)
        rs_level, rs_display = calc_relative_strength(df_price, index_df)

        score, signal, detail = calc_signal_score(
            last, prev, ichimoku_status, w_ichimoku_status, cci_now, cci_prev,
            weekly_two_bullish, ma20_breakout, dual_cloud_breakout, accum_level,
            triple_bull, triple_bear, rs_level
        )
        chart_url = f"https://stock.naver.com/fchart/domestic/stock/{code}"

        # COLUMNS 순서와 반드시 일치해야 함
        return [
            code, name, current_change,
            int(last['종가']), disparity_fmt,
            score, signal,
            ichimoku_status, w_ichimoku_status, sam_display, ma_text,
            cci_display, vol_display, accum_display, rs_display,
            chart_url
        ]
    except Exception:
        return None


# ------------------------------------------------------------
# [6] UI / 나머지 부분 수정 (기존 코드에서 해당 부분만 교체)
# ------------------------------------------------------------
# (a) COLUMNS 교체
# COLUMNS = ['코드', '종목명', '등락률', '현재가', '이격률',
#            '총점', '신호',
#            '일목(일봉)', '일목(주봉)', '삼역', 'MA크로스',
#            'CCI', '거래량', '매집(20일)', 'RS(60일)',
#            '차트']
#
# (b) 스타일 함수 추가
# def style_rs(val):
#     v = str(val)
#     if '💪' in v: return 'color:#c62828;font-weight:bold'
#     if '🥶' in v: return 'color:#1565c0;font-weight:bold'
#     return 'color:#9e9e9e'
#
# def style_sam(val):
#     v = str(val)
#     if '호전' in v: return 'color:white;background-color:#c62828;font-weight:bold'
#     if '역전' in v: return 'color:white;background-color:#1565c0;font-weight:bold'
#     return 'color:#9e9e9e'
#
# (c) show_styled_dataframe 안의 두 곳(editor_styler 쪽, styled 쪽)에 각각 추가
#     editor_styler = map_cell_style(editor_styler, style_rs, ["RS(60일)"])
#     editor_styler = map_cell_style(editor_styler, style_sam, ["삼역"])
#     ...
#     styled = map_cell_style(styled, style_rs, ['RS(60일)'])
#     styled = map_cell_style(styled, style_sam, ['삼역'])
#
# (d) 사이드바: start_btn 줄 바로 위에 추가
# exclude_last_bar = st.sidebar.checkbox(
#     "마지막 봉 제외 (장중 분석)",
#     value=is_market_open_now(),
#     help="장중에는 오늘 일봉과 이번 주 주봉이 미완성이므로 제외하고 분석합니다. 장 마감 후에는 해제하세요.",
# )
#
# (e) run_stock_analysis_job 시그니처와 호출부 교체
# def run_stock_analysis_job(job_id, stock_records, job_store, drop_last=False, index_df=None):
#     ...
#             result = analyze_stock(stock["종목코드"], stock["종목명"], stock["등락률"],
#                                    drop_last, index_df)
#
# (f) if start_btn: 블록 안
#     index_df = get_index_price_data(market)                      # 추가
#     st.session_state['market_trend'] = get_market_trend(market, index_df)   # 교체
#     if index_df.empty:
#         st.sidebar.warning("지수 데이터를 못 가져와 RS는 '-'로 표시됩니다.")
#     ...
#     worker = threading.Thread(
#         target=run_stock_analysis_job,
#         args=(job_id, stock_records, ANALYSIS_JOB_STORE, exclude_last_bar, index_df),
#         daemon=True)
