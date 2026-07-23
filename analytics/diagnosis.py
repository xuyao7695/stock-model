"""
行为诊断 v2：理解对账单字段含义
- 卖出 amount = 成交金额（cash proceeds）
- 买入 amount = 成本（cash out）
- 月度 P&L 才是真实实现盈亏的权威值
- 单笔 P&L 需要 FIFO 配对（同窗口内可部分计算）
"""
import pandas as pd
import numpy as np
from pathlib import Path

# 加载
trades = pd.read_csv("data/trades.csv", parse_dates=["date"])
monthly = pd.read_csv("data/monthly_summary.csv")
buy = trades[trades["is_buy"]].copy()
sell = trades[trades["is_sell"]].copy()

# 基础
period_start = trades["date"].min().date()
period_end = trades["date"].max().date()
days = (trades["date"].max() - trades["date"].min()).days + 1
total_buy_sell = len(buy) + len(sell)
trades_per_day = total_buy_sell / days
unique_stocks = trades["name"].nunique()
rotation_rate = total_buy_sell / max(1, unique_stocks)

# FIFO 配对算单笔 P&L
buy_pool = {}
for _, r in buy.iterrows():
    if pd.notna(r["qty"]) and pd.notna(r["price"]):
        buy_pool.setdefault(r["name"], []).append({
            "date": r["date"], "qty": int(r["qty"]),
            "price": float(r["price"]),
        })

matched_trades = []  # 完整配对的（buy+sell）循环
unmatched_sells = []  # 找不到匹配的卖出
sell_pnl_list = []  # 每笔卖出的 P&L

for _, r in sell.iterrows():
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
        pnl = sell_proceeds - matched_cost
        days_held = (r["date"] - first_buy_date).days
        sell_pnl_list.append({
            "name": name, "sell_date": r["date"], "days_held": days_held,
            "sell_price": r["price"], "avg_cost": matched_cost / matched_qty,
            "qty": int(r["qty"]), "proceeds": sell_proceeds,
            "cost": matched_cost, "pnl": pnl,
        })
    else:
        unmatched_sells.append({"name": name, "qty": int(r["qty"]) - matched_qty,
                                "sell_date": r["date"]})

pnl_df = pd.DataFrame(sell_pnl_list)
unmatched_count = len(unmatched_sells)
matched_count = len(pnl_df)

# 胜率 / 盈亏比（基于配对 P&L）
if len(pnl_df):
    winners = pnl_df[pnl_df["pnl"] > 0]
    losers = pnl_df[pnl_df["pnl"] < 0]
    win_rate = len(winners) / len(pnl_df)
    avg_win = winners["pnl"].mean() if len(winners) else 0
    avg_loss = losers["pnl"].mean() if len(losers) else 0
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
    profit_factor = winners["pnl"].sum() / abs(losers["pnl"].sum()) if len(losers) else float("inf")
    avg_hold_win = winners["days_held"].mean() if len(winners) else 0
    avg_hold_loss = losers["days_held"].mean() if len(losers) else 0
    disposition_effect = avg_hold_win - avg_hold_loss
else:
    win_rate = avg_win = avg_loss = pl_ratio = profit_factor = 0
    avg_hold_win = avg_hold_loss = disposition_effect = 0

# 持仓周期
if len(pnl_df):
    median_hold = float(pnl_df["days_held"].median())
    mean_hold = float(pnl_df["days_held"].mean())
    zero_day_trades = int((pnl_df["days_held"] == 0).sum())
    zero_day_rate = zero_day_trades / len(pnl_df)
else:
    median_hold = mean_hold = zero_day_rate = 0

# 标的集中
top_stocks = trades["name"].value_counts().head(10)
top_pnl = pnl_df.groupby("name")["pnl"].agg(["sum", "count"]).sort_values("sum") if len(pnl_df) else pd.DataFrame()

# 时段
hour_dist = trades.dropna(subset=["date"]).copy()
hour_dist["hour"] = pd.to_datetime(hour_dist["time"], format="%H:%M", errors="coerce").dt.hour
hour_counts = hour_dist["hour"].value_counts().sort_index()

# 写报告
report = []
R = report.append

R("# 行为诊断报告")
R("")
R(f"**生成时间**: 2026-07-23  ")
R(f"**数据来源**: 广发证券对账单 OCR（{period_start} 至 {period_end}，共 {days} 天）  ")
R(f"**样本量**: {len(trades)} 笔交易（买入 {len(buy)} / 卖出 {len(sell)} / 申购 {trades['is_ipo'].sum()} / 银行转取 {trades['is_bank'].sum()}）  ")
R("")
R("---")
R("")

