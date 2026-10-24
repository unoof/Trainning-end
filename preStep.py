import argparse
import os
import pandas as pd
from crawl import crawl_chotot, crawl_phongtro123
from cleanup import clean

OUT_DIR = "data"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=50, help="số trang mỗi nguồn")
    ap.add_argument("--city", default="ha-noi")
    ap.add_argument("--detail", action="store_true", help="tải trang chi tiết Phongtro123")
    ap.add_argument("--source", default="all", choices=["all", "chotot", "phongtro123"])
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    region = {"ha-noi": "12000"}[args.city]

    frames = []
    if args.source in ("all", "chotot"):
        ct = crawl_chotot(args.pages, region)
        if ct:
            d = pd.DataFrame(ct)
            d.to_csv(os.path.join(OUT_DIR, "raw_chotot.csv"), index=False, encoding="utf-8-sig")
            frames.append(d)
    if args.source in ("all", "phongtro123"):
        pt = crawl_phongtro123(args.pages, args.city, args.detail)
        if pt:
            d = pd.DataFrame(pt)
            d.to_csv(os.path.join(OUT_DIR, "raw_phongtro123.csv"), index=False, encoding="utf-8-sig")
            frames.append(d)

    if not frames:
        print("Không thu được dữ liệu nào. Kiểm tra mạng / selector / API.")
        return

    raw = pd.concat(frames, ignore_index=True)
    clean_df = clean(raw)
    if clean_df.empty:
        print("Sau khi làm sạch không còn dòng nào, xem lại ngưỡng lọc.")
        return

    out = os.path.join(OUT_DIR, "phongtro_clean.csv")
    clean_df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nĐã lưu {out}")

    cols = ["source", "district", "ptype", "price", "area", "has_ac", "furnished", "has_balcony"]
    print(clean_df[cols].head(10).to_string(index=False))
    print("\nTin mỗi quận (top 10):")
    print(clean_df["district"].value_counts().head(10).to_string())
    print("\nTỷ lệ feature = 1 (nếu gần 0% thì văn bản mô tả đang bị cắt):")
    feat_cols = [c for c in clean_df.columns if c.startswith(("has_", "private_", "free_", "no_shared", "furnished"))]
    print((clean_df[feat_cols].mean() * 100).round(1).astype(str).add("%").to_string())


if __name__ == "__main__":
    main()