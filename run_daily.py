"""
一键每日流程：扫描 → 建议 → 推送
==================================
python run_daily.py            # 扫描 + 建议 + (若有 webhook) 推送企业微信
python run_daily.py --no-push  # 只扫描 + 建议，不推送
"""
import sys
import subprocess
import importlib.util
from pathlib import Path

def run_script(path, args=None):
    cmd = [sys.executable, str(path)] + (args or [])
    print(f"\n▶ 运行: {' '.join(cmd)}")
    r = subprocess.run(cmd)
    return r.returncode == 0

def main():
    base = Path(".")
    print("=" * 60)
    print("股票投资模型 · 每日流程")
    print("=" * 60)

    # 1. 扫描
    if not run_script(base / "screener/scan.py"):
        print("❌ 扫描失败，终止")
        return

    # 2. 建议
    if not run_script(base / "screener/advise.py"):
        print("❌ 建议失败，终止")
        return

    # 3. 存档（永久保留）
    import json
    adv_path = base / "data/advices.json"
    if adv_path.exists():
        with open(adv_path, encoding="utf-8") as f:
            adv_data = json.load(f)
        spec = importlib.util.spec_from_file_location("history", base / "screener/history.py")
        hmod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hmod)
        p = hmod.archive_today_scan(adv_data)
        print(f"✅ 已存档: {p}")

    # 4. 推送（除非 --no-push）
    if "--no-push" not in sys.argv:
        # 动态 import wecom_bot 的 push
        spec = importlib.util.spec_from_file_location("wecom_bot", base / "delivery/wecom_bot.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        wh = mod.load_webhook()
        content = mod.render_markdown()
        if wh and content:
            mod.push(wh, content)
        else:
            print("ℹ️ 未配置企业微信 webhook，跳过推送（可用 `python delivery/wecom_bot.py <webhook_url>` 配置）")
    else:
        print("ℹ️ --no-push，跳过推送")

    print("\n✅ 完成。看板：streamlit run dashboard/app.py ｜ 手机app：python dashboard/standalone_app.py")

if __name__ == "__main__":
    main()
