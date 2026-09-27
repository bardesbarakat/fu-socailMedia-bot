import os
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
import cloudinary
import cloudinary.uploader
import urllib3

# إيقاف تحذيرات شهادات الأمان الخاصة بسيرفر الجامعة
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. Variables & Config
# ==========================================
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
IG_USER_ID = os.getenv("IG_USER_ID")

cloudinary.config(
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key = os.getenv('CLOUDINARY_API_KEY'),
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
)

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
# 3. Image Processing (Cloudinary)
# ==========================================
def process_and_upload_image(image_url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.fayoum.edu.eg/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }
        
        img_res = session.get(image_url, headers=headers, timeout=30, verify=False)
        
        if img_res.status_code != 200:
            print(f"  [!] فشل تحميل الصورة من سيرفر الجامعة (Code: {img_res.status_code})")
            return None
            
        response = cloudinary.uploader.upload(
            img_res.content,
            format="jpg",
            transformation=[
                {'width': 1080, 'height': 1080, 'crop': 'pad', 'background': 'auto'}
            ]
        )
        return response.get('secure_url')
    except Exception as e:
        print(f"  [!] خطأ في تحميل أو رفع الصورة: {e}")
        return None

# ==========================================
# 4. Publishing Functions
# ==========================================
def publish_to_facebook(message, link_url, image_urls):
    if not PAGE_ACCESS_TOKEN or not PAGE_ID: return False
    try:
        if image_urls and len(image_urls) > 0:
            # النشر كصورة صريحة لتجنب اللوجو الافتراضي
            url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/photos"
            full_message = f"{message}\n\n🔗 لقراءة التفاصيل كاملة عبر الموقع:\n{link_url}"
            payload = {
                "url": image_urls[0],
                "message": full_message,
                "access_token": PAGE_ACCESS_TOKEN
            }
        else:
            # النشر كرابط في حال عدم وجود صور نهائياً
            url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
            payload = {"message": message, "link": link_url, "access_token": PAGE_ACCESS_TOKEN}
            
        res = requests.post(url, data=payload, timeout=30)
        if res.status_code == 200:
            print("  [+] تم النشر على فيسبوك بنجاح (Photo Post).")
            return True
        else:
            print(f"  [!] خطأ النشر على فيسبوك: {res.json()}")
            return False
    except Exception as e: 
        print(f"  [!] خطأ برمجي في فيسبوك: {e}")
        return False

def publish_to_instagram(image_urls, caption):
    if not PAGE_ACCESS_TOKEN or not IG_USER_ID or not image_urls: 
        print("  [!] تم تخطي انستجرام: البيانات المطلوبة (Tokens) أو الصور مفقودة.")
        return False
    try:
        if len(image_urls) == 1:
            media_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
            res_media = requests.post(media_url, data={"image_url": image_urls[0], "caption": caption, "access_token": PAGE_ACCESS_TOKEN}, timeout=30)
            if res_media.status_code != 200:
                print(f"  [!] خطأ رفع الصورة لانستجرام (Media): {res_media.json()}")
                return False
            creation_id = res_media.json().get("id")
            time.sleep(10)
        else:
            item_ids = []
            for img_url in image_urls:
                res = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media", data={"image_url": img_url, "is_carousel_item": "true", "access_token": PAGE_ACCESS_TOKEN}, timeout=30)
                if res.status_code == 200: 
                    item_ids.append(res.json().get("id"))
                else:
                    print(f"  [!] خطأ في صورة الألبوم (Carousel Item): {res.json()}")
                time.sleep(2)
            
            if not item_ids: return False
            
            if len(item_ids) == 1:
                media_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
                res_media = requests.post(media_url, data={"image_url": image_urls[0], "caption": caption, "access_token": PAGE_ACCESS_TOKEN}, timeout=30)
                if res_media.status_code != 200: return False
                creation_id = res_media.json().get("id")
                time.sleep(10)
            else:
                res_container = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media", data={"media_type": "CAROUSEL", "children": ",".join(item_ids), "caption": caption, "access_token": PAGE_ACCESS_TOKEN}, timeout=30)
                if res_container.status_code != 200: 
                    print(f"  [!] خطأ تجميع الألبوم (Carousel Container): {res_container.json()}")
                    return False
                creation_id = res_container.json().get("id")
                time.sleep(15)
            
        res_pub = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish", data={"creation_id": creation_id, "access_token": PAGE_ACCESS_TOKEN}, timeout=30)
        if res_pub.status_code == 200:
            print("  [+] تم النشر على إنستجرام بنجاح.")
            return True
        else:
            print(f"  [!] خطأ النشر النهائي لانستجرام (Publish): {res_pub.json()}")
            return False
    except Exception as e: 
        print(f"  [!] خطأ برمجي أثناء التعامل مع انستجرام: {e}")
        return False

