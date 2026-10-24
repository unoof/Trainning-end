import os
import re
import pandas as pd

from crawl import OUT_DIR, norm_text
from cleanup import looks_ambiguous
from normalize import extract_features, is_dorm

# Ngưỡng lọc dữ liệu chuẩn cho bài toán Phòng trọ / CCMN
PRICE_MIN, PRICE_MAX = 1.2, 12.0     # triệu đồng/tháng
AREA_MIN, AREA_MAX = 10.0, 65.0      # m2

# Danh sách chuẩn các Quận/Huyện tại Hà Nội
# (không có 'tu liem' chung chung; chỉ giữ 'bac tu liem' và 'nam tu liem')
HANOI_DISTRICTS = {
    "ba dinh", "hoan kiem", "tay ho", "long bien", "cau giay", "dong da",
    "hai ba trung", "hoang mai", "thanh xuan", "nam tu liem", "bac tu liem", "ha dong",
    "son tay", "ba vi", "chuong my", "dan phuong", "dong anh", "gia lam",
    "hoai duc", "me linh", "my duc", "phu xuyen", "phuc tho", "quoc oai",
    "soc son", "thach that", "thanh oai", "thanh tri", "thuong tin", "ung hoa"
}

# Nhãn quận chung chung, không phân biệt được Bắc/Nam -> loại bỏ
DROP_DISTRICTS = {"tu liem"}


def extract_street_key(street_address, title):
    """Chuẩn hóa tên đường/ngõ để làm khóa lọc trùng kết hợp với Quận."""
    s = norm_text(street_address)
    s = re.sub(r"\b(ha noi|ho chi minh|tp hcm|viet nam)\b", "", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if parts:
        return parts[0]

    t = norm_text(title)
    m = re.search(r"\b(ngo\s+\d+\s*\w*|pho\s+\w+\s+\w+|duong\s+\w+\s+\w+)\b", t)
    return m.group(1) if m else ""

def clean_hanoi_data(df_raw):
    df = df_raw.copy()
    log = [("thô ban đầu", len(df))]

    # 1. Bỏ trùng ID trong cùng 1 nguồn
    df = df.drop_duplicates(subset=["source", "post_id"])
    log.append(("bỏ trùng theo (source, post_id)", len(df)))

    # 2. Bỏ các tin có district = 'tu liem' (chung chung), giữ 'bac tu liem' và 'nam tu liem'
    mask_tu_liem = df["district"].astype(str).str.strip().isin(DROP_DISTRICTS)
    print(f"-> Bỏ {int(mask_tu_liem.sum())} tin có district 'tu liem' chung chung "
          f"(giữ nguyên bac tu liem / nam tu liem).")
    df = df[~mask_tu_liem]
    log.append(("bỏ district 'tu liem' chung chung", len(df)))

    # 3. Chỉ giữ dữ liệu thuộc Hà Nội
    df = df[df["city"] == "ha noi"]
    df = df[df["district"].isin(HANOI_DISTRICTS)]
    log.append(("chỉ giữ các quận/huyện thuộc Hà Nội", len(df)))

    # 4. Bỏ ký túc xá / ở ghép / sleepbox
    mask_dorm = df.apply(lambda r: is_dorm(r["title"], r["text"]), axis=1)
    df = df[~mask_dorm]
    log.append(("bỏ ký túc xá / ở ghép / sleepbox", len(df)))

    # 5. Bỏ tin khoảng giá/diện tích mơ hồ
    mask_amb = df.apply(lambda r: looks_ambiguous(r["title"], r["text"]), axis=1).astype(bool)
    df = df[~mask_amb]
    log.append(("bỏ tin giá/diện tích dạng khoảng", len(df)))

    # 6. Lọc Outliers theo Giá và Diện tích
    df = df[df["price"].between(PRICE_MIN, PRICE_MAX)]
    log.append((f"giá trong [{PRICE_MIN}, {PRICE_MAX}] triệu", len(df)))

    df = df[df["area"].between(AREA_MIN, AREA_MAX)]
    log.append((f"diện tích trong [{AREA_MIN}, {AREA_MAX}] m2", len(df)))

    # 7. Gộp trùng giữa 2 sàn theo (Quận, Đường/Ngõ, Giá, Diện tích)
    df["_street_key"] = df.apply(lambda r: extract_street_key(r["street_address"], r["title"]), axis=1)
    df["_price_key"] = df["price"].round(1)
    df["_area_key"] = df["area"].round(0)

    df = df.sort_values("source").groupby(
        ["city", "district", "_street_key", "_price_key", "_area_key"], as_index=False
    ).agg({
        "post_id": "first",
        "source": lambda s: "+".join(sorted(set(s))),
        "title": "first",
        "price": "mean",
        "area": "first",
        "street_address": "first",
        "url": "first",
        "vip_stars": "first",
        "ptype": "first",
        "text": lambda texts: " ".join(str(t) for t in texts)
    }).drop(columns=["_street_key", "_price_key", "_area_key"])
    log.append(("gộp trùng theo (địa chỉ, giá, diện tích)", len(df)))

    # 8. Trích xuất 12 cột tiện ích nhị phân (0/1)
    feats = df["text"].map(extract_features).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), feats.reset_index(drop=True)], axis=1)

    print("\nSố dòng sau từng bước:")
    for name, n in log:
        print(f"  {n:6d}  {name}")
    return df

if __name__ == "__main__":
    frames = []
    for filename in ["raw_chotot.csv", "raw_phongtro123.csv"]:
        path = os.path.join(OUT_DIR, filename)
        if os.path.exists(path):
            frames.append(pd.read_csv(path))
            print(f"Đã nạp {path} ({len(frames[-1])} dòng)")

    if not frames:
        print("Không tìm thấy file raw_*.csv trong thư mục data/!")
    else:
        raw_all = pd.concat(frames, ignore_index=True)
        clean_df = clean_hanoi_data(raw_all)

        out_path = os.path.join(OUT_DIR, "phongtro_clean.csv")
        clean_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"\nĐã cập nhật file sạch tại: {out_path}")

        print("\nTin mỗi quận (Top 10):")
        print(clean_df["district"].value_counts().head(10).to_string())