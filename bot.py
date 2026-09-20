import os
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

# ==========================================
# 1. Variables (المتغيرات)
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
# 2. Resilient Session (تهيئة الاتصال)
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
            # قراءة الروابط مع التأكد من إزالة أي مسافات زائدة لمنع التكرار
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted_url(url):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(url.strip() + "\n")

# ==========================================
# 3. Image Processing (معالجة الصورة لإنستجرام)
# ==========================================
def process_and_upload_image(image_url):
    """تحميل الصورة، وضع خلفية بيضاء لتصبح 1:1 بدون قص، ثم رفعها لـ IMGBB"""
    if not IMGBB_API_KEY:
        return image_url
    
    try:
        from PIL import Image
        from io import BytesIO
        import base64

        img_response = requests.get(image_url, timeout=15)
        img = Image.open(BytesIO(img_response.content))
        
        # إنشاء خلفية بيضاء مربعة بحجم الضلع الأكبر
        width, height = img.size
        new_size = max(width, height)
        new_img = Image.new("RGB", (new_size, new_size), "white")
        
        # لصق الصورة الأصلية في منتصف المربع الأبيض
        paste_pos = ((new_size - width) // 2, (new_size - height) // 2)
        new_img.paste(img, paste_pos)
        
        buffered = BytesIO()
        new_img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMGBB_API_KEY,
            "image": img_str
        }
        res = requests.post(url, data=payload, timeout=30).json()
        if res.get("success"):
            return res["data"]["url"]
            
    except Exception as e:
        pass 
    
    return image_url

# ==========================================
# 4. Publishing Functions (دوال النشر)
# ==========================================
def publish_to_facebook(message, link_url):
    if not PAGE_ACCESS_TOKEN or not PAGE_ID: return False
    try:
        url = f"https://graph.facebook.com/v26.0/{PAGE_ID}/feed"
        # إذا تم تمرير رسالة فارغة، سيقوم فيسبوك بعرض رابط المعاينة فقط
        payload = {"link": link_url, "access_token": PAGE_ACCESS_TOKEN}
        if message: 
            payload["message"] = message
            
        requests.post(url, data=payload, timeout=30)
        return True
    except Exception as e: pass
    return False

def publish_to_instagram(image_url, caption):
    if not PAGE_ACCESS_TOKEN or not IG_USER_ID or not image_url: return False
    try:
        media_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
        media_payload = {"image_url": image_url, "caption": caption, "access_token": PAGE_ACCESS_TOKEN}
        res_media = requests.post(media_url, data=media_payload, timeout=30).json()

        if "id" not in res_media: return False

        creation_id = res_media["id"]
        time.sleep(10) # انتظار المعالجة

        publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
        publish_payload = {"creation_id": creation_id, "access_token": PAGE_ACCESS_TOKEN}
        requests.post(publish_url, data=publish_payload, timeout=30)
        return True
    except Exception as e: pass
    return False

# ==========================================
# 5. Core Logic (المنطق الأساسي)
# ==========================================
def run():
    posted_urls = get_posted_urls()
    
    # صيغ التاريخ المحتملة في موقع الجامعة
    today_date_1 = datetime.now().strftime("%Y-%m-%d")
    today_date_2 = datetime.now().strftime("%d/%m/%Y")
    today_date_3 = datetime.now().strftime("%d-%m-%Y")

    for source_url in SOURCES:
        try:
            res = session.get(source_url, timeout=30)
            if res.status_code != 200: continue
            soup = BeautifulSoup(res.text, "html.parser")
            links = soup.find_all("a", href=True)
            
            for link in links:
                href = link["href"]
                if "/News/Details/" in href or "/Announcements/Details/" in href:
                    full_url = href if href.startswith("http") else f"https://www.fayoum.edu.eg{href}"
                    
                    if full_url in posted_urls: continue
                    
                    article_res = session.get(full_url, timeout=30)
                    if article_res.status_code == 200:
                        article_html = article_res.text
                        article_soup = BeautifulSoup(article_html, "html.parser")
                        
                        # التأكد من تاريخ اليوم
                        if not any(date_fmt in article_html for date_fmt in [today_date_1, today_date_2, today_date_3]):
                            save_posted_url(full_url)
                            posted_urls.add(full_url)
                            continue
                        
                        # 1. استخراج العنوان الفعلي
                        article_title = ""
                        h_tag = article_soup.find(["h1", "h2", "h3"])
                        if h_tag:
                            article_title = h_tag.get_text(strip=True)
                        if not article_title:
                            article_title = link.get_text(strip=True).replace("اقرأ المزيد", "").replace("اقرا المزيد", "").strip()

                        # 2. استخراج تفاصيل الخبر (من أجل إنستجرام فقط)
                        details_list = []
                        for p in article_soup.find_all("p"):
                            p_text = p.get_text(strip=True)
                            if len(p_text) > 30: 
                                details_list.append(p_text)
                        
                        article_details = "\n\n".join(details_list)
                        if len(article_details) > 1500:
                            article_details = article_details[:1500] + " ... (متابعة القراءة عبر الرابط)"

                        # 3. استخراج الصورة
                        image_url = None
                        og_image = article_soup.find("meta", property="og:image")
                        if og_image and og_image.get("content"):
                            image_url = og_image["content"]
                        else:
                            for img in article_soup.find_all("img"):
                                src = img.get("src", "")
                                if "logo" not in src.lower() and "icon" not in src.lower():
                                    image_url = src if src.startswith("http") else f"https://www.fayoum.edu.eg{src}"
                                    break
                        
                        # معالجة الصورة عبر IMGBB
                        if image_url:
                            image_url = process_and_upload_image(image_url)

                        # 🔴 التعديل هنا: إرسال نص فارغ لفيسبوك لمنع ظهور أي كلام فوق الصورة
                        publish_to_facebook(message="", link_url=full_url)

                        # إرسال التفاصيل كاملة لإنستجرام فقط
                        if image_url:
                            ig_caption = f"🔴 {article_title}\n\n{article_details}\n\n🔗 التفاصيل عبر الرابط: {full_url}"
                            publish_to_instagram(image_url=image_url, caption=ig_caption)
                        
                        # تسجيل الرابط لمنع التكرار
                        save_posted_url(full_url)
                        posted_urls.add(full_url)
                        time.sleep(2)
                        
        except Exception as e: pass

if __name__ == "__main__":
    run()