# ==========================================
# 5. Core Logic
# ==========================================
def run():
    posted_urls = get_posted_urls()
    print(f"[*] تم تحميل {len(posted_urls)} روابط مسجلة.")
    
    now_egypt = datetime.utcnow() + timedelta(hours=3)
    arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    month_ar = arabic_months[now_egypt.month - 1]
    
    today_formats = [
        now_egypt.strftime("%Y-%m-%d"), now_egypt.strftime("%d/%m/%Y"), now_egypt.strftime("%d-%m-%Y"),
        f"{now_egypt.day}/{now_egypt.month}/{now_egypt.year}", f"{now_egypt.day:02d}/{now_egypt.month:02d}/{now_egypt.year}",
        f"{now_egypt.day} {month_ar} {now_egypt.year}", f"{now_egypt.day:02d} {month_ar} {now_egypt.year}"
    ]

    for source_url in SOURCES:
        try:
            res = session.get(source_url, timeout=30, verify=False)
            if res.status_code != 200: continue
            
            soup = BeautifulSoup(res.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "/News/Details/" in href or "/Announcements/Details/" in href:
                    full_url = href if href.startswith("http") else f"https://www.fayoum.edu.eg{href}"
                    if full_url in posted_urls: continue
                    
                    article_res = session.get(full_url, timeout=30, verify=False)
                    if article_res.status_code == 200:
                        article_soup = BeautifulSoup(article_res.text, "html.parser")
                        
                        page_text = article_soup.get_text(separator=" ", strip=True)
                        if not any(fmt in page_text for fmt in today_formats):
                            save_posted_url(full_url)
                            posted_urls.add(full_url)
                            continue

                        for unwanted in article_soup.find_all(["header", "footer", "nav", "aside"]):
                            unwanted.decompose()
                        
                        for tag in article_soup.find_all(True):
                            if getattr(tag, 'attrs', None) is None: continue
                            classes = tag.get("class", [])
                            if isinstance(classes, str): classes = [classes]
                            if classes and any(any(w in c.lower() for w in ["header", "footer", "nav", "menu", "social", "lang", "topbar"]) for c in classes):
                                tag.decompose()

                        article_title = ""
                        h_tag = article_soup.find(["h1", "h2", "h3"])
                        if h_tag: article_title = h_tag.get_text(strip=True)
                        if not article_title: article_title = link.get_text(strip=True).replace("اقرأ المزيد", "").strip()

                        details_list = []
                        ignore_texts = ["جميع الحقوق محفوظة", "إجمالي الزوار", "الزوار الآن", "تصميم وتطوير"]
                        for p in article_soup.find_all("p"):
                            p_text = p.get_text(strip=True)
                            if len(p_text) > 30 and not any(txt in p_text for txt in ignore_texts):
                                details_list.append(p_text)
                        
                        article_details = "\n\n".join(details_list)
                        if len(article_details) > 1500:
                            article_details = article_details[:1500] + " ... (اقرأ المزيد على الموقع)"

                        raw_image_urls = []
                        excluded_words = ["logo", "icon", "flag", "banner", "egypt", "ar.", "en.", "eg.", "uk.", "bg", "avatar"]
                        for img in article_soup.find_all("img"):
                            if getattr(img, 'attrs', None) is None: continue 
                            src = img.get("src", "").strip()
                            if not src or src == "/" or src.startswith("data:"): continue
                            
                            if not any(w in src.lower() for w in excluded_words):
                                if src.startswith("http"): full_src = src
                                else: full_src = f"https://www.fayoum.edu.eg{src if src.startswith('/') else '/' + src}"
                                if full_src not in raw_image_urls: raw_image_urls.append(full_src)
                            if len(raw_image_urls) == 10: break
                        
                        valid_images = []
                        for img_url in raw_image_urls:
                            processed_url = process_and_upload_image(img_url)
                            if processed_url: valid_images.append(processed_url)

                        fb_caption = f"🔴 {article_title}\n\n{article_details}"
                        ig_caption = f"🔴 {article_title}\n\n{article_details}\n\n🔗 التفاصيل بالكامل عبر الرابط: {full_url}"
                        
                        if not valid_images:
                            print("  [!] لا توجد صور صالحة، سيتم تخطي انستجرام لهذا الرابط.")

                        fb_status = publish_to_facebook(message=fb_caption, link_url=full_url, image_urls=valid_images)
                        
                        ig_status = False
                        if valid_images:
                            ig_status = publish_to_instagram(image_urls=valid_images, caption=ig_caption)
                        
                        if fb_status or ig_status:
                            save_posted_url(full_url)
                            posted_urls.add(full_url)
                            print(f"  -> تم التسجيل بنجاح (فيسبوك: {fb_status} | انستجرام: {ig_status}) : {full_url}")
                        
                        time.sleep(2)
                        
        except Exception as e: 
            print(f"[!] خطأ: {e}")

if __name__ == "__main__":
    run()
