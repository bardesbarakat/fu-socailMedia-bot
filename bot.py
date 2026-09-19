import os
import time
import requests
from bs4 import BeautifulSoup
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

# ==========================================
# 1. قراءة المتغيرات من GitHub Secrets
# ==========================================
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
IG_USER_ID = os.getenv("IG_USER_ID")

# روابط موقع الجامعة
SOURCES = [
    "https://www.fayoum.edu.eg/ar/News?tab=news&pageNumber=1&pageSize=6",
    "https://www.fayoum.edu.eg/ar/Announcements?pageNumber=1&pageSize=6",
    "https://www.fayoum.edu.eg/ar/News?tab=events&pageNumber=1&pageSize=6"
]

# ==========================================
# 2. إنشاء جلسة اتصال قوية لتفادي Connection Reset
# ==========================================
def create_resilient_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.fayoum.edu.eg/",
        "Connection": "keep-alive"
    })
    
    # إعادة المحاولة تلقائياً 5 مرات في حال حدوث خطأ من السيرفر
    retries = Retry(
        total=5,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

session = create_resilient_session()

# ==========================================
# 3. دوال النشر على فيسبوك
# ==========================================
def publish_to_facebook(text, image_url=None):
    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("⚠️ لم يتم العثور على PAGE_ACCESS_TOKEN أو PAGE_ID في البيئة.")
        return False

    try:
        if image_url:
            # رفع الصورة مع نص الخبر
            url = f"https://graph.facebook.com/v26.0/{PAGE_ID}/photos"
            payload = {
                "url": image_url,
                "caption": text,
                "access_token": PAGE_ACCESS_TOKEN
            }
        else:
            # نشر نصي فقط
            url = f"https://graph.facebook.com/v26.0/{PAGE_ID}/feed"
            payload = {
                "message": text,
                "access_token": PAGE_ACCESS_TOKEN
            }

        res = requests.post(url, data=payload, timeout=30).json()
        if "id" in res:
            print(f"✅ تم النشر على فيسبوك بنجاح! ID: {res['id']}")
            return True
        else:
            print(f"❌ خطأ من فيسبوك: {res}")
            return False
    except Exception as e:
        print(f"❌ استثناء أثناء النشر على فيسبوك: {e}")
        return False

# ==========================================
# 4. دوال النشر على إنستغرام (اختياري)
# ==========================================
def publish_to_instagram(image_url, caption):
    if not PAGE_ACCESS_TOKEN or not IG_USER_ID or not image_url:
        return False

    try:
        # الخطوة 1: إنشاء حاوية الميديا
        media_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
        media_payload = {
            "image_url": image_url,
            "caption": caption,
            "access_token": PAGE_ACCESS_TOKEN
        }
        res_media = requests.post(media_url, data=media_payload, timeout=30).json()

        if "id" not in res_media:
            print(f"❌ خطأ إنشاء وسائط إنستغرام: {res_media}")
            return False

        creation_id = res_media["id"]
        time.sleep(5)  # انتظار معالجة الصورة

        # الخطوة 2: نشر الوسائط
        publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
        publish_payload = {
            "creation_id": creation_id,
            "access_token": PAGE_ACCESS_TOKEN
        }
        res_pub = requests.post(publish_url, data=publish_payload, timeout=30).json()
        if "id" in res_pub:
            print(f"✅ تم النشر على إنستغرام بنجاح! ID: {res_pub['id']}")
            return True
        else:
            print(f"❌ خطأ نشر إنستغرام: {res_pub}")
            return False
    except Exception as e:
        print(f"❌ استثناء أثناء النشر على إنستغرام: {e}")
        return False

# ==========================================
# 5. جلب الأخبار من الموقع
# ==========================================
def fetch_url(url):
    try:
        res = session.get(url, timeout=30)
        if res.status_code == 200:
            return res.text
        print(f"⚠️ كود الاستجابة غير متوقع: {res.status_code} للرابط: {url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ تعذر الاتصال بـ {url}: {e}")
        return None

def run():
    print("--- بدء الفحص السريع (المنصة: all) ---")

    for source_url in SOURCES:
        html = fetch_url(source_url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        
        # البحث عن روابط الأخبار
        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"]
            if "/News/Details/" in href or "/Announcements/Details/" in href:
                full_url = href if href.startswith("http") else f"https://www.fayoum.edu.eg{href}"
                title = link.get_text(strip=True) or "خبر جديد من جامعة الفيوم"
                
                print(f"⚡ رصد خبر: {full_url}")
                post_text = f"{title}\n\nالتفاصيل: {full_url}"
                
                # تنفيذ النشر على فيسبوك
                publish_to_facebook(text=post_text)
                time.sleep(2)
                break  # يكتفي بأحدث خبر من كل مصدر للتجربة

if __name__ == "__main__":
    run()
