"""
历史存档管理
============
- 每日扫描结果按日期存档到 data/history/YYYY-MM-DD_scan.json
- 每日实际操作按日期存档到 data/history/YYYY-MM-DD_trades.json
- 永久保留，支持任意日期回查
- 提供 list_history / load_day / load_range 接口
"""
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta

HISTORY_DIR = Path("data/history")


def ensure_dir():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def archive_today_scan(advices_data):
    """把当天扫描结果存档（带日期文件名，永久保留）"""
    ensure_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    # 从 advices_data 取 scan_time 推断日期
    scan_time = advices_data.get("scan_time", "")
    if scan_time:
        try:
            today = scan_time[:10]
        except:
            pass
    # 存两份：latest + 带日期
    latest_path = HISTORY_DIR / "latest_scan.json"
    dated_path = HISTORY_DIR / f"{today}_scan.json"
    for p in (latest_path, dated_path):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(advices_data, f, ensure_ascii=False, indent=1)
    return dated_path


def archive_day_trades(date_str, trades_list):
    """存档当天实际操作（手动录入或 OCR 识别）"""
    ensure_dir()
    path = HISTORY_DIR / f"{date_str}_trades.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "record_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trades": trades_list,
        }, f, ensure_ascii=False, indent=1)
    return path


def list_history(days=10):
    """列出最近 N 天的历史记录（扫描 + 操作）"""
    ensure_dir()
    result = []
    today = datetime.now().date()
    for i in range(days):
        d = today - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        scan_path = HISTORY_DIR / f"{ds}_scan.json"
        trades_path = HISTORY_DIR / f"{ds}_trades.json"
        entry = {
            "date": ds,
            "weekday": ["一","二","三","四","五","六","日"][d.weekday()],
            "has_scan": scan_path.exists(),
            "has_trades": trades_path.exists(),
            "scan_count": 0,
            "trade_count": 0,
        }
        if scan_path.exists():
            try:
                with open(scan_path, encoding="utf-8") as f:
                    s = json.load(f)
                entry["scan_count"] = len(s.get("advices", []))
                entry["scan_time"] = s.get("scan_time", "")
            except: pass
        if trades_path.exists():
            try:
                with open(trades_path, encoding="utf-8") as f:
                    t = json.load(f)
                entry["trade_count"] = len(t.get("trades", []))
            except: pass
        result.append(entry)
    return result


def list_all_history():
    """列出所有有记录的日期（不限于 10 天）"""
    ensure_dir()
    dates = set()
    for p in HISTORY_DIR.glob("*_scan.json"):
        dates.add(p.name[:10])
    for p in HISTORY_DIR.glob("*_trades.json"):
        dates.add(p.name[:10])
    return sorted(dates, reverse=True)


def load_day(date_str):
    """加载某天的扫描 + 操作"""
    ensure_dir()
    scan_path = HISTORY_DIR / f"{date_str}_scan.json"
    trades_path = HISTORY_DIR / f"{date_str}_trades.json"
    result = {"date": date_str, "scan": None, "trades": None}
    if scan_path.exists():
        with open(scan_path, encoding="utf-8") as f:
            result["scan"] = json.load(f)
    if trades_path.exists():
        with open(trades_path, encoding="utf-8") as f:
            result["trades"] = json.load(f)
    return result


def load_range(start_date, end_date):
    """加载日期范围内的所有记录"""
    ensure_dir()
    result = []
    d = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    while d <= end:
        ds = d.strftime("%Y-%m-%d")
        r = load_day(ds)
        if r["scan"] or r["trades"]:
            result.append(r)
        d += timedelta(days=1)
    return result


def review_day(date_str):
    """某天的"建议 vs 实际"复盘对比"""
    data = load_day(date_str)
    scan = data.get("scan", {})
    actual = data.get("trades", {})
    advices = scan.get("advices", []) if scan else []
    trades = actual.get("trades", []) if actual else []

    # 按标的匹配
    advice_by_name = {}
    for a in advices:
        advice_by_name.setdefault(a["name"], []).append(a)
    trade_by_name = {}
    for t in trades:
        trade_by_name.setdefault(t.get("name", ""), []).append(t)

    all_names = set(advice_by_name.keys()) | set(trade_by_name.keys())
    comparisons = []
    for name in all_names:
        adv = advice_by_name.get(name, [])
        trd = trade_by_name.get(name, [])
        # 建议动作
        adv_action = adv[0]["action"] if adv else "—"
        # 实际操作
        actual_action = "未操作"
        actual_pnl = 0
        actual_qty = 0
        followed_plan = False
        if trd:
            actions = [t.get("action", "") for t in trd]
            if any("买" in a for a in actions):
                actual_action = "买入"
            if any("卖" in a for a in actions):
                actual_action = "卖出" if actual_action == "买入" else "卖出"
            actual_qty = sum(int(t.get("qty", 0) or 0) for t in trd)
            actual_pnl = sum(float(t.get("pnl", 0) or 0) for t in trd)
            followed_plan = bool(adv)  # 简化：有建议且操作了算跟计划
        comparisons.append({
            "name": name,
            "advice_action": adv_action,
            "advice_pos": adv[0].get("pos_pct", 0) if adv else 0,
            "advice_stop": adv[0].get("stop_pct", 0) if adv else 0,
            "actual_action": actual_action,
            "actual_qty": actual_qty,
            "actual_pnl": actual_pnl,
            "followed_plan": followed_plan,
            "had_advice": bool(adv),
        })
    # 统计
    n_with_advice = sum(1 for c in comparisons if c["had_advice"])
    n_followed = sum(1 for c in comparisons if c["followed_plan"])
    n_off_plan = len([c for c in comparisons if not c["had_advice"] and c["actual_action"] != "未操作"])
    total_pnl = sum(c["actual_pnl"] for c in comparisons)
    return {
        "date": date_str,
        "comparisons": comparisons,
        "stats": {
            "advice_count": n_with_advice,
            "followed": n_followed,
            "off_plan": n_off_plan,
            "total_pnl": total_pnl,
        },
    }


if __name__ == "__main__":
    # 把当前 advices.json 存档
    adv_path = Path("data/advices.json")
    if adv_path.exists():
        with open(adv_path, encoding="utf-8") as f:
            data = json.load(f)
        p = archive_today_scan(data)
        print(f"✅ 已存档: {p}")
    # 列出历史
    print("\n最近 10 天历史:")
    for h in list_history(10):
        print(f"  {h['date']} 周{h['weekday']}  扫描:{h['scan_count']}只  操作:{h['trade_count']}笔")
    print("\n所有有记录的日期:")
    for d in list_all_history():
        print(f"  {d}")
