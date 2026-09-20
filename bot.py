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
IG_USER_ID = os.getenv("IG_USER_ID")
# متغير IMGBB تم حذفه لأنه لم يعد هناك حاجة إليه (نسحب الصورة من الموقع مباشرة)

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
# 3. دوال النشر على فيسبوك (بشكل Link Preview)
# ==========================================
def publish_to_facebook(message, link_url):
    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("⚠️ لم يتم العثور على PAGE_ACCESS_TOKEN أو PAGE_ID في البيئة.")
        return False

    try:
        url = f"https://graph.facebook.com/v26.0/{PAGE_ID}/feed"
        payload = {
            "message": message,
            "link": link_url,
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
# 4. دوال النشر على إنستغرام
# ==========================================
def publish_to_instagram(image_url, caption):
    if not PAGE_ACCESS_TOKEN or not IG_USER_ID or not image_url:
        print("⚠️ توكن إنستجرام أو رابط الصورة مفقود.")
        return False

    try:
        # الخطوة 1: رفع الصورة
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
        print("⏳ جاري معالجة الصورة في إنستجرام (انتظار 10 ثوانٍ)...")
        time.sleep(10)

        # الخطوة 2: النشر الفعلي
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
# 5. جلب الأخبار من الموقع وتشغيل النشر
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
    print("--- بدء الفحص السريع للأخبار ---")

    for source_url in SOURCES:
        html = fetch_url(source_url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=True)
        
        for link in links:
            href = link["href"]
            if "/News/Details/" in href or "/Announcements/Details/" in href:
                full_url = href if href.startswith("http") else f"https://www.fayoum.edu.eg{href}"
                title = link.get_text(strip=True) or "خبر جديد من جامعة الفيوم"
                print(f"\n⚡ تم العثور على خبر: {full_url}")
                
                # جلب صورة الخبر للإنستجرام
                image_url = None
                article_html = fetch_url(full_url)
                if article_html:
                    article_soup = BeautifulSoup(article_html, "html.parser")
                    # نبحث عن الصورة الرئيسية داخل الخبر
                    img_tag = article_soup.find("img")
                    if img_tag and img_tag.get("src"):
                        img_src = img_tag["src"]
                        image_url = img_src if img_src.startswith("http") else f"https://www.fayoum.edu.eg{img_src}"

                # 1. النشر على فيسبوك
                print("جاري النشر على فيسبوك...")
                publish_to_facebook(message=title, link_url=full_url)

                # 2. النشر على إنستجرام
                if image_url:
                    print("جاري النشر على إنستجرام...")
                    ig_caption = f"{title}\n\nللتفاصيل: {full_url}"
                    publish_to_instagram(image_url=image_url, caption=ig_caption)
                else:
                    print("⚠️ تم تخطي إنستجرام لعدم العثور على صورة داخل الخبر.")

                time.sleep(2)
                break  # نكتفي بأحدث خبر من كل مصدر للتجربة

# هذا هو الجزء الذي يضمن تنفيذ الكود عند تشغيل الملف
if __name__ == "__main__":
    run()
