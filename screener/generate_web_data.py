"""
生成静态前端所需的 JSON 数据包
================================
- 汇总当天扫描结果 + 最近 10 天历史
- 输出到 docs/data/ 供 GitHub Pages 前端读取
- GitHub Actions 每天跑完后自动调用此脚本
"""
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import importlib.util

BASE = Path(".")
HISTORY_DIR = BASE / "data/history"
OUT_DIR = BASE / "docs/data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 加载 history 模块
spec = importlib.util.spec_from_file_location("history", BASE / "screener/history.py")
hist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hist)

def load_rules():
    rp = BASE / "screener/rules.json"
    if rp.exists():
        with open(rp, encoding="utf-8") as f:
            return json.load(f)
    return {}

def generate_bundle():
    """生成前端数据包"""
    rules = load_rules()

    # 最近 10 天概览
    history = hist.list_history(10)

    # 当天详情
    today = datetime.now().strftime("%Y-%m-%d")
    day_data = hist.load_day(today)
    scan = day_data.get("scan") or {}
    advices = sorted(scan.get("advices", []), key=lambda x: x.get("score", 0), reverse=True)

    # 最近 10 天每天的详情概要
    days_detail = []
    for h in history:
        d = hist.load_day(h["date"])
        s = d.get("scan") or {}
        t = d.get("trades") or {}
        adv = sorted(s.get("advices", []), key=lambda x: x.get("score", 0), reverse=True)[:10] if s else []
        trades = []  # 隐私保护：不在公开 bundle 中暴露实际交易明细
        days_detail.append({
            "date": h["date"],
            "weekday": h["weekday"],
            "scan_time": s.get("scan_time", ""),
            "total_zt": s.get("total_zt", 0),
            "advices": adv,
            "trades": trades,
            "trade_count": len(trades),
            "advice_count": len(adv),
        })

    bundle = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rules": rules,
        "today": today,
        "history_10days": history,
        "days_detail": days_detail,
    }

    # 写入（供前端读取）
    out_path = OUT_DIR / "bundle.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=1)
    print(f"✅ 前端数据包: {out_path} ({out_path.stat().st_size//1024}KB)")

    # 也存一份带日期的快照（永久保留）
    snapshot = OUT_DIR / f"snapshot_{today}.json"
    shutil.copy(out_path, snapshot)

    # 复制盈亏汇总 + 推荐统计到前端可读目录
    for src_name, dst_name in [("portfolio.json", "portfolio.json"), ("recommendation_stats.json", "recommendation_stats.json")]:
        src = BASE / "data" / src_name
        if src.exists():
            dst = OUT_DIR / dst_name
            # 盈亏汇总可能含交易明细，做脱敏：只保留统计和持仓
            with open(src, encoding="utf-8") as f:
                d = json.load(f)
            # 移除 recent_realized 中的 reason/emotion（隐私）
            if "recent_realized" in d:
                for r in d["recent_realized"]:
                    r.pop("reason", None)
                    r.pop("emotion", None)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            print(f"✅ {dst_name}: {dst}")
    print(f"✅ 每日快照: {snapshot}")
    return out_path

if __name__ == "__main__":
    generate_bundle()
