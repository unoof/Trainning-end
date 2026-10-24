import re
import pandas as pd
from normalize import norm_text, is_dorm, looks_ambiguous, extract_features

PRICE_MIN, PRICE_MAX = 0.8, 30.0
AREA_MIN, AREA_MAX = 8.0, 120.0


def extract_street_key(street_address, title):
    """
    Chuẩn hóa địa chỉ đường/ngõ để lọc trùng chính xác hơn cấp Quận.
    Ưu tiên lấy từ cột street_address, nếu trống thì dò tên ngõ/đường trong title.
    """
    s = norm_text(street_address)
    # Bỏ các phần tên quận/thành phố ở cuối địa chỉ để lấy tên đường/phường
    s = re.sub(r"\b(ha noi|ho chi minh|tp hcm|viet nam)\b", "", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if parts:
        return parts[0]  # Lấy phần cụ thể nhất (Số nhà / Tên đường / Tên phường)
    
    # Dự phòng: tìm tên đường/ngõ/phố trong tiêu đề
    t = norm_text(title)
    m = re.search(r"\b(ngo\s+\d+\s*\w*|pho\s+\w+\s+\w+|duong\s+\w+\s+\w+)\b", t)
    return m.group(1) if m else ""

def clean(df_raw):
    df = df_raw.copy()
    log = [("thô", len(df))]

    df = df.drop_duplicates(subset=["source", "post_id"])
    log.append(("bỏ trùng theo (source, post_id)", len(df)))

    mask_dorm = df.apply(lambda r: is_dorm(r["title"], r["text"]), axis=1)
    df = df[~mask_dorm]
    log.append(("bỏ ký túc xá / ở ghép / sleepbox", len(df)))

    mask_amb = df.apply(lambda r: looks_ambiguous(r["title"], r["text"]), axis=1).astype(bool)
    df = df[~mask_amb]
    log.append(("bỏ tin giá/diện tích dạng khoảng", len(df)))

    df = df[df["price"].between(PRICE_MIN, PRICE_MAX)]
    log.append((f"giá trong [{PRICE_MIN}, {PRICE_MAX}] triệu", len(df)))

    df = df[df["area"].between(AREA_MIN, AREA_MAX)]
    log.append((f"diện tích trong [{AREA_MIN}, {AREA_MAX}] m2", len(df)))

    df = df[df["district"] != ""]
    log.append(("có quận/huyện", len(df)))

    # Tạo khóa lọc trùng theo: (Thành phố, Quận, Địa chỉ đường/phường, Giá làm tròn, Diện tích làm tròn)
    df["_street_key"] = df.apply(lambda r: extract_street_key(r["street_address"], r["title"]), axis=1)
    df["_price_key"] = df["price"].round(1)
    df["_area_key"] = df["area"].round(0)

    # Gộp các tin trùng giữa Chợ Tốt và Phongtro123 (nối văn bản mô tả để không sót tiện ích)
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

    # Trích xuất feature từ văn bản đã gộp
    feats = df["text"].map(extract_features).apply(pd.Series)
    df = pd.concat([df.reset_index(drop=True), feats.reset_index(drop=True)], axis=1)

    print("\nSố dòng sau từng bước:")
    for name, n in log:
        print(f"  {n:6d}  {name}")
    return df
