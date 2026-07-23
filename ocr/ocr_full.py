"""
全图 OCR 流水：
1. 长图按 ~1200px 切块（每块重叠 150px）
2. 每块 3x 放大后 PaddleOCR
3. 按 y 坐标聚行，x 坐标聚列
4. 解析成结构化记录，写入 CSV + JSON
"""
import os, sys, json, time, re
import numpy as np
import pandas as pd
from PIL import Image
from paddleocr import PaddleOCR

SRC = "/root/.codebuddy/blobs/7a/7ace7c5994dc13493bac11c0fe0a5a00ff2dce0aadbdf830a911533301c05b8e.jpg"
OUT_DIR = "/workspace/stock_model/ocr"
os.makedirs(OUT_DIR, exist_ok=True)

CHUNK_H = 1200
OVERLAP = 150
UPSAMPLE = 3

def load_image():
    im = Image.open(SRC).convert("RGB")
    return im

def slice_chunks(im, chunk_h=CHUNK_H, overlap=OVERLAP):
    W, H = im.size
    chunks = []
    y = 0
    idx = 0
    while y < H:
        bottom = min(y + chunk_h, H)
        chunks.append((idx, y, bottom, W, H))
        if bottom == H:
            break
        y = bottom - overlap
        idx += 1
    return chunks

def ocr_chunk(ocr, im, top, bottom):
    W = im.size[0]
    seg = im.crop((0, top, W, bottom))
    seg_up = seg.resize((W * UPSAMPLE, (bottom - top) * UPSAMPLE), Image.LANCZOS)
    tmp_path = os.path.join(OUT_DIR, f"_chunk_{top}_{bottom}.png")
    seg_up.save(tmp_path)
    out = ocr.ocr(tmp_path, cls=True)
    os.remove(tmp_path)
    items = []
    if out and out[0]:
        for box, (txt, conf) in out[0]:
            x1, y1 = box[0]
            x2, y2 = box[2]
            # 把坐标缩回原图坐标
            cx = (x1 + x2) / 2 / UPSAMPLE
            cy = (y1 + y2) / 2 / UPSAMPLE + top
            items.append({
                "x": cx, "y": cy,
                "x1": x1 / UPSAMPLE, "y1": y1 / UPSAMPLE + top,
                "x2": x2 / UPSAMPLE, "y2": y2 / UPSAMPLE + top,
                "txt": txt, "conf": float(conf),
            })
    return items

def group_lines(items, y_tol=8):
    """按 y 坐标聚行"""
    if not items:
        return []
    items_sorted = sorted(items, key=lambda d: d["y"])
    lines = []
    cur = [items_sorted[0]]
    for it in items_sorted[1:]:
        if abs(it["y"] - cur[-1]["y"]) <= y_tol:
            cur.append(it)
        else:
            lines.append(sorted(cur, key=lambda d: d["x"]))
            cur = [it]
    lines.append(sorted(cur, key=lambda d: d["x"]))
    return lines

def main():
    im = load_image()
    W, H = im.size
    print(f"原图 {W}x{H}")
    chunks = slice_chunks(im)
    print(f"分块数 {len(chunks)}, 块高 {CHUNK_H}, 重叠 {OVERLAP}")

    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    all_items = []
    t0 = time.time()
    for i, (idx, top, bottom, W2, H2) in enumerate(chunks):
        ts = time.time()
        items = ocr_chunk(ocr, im, top, bottom)
        print(f"  块 {idx+1}/{len(chunks)} y=[{top},{bottom}] -> {len(items)} 条, {time.time()-ts:.1f}s")
        all_items.extend(items)
    print(f"OCR 总耗时 {time.time()-t0:.1f}s, 共 {len(all_items)} 条")

    # 存原始 OCR 结果
    with open(os.path.join(OUT_DIR, "ocr_raw.json"), "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=1)

    # 按行聚合
    lines = group_lines(all_items, y_tol=6)
    print(f"聚行 {len(lines)} 行")

    # 行落盘
    with open(os.path.join(OUT_DIR, "ocr_lines.json"), "w", encoding="utf-8") as f:
        json.dump([
            [{"x": it["x"], "txt": it["txt"], "conf": it["conf"]} for it in line]
            for line in lines
        ], f, ensure_ascii=False, indent=1)

    # 输出预览
    print("\n--- 前 10 行预览 ---")
    for line in lines[:10]:
        print("  | ".join(f"{it['txt']}" for it in line))

    print("\n--- 后 5 行预览 ---")
    for line in lines[-5:]:
        print("  | ".join(f"{it['txt']}" for it in line))

if __name__ == "__main__":
    main()
