"""
Streamlit 看板 v2（含历史 + 复盘）
=================================
运行：streamlit run dashboard/app.py --server.port 8501
功能：
  - 当天候选池（可筛选/排序）
  - 历史日期选择 + 加载
  - 建议 vs 实际复盘对比
  - 风控状态面板
"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="股票投资模型", page_icon="📈", layout="wide")
BASE = Path(".")

@st.cache_data(ttl=60)
def load_rules():
    p = BASE / "screener/rules.json"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}

@st.cache_data(ttl=60)
def load_day(date_str):
    import importlib.util
    spec = importlib.util.spec_from_file_location("history", BASE / "screener/history.py")
    hist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hist)
    return hist.load_day(date_str)

@st.cache_data(ttl=60)
def list_history(days=30):
    import importlib.util
    spec = importlib.util.spec_from_file_location("history", BASE / "screener/history.py")
    hist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hist)
    return hist.list_history(days)

def main():
    st.title("📈 股票投资模型 · 看板")
    rules = load_rules()

    # 日期选择
    history = list_history(30)
    date_options = [h["date"] for h in history]
    today = datetime.now().strftime("%Y-%m-%d")
    default_idx = date_options.index(today) if today in date_options else 0
    sel_date = st.sidebar.selectbox("选择日期", date_options, index=default_idx)

    data = load_day(sel_date)
    scan = data.get("scan") or {}
    advices = sorted(scan.get("advices", []), key=lambda x: x.get("score", 0), reverse=True)
    trades_data = data.get("trades") or {}
    trades = trades_data.get("trades", [])

    st.caption(f"📅 {sel_date} ｜ 扫描时间：{scan.get('scan_time','—')} ｜ 今日涨停：{scan.get('total_zt','?')} 只")

    # 风控状态栏
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("单只上限", f"{rules.get('max_single_position',0):.0%}")
    c2.metric("总仓上限", f"{rules.get('max_total_position',0):.0%}")
    c3.metric("日亏熔断", f"{rules.get('daily_loss_circuit_breaker',0):.0%}")
    c4.metric("日最大笔数", rules.get("max_daily_trades", 0))
    c5.metric("候选数", len(advices))
    c6.metric("实际操作", len(trades))

    tab1, tab2, tab3 = st.tabs(["📋 系统建议", "✋ 实际操作", "📊 复盘对比"])

    # Tab 1: 系统建议
    with tab1:
        if not advices:
            st.warning("当天无扫描数据")
        else:
            df = pd.DataFrame(advices)
            industries = ["全部"] + sorted(df["industry"].unique().tolist()) if "industry" in df else ["全部"]
            c1, c2 = st.columns(2)
            sel_ind = c1.selectbox("按行业筛选", industries)
            min_score = c2.slider("最低评分", 0.0, 1.0, 0.0, 0.01)
            dff = df.copy()
            if sel_ind != "全部" and "industry" in dff:
                dff = dff[dff["industry"] == sel_ind]
            dff = dff[dff["score"] >= min_score].sort_values("score", ascending=False)
            show_cols = [c for c in ["name","code","path","zt_count","industry","industry_heat","seal_money","score","change_pct","pos_pct","stop_pct","target_pct"] if c in dff.columns]
            st.dataframe(dff[show_cols], use_container_width=True, height=350)
            for i, (_, r) in enumerate(dff.iterrows(), 1):
                with st.expander(f"{i}. {r['name']}（{r['code']}）— 评分 {r['score']:.3f}"):
                    st.write(f"**仓位** {int(r.get('pos_pct',0)*100)}% ｜ **止损** {int(r.get('stop_pct',-8)*100)}% ｜ **目标** +{int(r.get('target_pct',15)*100)}% ｜ **持仓** {r.get('max_hold_days',10)}天")
                    for d in r.get("discipline", []):
                        st.write(f"  {d}")

    # Tab 2: 实际操作
    with tab2:
        if not trades:
            st.info(f"当天无实际操作记录。手机端可录入：http://IP:5001/record?date={sel_date}")
        else:
            tdf = pd.DataFrame(trades)
            show = [c for c in ["action","name","code","price","qty","pnl","time","reason","emotion","followed_plan"] if c in tdf.columns]
            st.dataframe(tdf[show], use_container_width=True)
            total_pnl = sum(float(t.get("pnl",0) or 0) for t in trades)
            st.metric("当日总盈亏", f"{total_pnl:+.2f}")

    # Tab 3: 复盘
    with tab3:
        import importlib.util
        spec = importlib.util.spec_from_file_location("history", BASE / "screener/history.py")
        hist = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hist)
        r = hist.review_day(sel_date)
        stats = r["stats"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("建议数", stats["advice_count"])
        c2.metric("跟计划", stats["followed"])
        c3.metric("计划外", stats["off_plan"])
        c4.metric("总盈亏", f"{stats['total_pnl']:+.0f}")
        if r["comparisons"]:
            cdf = pd.DataFrame(r["comparisons"])
            show = [c for c in ["name","advice_action","actual_action","actual_qty","actual_pnl","followed_plan","had_advice"] if c in cdf.columns]
            st.dataframe(cdf[show], use_container_width=True)
        else:
            st.info("当天无对比数据（需同时有建议和操作记录）")

    st.divider()
    st.caption("⚠️ 系统按规则生成，仅供参考，不构成投资建议。")

if __name__ == "__main__":
    main()
