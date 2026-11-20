
# ============================================================
# 패치 B: 분석 결과가 사라지는 문제 해결
#  - 분석이 끝나면 결과를 session_state['df_all']에 저장 (지금은 저장 코드가 없음)
#  - 결과를 파일에도 저장해서, 새로고침/연결 끊김 후에도 마지막 결과를 복원
#  - 완료 후 1초마다 도는 fragment(run_every=1)를 종료
# 기존 파일에 아래 1~4번을 반영하세요.
# ============================================================
import os
from datetime import datetime
import pandas as pd
 
# ------------------------------------------------------------
# [1] 헬퍼 함수 추가 (WATCHLIST_DB_PATH 정의 근처에 두면 됨)
#     COLUMNS 는 기존 코드에서 정의된 것을 그대로 사용
# ------------------------------------------------------------
RESULT_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_scan_result.pkl")
 
 
def save_last_result(df, market_name, info):
    try:
        pd.to_pickle({"df": df, "market": market_name, "info": info}, RESULT_CACHE_PATH)
    except Exception:
        pass  # 저장 실패해도 화면 표시에는 영향 없음
 
 
def load_last_result():
    """저장된 마지막 결과. 컬럼 구성이 현재 COLUMNS와 다르면(버전 변경) 무시."""
    try:
        if not os.path.exists(RESULT_CACHE_PATH):
            return None
        saved = pd.read_pickle(RESULT_CACHE_PATH)
        df = saved.get("df")
        if df is None or df.empty or not set(COLUMNS).issubset(df.columns):
            return None
        return saved
    except Exception:
        return None
 
 
# ------------------------------------------------------------
# [2] render_analysis_progress 맨 끝의 아래 부분을 교체
#
#   (기존)
#     if done:
#         st.success(f"분석 완료: 결과 {len(snapshot['rows'])}개, 분석 실패 {snapshot['failed']}개")
#
#   (교체)
# ------------------------------------------------------------
#     if done:
#         if snapshot["rows"]:
#             finished_df = (pd.DataFrame(snapshot["rows"], columns=COLUMNS)
#                            .sort_values("총점", ascending=False).reset_index(drop=True))
#             info = (f"{market_name} · {datetime.now():%Y-%m-%d %H:%M} 분석 · "
#                     f"결과 {len(finished_df)}개 / 실패 {snapshot['failed']}개")
#             st.session_state["df_all"] = finished_df
#             st.session_state["df_all_info"] = info
#             save_last_result(finished_df, market_name, info)
#         with ANALYSIS_JOB_STORE["lock"]:
#             ANALYSIS_JOB_STORE["jobs"].pop(job_id, None)      # 메모리 정리
#         st.session_state["analysis_job_id"] = None             # fragment 종료
#         rerun_streamlit()                                      # 전체 재실행 -> 저장된 결과 화면으로 전환
 
 
# ------------------------------------------------------------
# [3] if start_btn: 블록 맨 앞(st.session_state["analysis_run_id"] = ... 위)에 추가
#     새 분석을 시작하면 이전 결과는 비운다.
# ------------------------------------------------------------
#     st.session_state.pop("df_all", None)
#     st.session_state.pop("df_all_info", None)
 
 
# ------------------------------------------------------------
# [4] active_job_id = st.session_state.get("analysis_job_id") 줄 바로 위에 추가
#     (새로고침·재접속으로 session_state 가 비었을 때 마지막 결과 복원)
# ------------------------------------------------------------
# if (not start_btn and "df_all" not in st.session_state
#         and not st.session_state.get("analysis_job_id")):
#     saved = load_last_result()
#     if saved:
#         st.session_state["df_all"] = saved["df"]
#         st.session_state["df_all_info"] = "(저장된 마지막 결과) " + saved.get("info", "")
#
# 그리고 기존 하단의 결과 표시 블록에서 result_title 줄 아래에 한 줄 추가:
#     result_title.subheader(f"🔍 결과 리스트 ({st.session_state.filter} / {len(display_df)}개)")
#     st.caption(st.session_state.get("df_all_info", ""))
 
