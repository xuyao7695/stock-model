"""
盈亏汇总 + 月度统计
==================
基于录入的实际操作（买入/卖出），FIFO 配对计算盈亏。
按月聚合，输出月度统计 + 累计曲线。
"""
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

HISTORY_DIR = Path("data/history")
PORTFOLIO_PATH = Path("data/portfolio.json")

def load_all_trades():
    """从历史存档加载所有实际操作记录"""
    trades = []
    if not HISTORY_DIR.exists():
        return trades
    for p in sorted(HISTORY_DIR.glob("*_trades.json")):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for t in data.get("trades", []):
            t["record_date"] = data.get("date", p.name[:10])
            trades.append(t)
    return trades

def calc_pnl_fifo(trades):
    """FIFO 配对计算盈亏"""
    buy_pool = {}  # name -> list of {qty, price, date}
    realized = []  # 已实现盈亏

    for t in sorted(trades, key=lambda x: (x.get("record_date",""), x.get("time",""))):
        name = t.get("name", "")
        action = t.get("action", "")
        qty = int(t.get("qty", 0) or 0)
        price = float(t.get("price", 0) or 0)

        if "买入" in action:
            buy_pool.setdefault(name, []).append({
                "qty": qty, "price": price,
                "date": t.get("record_date", ""),
                "time": t.get("time", ""),
            })
        elif "卖出" in action:
            remaining = qty
            while remaining > 0 and buy_pool.get(name):
                buy = buy_pool[name][0]
                matched = min(buy["qty"], remaining)
                pnl = (price - buy["price"]) * matched
                realized.append({
                    "name": name,
                    "buy_date": buy["date"],
                    "sell_date": t.get("record_date", ""),
                    "qty": matched,
                    "buy_price": buy["price"],
                    "sell_price": price,
                    "pnl": round(pnl, 2),
                    "reason": t.get("reason", ""),
                    "emotion": t.get("emotion", ""),
                })
                buy["qty"] -= matched
                remaining -= matched
                if buy["qty"] <= 0:
                    buy_pool[name].pop(0)
    return realized

def monthly_summary(realized):
    """按月汇总"""
    by_month = defaultdict(lambda: {"trades": [], "pnl": 0, "wins": 0, "losses": 0})
    for r in realized:
        month = r["sell_date"][:7] if r["sell_date"] else "未知"
        by_month[month]["trades"].append(r)
        by_month[month]["pnl"] += r["pnl"]
        if r["pnl"] > 0:
            by_month[month]["wins"] += 1
        else:
            by_month[month]["losses"] += 1

    result = []
    for month in sorted(by_month.keys()):
        m = by_month[month]
        total = m["wins"] + m["losses"]
        win_rate = round(m["wins"] / total * 100, 1) if total > 0 else 0
        result.append({
            "month": month,
            "pnl": round(m["pnl"], 2),
            "wins": m["wins"],
            "losses": m["losses"],
            "total": total,
            "win_rate": win_rate,
        })
    return result

def build_portfolio_data():
    """构建完整持仓盈亏数据"""
    trades = load_all_trades()
    if not trades:
        return {
            "total_trades": 0,
            "realized_count": 0,
            "cumulative_pnl": 0,
            "monthly": [],
            "current_holdings": [],
            "recent_realized": [],
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    realized = calc_pnl_fifo(trades)
    monthly = monthly_summary(realized)
    cumulative = round(sum(r["pnl"] for r in realized), 2)

    # 当前持仓（未卖出的）
    buy_pool = {}
    for t in sorted(trades, key=lambda x: (x.get("record_date",""), x.get("time",""))):
        name = t.get("name", "")
        action = t.get("action", "")
        qty = int(t.get("qty", 0) or 0)
        price = float(t.get("price", 0) or 0)
        if "买入" in action:
            buy_pool.setdefault(name, []).append({"qty": qty, "price": price, "date": t.get("record_date","")})
        elif "卖出" in action:
            remaining = qty
            while remaining > 0 and buy_pool.get(name):
                buy = buy_pool[name][0]
                matched = min(buy["qty"], remaining)
                buy["qty"] -= matched
                remaining -= matched
                if buy["qty"] <= 0:
                    buy_pool[name].pop(0)

    current_holdings = []
    for name, buys in buy_pool.items():
        total_qty = sum(b["qty"] for b in buys)
        if total_qty > 0:
            avg_cost = sum(b["qty"] * b["price"] for b in buys) / total_qty
            current_holdings.append({
                "name": name,
                "qty": total_qty,
                "avg_cost": round(avg_cost, 2),
                "cost_total": round(avg_cost * total_qty, 2),
            })

    return {
        "total_trades": len(trades),
        "realized_count": len(realized),
        "cumulative_pnl": cumulative,
        "monthly": monthly,
        "current_holdings": current_holdings,
        "recent_realized": realized[-20:],  # 最近 20 笔
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def main():
    data = build_portfolio_data()
    PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"✅ 盈亏汇总已保存: {PORTFOLIO_PATH}")
    print(f"   总交易笔数: {data['total_trades']}")
    print(f"   已配对笔数: {data['realized_count']}")
    print(f"   累计盈亏: {data['cumulative_pnl']:+.2f}")
    if data["monthly"]:
        print("   月度统计:")
        for m in data["monthly"]:
            print(f"     {m['month']}: {m['pnl']:+.2f} 元  胜率 {m['win_rate']}%  ({m['wins']}胜{m['losses']}负)")
    if data["current_holdings"]:
        print("   当前持仓:")
        for h in data["current_holdings"]:
            print(f"     {h['name']}: {h['qty']}股  均价{h['avg_cost']}")

if __name__ == "__main__":
    main()
