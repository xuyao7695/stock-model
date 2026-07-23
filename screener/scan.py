"""
选股扫描器：题材板块资金流 + 技术突破量能
========================================
数据源（akshare）：
  - 涨停池 stock_zt_pool_em        → 连板/封单/炸板/行业（主）
  - 涨停池按行业聚合                → 题材热度（备用，无需额外请求）
  - 全市场 spot stock_zh_a_spot_em → 技术强势过滤（限流时跳过）

输出：candidates.json（候选池，含原始分 + 命中条件）
"""
import json
import time
import warnings
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
import akshare as ak

CONFIG_PATH = Path("screener/scan_config.json")
OUT_PATH = Path("data/candidates.json")

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

def safe_call(fn, *a, retries=4, delay=6, **k):
    last = None
    for i in range(retries):
        try:
            return fn(*a, **k)
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(delay)
    raise last

def get_trade_date():
    # 往前找最近交易日
    today = datetime.now()
    for i in range(0, 12):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        yield d

def industry_heat(zt_df):
    """按行业聚合涨停数 → 题材热度排名"""
    if zt_df is None or len(zt_df) == 0:
        return {}, {}
    counts = zt_df.groupby("所属行业").size().sort_values(ascending=False)
    heat = (counts / counts.max()).round(3).to_dict()  # 归一化 0-1
    return heat, counts.to_dict()

def scan_limit_up(zt_df, cfg, heat):
    """路径 A：涨停/连板战法（基于涨停池）"""
    ic = cfg["individual"]
    out = []
    for _, r in zt_df.iterrows():
        name = str(r.get("名称", ""))
        code = str(r.get("代码", ""))
        # ST / 新股 过滤
        if ic.get("exclude_st") and ("ST" in name or "*ST" in name):
            continue
        try:
            zt_count = int(r.get("连板数", 0))
        except:
            zt_count = 0
        if zt_count < ic.get("min_zt_count", 1) or zt_count > ic.get("max_zt_count", 5):
            continue
        try:
            broken = int(r.get("炸板次数", 0))
        except:
            broken = 0
        if broken > ic.get("max_broken_times", 0):
            continue
        try:
            seal = float(r.get("封板资金", 0) or 0)
        except:
            seal = 0
        if seal < ic.get("min_seal_money", 0):
            continue
        ind = str(r.get("所属行业", ""))
        h = heat.get(ind, 0.0)
        # 打分
        sc = cfg["scoring"]
        score = (min(zt_count, 5) / 5) * sc["zt_count"] \
               + min(seal / 5e8, 1) * sc["seal_money"] \
               + h * sc["industry_heat"]
        out.append({
            "code": code, "name": name, "path": "A-连板",
            "zt_count": zt_count, "seal_money": seal, "broken": broken,
            "industry": ind, "industry_heat": h,
            "change_pct": float(r.get("涨跌幅", 0) or 0),
            "cir_mv": float(r.get("流通市值", 0) or 0),
            "score": round(score, 3),
            "matched": ["连板数达标", "封单达标", "未炸板", f"行业热度{h:.2f}"],
            "raw": {k: r.get(k) for k in ["代码","名称","涨跌幅","连板数","封板资金","炸板次数","流通市值","所属行业","首次封板时间"]},
        })
    return out

def scan_strong(cfg):
    """路径 B：技术强势（全市场 spot，涨幅3-9.4% + 量比 + 换手）"""
    tc = cfg["technical"]
    if not tc.get("enabled") or not tc.get("scan_spot"):
        return []
    try:
        df = safe_call(ak.stock_zh_a_spot_em)
    except Exception as e:
        print(f"  ⚠️ spot 拉取失败（限流），跳过路径 B: {e}")
        return []
    df = df.copy()
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce")
    df["量比"] = pd.to_numeric(df["量比"], errors="coerce")
    mask = (
        (df["涨跌幅"] >= tc["min_change_pct"]) &
        (df["涨跌幅"] <= tc["max_change_pct"]) &
        (df["换手率"] >= tc["min_turnover_rate"]) &
        (df["量比"] >= tc["min_volume_ratio"])
    )
    sub = df[mask].copy()
    out = []
    sc = cfg["scoring"]
    for _, r in sub.iterrows():
        name = str(r.get("名称", ""))
        if "ST" in name or "*ST" in name:
            continue
        chg = float(r.get("涨跌幅", 0))
        vol = float(r.get("量比", 0) or 0)
        turn = float(r.get("换手率", 0) or 0)
        score = (chg / 10) * 0.5 + min(vol / 5, 1) * 0.3 + min(turn / 20, 1) * 0.2
        score *= sc["technical"]
        out.append({
            "code": str(r.get("代码", "")), "name": name, "path": "B-强势",
            "zt_count": 0, "seal_money": 0, "broken": 0,
            "industry": "—", "industry_heat": 0.0,
            "change_pct": chg, "cir_mv": 0.0,
            "score": round(score, 3),
            "matched": [f"涨幅{chg:.1f}%", f"量比{vol:.1f}", f"换手{turn:.1f}%"],
            "raw": {k: r.get(k) for k in ["代码","名称","最新价","涨跌幅","换手率","量比","市盈率-动态","市净率"]},
        })
    return out

def main():
    cfg = load_config()
    print("🔍 开始选股扫描...")
    zt_df = None
    for d in get_trade_date():
        try:
            zt_df = safe_call(ak.stock_zt_pool_em, date=d)
            if zt_df is not None and len(zt_df) > 0:
                print(f"  ✅ 涨停池 {d}: {len(zt_df)} 只")
                break
        except Exception as e:
            print(f"  ⚠️ {d} 失败: {e}")
            continue
    if zt_df is None:
        print("❌ 涨停池拉取失败")
        return

    heat, _ = industry_heat(zt_df)
    print(f"  ✅ 题材热度行业数: {len(heat)}")

    candidates = []
    if cfg["theme"].get("enabled"):
        candidates += scan_limit_up(zt_df, cfg, heat)
    candidates += scan_strong(cfg)

    # 按分排序
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_n = cfg.get("top_n", 20)
    candidates = candidates[:top_n]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "akshare (东方财富)",
        "total_zt": len(zt_df),
        "candidates": candidates,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"✅ 候选池已保存: {OUT_PATH} ({len(candidates)} 只)")
    print("\nTop 10 候选:")
    for c in candidates[:10]:
        print(f"  [{c['path']}] {c['name']}({c['code']}) 分={c['score']:.3f} 连板={c['zt_count']} 封单={c['seal_money']/1e4:.0f}万 行业={c['industry']}")
    return result

if __name__ == "__main__":
    main()
