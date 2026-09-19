import base64
import io
import os
import re
import time
from bs4 import BeautifulSoup
from PIL import Image
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
IMGBB_KEY = os.environ.get("IMGBB_API_KEY")

HISTORY_FILE = "posted_news.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


def get_posted_links():
  if not os.path.exists(HISTORY_FILE):
    return set()
  with open(HISTORY_FILE, "r", encoding="utf-8") as f:
    return set(line.strip() for line in f if line.strip())


def save_posted_link(link):
  with open(HISTORY_FILE, "a", encoding="utf-8") as f:
    f.write(f"{link}\n")


def adjust_and_upload_image(image_url):
  """فحص أبعاد الصورة وضبطها لتوافق إنستجرام ورفعها عبر ImgBB"""
  try:
    resp = requests.get(image_url, headers=HEADERS, timeout=25, verify=False)
    if resp.status_code != 200:
      return image_url

    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    w, h = img.size
    ratio = w / h

    # نسبة إنستجرام القياسية بين 0.8 و 1.91
    if 0.8 <= ratio <= 1.91 and w >= 320:
      return image_url

    # وضع الصورة داخل إطار مربع بنسبة 1:1
    max_side = max(w, h, 600)
    new_img = Image.new("RGB", (max_side, max_side), (255, 255, 255))
    offset = ((max_side - w) // 2, (max_side - h) // 2)
    new_img.paste(img, offset)

    buffer = io.BytesIO()
    new_img.save(buffer, format="JPEG", quality=92)
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    if IMGBB_KEY:
      up_res = requests.post(
          "https://api.imgbb.com/1/upload",
          data={"key": IMGBB_KEY, "image": img_b64},
          timeout=30,
      ).json()
      if up_res.get("success"):
        return up_res["data"]["url"]

  except Exception as e:
    print(f"خطأ بمعالجة الصورة: {e}")

  return image_url


def post_to_facebook(message, link):
  url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
  payload = {"message": message, "link": link, "access_token": ACCESS_TOKEN}
  return requests.post(url, data=payload, timeout=20).json()


def post_to_instagram(image_url, caption):
  if not image_url or not IG_USER_ID:
    return None

  final_image_url = adjust_and_upload_image(image_url)

  container_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
  container_payload = {
      "image_url": final_image_url,
      "caption": caption,
      "access_token": ACCESS_TOKEN,
  }
  c_res = requests.post(
      container_url, data=container_payload, timeout=20
  ).json()
  creation_id = c_res.get("id")
  if not creation_id:
    print(f"خطأ حاوية إنستجرام: {c_res}")
    return c_res

  time.sleep(5)
  publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
  return requests.post(
      publish_url,
      data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
      timeout=20,
  ).json()


def fetch_all_unposted_news():
  posted_links = get_posted_links()
  # فحص كلاً من صفحة الأخبار الرئيسية وصفحة الأرشيف لضمان التقاط كل ما هو متاح
  sources = [
      "https://www.fayoum.edu.eg/ar/News/AllNews",
      "https://www.fayoum.edu.eg/Default.aspx",
  ]

  found_links = []

  for source_url in sources:
    try:
      r = requests.get(source_url, headers=HEADERS, verify=False, timeout=25)
      soup = BeautifulSoup(r.text, "html.parser")
      for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if re.search(r"/News/Details/\d+", href, re.IGNORECASE):
          full_url = (
              href
              if href.startswith("http")
              else f"https://www.fayoum.edu.eg{href}"
          )
          if full_url not in found_links:
            found_links.append(full_url)
    except Exception as e:
      print(f"خطأ في جلب الروابط من {source_url}: {e}")

  # تصفية الروابط واستخراج ما لم يتم نشره فقط
  unposted = [link for link in found_links if link not in posted_links]
  return unposted


def run():
  print("--- بدء فحص الأخبار غير المنشورة ---")
  unposted_items = fetch_all_unposted_news()
  print(f"إجمالي الأخبار غير المنشورة التي تم العثور عليها: {len(unposted_items)}")

  if not unposted_items:
    print("جميع الأخبار الحالية منشورة بالفعل.")
    return

  # نشر الأخبار بترتيبها من الأقدم إلى الأحدث أو حتى تصفية القائمة
  for link in reversed(unposted_items):
    print(f"جاري نشر: {link}")
    try:
      det_res = requests.get(link, headers=HEADERS, verify=False, timeout=25)
      det_soup = BeautifulSoup(det_res.text, "html.parser")

      title_elem = (
          det_soup.find("h1")
          or det_soup.find("h2")
          or det_soup.find("title")
      )
      title = (
          title_elem.get_text(strip=True)
          if title_elem
          else "خبر جديد من جامعة الفيوم"
      )

      img_elem = det_soup.find(
          "img",
          src=lambda s: s
          and any(k in s.lower() for k in ["news", "upload", "images"]),
      )
      img_url = ""
      if img_elem and img_elem.get("src"):
        src = img_elem["src"]
        img_url = (
            src if src.startswith("http") else f"https://www.fayoum.edu.eg{src}"
        )

      message = f"{title}\n\nالتفاصيل كاملة عبر الرابط:\n{link}"

      # النشر على فيسبوك
      fb_res = post_to_facebook(message, link)
      print(f"استجابة فيسبوك: {fb_res}")

      # النشر على إنستجرام
      if img_url:
        ig_res = post_to_instagram(img_url, message)
        print(f"استجابة إنستجرام: {ig_res}")

      # توثيق الخبر بعد نجاحه
      if "id" in fb_res:
        save_posted_link(link)
        print(f"تم توثيق الخبر بنجاح: {link}")

      # مهلة انتظار 10 ثوانٍ بين كل خبر لمنع حظر المنصات
      time.sleep(10)

    except Exception as e:
      print(f"خطأ أثناء نشر الرابط {link}: {e}")


if __name__ == "__main__":
  run()
