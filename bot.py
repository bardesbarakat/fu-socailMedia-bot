import base64
from datetime import datetime
import io
import os
import re
import time
from bs4 import BeautifulSoup
from PIL import Image
import requests
import urllib3

# تعطيل تحذيرات شهادات الأمان غير الموثقة من موقع الجامعة
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# المتغيرات السرية وبيئة التشغيل
ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
IMGBB_KEY = os.environ.get("IMGBB_API_KEY")
TARGET_PLATFORM = os.environ.get("TARGET_PLATFORM", "all").lower()

# ملفات توثيق مستقلة لكل منصة
FB_HISTORY_FILE = "posted_fb.txt"
IG_HISTORY_FILE = "posted_ig.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


def get_posted_links(file_path):
  if not os.path.exists(file_path):
    return set()
  with open(file_path, "r", encoding="utf-8") as f:
    return set(line.strip() for line in f if line.strip())


def save_posted_link(file_path, link):
  with open(file_path, "a", encoding="utf-8") as f:
    f.write(f"{link}\n")


def extract_real_article_image(soup):
  """استخراج الصورة الأصلية للخبر بدقة واستبعاد اللوجو والشعارات والأيقونات."""
  # 1. فحص وسم Open Graph للخبر أولاً
  og_image = soup.find("meta", property="og:image")
  if og_image and og_image.get("content"):
    candidate = og_image["content"].strip()
    if candidate.startswith("http") and not any(
        x in candidate.lower()
        for x in ["logo", "icon", "default", "placeholder", "header", "footer"]
    ):
      return candidate

  # 2. حصر البحث داخل الحاوية النصية للخبر وتجاهل القوائم وشريط التنقل
  article_body = (
      soup.find(
          "div", class_=re.compile(r"details|content|article|news-body", re.I)
      )
      or soup.find("article")
      or soup.find("main")
      or soup
  )

  bad_keywords = [
      "logo",
      "icon",
      "banner",
      "header",
      "footer",
      "arrow",
      "social",
      "flag",
      "avatar",
      "spacer",
      "btn",
  ]

  candidates = []
  for img in article_body.find_all("img", src=True):
    src = img["src"].strip()
    if not src:
      continue

    if any(bad in src.lower() for bad in bad_keywords):
      continue

    full_url = (
        src if src.startswith("http") else f"https://www.fayoum.edu.eg{src}"
    )

    if any(
        k in full_url.lower()
        for k in ["upload", "news", "events", "announc", "details", "images"]
    ):
      candidates.append(full_url)

  # 3. التأكد من أبعاد الصورة الفعلية حتى لا تكون أيقونة مصغرة
  for img_url in candidates:
    try:
      resp = requests.get(img_url, headers=HEADERS, timeout=15, verify=False)
      if resp.status_code == 200:
        temp_img = Image.open(io.BytesIO(resp.content))
        w, h = temp_img.size
        if w >= 300 and h >= 200:
          return img_url
    except Exception:
      continue

  return candidates[0] if candidates else ""


def adjust_and_upload_image(image_url):
  """فحص أبعاد الصورة وضبطها لتوافق معايير إنستجرام ورفعها عبر ImgBB."""
  try:
    resp = requests.get(image_url, headers=HEADERS, timeout=25, verify=False)
    if resp.status_code != 200:
      return image_url

    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    w, h = img.size
    ratio = w / h

    # إنستجرام يتطلب نسبة بين 0.8 و 1.91 وعرض لا يقل عن 320 بكسل
    if 0.8 <= ratio <= 1.91 and w >= 320:
      return image_url

    # وضع الصورة داخل إطار مربع بنسبة 1:1 بخلفية بيضاء
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
        hosted_url = up_res["data"]["url"]
        print(f"تم رفع صورة الخبر المعدلة بنجاح: {hosted_url}")
        return hosted_url
      else:
        print(f"تنبيه ImgBB: {up_res}")

  except Exception as e:
    print(f"خطأ أثناء معالجة الصورة: {e}")

  return image_url


def post_to_facebook(message, link):
  """النشر على فيسبوك المتوافق مع New Pages Experience."""
  url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
  full_message = f"{message}\n\n{link}" if link not in message else message
  payload = {"message": full_message, "access_token": ACCESS_TOKEN}
  return requests.post(url, data=payload, timeout=25).json()


def post_to_instagram(image_url, caption):
  """نشر الصورة والمنشور على إنستجرام."""
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
      container_url, data=container_payload, timeout=25
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
      timeout=25,
  ).json()


