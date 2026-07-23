"""
可视化看板：生成 4 张关键图表
1. 月度 P&L vs 上证对比柱图
2. 累计 P&L 曲线
3. 标的盈亏 Top 10 横向柱图
4. 时段分布柱图
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.font_manager as fm

# 强制用 Noto Sans CJK JP（含简繁中文）
CJK_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
fm.fontManager.addfont(CJK_PATH)
zh_name = fm.FontProperties(fname=CJK_PATH).get_name()
matplotlib.rcParams['font.sans-serif'] = [zh_name, "DejaVu Sans"]
matplotlib.rcParams['font.family'] = "sans-serif"
matplotlib.rcParams['axes.unicode_minus'] = False
print(f"使用中文字体: {zh_name}")
from pathlib import Path

trades = pd.read_csv("data/trades.csv", parse_dates=["date"])
monthly = pd.read_csv("data/monthly_summary.csv")
out_dir = Path("reports/figures")
out_dir.mkdir(parents=True, exist_ok=True)

# FIFO 配对算 P&L（与 diagnosis.py 保持一致）
buy_df = trades[trades["is_buy"]].copy()
sell_df = trades[trades["is_sell"]].copy()
buy_pool = {}
for _, r in buy_df.iterrows():
    if pd.notna(r["qty"]) and pd.notna(r["price"]):
        buy_pool.setdefault(r["name"], []).append({
            "date": r["date"], "qty": int(r["qty"]),
            "price": float(r["price"]),
        })
matched = []
for _, r in sell_df.iterrows():
    name = r["name"]
    qty_to_match = int(r["qty"])
    sell_proceeds = float(r["qty"]) * float(r["price"])
    matched_cost = 0
    matched_qty = 0
    first_buy_date = None
    while qty_to_match > 0 and buy_pool.get(name):
        b = buy_pool[name][0]
        if first_buy_date is None or b["date"] < first_buy_date:
            first_buy_date = b["date"]
        if b["qty"] <= qty_to_match:
            matched_cost += b["qty"] * b["price"]
            matched_qty += b["qty"]
            qty_to_match -= b["qty"]
            buy_pool[name].pop(0)
        else:
            matched_cost += qty_to_match * b["price"]
            matched_qty += qty_to_match
            b["qty"] -= qty_to_match
            qty_to_match = 0
    if matched_qty == int(r["qty"]):
        matched.append({
            "name": name, "sell_date": r["date"], "pnl": sell_proceeds - matched_cost,
        })
matched_df = pd.DataFrame(matched)

# --- 图 1: 月度 P&L vs 上证 ---
fig, ax = plt.subplots(figsize=(10, 5))
months = monthly["year_month"].astype(str).tolist()
pnls = monthly["pnl"].tolist()
# 解析收益率字符串
def parse_pct(s):
    if not isinstance(s, str): return 0
    return float(s.replace("%", "").replace("上证", "").replace("上证", ""))
rets = [parse_pct(m) for m in monthly["return_rate"]]
idxs = [parse_pct(m) for m in monthly["index_return"]]

x = np.arange(len(months))
w = 0.35
b1 = ax.bar(x - w/2, rets, w, label="你的收益率", color="#e74c3c", alpha=0.8)
b2 = ax.bar(x + w/2, idxs, w, label="上证同期", color="#3498db", alpha=0.8)
ax.set_xticks(x)
ax.set_xticklabels(months)
ax.set_ylabel("收益率 (%)")
ax.set_title("月度收益率 vs 上证指数")
ax.legend()
ax.axhline(0, color="gray", lw=0.5)
ax.grid(axis="y", alpha=0.3)
# 标 P&L 数字
for i, p in enumerate(pnls):
    ax.text(i, max(rets[i], idxs[i]) + 1, f"{p:+.0f}", ha="center", fontsize=10, fontweight="bold",
            color="green" if p > 0 else "red")
plt.tight_layout()
plt.savefig(out_dir / "01_monthly_vs_index.png", dpi=120, bbox_inches="tight")
plt.close()
print(f"✅ {out_dir}/01_monthly_vs_index.png")

# --- 图 2: 累计 P&L 曲线 ---
# 月度按时间正序排（5 → 6 → 7）
monthly_sorted = monthly.sort_values("year_month").reset_index(drop=True)
fig, ax = plt.subplots(figsize=(10, 5))
cum_pnl = monthly_sorted["pnl"].cumsum()
ax.plot(monthly_sorted["year_month"].astype(str), cum_pnl, marker="o", linewidth=2.5, color="#e74c3c", markersize=10)
ax.fill_between(range(len(monthly_sorted)), cum_pnl, 0, alpha=0.2, color="#e74c3c")
ax.axhline(0, color="gray", lw=0.8, linestyle="--")
ax.set_title("累计实现盈亏（样本期，5→7月）")
ax.set_ylabel("累计 P&L (元)")
ax.grid(alpha=0.3)
for i, v in enumerate(cum_pnl):
    ax.text(i, v + (500 if v >= 0 else -1500), f"{v:+.0f}", ha="center", fontweight="bold",
            color="green" if v >= 0 else "red")
plt.tight_layout()
plt.savefig(out_dir / "02_cumulative_pnl.png", dpi=120, bbox_inches="tight")
plt.close()
print(f"✅ {out_dir}/02_cumulative_pnl.png")

# --- 图 3: 标的盈亏分布（基于 FIFO 配对的真实 P&L）---
if len(matched_df):
    pnl_by_stock = matched_df.groupby("name")["pnl"].agg(["sum", "count"]).sort_values("sum")
    # 取头尾各 7（最亏 7 + 最赚 7）
    losers7 = pnl_by_stock.head(7)
    winners7 = pnl_by_stock.tail(7)
    plot_data = pd.concat([losers7, winners7]).sort_values("sum")
    fig, ax = plt.subplots(figsize=(10, 8))
    colors = ["#e74c3c" if v < 0 else "#27ae60" for v in plot_data["sum"]]
    bars = ax.barh(plot_data.index.astype(str), plot_data["sum"], color=colors, alpha=0.85)
    for bar, v in zip(bars, plot_data["sum"]):
        x_pos = v + (30 if v >= 0 else -30)
        align = "left" if v >= 0 else "right"
        ax.text(x_pos, bar.get_y() + bar.get_height()/2, f"{v:+.0f}",
                ha=align, va="center", fontweight="bold",
                color="green" if v >= 0 else "red", fontsize=10)
    ax.set_xlabel("P&L (元) — FIFO 配对真实盈亏")
    ax.set_title("标的盈亏贡献（最亏 7 + 最赚 7，按真实 P&L）")
    ax.axvline(0, color="gray", lw=1.0)
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "03_top_stocks_pnl.png", dpi=120, bbox_inches="tight")
    plt.close()
    print(f"✅ {out_dir}/03_top_stocks_pnl.png")

# --- 图 4: 交易时段 ---
trades_clean = trades.dropna(subset=["date"]).copy()
trades_clean["hour"] = pd.to_datetime(trades_clean["time"], format="%H:%M", errors="coerce").dt.hour
hour_counts = trades_clean["hour"].dropna().astype(int).value_counts().sort_index()
fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(hour_counts.index, hour_counts.values, color="#9b59b6", alpha=0.8)
ax.set_xticks(range(24))
ax.set_xlabel("小时")
ax.set_ylabel("交易笔数")
ax.set_title("交易时段分布")
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig(out_dir / "04_hour_distribution.png", dpi=120, bbox_inches="tight")
plt.close()
print(f"✅ {out_dir}/04_hour_distribution.png")

# --- 图 5: 胜率与盈亏比（按月，使用 FIFO 配对的真实 P&L）---
if len(matched_df):
    fig, ax = plt.subplots(figsize=(10, 5))
    matched_df["ym"] = matched_df["sell_date"].dt.to_period("M").astype(str)
    win_rate_by_ym = matched_df.groupby("ym").apply(
        lambda g: (g["pnl"] > 0).sum() / len(g) if len(g) else 0
    ).sort_index()
    colors = ["#27ae60" if v >= 0.5 else "#e74c3c" for v in win_rate_by_ym.values]
    ax.bar(win_rate_by_ym.index, win_rate_by_ym.values * 100, color=colors, alpha=0.8)
    ax.axhline(50, color="red", lw=1.2, linestyle="--", label="50% 分界线")
    for i, v in enumerate(win_rate_by_ym.values):
        ax.text(i, v * 100 + 2, f"{v*100:.0f}%", ha="center", fontweight="bold", fontsize=11)
    ax.set_ylabel("胜率 (%)")
    ax.set_title("月度胜率（基于 FIFO 配对的真实 P&L）")
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "05_win_rate_by_month.png", dpi=120, bbox_inches="tight")
    plt.close()
    print(f"✅ {out_dir}/05_win_rate_by_month.png")
else:
    print("⚠️ 无匹配数据，跳过图 5")

print(f"\n所有图表已保存到 {out_dir}/")
