"""
企业微信推送 v2：图片格式
========================
把 Top6 候选渲染成图片，推送到企业微信群。
图片不受 4096 字符限制，信息量大且清晰。
"""
import json
import os
import base64
import requests
from pathlib import Path
from datetime import datetime
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 中文字体
CJK_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if Path(CJK_PATH).exists():
    fm.fontManager.addfont(CJK_PATH)
    zh = fm.FontProperties(fname=CJK_PATH).get_name()
    matplotlib.rcParams['font.sans-serif'] = [zh]
    matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['axes.unicode_minus'] = False

ADVices_PATH = Path("data/advices.json")
IMG_PATH = Path("reports/daily_push.png")

def load_webhook():
    wh = os.getenv("WECOM_WEBHOOK")
    if wh:
        return wh
    cfg = Path("delivery/wecom_config.json")
    if cfg.exists():
        with open(cfg, encoding="utf-8") as f:
            return json.load(f).get("webhook")
    return None

def render_image(advices_data):
    """把 Top6 候选渲染成图片"""
    advices = advices_data.get("advices", [])
    scan_time = advices_data.get("scan_time", "")
    total_zt = advices_data.get("total_zt", 0)

    n = len(advices)
    if n == 0:
        return None

    fig, ax = plt.subplots(figsize=(10, 2.5 + n * 1.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2.5 + n * 1.8)
    ax.axis('off')
    fig.patch.set_facecolor('#0d1117')

    # 标题
    ax.text(5, 2.5 + n * 1.8 - 0.5, f'每日选股 Top{n}', ha='center', va='top',
            fontsize=18, fontweight='bold', color='#e6edf3')
    ax.text(5, 2.5 + n * 1.8 - 1.2, f'{scan_time} ｜ 今日涨停 {total_zt} 只 ｜ 同板块≤2只',
            ha='center', va='top', fontsize=10, color='#8b949e')

    y = 2.5 + n * 1.8 - 2.2
    for i, a in enumerate(advices):
        y_top = y - i * 1.8
        # 卡片背景
        rect = plt.Rectangle((0.3, y_top - 1.5), 9.4, 1.6, linewidth=1,
                              edgecolor='#30363d', facecolor='#161b22', zorder=1)
        ax.add_patch(rect)
        # 序号 + 名称
        ax.text(0.6, y_top - 0.3, f'{i+1}', fontsize=14, fontweight='bold', color='#d29922', va='top')
        ax.text(1.1, y_top - 0.3, a['name'], fontsize=15, fontweight='bold', color='#e6edf3', va='top')
        ax.text(1.1 + len(a['name'])*0.32, y_top - 0.3, a.get('code',''), fontsize=10, color='#8b949e', va='top')
        # 评分
        ax.text(9.2, y_top - 0.3, f'分{a["score"]:.2f}', fontsize=12, color='#d29922', va='top', ha='right')
        # 标签行
        tag = f'{a.get("path","")} ｜ 连板{a.get("zt_count",0)} ｜ {a.get("industry","")}'
        ax.text(1.1, y_top - 0.7, tag, fontsize=10, color='#8b949e', va='top')
        # 四个指标
        ax.text(1.1, y_top - 1.1, f'仓位 {int(a.get("pos_pct",0)*100)}%', fontsize=11, color='#3fb950', va='top')
        ax.text(3.3, y_top - 1.1, f'止损 {int(a.get("stop_pct",-8)*100)}%', fontsize=11, color='#f85149', va='top')
        ax.text(5.5, y_top - 1.1, f'目标 +{int(a.get("target_pct",15)*100)}%', fontsize=11, color='#3fb950', va='top')
        ax.text(7.7, y_top - 1.1, f'持仓 {a.get("max_hold_days",10)}天', fontsize=11, color='#58a6ff', va='top')

    ax.text(5, 0.3, '⚠️ 系统按规则生成，仅供参考，不构成投资建议',
            ha='center', fontsize=9, color='#8b949e')

    IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(IMG_PATH), dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    return IMG_PATH

def push_image(webhook, img_path):
    """推送图片到企业微信"""
    # 企业微信图片限制 2MB，需要 base64 + md5
    import hashlib
    with open(img_path, "rb") as f:
        img_data = f.read()
    # 如果超过 2MB，压缩
    if len(img_data) > 2 * 1024 * 1024:
        from PIL import Image
        im = Image.open(img_path)
        ratio = 0.7
        while len(img_data) > 2 * 1024 * 1024 and ratio > 0.1:
            new_size = (int(im.width * ratio), int(im.height * ratio))
            im2 = im.resize(new_size, Image.LANCZOS)
            im2.save(str(img_path), format='PNG', optimize=True)
            with open(img_path, "rb") as f2:
                img_data = f2.read()
            ratio -= 0.1

    b64 = base64.b64encode(img_data).decode()
    md5 = hashlib.md5(img_data).hexdigest()

    payload = {
        "msgtype": "image",
        "image": {"base64": b64, "md5": md5}
    }
    try:
        r = requests.post(webhook, json=payload, timeout=15)
        resp = r.json()
        if resp.get("errcode") == 0:
            print("✅ 企业微信图片推送成功")
            return True
        else:
            print(f"❌ 推送失败: {resp}")
            return False
    except Exception as e:
        print(f"❌ 推送异常: {e}")
        return False

def main():
    wh = load_webhook()
    if not wh:
        print("⚠️ 未配置 webhook")
        return
    if not ADVices_PATH.exists():
        print("❌ 先运行 screener/advise.py")
        return
    with open(ADVices_PATH, encoding="utf-8") as f:
        data = json.load(f)
    img = render_image(data)
    if img:
        print(f"✅ 图片已生成: {img} ({img.stat().st_size//1024}KB)")
        push_image(wh, img)

if __name__ == "__main__":
    main()
