import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from normalize import norm_text, norm_district, detect_ptype


HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}
OUT_DIR = "data"

def get_with_retry(url, retries=3, timeout=12):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                wait = 15 * (i + 1)
                print(f"  HTTP {r.status_code}, chờ {wait}s rồi thử lại...")
                time.sleep(wait)
                continue
            print(f"  HTTP {r.status_code} cho {url}")
            return None
        except requests.RequestException as e:
            print(f"  Lỗi mạng ({e}), thử lại {i + 1}/{retries}")
            time.sleep(3)
    return None


# ======================================================================
# 2. CHỢ TỐT (API JSON)
# ======================================================================

def crawl_chotot(max_pages=50, region_v2="12000"):
    rows, limit = [], 20
    print("Đang cào Chợ Tốt...")
    for page in range(max_pages):
        url = (f"https://gateway.chotot.com/v1/public/ad-listing?cg=1050"
               f"&region_v2={region_v2}&st=u,h&limit={limit}&o={page * limit}")
        res = get_with_retry(url)
        if res is None:
            continue
        try:
            ads = res.json().get("ads", [])
        except ValueError:
            print("  Phản hồi không phải JSON")
            continue
        if page == 0 and ads:
            os.makedirs(OUT_DIR, exist_ok=True)
            with open(os.path.join(OUT_DIR, "chotot_sample_ad.json"), "w", encoding="utf-8") as f:
                json.dump(ads[0], f, ensure_ascii=False, indent=2)
        if not ads:
            print(f"  Trang {page + 1}: không có tin, dừng.")
            break

        for ad in ads:
            price = (ad.get("price") or 0) / 1_000_000
            area = ad.get("size") or 0
            title = (ad.get("subject") or "").strip()
            body = ad.get("body") or ""
            text = f"{title} {body}"
            district_raw = ad.get("area_name") or ""
            rows.append({
                "post_id": str(ad.get("list_id") or ""),
                "source": "Chotot",
                "title": title,
                "price": round(float(price), 3),
                "area": float(area),
                "city": norm_text(ad.get("region_name") or ""),
                "district": norm_district(district_raw),
                "street_address": ", ".join(x for x in [ad.get("street_name"), ad.get("ward_name"),
                                                        district_raw] if x),
                "url": f"https://www.chotot.com/{ad.get('list_id')}" if ad.get("list_id") else "",
                "vip_stars": None,
                "ptype": detect_ptype(title),
                "text": text,
            })
        time.sleep(0.8)
    print(f"-> Chợ Tốt: {len(rows)} tin thô.")
    return rows


# ======================================================================
# 3. PHONGTRO123 (HTML)
# ======================================================================

def parse_phongtro123_page(html):
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("ul.post__listing > li")
    if not items:
        print("  CẢNH BÁO: không thấy tin nào (selector sai / bị chặn / trang render bằng JS?)")
    rows = []
    for li in items:
        btn = li.select_one("[data-post-id]")
        post_id = btn["data-post-id"] if btn else ""

        ld = {}
        s = li.find("script", type="application/ld+json")
        if s and s.string:
            try:
                ld = json.loads(s.string)
            except json.JSONDecodeError:
                pass

        # Giá (triệu): ưu tiên JSON-LD (VND), dự phòng đọc chữ
        price = None
        pr = str(ld.get("priceRange", ""))
        if pr.isdigit():
            price = int(pr) / 1_000_000
        else:
            el = li.select_one("span.text-green")
            if el and "triệu" in el.get_text():
                m = re.search(r"\d+(?:[.,]\d+)?", el.get_text())
                price = float(m.group().replace(",", ".")) if m else None

        # Diện tích: <span>25 m<sup>2</sup></span>
        sup = li.select_one("span sup")
        m = re.search(r"\d+(?:[.,]\d+)?", sup.parent.get_text(" ")) if sup else None
        area = float(m.group().replace(",", ".")) if m else None

        # Khu vực từ slug href: /tinh-thanh/ha-noi/quan-hoang-mai
        loc = li.select_one("a.text-body[href*='/tinh-thanh/']")
        city = district = ""
        if loc:
            parts = loc["href"].rstrip("/").split("/")
            if len(parts) >= 2:
                city, district = norm_text(parts[-2]), norm_district(parts[-1])

        title_a = li.select_one("h3 a")
        title = (title_a.get("title") or title_a.get_text(" ", strip=True)).strip() if title_a else ""
        summ = li.select_one("p.line-clamp-2")
        summary = summ.get_text(" ", strip=True) if summ else ""

        star = li.select_one("span.star")
        sm = re.search(r"star-(\d)", " ".join(star.get("class", []))) if star else None

        if not (post_id and price and area and district):
            continue
        rows.append({
            "post_id": post_id,
            "source": "Phongtro123",
            "title": title,
            "price": round(price, 3),
            "area": area,
            "city": city,
            "district": district,
            "street_address": ld.get("address", {}).get("streetAddress", ""),
            "url": ld.get("url", ""),
            "vip_stars": int(sm.group(1)) if sm else None,
            "ptype": detect_ptype(title),
            "text": f"{title} {summary}",
        })
    return rows


def fetch_detail_text(url):
    """Tải trang chi tiết để lấy mô tả đầy đủ. Chưa kiểm chứng cấu trúc trang chi tiết:
    thử JSON-LD 'description', rồi meta description."""
    res = get_with_retry("https://phongtro123.com" + url if url.startswith("/") else url)
    if res is None:
        return ""
    soup = BeautifulSoup(res.text, "html.parser")
    best = ""
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or "")
        except json.JSONDecodeError:
            continue
        for obj in (d if isinstance(d, list) else [d]):
            if isinstance(obj, dict) and len(str(obj.get("description", ""))) > len(best):
                best = str(obj["description"])
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and len(meta.get("content", "")) > len(best):
        best = meta["content"]
    return best


def crawl_phongtro123(max_pages=50, city_slug="ha-noi", detail=False):
    rows = []
    print("Đang cào Phongtro123...")
    for page in range(1, max_pages + 1):
        url = f"https://phongtro123.com/tinh-thanh/{city_slug}?orderby=moi-nhat&page={page}"
        res = get_with_retry(url)
        if res is None:
            continue
        page_rows = parse_phongtro123_page(res.text)
        print(f"  Trang {page}: {len(page_rows)} tin hợp lệ")
        if not page_rows:
            break
        rows += page_rows
        time.sleep(1.0)

    if detail:
        print(f"Đang tải {len(rows)} trang chi tiết (chậm)...")
        for r in rows:
            full = fetch_detail_text(r["url"]) if r["url"] else ""
            if len(full) > len(r["text"]):
                r["text"] = f"{r['title']} {full}"
            time.sleep(1.2)
    print(f"-> Phongtro123: {len(rows)} tin thô.")
    return rows