import re
import unicodedata

# Tin tính giá theo giường / không phải phòng riêng -> loại
DORM_KW = ["ky tuc xa", "ktx", "sleepbox", "sleep box", "o ghep", "tim nguoi o ghep",
           "pass slot", "giuong tang", "giuong ky tuc"]
_PREFIX = re.compile(r"^(quan|huyen|thi xa|thanh pho|tp\.?)\s+")

def norm_text(s):
    """Chữ thường, bỏ dấu, '-'/'_' thành khoảng trắng, gọn khoảng trắng."""
    if s is None or (isinstance(s, float) and s != s):
        return ""
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    s = re.sub(r"[-_]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def norm_district(s):
    """
    'Quận Cầu Giấy, Hà Nội' | 'quan-cau-giay' | 'Cầu Giấy' -> 'cau giay'
    """
    parts = [p.strip() for p in norm_text(s).split(",") if p.strip()]
    if not parts:
        return ""
    target = next((p for p in parts if _PREFIX.match(p)), parts[0])
    return _PREFIX.sub("", target).strip()

def has_kw(text_norm, keywords):
    for k in keywords:
        for m in re.finditer(r"\b" + re.escape(k) + r"\b", text_norm):
            # chỉ xét phần cùng mệnh đề, phía trước từ khóa
            clause = re.split(r"[,.;:+/()\n]", text_norm[:m.start()])[-1]
            if re.search(r"\b(khong|chua|het|thieu)\b(?!\s+gian)", clause[-20:]):
                continue
            return 1
    return 0

def extract_features(text):
    t = norm_text(text)
    return {
        "has_ac":        has_kw(t, ["dieu hoa", "may lanh"]),
        "has_loft":      has_kw(t, ["gac xep", "gac lung", "co gac", "gac cao"]),
        "has_balcony":   has_kw(t, ["ban cong"]),
        "private_wc":    has_kw(t, ["khep kin", "wc rieng", "ve sinh rieng", "toilet rieng"]),
        "free_hours":    has_kw(t, ["gio giac tu do", "gio tu do", "tu do gio giac"]),
        "no_shared_owner": has_kw(t, ["khong chung chu", "khong o chung chu"]),
        "has_elevator":  has_kw(t, ["thang may"]),
        "has_washer":    has_kw(t, ["may giat"]),
        "has_fridge":    has_kw(t, ["tu lanh"]),
        "furnished":     has_kw(t, ["full noi that", "day du noi that", "full do", "du do",
                                    "noi that day du", "co san noi that", "trang bi day du"]),
        "has_security":  has_kw(t, ["bao ve", "camera", "van tay", "an ninh 24"]),
        "has_parking":   has_kw(t, ["de xe", "cho gui xe", "ham xe", "bai xe", "nha xe"]),
    }


def detect_ptype(title):
    t = norm_text(title)
    if "can ho dich vu" in t or "chdv" in t:
        return "can_ho_dich_vu"
    if "can ho mini" in t or "chung cu mini" in t or "ccmn" in t:
        return "can_ho_mini"
    if "can ho" in t or "chung cu" in t:
        return "can_ho"
    return "phong_tro"


def looks_ambiguous(title, text):
    """Chỉ lọc các tin ghi giá/diện tích dạng khoảng hoặc báo còn trống nhiều phòng."""
    t = norm_text(f"{title} {text}")
    return int(bool(
        re.search(r"\btu \d+[\d.,]*\s*(tr|trieu|k)\b", t)
        or re.search(r"\b\d+\s*-\s*\d+\s*m2?\b", t)
        or re.search(r"\b(trong|con|he thong|toa)\s+\d+\s*phong\b", t)
    ))


def is_dorm(title, text):
    t = norm_text(f"{title} {text}")
    return any(k in t for k in DORM_KW)
