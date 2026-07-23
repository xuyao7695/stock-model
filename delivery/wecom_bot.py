"""
企业微信群机器人推送
===================
把每日选股 + 操作建议推送到企业微信群机器人 webhook。

配置：delivery/wecom_config.json 或 环境变量 WECOM_WEBHOOK
消息格式：markdown（企业微信支持有限 markdown 语法）

用法：
    python delivery/wecom_bot.py          # 推送今日建议（若有 webhook）
    python delivery/wecom_bot.py --test    # 仅打印，不推送
"""
import json
import os
import sys
import requests
from pathlib import Path
from datetime import datetime

CONFIG_PATH = Path("delivery/wecom_config.json")
ADVICE_PATH = Path("reports/每日操作建议.md")

def load_webhook():
    # 优先环境变量
    wh = os.getenv("WECOM_WEBHOOK")
    if wh:
        return wh
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("webhook")
    return None

def save_webhook(webhook):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"webhook": webhook}, f, ensure_ascii=False, indent=1)
    print(f"✅ webhook 已保存: {CONFIG_PATH}")

def render_markdown(report_path=ADVICE_PATH, max_items=5):
    """把 Markdown 报告精简成企业微信可发的短版（<4096 字符）"""
    if not report_path.exists():
        return None
    with open(report_path, encoding="utf-8") as f:
        text = f.read()
    # 取标题 + 风控状态 + 前 N 只建议
    lines = text.split("\n")
    out = []
    item_count = 0
    in_disc = False
    for ln in lines:
        # 跳过交易纪律详情（太长），只保留关键行
        if ln.strip().startswith("⛔") or ln.strip().startswith("🛑") or ln.strip().startswith("🎯") or ln.strip().startswith("⏱") or ln.strip().startswith("📝") or ln.strip().startswith("🔥"):
            continue
        out.append(ln)
        if ln.startswith("### "):
            item_count += 1
            if item_count > max_items:
                break
    body = "\n".join(out)
    # 企业微信 markdown 限制：<4096 字符
    if len(body) > 3900:
        body = body[:3900] + "\n\n> …更多见完整报告"
    return body

def push(webhook, content):
    if not webhook:
        print("⚠️ 未配置 webhook，仅打印：")
        print(content)
        return False
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
        r = requests.post(webhook, json=payload, timeout=10)
        resp = r.json()
        if resp.get("errcode") == 0:
            print("✅ 企业微信推送成功")
            return True
        else:
            print(f"❌ 推送失败: {resp}")
            return False
    except Exception as e:
        print(f"❌ 推送异常: {e}")
        return False

def main():
    test = "--test" in sys.argv
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        wh = sys.argv[1]
        save_webhook(wh)
    else:
        wh = load_webhook()

    content = render_markdown()
    if not content:
        print("❌ 没有可推送的报告，先运行 screener/advise.py")
        return

    if test:
        print(content)
    else:
        push(wh, content)

if __name__ == "__main__":
    main()
