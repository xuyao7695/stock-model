"""
操作建议生成器：风控规则 + 交易纪律 → 每只候选的具体建议
==========================================================
输入：scan 的候选池 + 当前仓位状态（用户提供）
输出：带 买/不买/观察 + 仓位 + 止损 + 目标 + 纪律 的建议清单
"""
import json
from datetime import datetime
from pathlib import Path

RISK_PATH = Path("screener/rules.json")
CAND_PATH = Path("data/candidates.json")

def load_rules():
    with open(RISK_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_candidates():
    if not CAND_PATH.exists():
        return None
    with open(CAND_PATH, encoding="utf-8") as f:
        return json.load(f)

def risk_gate(rules, portfolio, candidate_amount, total_assets):
    """交易前风控闸门。返回 (pass, reason)"""
    # 1. 单日熔断
    daily_loss = portfolio.get("today_pnl", 0)
    if total_assets and daily_loss / total_assets <= rules["daily_loss_circuit_breaker"]:
        return False, f"今日亏损 {daily_loss/total_assets:.1%} 触发 {rules['daily_loss_circuit_breaker']:.0%} 熔断 → 今日停手"
    # 2. 总仓位
    used = portfolio.get("used_assets", 0)
    if total_assets and (used + candidate_amount) / total_assets > rules["max_total_position"]:
        return False, f"总仓位将超 {rules['max_total_position']:.0%} 上限"
    # 3. 单只仓位
    if total_assets and candidate_amount / total_assets > rules["max_single_position"]:
        return False, f"单只仓位 {candidate_amount/total_assets:.1%} 超 {rules['max_single_position']:.0%} 上限"
    # 4. 日交易笔数
    if portfolio.get("trades_today", 0) >= rules["max_daily_trades"]:
        return False, f"今日已交易 {portfolio.get('trades_today',0)} 笔，达 {rules['max_daily_trades']} 笔上限"
    return True, "通过"

def advise_one(c, rules, portfolio, total_assets):
    """对单只候选生成操作建议"""
    name = c["name"]
    code = c["code"]
    zt = c.get("zt_count", 0)
    seal = c.get("seal_money", 0)
    ind = c.get("industry", "—")
    heat = c.get("industry_heat", 0)

    # 仓位建议（基于连板 + 封单 + 题材热度）
    base = rules["max_single_position"]
    # 连板越高，仓位越保守（高位风险大）
    if zt >= 4:
        pos_pct = min(base * 0.5, 0.15)   # 高位：轻仓 15%
        pos_note = "高位连板，轻仓试错"
    elif zt == 3:
        pos_pct = min(base * 0.7, 0.20)
        pos_note = "三板，半仓以内"
    elif zt == 2:
        pos_pct = min(base * 0.85, 0.25)
        pos_note = "二板，主仓位"
    else:  # 首板
        pos_pct = min(base * 0.6, 0.18)
        pos_note = "首板，轻仓埋伏"

    candidate_amount = pos_pct * total_assets if total_assets else 0

    # 止损位（基于当前涨停价推算买入成本）
    # 涨停价 ≈ 买入价 * 1.1（主板）；这里用 封板资金 不作为价，改用 题材强度给比例
    stop_pct = rules["max_single_loss"]  # 默认 -8%
    if zt >= 3:
        stop_pct = -0.06  # 高位更紧
    target_pct = max(rules["min_risk_reward"] * abs(stop_pct), 0.15)  # 目标 ≥ 盈亏比 × 止损

    # 风控闸门
    gate_pass, gate_reason = risk_gate(rules, portfolio, candidate_amount, total_assets)

    # 持仓天数
    max_hold = rules["max_holding_days"]

    # 纪律清单
    discipline = [
        f"⛔ 单只 ≤ {pos_pct:.0%} 仓位，总仓 ≤ {rules['max_total_position']:.0%}",
        f"🛑 硬止损 {stop_pct:.0%}（到价无条件砍，不补仓）",
        f"🎯 目标 +{target_pct:.0%} 或 题材退潮即走",
        f"⏱ 最大持仓 {max_hold} 天，到期强制复盘",
        f"📝 买入前写一句理由 + 信号来源（不写不买）",
        f"🔥 今日已亏 {rules['daily_loss_circuit_breaker']:.0%} 熔断 → 关 APP",
    ]

    action = "✅ 关注买入" if gate_pass else "⛔ 不参与"
    if not gate_pass:
        action = "⛔ 风控拦截"

    return {
        "code": code, "name": name, "path": c.get("path"),
        "zt_count": zt, "industry": ind, "industry_heat": heat,
        "score": c.get("score"),
        "action": action,
        "gate_pass": gate_pass,
        "gate_reason": gate_reason,
        "pos_pct": pos_pct,
        "pos_note": pos_note,
        "stop_pct": stop_pct,
        "target_pct": target_pct,
        "max_hold_days": max_hold,
        "discipline": discipline,
        "matched": c.get("matched", []),
    }

def dedupe_by_industry(advices, max_per_industry=2, top_n=6):
    """同板块只留 max_per_industry 个，取评分最高的 top_n 个"""
    by_ind = {}
    for a in advices:
        ind = a.get("industry", "—")
        by_ind.setdefault(ind, []).append(a)
    # 每个行业按分排序，取前 max_per_industry
    result = []
    for ind, lst in by_ind.items():
        lst.sort(key=lambda x: x.get("score", 0), reverse=True)
        result.extend(lst[:max_per_industry])
    # 总体按分排序，取 top_n
    result.sort(key=lambda x: x.get("score", 0), reverse=True)
    return result[:top_n]

def build_report(candidates, rules, portfolio, total_assets, scan_time):
    all_advices = [advise_one(c, rules, portfolio, total_assets) for c in candidates]
    # 同板块��重，取最优 6 个
    advices = dedupe_by_industry(all_advices, max_per_industry=2, top_n=6)
    # 统计
    n_pass = sum(1 for a in advices if a["gate_pass"])
    n_block = len(advices) - n_pass
    lines = []
    R = lines.append
    R(f"# 每日选股 + 操作建议（{scan_time}）")
    R("")
    R(f"> 数据源：akshare 实盘 · 条件：题材资金流 + 技术突破量能 · 风控：硬规则闸门")
    R("")
    R("## 一、盘面与风控状态")
    R("")
    R("| 项目 | 数值 |")
    R("|---|---|")
    R(f"| 候选数 | {len(advices)} |")
    R(f"| 风控通过 | {n_pass} |")
    R(f"| 风控拦截 | {n_block} |")
    R(f"| 单只上限 | {rules['max_single_position']:.0%} |")
    R(f"| 总仓上限 | {rules['max_total_position']:.0%} |")
    R(f"| 日亏熔断 | {rules['daily_loss_circuit_breaker']:.0%} |")
    R(f"| 日最大笔数 | {rules['max_daily_trades']} |")
    R("")
    R("## 二、操作建议清单（按分排序）")
    R("")
    for i, a in enumerate(advices, 1):
        R(f"### {i}. {a['name']}（{a['code']}）— {a['action']}")
        R("")
        R(f"- **路径**：{a['path']} ｜ **评分**：{a['score']:.3f} ｜ **连板**：{a['zt_count']} ｜ **行业**：{a['industry']}（热度{a['industry_heat']:.2f}）")
        R(f"- **建议仓位**：{a['pos_pct']:.0%}（{a['pos_note']}）")
        R(f"- **止损位**：{a['stop_pct']:.0%} ｜ **目标**：+{a['target_pct']:.0%} ｜ **最大持仓**：{a['max_hold_days']} 天")
        if not a['gate_pass']:
            R(f"- **拦截原因**：{a['gate_reason']}")
        R(f"- **命中条件**：{', '.join(a['matched'])}")
        R("")
        R("**交易纪律**")
        for d in a['discipline']:
            R(f"  {d}")
        R("")
    R("---")
    R("")
    R("> ⚠️ 本建议由系统按规则生成，仅供参考，不构成投资建议。最终决策与风险自担。")
    return "\n".join(lines), advices

def main():
    rules = load_rules()
    data = load_candidates()
    if not data:
        print("❌ 先运行 screener/scan.py 生成候选池")
        return
    candidates = data["candidates"]
    scan_time = data.get("scan_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 默认空仓状态（用户实际运行时替换）
    portfolio = {
        "total_assets": 100000,   # 示例：10万
        "used_assets": 0,
        "today_pnl": 0,
        "trades_today": 0,
    }
    all_advices = [advise_one(c, rules, portfolio, portfolio["total_assets"]) for c in candidates]
    report, advices = build_report(candidates, rules, portfolio, portfolio["total_assets"], scan_time)
    out = Path("reports/每日操作建议.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    # 同时存结构化 JSON，供看板/App 读取
    adv_path = Path("data/advices.json")
    adv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(adv_path, "w", encoding="utf-8") as f:
        json.dump({
            "scan_time": scan_time,
            "total_zt": len(candidates),
            "top_n": 6,
            "advices": advices,
            "all_advices": all_advices,
        }, f, ensure_ascii=False, indent=1)
    print(f"✅ 操作建议已保存: {out}")
    print(f"✅ 结构化建议: {adv_path}")
    print(f"   总候选 {len(all_advices)} → 去重后 {len(advices)} 只（同板块≤2，Top6）")

if __name__ == "__main__":
    main()
