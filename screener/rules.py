"""
选股 / 提醒助手（骨架）
=======================
当前为骨架版本。功能占位，待接入 akshare / 真实数据源。

核心规则（默认，可在 docs/投资模型框架.md 中修改）：
- 信号来源：用户记录"大V/社群推荐" → 跟踪 N 日后表现
- 触发：仅在 风控规则全部通过时 才发提醒
- 风控规则（默认）：
    单只仓位 ≤ 30%
    总仓位 ≤ 80%
    今日亏损 ≥ -5% 则熔断
    单笔预估亏损 ≥ -8% 则不出手

数据源（推荐）：
- 行情：akshare（免费） / tushare（需 token） / 券商 SDK
- 公告/题材：东方财富、同花顺、巨潮资讯
"""
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

# 默认风控参数（与 docs/投资模型框架.md 对齐）
DEFAULT_RISK_RULES = {
    "max_single_position": 0.30,    # 单只仓位上限 30%
    "max_total_position": 0.80,     # 总仓位上限 80%
    "daily_loss_circuit_breaker": -0.05,  # 单日亏损熔断
    "max_single_loss": -0.08,       # 单笔硬止损
    "min_risk_reward": 2.0,         # 最小盈亏比
    "max_daily_trades": 3,          # 日最大交易笔数
    "max_holding_days": 10,         # 最大持仓天数
}

def load_rules():
    cfg_path = Path("screener/rules.json")
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_RISK_RULES

def check_risk_gate(current_positions, today_pnl, total_assets, candidate_amount):
    """交易前风控闸门检查。
    返回 (pass: bool, reason: str)
    """
    rules = load_rules()
    # 1. 单日熔断
    if today_pnl / total_assets <= rules["daily_loss_circuit_breaker"]:
        return False, f"今日亏损 {today_pnl/total_assets:.2%} 触发 {rules['daily_loss_circuit_breaker']:.0%} 熔断，停手"
    # 2. 单只仓位上限
    new_pos_pct = candidate_amount / total_assets
    if new_pos_pct > rules["max_single_position"]:
        return False, f"拟买入仓位 {new_pos_pct:.1%} 超 {rules['max_single_position']:.0%} 上限"
    # 3. 总仓位
    total_used = sum(current_positions.values()) / total_assets
    if total_used + new_pos_pct > rules["max_total_position"]:
        return False, f"总仓位将达 {total_used+new_pos_pct:.1%} 超 {rules['max_total_position']:.0%} 上限"
    return True, "通过"

def signal_tracker_template():
    """信号追踪模板：用于记录 大V/社群 推荐 → 后续 N 日表现"""
    schema = {
        "signal_date": "信号日期",
        "source": "来源 (大V/社群/自选)",
        "stock": "标的",
        "code": "代码（待补）",
        "signal_type": "推荐类型 (买入/卖出/观望)",
        "target_price": "目标价",
        "stop_loss": "建议止损",
        "n_day_returns": "N 日实际涨跌 (1/3/5/10 日)",
        "hit": "是否命中 (1/0)",
        "note": "备注",
    }
    return schema

def daily_checklist():
    """每日盘前/盘中 Checklist"""
    items = [
        "✓ 总仓位 ≤ 80%？",
        "✓ 单一标的 ≤ 30%？",
        "✓ 今日已亏损 ≥ 5%？（是 → 停手）",
        "✓ 拟买入的盈亏比 ≥ 2:1？",
        "✓ 今日已交易笔数 < 3？",
        "✓ 拟买入有明确止损位？",
        "✓ 信号来源过去 30 日胜率 ≥ 40%？",
        "✓ 非追涨（已涨 > 5% 慎入）？",
        "✓ 非情绪化（写一句买入理由）？",
    ]
    return items

if __name__ == "__main__":
    print("=" * 60)
    print("选股 / 提醒助手（骨架）")
    print("=" * 60)
    print("\n【风控规则】")
    for k, v in load_rules().items():
        print(f"  {k}: {v}")
    print("\n【信号追踪字段】")
    for k, v in signal_tracker_template().items():
        print(f"  {k}: {v}")
    print("\n【每日 Checklist】")
    for it in daily_checklist():
        print(f"  {it}")
    print("\n⚠️ 这是骨架。需接入真实数据源（akshare/tushare）后才能真正工作。")
    print("   详见 docs/投资模型框架.md 第 X 节。")
