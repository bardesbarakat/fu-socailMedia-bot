import os
import re
import time
import requests
from bs4 import BeautifulSoup

PAGE_ID = os.environ.get("PAGE_ID", "201624046515768")
IG_USER_ID = os.environ.get("IG_USER_ID", "17841410383378089")
ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")

HISTORY_FILE = "posted_news.txt"

SOURCES = [
    {"type": "أخبار", "url": "https://www.fayoum.edu.eg/ar/News?tab=news&pageNumber=1"},
    {"type": "إعلانات", "url": "https://www.fayoum.edu.eg/ar/Announcements?pageNumber=1&pageSize=12"},
    {"type": "فعاليات", "url": "https://www.fayoum.edu.eg/ar/News?tab=events&pageNumber=1"}
]

def load_posted():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_posted(identifier):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(identifier + "\n")

def get_target_links(source_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    found_links = []
    try:
        res = requests.get(source_url, headers=headers, timeout=25, verify=False)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a['href'].strip()
            if re.search(r'/(News/Details|Announcements/ADsDetails)/\d+', href, re.IGNORECASE):
                full_url = href if href.startswith("http") else f"https://www.fayoum.edu.eg{href if href.startswith('/') else '/' + href}"
                if full_url not in found_links:
                    found_links.append(full_url)
    except Exception as e:
        print(f"خطأ: {e}")
    return found_links

def fetch_article_meta(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    title = ""
    image_url = None
    try:
        r = requests.get(url, headers=headers, timeout=20, verify=False)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, "html.parser")

        if soup.title:
            title = soup.title.get_text().replace("البوابة الرسمية لجامعة الفيوم", "").replace("|", "").strip()

        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"]
        else:
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if any(k in src.lower() for k in ["upload", "news", "ads", "events"]) and not src.startswith("data:image"):
                    image_url = src if src.startswith("http") else f"https://www.fayoum.edu.eg{src if src.startswith('/') else '/' + src}"
                    break
    except Exception as e:
        print(f"خطأ أثناء جلب المقال: {e}")

    return title, image_url

def post_to_facebook(link):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/feed"
    payload = {
        "link": link,
        "access_token": ACCESS_TOKEN
    }
    res = requests.post(url, data=payload)
    return res.json()

def post_to_instagram(image_url, caption):
    if not image_url:
        print("تخطي إنستجرام: المقال لا يحتوي على صورة.")
        return None

    container_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    c_res = requests.post(container_url, data=container_payload).json()
    creation_id = c_res.get("id")

    if not creation_id:
        print("خطأ حاوية إنستجرام:", c_res)
        return c_res

    time.sleep(5)

    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN
    }
    return requests.post(publish_url, data=publish_payload).json()

def run_agent():
    print("--- فحص المحتوى ونشره ---")
    posted = load_posted()

    for src in SOURCES:
        section_type = src["type"]
        links = get_target_links(src["url"])

        for link in links:
            if link not in posted:
                print(f"رصد عنصر جديد من [{section_type}]: {link}")

                # نشر على فيسبوك بنظام Link Preview
                fb_res = post_to_facebook(link)
                print("استجابة فيسبوك:", fb_res)

                # نشر الأخبار والفعاليات فقط على إنستجرام
                if section_type in ["أخبار", "فعاليات"]:
                    title, img_url = fetch_article_meta(link)
                    ig_caption = f"📢 {title}\n\n🔗 لمزيد من التفاصيل يرجى زيارة موقع جامعة الفيوم عبر الرابط:\n{link}\n\n#جامعة_الفيوم #{section_type}"
                    ig_res = post_to_instagram(img_url, ig_caption)
                    print("استجابة إنستجرام:", ig_res)

                if "id" in fb_res:
                    save_posted(link)
                    print("تم التوثيق بنجاح.")
                    return

    print("لا توجد عناصر جديدة.")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    run_agent()
