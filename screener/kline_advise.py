"""
K线策略操作建议生成器
====================
将 kline_scan.py 的候选池与风控规则结合，
生成带仓位/止损/目标/纪律的操作建议。

特殊处理：
  - 不同K线信号的止损/目标不同（反转信号止损更紧）
  - 量能配合度影响仓位建议
  - 均线排列影响持仓周期建议
"""
import json
from datetime import datetime
from pathlib import Path

RISK_PATH = Path("screener/rules.json")
KLINE_PATH = Path("data/kline_candidates.json")
OUT_PATH = Path("data/kline_advices.json")

# 信号 → 操作参数映射
SIGNAL_PARAMS = {
    "放量突破": {
        "stop_pct": -0.05,       # 突破失败止损5%
        "target_pct": 0.15,      # 目标15%
        "pos_factor": 1.0,       # 仓位系数（满仓建议）
        "max_hold": 10,          # 最大持仓天数
        "note": "突破颈线/前高，放量确认后跟进",
    },
    "缩量回踩": {
        "stop_pct": -0.06,       # 跌破均线止损6%
        "target_pct": 0.12,
        "pos_factor": 0.9,
        "max_hold": 12,
        "note": "回踩均线缩量企稳，低吸机会",
    },
    "倍量柱": {
        "stop_pct": -0.07,       # 倍量柱次日常有震荡
        "target_pct": 0.15,
        "pos_factor": 0.8,
        "max_hold": 8,
        "note": "主力资金入场信号，关注次日是否持续",
    },
    "早晨之星": {
        "stop_pct": -0.05,       # 反转信号止损紧
        "target_pct": 0.10,
        "pos_factor": 0.7,
        "max_hold": 7,
        "note": "底部反转信号，轻仓试探",
    },
    "红三兵": {
        "stop_pct": -0.05,
        "target_pct": 0.12,
        "pos_factor": 0.85,
        "max_hold": 10,
        "note": "温和上行趋势，顺势加仓",
    },
    "锤头线": {
        "stop_pct": -0.04,       # 锤头线止损最紧（跌破下影线）
        "target_pct": 0.08,
        "pos_factor": 0.6,
        "max_hold": 5,
        "note": "底部锤头线，极轻仓抄底",
    },
    "阳包阴": {
        "stop_pct": -0.05,
        "target_pct": 0.10,
        "pos_factor": 0.75,
        "max_hold": 7,
        "note": "多头反吞，短线反转信号",
    },
}


