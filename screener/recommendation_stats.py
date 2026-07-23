"""
推荐后涨跌统计
==============
每天扫描后，回查 N 天前推荐的标的实际涨跌。
追踪 1/3/5/10 日后的表现，统计命中率。
"""
import json
import time
import warnings
from pathlib import Path
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

HISTORY_DIR = Path("data/history")
STATS_PATH = Path("data/recommendation_stats.json")

def get_stock_history(code, days=15):
    """获取个股近 N 天日K"""
    try:
        import akshare as ak
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days+10)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        if df is not None and len(df) > 0:
            return df
    except:
        pass
    return None

def calc_returns(df, base_idx, n_days_list=(1, 3, 5, 10)):
    """从 base_idx 那天算 N 日后涨跌"""
    base_close = df.iloc[base_idx]["收盘"]
    results = {}
    for n in n_days_list:
        target_idx = base_idx + n
        if target_idx < len(df):
            future_close = df.iloc[target_idx]["收盘"]
            results[f"{n}d"] = round((future_close - base_close) / base_close * 100, 2)
        else:
            results[f"{n}d"] = None
    return results

def update_stats():
    """更新推荐涨跌统计"""
    if not HISTORY_DIR.exists():
        print("无历史数据")
        return

    # 加载已有统计
    stats = {"records": [], "summary": {}}
    if STATS_PATH.exists():
        with open(STATS_PATH, encoding="utf-8") as f:
            stats = json.load(f)

    # 找所有有扫描记录的日期
    scan_dates = sorted(set(p.name[:10] for p in HISTORY_DIR.glob("*_scan.json") if p.name[:4].isdigit()))
    existing_dates = {r["date"] for r in stats["records"]}

    for scan_date in scan_dates:
        if scan_date in existing_dates:
            continue
        scan_path = HISTORY_DIR / f"{scan_date}_scan.json"
        with open(scan_path, encoding="utf-8") as f:
            scan = json.load(f)
        advices = scan.get("advices", [])
        if not advices:
            continue

        print(f"处理 {scan_date} 的 {len(advices)} 只推荐...")
        for a in advices[:6]:  # 只统计 Top6
            code = a.get("code", "")
            name = a.get("name", "")
            if not code:
                continue
            time.sleep(0.5)  # 限速
            df = get_stock_history(code, days=20)
            if df is None or len(df) < 2:
                continue
            # 找 scan_date 在日K中的位置
            df["日期"] = df["日期"].astype(str)
            match_idx = None
            for i, row in df.iterrows():
                if scan_date.replace("-","") in row["日期"].replace("-",""):
                    match_idx = i
                    break
            if match_idx is None:
                # 用最近的
                match_idx = len(df) - 2
            if match_idx >= len(df) - 1:
                continue
            rets = calc_returns(df, match_idx)
            stats["records"].append({
                "date": scan_date,
                "code": code,
                "name": name,
                "score": a.get("score", 0),
                "industry": a.get("industry", ""),
                "returns": rets,
                "base_price": float(df.iloc[match_idx]["收盘"]),
            })

    # 汇总
    all_recs = stats["records"]
    summary = {"total": len(all_recs), "by_period": {}}
    for period in ["1d", "3d", "5d", "10d"]:
        valid = [r for r in all_recs if r["returns"].get(period) is not None]
        if valid:
            wins = [r for r in valid if r["returns"][period] > 0]
            avg_ret = sum(r["returns"][period] for r in valid) / len(valid)
            summary["by_period"][period] = {
                "count": len(valid),
                "win_rate": round(len(wins) / len(valid) * 100, 1),
                "avg_return": round(avg_ret, 2),
            }
    stats["summary"] = summary

    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    print(f"✅ 统计已保存: {STATS_PATH}")
    print(f"   总推荐数: {summary['total']}")
    for p, s in summary["by_period"].items():
        print(f"   {p}: 胜率 {s['win_rate']}%  平均涨跌 {s['avg_return']:+.2f}%")

if __name__ == "__main__":
    update_stats()