# 一、总览
R("## 一、总览")
R("")
R("| 指标 | 数值 | 含义 |")
R("|---|---|---|")
m_pnl_sum = monthly["pnl"].sum()
R(f"| 样本期累计 P&L | **{m_pnl_sum:+,.2f} 元** | 来自月度汇总（更可靠） |")
R(f"| 月均 P&L | {monthly['pnl'].mean():+,.2f} 元 | 3 个月平均 |")
R(f"| 月度胜率 | {sum(1 for _,m in monthly.iterrows() if m['pnl']>0)} / {len(monthly)} | 盈利月占比 |")
R(f"| 同期上证 | 约 {monthly['index_return'].iloc[-1]} | 末月上证 |")
R(f"| 交易活跃度 | **{trades_per_day:.2f} 笔/天** | 买卖双向 |")
R(f"| 覆盖标的 | {unique_stocks} 只 | 期内换过的股票 |")
R(f"| 换手强度 | {rotation_rate:.2f} 笔/股 | 平均每只票被交易次数 |")
R("")

# 二、月度
R("## 二、月度对比（权威 P&L）")
R("")
R("| 月份 | 盈亏 | 收益率 | 上证 | 对比 |")
R("|---|---|---|---|---|")
for _, m in monthly.iterrows():
    icon = "🟢" if m["pnl"] > 0 else "🔴"
    R(f"| {m['year_month']} | {m['pnl']:+,.2f} | {m['return_rate']} | {m['index_return']} | {icon} |")
R("")

# 三、单笔 P&L 分析（基于 OCR 窗口内可配对部分）
R("## 三、单笔 P&L 分析（FIFO 配对）")
R("")
R(f"**{matched_count} / {len(sell)}** 笔卖出可在 OCR 窗口内完成买卖配对")
R(f"（{unmatched_count} 笔卖出的对应买入在本窗口之前，未纳入）")
R("")
if len(pnl_df):
    R("| 指标 | 数值 | 解读 |")
    R("|---|---|---|")
    R(f"| 配对样本 | {matched_count} 笔 | — |")
    R(f"| 胜率 | **{win_rate*100:.1f}%** | {'❌ 偏低' if win_rate < 0.5 else '✅ 达标'} |")
    R(f"| 平均盈利 | {avg_win:+,.2f} 元 | — |")
    R(f"| 平均亏损 | {avg_loss:+,.2f} 元 | — |")
    R(f"| 盈亏比 | **{pl_ratio:.2f}** | {'❌ <1 整体亏损' if pl_ratio < 1 else '✅ 健康' if pl_ratio >= 2 else '⚠️ 偏低'} |")
    R(f"| 盈利因子 | {profit_factor:.2f} | {'❌ <1 总亏' if profit_factor < 1 else '✅ >1 总盈'} |")
R("")

# 四、持仓周期
R("## 四、持仓周期")
R("")
if len(pnl_df):
    R(f"基于 {matched_count} 笔配对卖出统计：")
    R("")
    R("| 指标 | 数值 | 含义 |")
    R("|---|---|---|")
    R(f"| 中位持仓 | {median_hold:.1f} 天 | 一半交易在这个天数内平仓 |")
    R(f"| 平均持仓 | {mean_hold:.1f} 天 | 全部配对交易 |")
    R(f"| 当日 T+0 比例 | {zero_day_rate*100:.1f}% | 频繁进出特征 |")
R("")

# 五、行为偏差
R("## 五、行为偏差（关键）")
R("")
R("### 5.1 处置效应（Disposition Effect）")
R("")
R("> **心理偏差**: 急于把盈利落袋（砍盈），却把亏损扛在手里（扛亏）")
R("")
if len(pnl_df) and len(winners) and len(losers):
    R("| | 盈利单 | 亏损单 |")
    R("|---|---|---|")
    R(f"| 平均持仓天数 | {avg_hold_win:.1f} | {avg_hold_loss:.1f} |")
    R(f"| 偏差 | {disposition_effect:+.1f} 天 | {'❌ 砍盈扛亏' if disposition_effect > 1 else '✅ 正常' if disposition_effect < -1 else '⚠️ 差异小'} |")
R("")

R("### 5.2 标的集中度")
R("")
R("**交易笔数 Top 10**")
R("")
R("| 标的 | 笔数 | 占总买卖% |")
R("|---|---|---|")
for name, cnt in top_stocks.items():
    R(f"| {name} | {cnt} | {cnt/total_buy_sell*100:.1f}% |")
R("")

