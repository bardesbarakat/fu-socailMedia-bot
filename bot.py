import os
import time
import requests
from bs4 import BeautifulSoup
import urllib3
import io
import base64
from PIL import Image

# تجاهل تحذيرات شهادات SSL غير الموثقة من خادم الجامعة
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# جلب المتغيرات السرية من البيئة
ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
IMGBB_KEY = os.environ.get("IMGBB_API_KEY")

HISTORY_FILE = "posted_news.txt"

def get_posted_links():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_posted_link(link):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")

def adjust_and_upload_image(image_url):
    """فحص أبعاد الصورة وضبطها لتناسب شروط إنستجرام ثم رفعها عبر ImgBB"""
    try:
        resp = requests.get(image_url, timeout=20, verify=False)
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        w, h = img.size
        ratio = w / h

        # النسبة المقبولة في إنستجرام بين 0.8 (4:5) و 1.91 (1.91:1)
        if 0.8 <= ratio <= 1.91:
            return image_url

        # جعل الصورة داخل مربع بخلفية بيضاء نقية دون قص تفاصيل الخبر
        max_side = max(w, h)
        new_img = Image.new("RGB", (max_side, max_side), (255, 255, 255))
        offset = ((max_side - w) // 2, (max_side - h) // 2)
        new_img.paste(img, offset)

        buffer = io.BytesIO()
        new_img.save(buffer, format="JPEG", quality=90)
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        if IMGBB_KEY:
            up_res = requests.post(
                "https://api.imgbb.com/1/upload",
                data={"key": IMGBB_KEY, "image": img_b64},
                timeout=25
            ).json()
            if up_res.get("success"):
                return up_res["data"]["url"]

    except Exception as e:
        print(f"تنبيه أثناء فحص الصورة: {e}")

    return image_url

def post_to_facebook(message, link):
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {
        "message": message,
        "link": link,
        "access_token": ACCESS_TOKEN
    }
    return requests.post(url, data=payload).json()

def post_to_instagram(image_url, caption):
    if not image_url or not IG_USER_ID:
        return None

    # ضبط الصورة إن كانت غير متطابقة مع أبعاد إنستجرام
    final_image_url = adjust_and_upload_image(image_url)

    container_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    container_payload = {
        "image_url": final_image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    c_res = requests.post(container_url, data=container_payload).json()
    creation_id = c_res.get("id")
    if not creation_id:
        print(f"خطأ حاوية إنستجرام: {c_res}")
        return c_res

    time.sleep(5)
    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    return requests.post(publish_url, data={"creation_id": creation_id, "access_token": ACCESS_TOKEN}).json()

def fetch_and_publish():
    print("--- فحص المحتوى ونشره ---")
    posted_links = get_posted_links()
    url = "https://www.fayoum.edu.eg/ar/News/AllNews"

    try:
        r = requests.get(url, verify=False, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        news_items = soup.find_all("div", class_="news-item") or soup.find_all("article") or soup.find_all("a", href=lambda h: h and "/News/Details/" in h)

        for item in news_items:
            link = item.get("href") if item.name == "a" else (item.find("a")["href"] if item.find("a") else None)
            if not link:
                continue

            if not link.startswith("http"):
                link = f"https://www.fayoum.edu.eg{link}"

            if link in posted_links:
                continue

            print(f"رصد عنصر جديد: {link}")

            # استخراج تفاصيل صفحة الخبر
            det_res = requests.get(link, verify=False, timeout=20)
            det_soup = BeautifulSoup(det_res.text, "html.parser")

            title_elem = det_soup.find("h1") or det_soup.find("h2") or det_soup.find("title")
            title = title_elem.get_text(strip=True) if title_elem else "خبر جديد من جامعة الفيوم"

            img_elem = det_soup.find("img", src=lambda s: s and ("News" in s or "Upload" in s or "images" in s))
            img_url = ""
            if img_elem and img_elem.get("src"):
                src = img_elem["src"]
                img_url = src if src.startswith("http") else f"https://www.fayoum.edu.eg{src}"

            message = f"{title}\n\nالتفاصيل كاملة عبر الرابط:\n{link}"

            # 1. النشر على فيسبوك
            fb_res = post_to_facebook(message, link)
            print(f"استجابة فيسبوك: {fb_res}")

            # 2. النشر على إنستجرام (في حال وجود صورة)
            if img_url:
                ig_res = post_to_instagram(img_url, message)
                print(f"استجابة إنستجرام: {ig_res}")

            # التوثيق عند نجاح النشر على فيسبوك
            if "id" in fb_res:
                save_posted_link(link)
                print("تم التوثيق بنجاح.")
                return

        print("لا توجد عناصر جديدة لنشرها حالياً.")

    except Exception as e:
        print(f"حدث خطأ أثناء فحص الموقع: {e}")

if __name__ == "__main__":
    fetch_and_publish()
