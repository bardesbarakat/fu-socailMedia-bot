import os
import time
import requests
from datetime import datetime
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

POSTED_FILE = "posted_urls.txt"

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
# 3. Image Processing (Crop & Upload)
# ==========================================
def process_and_upload_image(image_url):
    """Downloads, crops to 1:1, and uploads to IMGBB."""
    if not IMGBB_API_KEY:
        return image_url
    
    try:
        from PIL import Image
        from io import BytesIO
        import base64

        # Download the image
        img_response = requests.get(image_url, timeout=15)
        img = Image.open(BytesIO(img_response.content))
        
        # Crop to 1:1 Aspect Ratio for Instagram compatibility
        width, height = img.size
        new_size = min(width, height)
        left = (width - new_size) / 2
        top = (height - new_size) / 2
        right = (width + new_size) / 2
        bottom = (height + new_size) / 2
        img = img.crop((left, top, right, bottom))
        
        # Convert to Base64
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        # Upload to IMGBB
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMGBB_API_KEY,
            "image": img_str
        }
        res = requests.post(url, data=payload, timeout=30).json()
        if res.get("success"):
            return res["data"]["url"]
            
    except Exception as e:
        pass # Silent fail, try to return original url
    
    return image_url

# ==========================================
# 4. Publishing Functions
# ==========================================
def publish_to_facebook(message, link_url):
    if not PAGE_ACCESS_TOKEN or not PAGE_ID: return False
    try:
        url = f"https://graph.facebook.com/v26.0/{PAGE_ID}/feed"
        payload = {"message": message, "link": link_url, "access_token": PAGE_ACCESS_TOKEN}
        res = requests.post(url, data=payload, timeout=30).json()
        if "id" in res: return True
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
        time.sleep(10)

        publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
        publish_payload = {"creation_id": creation_id, "access_token": PAGE_ACCESS_TOKEN}
        res_pub = requests.post(publish_url, data=publish_payload, timeout=30).json()
        
        if "id" in res_pub: return True
    except Exception as e: pass
    return False

# ==========================================
# 5. Core Logic
# ==========================================
def run():
    posted_urls = get_posted_urls()
    
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
                    
                    # Clean title
                    title = link.get_text(strip=True).replace("اقرأ المزيد", "").replace("اقرا المزيد", "").strip()
                    
                    article_res = session.get(full_url, timeout=30)
                    if article_res.status_code == 200:
                        article_html = article_res.text
                        article_soup = BeautifulSoup(article_html, "html.parser")
                        
                        # Date check
                        if not any(date_fmt in article_html for date_fmt in [today_date_1, today_date_2, today_date_3]):
                            save_posted_url(full_url)
                            posted_urls.add(full_url)
                            continue
                        
                        # Image extraction
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
                        
                        # Process Image
                        if image_url:
                            image_url = process_and_upload_image(image_url)

                        # Publish
                        publish_to_facebook(message=title, link_url=full_url)

                        if image_url:
                            ig_caption = f"{title}\n\nللتفاصيل: {full_url}"
                            publish_to_instagram(image_url=image_url, caption=ig_caption)
                        
                        save_posted_url(full_url)
                        posted_urls.add(full_url)
                        time.sleep(2)
                        
        except Exception as e: pass

if __name__ == "__main__":
    run()
