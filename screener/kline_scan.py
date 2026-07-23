"""
K线形态 + 量能配合 选股策略（路径 C）
======================================
独立于涨停池选股，基于经典技术分析：

信号类型：
  C1-放量突破  ：股价突破近N日高点，成交量放大≥2倍
  C2-缩量回踩  ：股价回踩均线（5/10/20日）缩量企稳
  C3-倍量柱    ：单日成交量≥前5日均量2倍，且涨幅>3%
  C4-早晨之星  ：三根K线组合（跌→十字星→涨）反转信号
  C5-红三兵    ：连续三根小阳线递增，温和放量
  C6-锤头线    ：下影线>实体2倍，出现在下跌末端
  C7-阳包阴    ：当日阳线完全包住昨日阴线，放量

数据源：akshare 个股历史行情（前复权）
输出：kline_candidates.json
"""
import json
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
import akshare as ak

CONFIG_PATH = Path("screener/kline_config.json")
OUT_PATH = Path("data/kline_candidates.json")


def load_config():
    if not CONFIG_PATH.exists():
        # 默认配置
        cfg = {
            "scan_universe": "zt_pool",
            "history_days": 60,
            "min_volume_multiple": 2.0,
            "min_change_pct": 3.0,
            "ma_periods": [5, 10, 20],
            "breakout_lookback": 20,
            "top_n": 20,
            "exclude_st": True,
            "signals": {
                "c1_breakout_volume": true,
                "c2_pullback_shrink": true,
                "c3_double_volume": true,
                "c4_morning_star": true,
                "c5_three_soldiers": true,
                "c6_hammer": true,
                "c7_bullish_engulfing": true
            },
            "scoring": {
                "c1_breakout_volume": 0.25,
                "c2_pullback_shrink": 0.20,
                "c3_double_volume": 0.15,
                "c4_morning_star": 0.15,
                "c5_three_soldiers": 0.10,
                "c6_hammer": 0.10,
                "c7_bullish_engulfing": 0.15,
                "volume_confirm_bonus": 0.10,
                "ma_align_bonus": 0.10
            }
        }
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return cfg
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def safe_call(fn, *a, retries=3, delay=5, **k):
    last = None
    for i in range(retries):
        try:
            return fn(*a, **k)
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(delay)
    raise last