def is_today_item(page_soup):
  """التأكد من أن تاريخ العنصر يوافق تاريخ اليوم بتوقيت النشر."""
  now = datetime.now()
  date_formats = [
      now.strftime("%Y/%m/%d"),
      now.strftime("%Y-%m-%d"),
      now.strftime("%d/%m/%Y"),
      now.strftime("%d-%m-%Y"),
      f"{now.day}/{now.month}/{now.year}",
      f"{now.year}/{now.month}/{now.day}",
  ]

  text_content = page_soup.get_text()
  for df in date_formats:
    if df in text_content:
      return True
  return False


def fetch_all_items():
  """جلب عناصر الأخبار والفعاليات والإعلانات من الروابط الرسمية المخصصة."""
  sources = [
      "https://www.fayoum.edu.eg/ar/News?tab=news&pageNumber=1&pageSize=12",
      "https://www.fayoum.edu.eg/ar/News?tab=events&pageNumber=1&pageSize=12",
      "https://www.fayoum.edu.eg/ar/Announcements?pageNumber=1&pageSize=12",
  ]

  found_links = []
  for source_url in sources:
    try:
      r = requests.get(source_url, headers=HEADERS, verify=False, timeout=25)
      soup = BeautifulSoup(r.text, "html.parser")
      for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if re.search(
            r"/(?:News|announcements|events)/Details/\d+", href, re.IGNORECASE
        ):
          full_url = (
              href
              if href.startswith("http")
              else f"https://www.fayoum.edu.eg{href}"
          )
          clean_url = full_url.split("?")[0]
          if clean_url not in found_links:
            found_links.append(clean_url)
    except Exception as e:
      print(f"خطأ أثناء فحص المصدر {source_url}: {e}")

  return found_links


def run():
  print(f"--- بدء دورة الفحص (المنصة المستهدفة: {TARGET_PLATFORM}) ---")
  all_links = fetch_all_items()
  print(f"إجمالي الروابط المرصودة في الأقسام: {len(all_links)}")

  fb_posted = get_posted_links(FB_HISTORY_FILE)
  ig_posted = get_posted_links(IG_HISTORY_FILE)

  for link in all_links:
    need_fb = (TARGET_PLATFORM in ["all", "facebook"]) and (
        link not in fb_posted
    )
    need_ig = (TARGET_PLATFORM in ["all", "instagram"]) and (
        link not in ig_posted
    )

    if not (need_fb or need_ig):
      continue

    try:
      det_res = requests.get(link, headers=HEADERS, verify=False, timeout=25)
      det_soup = BeautifulSoup(det_res.text, "html.parser")

      # التحقق من أن الخبر يخص تاريخ اليوم فقط
      if not is_today_item(det_soup):
        print(f"تخطي الرابط {link}: ليس بتاريخ اليوم.")
        continue

      print(f"\n--- معالجة عنصر اليوم: {link} ---")

      title_elem = (
          det_soup.find("h1")
          or det_soup.find("h2")
          or det_soup.find("title")
      )
      title = (
          title_elem.get_text(strip=True)
          if title_elem
          else "تحديث جديد من جامعة الفيوم"
      )

      # استخراج الصورة الحقيقية للخبر بدقة دون أيقونات
      img_url = extract_real_article_image(det_soup)

      # 1. النشر على فيسبوك
      if need_fb:
        fb_message = f"{title}\n\nالتفاصيل كاملة عبر الرابط:\n{link}"
        fb_res = post_to_facebook(fb_message, link)
        print(f"استجابة فيسبوك: {fb_res}")
        if fb_res and "id" in fb_res:
          save_posted_link(FB_HISTORY_FILE, link)
          print(f"تم توثيق الرابط على فيسبوك: {link}")

      # 2. النشر على إنستجرام
      if need_ig:
        if img_url:
          ig_caption = f"{title}\n.\n.\n#جامعة_الفيوم #أخبار_الجامعة"
          ig_res = post_to_instagram(img_url, ig_caption)
          print(f"استجابة إنستجرام: {ig_res}")
          if ig_res and "id" in ig_res:
            save_posted_link(IG_HISTORY_FILE, link)
            print(f"تم توثيق الرابط على إنستجرام: {link}")
        else:
          print("لا توجد صورة خبرية صالحة؛ تم تخطي إنستجرام لهذا العنصر.")

      time.sleep(12)

    except Exception as e:
      print(f"خطأ أثناء معالجة الرابط {link}: {e}")


if __name__ == "__main__":
  run()
