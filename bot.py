import os
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

# ==========================================
# 1. Variables
# ==========================================
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
IG_USER_ID = os.getenv("IG_USER_ID")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

SOURCES = [
    "https://www.fayoum.edu.eg/ar/News?tab=news&pageNumber=1&pageSize=6",
    "https://www.fayoum.edu.eg/ar/Announcements?pageNumber=1&pageSize=6",
    "https://www.fayoum.edu.eg/ar/News?tab=events&pageNumber=1&pageSize=6"
]

POSTED_FILE = "posted_news.txt"

# ==========================================
# 2. Resilient Session
# ==========================================
def create_resilient_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    retries = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

session = create_resilient_session()

def get_posted_urls():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return set(f.read().splitlines())
    return set()

def save_posted_url(url):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")

# ==========================================
# 3. Image Processing
# ==========================================
def process_and_upload_image(image_url):
    if not IMGBB_API_KEY: return None
    try:
        from PIL import Image
        from io import BytesIO
        import base64

        img_response = requests.get(image_url, timeout=15)
        if img_response.status_code != 200: return None
            
        img = Image.open(BytesIO(img_response.content))
        width, height = img.size
        new_size = max(width, height)
        new_img = Image.new("RGB", (new_size, new_size), "white")
        
        paste_pos = ((new_size - width) // 2, (new_size - height) // 2)
        new_img.paste(img, paste_pos)
        
        buffered = BytesIO()
        new_img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": IMGBB_API_KEY, "image": img_str}
        res = requests.post(url, data=payload, timeout=30).json()
        if res.get("success"):
            return res["data"]["url"]
    except Exception as e:
        print(f"[!] خطأ في معالجة الصور: {e}")
    return None

# ==========================================
# 4. Publishing Functions
# ==========================================
def publish_to_facebook(message, link_url):
    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("[-] خطأ: بيانات فيسبوك (Token أو ID) غير موجودة في الـ Secrets!")
        return False
    try:
        url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
        payload = {"message": message, "link": link_url, "access_token": PAGE_ACCESS_TOKEN}
        res = requests.post(url, data=payload, timeout=30)
        if res.status_code == 200:
            print("  [+] تم النشر على فيسبوك بنجاح.")
            return True
        else:
            print(f"  [-] فيسبوك رفض النشر. السبب: {res.text}")
            return False
    except Exception as e: 
        print(f"  [-] خطأ تقني أثناء النشر على فيسبوك: {e}")
        return False

def publish_to_instagram(image_urls, caption):
    if not PAGE_ACCESS_TOKEN or not IG_USER_ID or not image_urls: return False
    try:
        if len(image_urls) == 1:
            media_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
            media_payload = {"image_url": image_urls[0], "caption": caption, "access_token": PAGE_ACCESS_TOKEN}
            res_media = requests.post(media_url, data=media_payload, timeout=30)
            if res_media.status_code != 200:
                print(f"  [-] إنستجرام رفض الصورة. السبب: {res_media.text}")
                return False
            
            creation_id = res_media.json().get("id")
            time.sleep(10)
        else:
            item_ids = []
            for img_url in image_urls:
                media_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
                payload = {"image_url": img_url, "is_carousel_item": "true", "access_token": PAGE_ACCESS_TOKEN}
                res = requests.post(media_url, data=payload, timeout=30)
                if res.status_code == 200:
                    item_ids.append(res.json().get("id"))
                time.sleep(2)
            if not item_ids: return False
            
            container_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
            container_payload = {
                "media_type": "CAROUSEL",
                "children": ",".join(item_ids),
                "caption": caption,
                "access_token": PAGE_ACCESS_TOKEN
            }
            res_container = requests.post(container_url, data=container_payload, timeout=30)
            if res_container.status_code != 200:
                print(f"  [-] إنستجرام رفض الألبوم. السبب: {res_container.text}")
                return False
                
            creation_id = res_container.json().get("id")
            time.sleep(15)
            
        publish_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish"
        publish_payload = {"creation_id": creation_id, "access_token": PAGE_ACCESS_TOKEN}
        publish_res = requests.post(publish_url, data=publish_payload, timeout=30)
        if publish_res.status_code == 200:
            print("  [+] تم النشر على إنستجرام بنجاح.")
            return True
        else:
            print(f"  [-] فشل النشر النهائي على إنستجرام. السبب: {publish_res.text}")
            return False
            
    except Exception as e: 
        print(f"  [-] خطأ تقني أثناء النشر على إنستجرام: {e}")
        return False

# ==========================================
# 5. Core Logic
# ==========================================
def run():
    posted_urls = get_posted_urls()
    print(f"[*] تم تحميل {len(posted_urls)} روابط مسجلة مسبقاً.")
    
    now_egypt = datetime.utcnow() + timedelta(hours=3)
    arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    month_ar = arabic_months[now_egypt.month - 1]
    
    today_formats = [
        now_egypt.strftime("%Y-%m-%d"), now_egypt.strftime("%d/%m/%Y"), now_egypt.strftime("%d-%m-%Y"),
        f"{now_egypt.day}/{now_egypt.month}/{now_egypt.year}", f"{now_egypt.day:02d}/{now_egypt.month:02d}/{now_egypt.year}",
        f"{now_egypt.day} {month_ar} {now_egypt.year}", f"{now_egypt.day:02d} {month_ar} {now_egypt.year}"
    ]

    for source_url in SOURCES:
        print(f"\n[*] جاري فحص الرابط: {source_url}")
        try:
            res = session.get(source_url, timeout=30)
            if res.status_code != 200: continue
            
            soup = BeautifulSoup(res.text, "html.parser")
            links = soup.find_all("a", href=True)
            
            for link in links:
                href = link["href"]
                if "/News/Details/" in href or "/Announcements/Details/" in href:
                    full_url = href if href.startswith("http") else f"https://www.fayoum.edu.eg{href}"
                    
                    if full_url in posted_urls:
                        continue
                    
                    print(f"\n- خبر جديد: {full_url}")
                    article_res = session.get(full_url, timeout=30)
                    if article_res.status_code == 200:
                        article_html = article_res.text
                        article_soup = BeautifulSoup(article_html, "html.parser")
                        page_text = article_soup.get_text(separator=" ", strip=True)
                        
                        is_today = any(fmt in page_text for fmt in today_formats)
                        
                        if not is_today:
                            save_posted_url(full_url)
                            posted_urls.add(full_url)
                            continue
                        
                        print("  -> التاريخ متطابق. جاري تجهيز المنشور...")
                        
                        article_title = ""
                        h_tag = article_soup.find(["h1", "h2", "h3"])
                        if h_tag: article_title = h_tag.get_text(strip=True)
                        if not article_title: article_title = link.get_text(strip=True).replace("اقرأ المزيد", "").strip()

                        details_list = []
                        for p in article_soup.find_all("p"):
                            p_text = p.get_text(strip=True)
                            if len(p_text) > 30: details_list.append(p_text)
                        
                        article_details = "\n\n".join(details_list)
                        if len(article_details) > 1500:
                            article_details = article_details[:1500] + " ... (اقرأ المزيد على الموقع)"

                        raw_image_urls = []
                        for img in article_soup.find_all("img"):
                            src = img.get("src", "").strip()
                            if not src or src == "/" or src.startswith("data:"): continue
                            if "logo" not in src.lower() and "icon" not in src.lower():
                                if src.startswith("http"): full_src = src
                                else:
                                    if not src.startswith("/"): src = "/" + src
                                    full_src = f"https://www.fayoum.edu.eg{src}"
                                if full_src not in raw_image_urls: raw_image_urls.append(full_src)
                            if len(raw_image_urls) == 10: break
                        
                        valid_images = []
                        for img_url in raw_image_urls:
                            processed_url = process_and_upload_image(img_url)
                            if processed_url: valid_images.append(processed_url)

                        ig_caption = f"🔴 {article_title}\n\n{article_details}\n\n🔗 التفاصيل بالكامل عبر الرابط: {full_url}"
                        
                        fb_status = publish_to_facebook(message="", link_url=full_url)
                        ig_status = False
                        if valid_images:
                            ig_status = publish_to_instagram(image_urls=valid_images, caption=ig_caption)
                        
                        # التسجيل فقط إذا نجح النشر على أي منصة
                        if fb_status or ig_status:
                            save_posted_url(full_url)
                            posted_urls.add(full_url)
                            print("  -> [تم الحفظ] تم تسجيل الخبر في الملف لمنع التكرار.")
                        else:
                            print("  -> [تحذير] لم يتم نشر الخبر بنجاح، ولن يتم تسجيله (سيحاول البوت مرة أخرى لاحقاً).")
                        
                        time.sleep(2)
                        
        except Exception as e: 
            print(f"[!] حدث خطأ أثناء المعالجة: {e}")

if __name__ == "__main__":
    run()