if len(top_pnl):
    R("**P&L 贡献 Top 5（盈利）**")
    R("")
    for name, row in top_pnl.tail(5).iterrows():
        R(f"- **{name}**: {row['sum']:+,.2f} 元 ({int(row['count'])} 笔)")
    R("")
    R("**P&L 贡献 Top 5（亏损）**")
    R("")
    for name, row in top_pnl.head(5).iterrows():
        R(f"- **{name}**: {row['sum']:+,.2f} 元 ({int(row['count'])} 笔)")
R("")

R("### 5.3 交易时段")
R("")
R("| 时段 | 笔数 | 占比 |")
R("|---|---|---|")
for hour, cnt in hour_counts.items():
    if pd.notna(hour):
        R(f"| {int(hour):02d}:00-{(int(hour)+1)%24:02d}:00 | {cnt} | {cnt/total_buy_sell*100:.1f}% |")
R("")

# 六、诊断
R("## 六、核心诊断")
R("")

score = 0
issues = []
if win_rate < 0.5: score -= 2; issues.append(f"胜率 {win_rate*100:.0f}% 不足 50%")
if pl_ratio and pl_ratio < 1: score -= 2; issues.append(f"盈亏比 {pl_ratio:.2f} 整体亏损")
if zero_day_rate and zero_day_rate > 0.3: score -= 2; issues.append(f"T+0 比例 {zero_day_rate*100:.0f}% 过高")
if disposition_effect and disposition_effect > 1.5: score -= 1; issues.append(f"砍盈扛亏偏差 {disposition_effect:.1f} 天")
if trades_per_day > 3: score -= 2; issues.append(f"日均 {trades_per_day:.1f} 笔过频")
if rotation_rate > 3: score -= 1; issues.append(f"换手强度 {rotation_rate:.1f} 标的过散")

if score <= -6:
    level = "🔴 高危 — 持续亏损概率高"
elif score <= -3:
    level = "🟠 需重点改进"
elif score <= 0:
    level = "🟡 整体可控，有优化空间"
else:
    level = "🟢 良好"

R(f"**整体评级**: {level}")
R("")
R("**主要问题**（按严重度）：")
R("")
for i, iss in enumerate(sorted(issues, reverse=True), 1):
    R(f"{i}. {iss}")
R("")

# 七、行动建议
R("## 七、行动建议（按优先级）")
R("")
R("### 紧急（本周内）")
R("")
R("1. **建硬止损**: 单笔亏损达 -5%（激进型）/ -8%（稳健型）即无条件平仓，不允许『再看看』")
R("2. **限单笔仓位**: 任何单一标的 ≤ 总资金 30%，避免单票黑天鹅")
R("3. **限日频次**: 每日交易 ≥ 3 笔即关 APP，避免手续费 + 情绪叠加")
R("")
R("### 短期（本月）")
R("")
R("4. **写『买入理由』日志**: 每次买入记录 ① 推荐来源 ② 预期收益 ③ 止损位 ④ 最大持仓天数；事后对照")
R("5. **信号源胜率审计**: 把你过去跟的大 V / 社群推荐逐条复盘，过滤掉 N 日胜率 < 40% 的来源")
R("6. **复盘 5 笔最大亏损单**: 找出共性（题材/价位/时间/情绪），针对性设防")
R("")
R("### 中期（3 个月内）")
R("")
R("7. **建立选股信号回测**: 用 akshare 把你常用的技术/题材信号跑历史数据，看真实胜率")
R("8. **建绩效看板**: 每日更新胜率、盈亏比、持仓天数、跑赢上证幅度")
R("9. **复盘周期制度化**: 每周日 30 分钟看本周交易日记，每月 1 日看月度 P&L")
R("")
R("---")
R("")
R(f"> **样本期说明**: 本份报告基于 **{len(trades)} 笔交易**（{days} 天 / {len(monthly)} 个月）,")
R("覆盖对账单 2023-12-01 至 2026-07-23 区间的**最近 64 天**。完整 2.6 年 2065 笔交易需补充更早的截图/导出数据。")
R("")
R("> **方法说明**: 单笔 P&L 来自 FIFO 配对（按买入日期升序匹配同标的卖出），窗口外买入未纳入。月度 P&L 直接来自对账单汇总行。")

Path("reports").mkdir(exist_ok=True)
with open("reports/行为诊断报告.md", "w", encoding="utf-8") as f:
    f.write("\n".join(report))

print("✅ 报告已保存: reports/行为诊断报告.md")
print(f"   样本 {len(trades)} 笔 / 配对 {matched_count} 笔 / 胜率 {win_rate*100:.1f}% / 盈亏比 {pl_ratio:.2f} / 日均 {trades_per_day:.1f} 笔")
print(f"   主要问题: {len(issues)} 项, 评分 {score}")