def get_kline(code, days=60):
    """获取个股前复权日K线"""
    df = safe_call(ak.stock_zh_a_hist, symbol=code, period="daily",
                   start_date=(datetime.now() - pd.Timedelta(days=days+30)).strftime("%Y%m%d"),
                   end_date=datetime.now().strftime("%Y%m%d"), adjust="qfq")
    if df is None or len(df) == 0:
        return None
    df = df.tail(days).copy()
    df.columns = [c.strip() for c in df.columns]
    # 统一列名
    col_map = {"日期": "date", "开盘": "open", "收盘": "close",
               "最高": "high", "最低": "low", "成交量": "volume",
               "成交额": "amount", "涨跌幅": "pct_chg"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    for c in ["open", "close", "high", "low", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "pct_chg" in df.columns:
        df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
    else:
        df["pct_chg"] = df["close"].pct_change() * 100
    df = df.dropna(subset=["open", "close", "high", "low", "volume"]).reset_index(drop=True)
    return df


def calc_ma(df, periods=[5, 10, 20]):
    """计算均线"""
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(p).mean()
    return df


def calc_avg_volume(df, window=5):
    """计算N日均量"""
    df[f"vol_ma{window}"] = df["volume"].rolling(window).mean()
    return df


# ============ 信号检测函数 ============

def signal_c1_breakout_volume(df, lookback=20, min_vol_mult=2.0):
    """C1-放量突破：最新价突破近N日最高价，且量比≥min_vol_mult"""
    if len(df) < lookback + 1:
        return False, {}
    prev_high = df["high"].iloc[-lookback-1:-1].max()
    last = df.iloc[-1]
    if last["close"] <= prev_high:
        return False, {}
    vol_ma = df["volume"].iloc[-6:-1].mean()
    if vol_ma == 0:
        return False, {}
    vol_ratio = last["volume"] / vol_ma
    if vol_ratio < min_vol_mult:
        return False, {}
    return True, {
        "breakout_high": round(prev_high, 2),
        "vol_ratio": round(vol_ratio, 2),
        "close": round(last["close"], 2)
    }


def signal_c2_pullback_shrink(df, ma_period=10, max_change=2.0):
    """C2-缩量回踩：股价回踩均线附近（±2%），成交量萎缩"""
    if len(df) < ma_period + 3:
        return False, {}
    ma_col = f"ma{ma_period}"
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if ma_col not in df.columns:
        return False, {}
    ma_val = last[ma_col]
    # 回踩：当日价格接近均线
    dist = abs(last["close"] - ma_val) / ma_val * 100
    if dist > max_change:
        return False, {}
    # 前几天在均线上方（趋势向上）
    above = (df["close"].iloc[-6:-2] > df[ma_col].iloc[-6:-2]).sum()
    if above < 2:
        return False, {}
    # 缩量：当日量 < 5日均量
    vol_ma = df["volume"].iloc[-6:-1].mean()
    if vol_ma == 0 or last["volume"] >= vol_ma:
        return False, {}
    vol_shrink = last["volume"] / vol_ma
    return True, {
        "ma": round(ma_val, 2),
        "distance_pct": round(dist, 2),
        "vol_shrink_ratio": round(vol_shrink, 2)
    }


def signal_c3_double_volume(df, min_chg=3.0, min_vol_mult=2.0):
    """C3-倍量柱：单日量≥5日均量2倍，涨幅>3%"""
    if len(df) < 6:
        return False, {}
    last = df.iloc[-1]
    if last["pct_chg"] < min_chg:
        return False, {}
    vol_ma = df["volume"].iloc[-6:-1].mean()
    if vol_ma == 0:
        return False, {}
    vol_ratio = last["volume"] / vol_ma
    if vol_ratio < min_vol_mult:
        return False, {}
    # 阳线
    if last["close"] <= last["open"]:
        return False, {}
    return True, {
        "vol_ratio": round(vol_ratio, 2),
        "pct_chg": round(last["pct_chg"], 2)
    }


def signal_c4_morning_star(df):
    """C4-早晨之星：三根K线（大阴→十字星→大阳）"""
    if len(df) < 3:
        return False, {}
    d1, d2, d3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    # 第一天：大阴线（跌幅>2%）
    if d1["pct_chg"] > -2:
        return False, {}
    # 第二天：十字星（实体小，振幅<2%）
    body2 = abs(d2["close"] - d2["open"])
    range2 = d2["high"] - d2["low"]
    if range2 == 0 or body2 / range2 > 0.3 or range2 / d2["close"] * 100 > 3:
        return False, {}
    # 第三天：大阳线（涨幅>2%），收盘高于第一天实体中点
    if d3["pct_chg"] < 2:
        return False, {}
    mid1 = (d1["open"] + d1["close"]) / 2
    if d3["close"] <= mid1:
        return False, {}
    return True, {
        "d1_chg": round(d1["pct_chg"], 2),
        "d3_chg": round(d3["pct_chg"], 2)
    }


def signal_c5_three_soldiers(df, min_chg=1.0):
    """C5-红三兵：连续三根阳线，收盘递增，温和放量"""
    if len(df) < 4:
        return False, {}
    d1, d2, d3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    # 三根阳线
    for d in [d1, d2, d3]:
        if d["close"] <= d["open"]:
            return False, {}
    # 收盘递增
    if not (d2["close"] > d1["close"] and d3["close"] > d2["close"]):
        return False, {}
    # 每根涨幅≥1%
    if d1["pct_chg"] < min_chg or d2["pct_chg"] < min_chg or d3["pct_chg"] < min_chg:
        return False, {}
    # 温和放量（三日量递增或持平）
    if d3["volume"] < d1["volume"] * 0.8:
        return False, {}
    return True, {
        "d1_chg": round(d1["pct_chg"], 2),
        "d2_chg": round(d2["pct_chg"], 2),
        "d3_chg": round(d3["pct_chg"], 2)
    }


def signal_c6_hammer(df, min_shadow_ratio=2.0):
    """C6-锤头线：下影线≥实体2倍，出现在下跌末端"""
    if len(df) < 5:
        return False, {}
    last = df.iloc[-1]
    body = abs(last["close"] - last["open"])
    if body == 0:
        return False, {}
    lower_shadow = min(last["open"], last["close"]) - last["low"]
    upper_shadow = last["high"] - max(last["open"], last["close"])
    # 下影线≥实体2倍，上影线短
    if lower_shadow < body * min_shadow_ratio:
        return False, {}
    if upper_shadow > body * 0.5:
        return False, {}
    # 前5日有下跌趋势
    prev_chg = df["pct_chg"].iloc[-6:-1].sum()
    if prev_chg > -3:
        return False, {}
    return True, {
        "lower_shadow_ratio": round(lower_shadow / body, 2),
        "prev_5d_chg": round(prev_chg, 2)
    }


def signal_c7_bullish_engulfing(df, min_vol_mult=1.5):
    """C7-阳包阴：当日阳线完全包住昨日阴线，放量"""
    if len(df) < 2:
        return False, {}
    d1, d2 = df.iloc[-2], df.iloc[-1]
    # 昨日阴线
    if d1["close"] >= d1["open"]:
        return False, {}
    # 今日阳线
    if d2["close"] <= d2["open"]:
        return False, {}
    # 包住：今日开盘≤昨日收盘，今日收盘≥昨日开盘
    if d2["open"] > d1["close"] or d2["close"] < d1["open"]:
        return False, {}
    # 放量
    if len(df) >= 6:
        vol_ma = df["volume"].iloc[-6:-1].mean()
        if vol_ma > 0 and d2["volume"] / vol_ma < min_vol_mult:
            return False, {}
    return True, {
        "d1_chg": round(d1["pct_chg"], 2),
        "d2_chg": round(d2["pct_chg"], 2)
    }


def check_ma_alignment(df):
    """均线多头排列：MA5 > MA10 > MA20"""
    if "ma5" not in df.columns or "ma10" not in df.columns or "ma20" not in df.columns:
        return False
    last = df.iloc[-1]
    return last["ma5"] > last["ma10"] > last["ma20"]


def analyze_stock(code, name, cfg):
    """分析单只股票的K线形态与量能"""
    df = get_kline(code, days=cfg.get("history_days", 60))
    if df is None or len(df) < 20:
        return None

    df = calc_ma(df, cfg.get("ma_periods", [5, 10, 20]))
    df = calc_avg_volume(df, window=5)

    signals_cfg = cfg.get("signals", {})
    scoring = cfg.get("scoring", {})

    matched_signals = []
    signal_details = {}
    score = 0.0

    # 检测各信号
    signal_checks = [
        ("c1_breakout_volume", signal_c1_breakout_volume,
         [cfg.get("breakout_lookback", 20), cfg.get("min_volume_multiple", 2.0)]),
        ("c2_pullback_shrink", signal_c2_pullback_shrink, [10, 2.0]),
        ("c3_double_volume", signal_c3_double_volume,
         [cfg.get("min_change_pct", 3.0), cfg.get("min_volume_multiple", 2.0)]),
        ("c4_morning_star", signal_c4_morning_star, []),
        ("c5_three_soldiers", signal_c5_three_soldiers, [1.0]),
        ("c6_hammer", signal_c6_hammer, [2.0]),
        ("c7_bullish_engulfing", signal_c7_bullish_engulfing, [1.5]),
    ]

    for sig_name, sig_fn, sig_args in signal_checks:
        if not signals_cfg.get(sig_name, True):
            continue
        try:
            hit, detail = sig_fn(df, *sig_args)
        except Exception:
            hit, detail = False, {}
        if hit:
            matched_signals.append(sig_name)
            signal_details[sig_name] = detail
            score += scoring.get(sig_name, 0.15)

    if not matched_signals:
        return None

    # 均线多头排列加成
    ma_aligned = check_ma_alignment(df)
    if ma_aligned:
        score += scoring.get("ma_align_bonus", 0.10)

    # 量能确认加成（最近3日量均>5日均量）
    if len(df) >= 8:
        vol_ma5 = df["volume"].iloc[-8:-3].mean()
        recent_vol = df["volume"].iloc[-3:].mean()
        if vol_ma5 > 0 and recent_vol > vol_ma5 * 1.2:
            score += scoring.get("volume_confirm_bonus", 0.10)

    last = df.iloc[-1]
    return {
        "code": code,
        "name": name,
        "path": "C-K线量能",
        "signals": matched_signals,
        "signal_details": signal_details,
        "ma_aligned": ma_aligned,
        "close": round(last["close"], 2),
        "pct_chg": round(last["pct_chg"], 2),
        "volume": int(last["volume"]),
        "score": round(min(score, 1.0), 3),
        "matched": [describe_signal(s) for s in matched_signals],
    }


def describe_signal(sig_name):
    """信号中文名"""
    names = {
        "c1_breakout_volume": "放量突破",
        "c2_pullback_shrink": "缩量回踩",
        "c3_double_volume": "倍量柱",
        "c4_morning_star": "早晨之星",
        "c5_three_soldiers": "红三兵",
        "c6_hammer": "锤头线",
        "c7_bullish_engulfing": "阳包阴",
    }
    return names.get(sig_name, sig_name)


def get_scan_universe(cfg):
    """获取扫描范围：涨停池或自定义列表"""
    universe = cfg.get("scan_universe", "zt_pool")
    stocks = []

    if universe == "zt_pool":
        # 从涨停池获取当日标的
        today = datetime.now()
        for i in range(0, 12):
            d = (today - pd.Timedelta(days=i)).strftime("%Y%m%d")
            try:
                zt_df = safe_call(ak.stock_zt_pool_em, date=d)
                if zt_df is not None and len(zt_df) > 0:
                    for _, r in zt_df.iterrows():
                        name = str(r.get("名称", ""))
                        if cfg.get("exclude_st", True) and ("ST" in name or "*ST" in name):
                            continue
                        stocks.append((str(r.get("代码", "")), name))
                    break
            except Exception:
                continue
    elif universe == "spot_strong":
        # 从全市场涨幅前50获取
        try:
            df = safe_call(ak.stock_zh_a_spot_em)
            df = df.sort_values("涨跌幅", ascending=False).head(50)
            for _, r in df.iterrows():
                name = str(r.get("名称", ""))
                if cfg.get("exclude_st", True) and ("ST" in name or "*ST" in name):
                    continue
                stocks.append((str(r.get("代码", "")), name))
        except Exception as e:
            print(f"  ⚠️ spot拉取失败: {e}")
    elif isinstance(universe, list):
        # 自定义股票列表 [["000001","平安银行"], ...]
        stocks = universe

    return stocks


def main():
    cfg = load_config()
    print("📈 K线形态+量能策略扫描开始...")
    print(f"  扫描范围: {cfg.get('scan_universe', 'zt_pool')}")

    stocks = get_scan_universe(cfg)
    print(f"  待扫描: {len(stocks)} 只")

    results = []
    for i, (code, name) in enumerate(stocks):
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(stocks)}")
        try:
            r = analyze_stock(code, name, cfg)
            if r:
                results.append(r)
                sig_str = "+".join(r["matched"])
                print(f"  ✅ {name}({code}) 信号: {sig_str} 分={r['score']:.3f}")
        except Exception as e:
            print(f"  ⚠️ {name}({code}) 分析失败: {e}")
        time.sleep(0.3)  # 限速

    # 按分排序
    results.sort(key=lambda x: x["score"], reverse=True)
    top_n = cfg.get("top_n", 20)
    results = results[:top_n]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": "K线形态+量能配合",
        "signals_used": ["放量突破", "缩量回踩", "倍量柱", "早晨之星", "红三兵", "锤头线", "阳包阴"],
        "total_scanned": len(stocks),
        "total_hits": len(results),
        "candidates": results,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)

    print(f"\n✅ K线策略扫描完成: {len(results)}/{len(stocks)} 只命中")
    print(f"   结果已保存: {OUT_PATH}")
    print("\n信号统计:")
    sig_count = {}
    for r in results:
        for s in r["matched"]:
            sig_count[s] = sig_count.get(s, 0) + 1
    for s, c in sorted(sig_count.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}次")

    return output


if __name__ == "__main__":
    main()