def load_rules():
    with open(RISK_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_candidates():
    if not KLINE_PATH.exists():
        return None
    with open(KLINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def best_signal(signals):
    """从命中的信号中选取评分最高的作为主信号"""
    if not signals:
        return None
    # 按信号在SIGNAL_PARAMS中的pos_factor排序
    ranked = sorted(signals, key=lambda s: SIGNAL_PARAMS.get(s, {}).get("pos_factor", 0.5), reverse=True)
    return ranked[0]


def advise_kline(c, rules, portfolio, total_assets):
    """对单只K线候选生成操作建议"""
    name = c["name"]
    code = c["code"]
    signals = c.get("matched", [])  # 中文名列表
    primary = best_signal(signals)
    params = SIGNAL_PARAMS.get(primary, {"stop_pct": -0.06, "target_pct": 0.10, "pos_factor": 0.7, "max_hold": 8, "note": ""})

    # 仓位：基础仓位 × 信号系数 × 量能调整
    base = rules["max_single_position"]
    pos_pct = min(base * params["pos_factor"], base)

    # 量能配合加成
    if c.get("ma_aligned"):
        pos_pct = min(pos_pct * 1.1, base)

    # 多信号叠加加成（最多+10%）
    if len(signals) >= 2:
        pos_pct = min(pos_pct * 1.05, base)
    if len(signals) >= 3:
        pos_pct = min(pos_pct * 1.05, base)

    pos_pct = round(pos_pct, 3)

    # 止损/目标
    stop_pct = params["stop_pct"]
    target_pct = params["target_pct"]

    # 检查盈亏比是否达标
    min_rr = rules.get("min_risk_reward", 2.0)
    actual_rr = target_pct / abs(stop_pct)
    if actual_rr < min_rr:
        # 提高目标价以达标
        target_pct = abs(stop_pct) * min_rr

    max_hold = params["max_hold"]

    # 纪律清单
    discipline = [
        f"⛔ 仓位 ≤ {pos_pct:.0%}，总仓 ≤ {rules['max_total_position']:.0%}",
        f"🛑 止损 {stop_pct:.0%}（到价无条件砍，不补仓）",
        f"🎯 目标 +{target_pct:.0%} 或 信号失效即走",
        f"⏱ 最大持仓 {max_hold} 天",
        f"📝 主信号：{primary}（{params['note']}）",
        f"🔥 叠加信号：{', '.join(signals)}" if len(signals) > 1 else "",
        f"⚠️ 均线{'多头排列' if c.get('ma_aligned') else '未对齐'}",
    ]
    discipline = [d for d in discipline if d]

    candidate_amount = pos_pct * total_assets if total_assets else 0

    # 风控闸门
    # 1. 日熔断
    daily_loss = portfolio.get("today_pnl", 0)
    gate_pass = True
    gate_reason = "通过"
    if total_assets and daily_loss / total_assets <= rules["daily_loss_circuit_breaker"]:
        gate_pass = False
        gate_reason = f"今日亏损触发熔断"
    # 2. 总仓位
    used = portfolio.get("used_assets", 0)
    if total_assets and (used + candidate_amount) / total_assets > rules["max_total_position"]:
        gate_pass = False
        gate_reason = f"总仓位超限"
    # 3. 日交易笔数
    if portfolio.get("trades_today", 0) >= rules["max_daily_trades"]:
        gate_pass = False
        gate_reason = f"今日交易笔数达上限"

    action = "✅ 关注买入" if gate_pass else "⛔ 风控拦截"

    return {
        "code": code, "name": name, "path": c.get("path", "C-K线量能"),
        "signals": signals, "primary_signal": primary,
        "ma_aligned": c.get("ma_aligned", False),
        "score": c.get("score"),
        "action": action,
        "gate_pass": gate_pass,
        "gate_reason": gate_reason,
        "pos_pct": pos_pct,
        "pos_note": params["note"],
        "stop_pct": stop_pct,
        "target_pct": round(target_pct, 3),
        "actual_rr": round(actual_rr, 2),
        "max_hold_days": max_hold,
        "discipline": discipline,
        "matched": signals,
        "signal_details": c.get("signal_details", {}),
    }


def dedupe_by_signal(advices, top_n=6):
    """去重：同股票取最高分，取top_n"""
    seen = {}
    for a in advices:
        code = a["code"]
        if code not in seen or a["score"] > seen[code]["score"]:
            seen[code] = a
    result = list(seen.values())
    result.sort(key=lambda x: x.get("score", 0), reverse=True)
    return result[:top_n]


def main():
    rules = load_rules()
    data = load_candidates()
    if not data:
        print("❌ 先运行 screener/kline_scan.py 生成K线候选池")
        return

    candidates = data["candidates"]
    scan_time = data.get("scan_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    portfolio = {
        "total_assets": 100000,
        "used_assets": 0,
        "today_pnl": 0,
        "trades_today": 0,
    }

    all_advices = [advise_kline(c, rules, portfolio, portfolio["total_assets"]) for c in candidates]
    advices = dedupe_by_signal(all_advices, top_n=6)

    output = {
        "scan_time": scan_time,
        "strategy": "K线形态+量能配合",
        "total_hits": len(candidates),
        "top_n": len(advices),
        "advices": advices,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)

    print(f"✅ K线策略建议已保存: {OUT_PATH}")
    print(f"   总命中 {len(candidates)} → 去重后 {len(advices)} 只")
    print("\n操作建议:")
    for a in advices:
        print(f"  {a['name']}({a['code']}) {a['action']} 信号:{'+'.join(a['signals'])} "
              f"仓位:{a['pos_pct']:.0%} 止损:{a['stop_pct']:.0%} 目标:+{a['target_pct']:.0%}")


if __name__ == "__main__":
    main()
