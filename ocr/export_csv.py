"""
把 records_v3.json 导出成 CSV，附加：
- 月度 P&L（来自汇总行）
- 按标的聚合
"""
import json
import pandas as pd

with open("ocr/records_v3.json", encoding="utf-8") as f:
    records = json.load(f)

trades = [r for r in records if r["type"] == "trade"]
monthly = [r for r in records if r["type"] == "monthly"]

# === 交易 CSV ===
df = pd.DataFrame(trades)
# 转换日期
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df = df.dropna(subset=["date"])
df = df.sort_values("date").reset_index(drop=True)

# 添加几个派生列
df["is_buy"] = df["action"].str.contains("买入", na=False)
df["is_sell"] = df["action"].str.contains("卖出", na=False)
df["is_ipo"] = df["action"] == "申购配号"
df["is_bank"] = df["action"] == "银行转取"
df["weekday"] = df["date"].dt.day_name()

# 输出列（派生列也保留在内存中供统计用）
print(f"✅ 交易 CSV: data/trades.csv ({len(df)} 条)")
df.to_csv("data/trades.csv", index=False, encoding="utf-8-sig")
print(df.head(10).to_string(index=False))

# === 月度 CSV ===
mdata = []
for m in monthly:
    raw = m["raw"]
    ym = m["year_month"]
    # 解析 P&L
    import re
    pnl_match = re.search(r'-?[\d,]+\.\d+', raw)
    pnl = None
    if pnl_match:
        try:
            pnl = float(pnl_match.group(0).replace(",", ""))
        except: pass
    # 解析收益率
    ret_match = re.search(r'-?\d+\.\d+%', raw)
    ret = ret_match.group(0) if ret_match else None
    # 上证收益率
    idx_match = re.findall(r'上证-?\d+\.\d+%', raw)
    idx = idx_match[0] if idx_match else None
    mdata.append({"year_month": ym, "pnl": pnl, "return_rate": ret, "index_return": idx, "raw": raw})

mdf = pd.DataFrame(mdata)
mdf.to_csv("data/monthly_summary.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ 月度 CSV: data/monthly_summary.csv ({len(mdf)} 条)")
print(mdf.to_string(index=False))

# 简要统计
print(f"\n=== 简要统计 ===")
print(f"总交易笔数: {len(df)}")
print(f"买入: {df['is_buy'].sum()}, 卖出: {df['is_sell'].sum()}, 申购: {df['is_ipo'].sum()}, 银行: {df['is_bank'].sum()}")
print(f"覆盖标的数: {df['name'].nunique()}")
print(f"时间跨度: {df['date'].min().date()} 至 {df['date'].max().date()} ({(df['date'].max() - df['date'].min()).days} 天)")
print(f"按月分布: {df.groupby(df['date'].dt.to_period('M')).size().to_dict()}")
