import base64
from datetime import datetime
import io
import os
import re
import time
import zoneinfo
from bs4 import BeautifulSoup
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
import urllib3
from urllib3.util.retry import Retry

# تعطيل تحذيرات شهادات SSL لموقع الجامعة
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# المتغيرات السرية وبيئة التشغيل
ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
IMGBB_KEY = os.environ.get("IMGBB_API_KEY")
TARGET_PLATFORM = os.environ.get("TARGET_PLATFORM", "all").lower()

FB_HISTORY_FILE = "posted_fb.txt"
IG_HISTORY_FILE = "posted_ig.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# إعداد جلسة اتصالات تتحمل بطء السيرفر وتكرر المحاولات عند الانقطاع
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    raise_on_status=False,
)
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))


def get_posted_links(file_path):
  if not os.path.exists(file_path):
    return set()
  with open(file_path, "r", encoding="utf-8") as f:
    return set(line.strip() for line in f if line.strip())


def save_posted_link(file_path, link):
  with open(file_path, "a", encoding="utf-8") as f:
    f.write(f"{link}\n")


def is_today_item(page_soup):
  """التحقق الدقيق من أن الخبر نُشر بتاريخ اليوم بتوقيت جمهورية مصر العربية."""
  try:
    cairo_tz = zoneinfo.ZoneInfo("Africa/Cairo")
    now = datetime.now(cairo_tz)
  except Exception:
    now = datetime.now()

  day = str(now.day)
  day_pad = f"{now.day:02d}"
  month = str(now.month)
  month_pad = f"{now.month:02d}"
  year = str(now.year)

  # أنماط الأرقام للتاريخ
  date_patterns = [
      f"{day_pad}/{month_pad}/{year}",
      f"{day}/{month}/{year}",
      f"{year}/{month_pad}/{day_pad}",
      f"{year}/{month}/{day}",
      f"{day_pad}-{month_pad}-{year}",
      f"{day}-{month}-{year}",
      f"{year}-{month_pad}-{day_pad}",
      f"{year}-{month}-{day}",
  ]

  # أسماء الشهور العربية
  arabic_months = [
      "",
      "يناير",
      "فبراير",
      "مارس",
      "أبريل",
      "مايو",
      "يونيو",
      "يوليو",
      "أغسطس",
      "سبتمبر",
      "أكتوبر",
      "نوفمبر",
      "ديسمبر",
  ]
  month_name = arabic_months[now.month]

  text = page_soup.get_text()

  # 1. مطابقة الأنماط الرقمية
  for dp in date_patterns:
    if dp in text:
      return True

  # 2. مطابقة التاريخ بالاسم العربي (مثال: 19 سبتمبر 2026)
  if (day in text or day_pad in text) and (month_name in text) and (year in text):
    return True

  # 3. البحث في وسوم meta المخصصة للتواريخ
  for meta_name in [
      "article:published_time",
      "date",
      "publication_date",
      "DC.date.issued",
  ]:
    meta = page_soup.find("meta", attrs={"name": meta_name}) or page_soup.find(
        "meta", attrs={"property": meta_name}
    )
    if meta and meta.get("content"):
      m_content = meta["content"]
      if (
          f"{year}-{month_pad}-{day_pad}" in m_content
          or f"{year}/{month_pad}/{day_pad}" in m_content
      ):
        return True

  return False


def extract_real_article_image(soup):
  """استخراج الصورة الأصلية المرفقة داخل محتوى الخبر وتجاهل الأيقونات واللوجو."""
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
      "placeholder",
      "default",
  ]

  # 1. فحص وسم Open Graph
  og_image = soup.find("meta", property="og:image")
  if og_image and og_image.get("content"):
    c = og_image["content"].strip()
    if c.startswith("http") and not any(bad in c.lower() for bad in bad_keywords):
      return c

  # 2. حصر البحث داخل جسم المقال فقط
  body = (
      soup.find(
          "div", class_=re.compile(r"details|content|article|news-body", re.I)
      )
      or soup.find("article")
      or soup.find("main")
      or soup
  )

  candidates = []
  for img in body.find_all("img", src=True):
    src = img["src"].strip()
    if not src or any(bad in src.lower() for bad in bad_keywords):
      continue

    full_url = (
        src if src.startswith("http") else f"https://www.fayoum.edu.eg{src}"
    )
    if any(
        k in full_url.lower()
        for k in ["upload", "news", "events", "announc", "details", "images"]
    ):
      candidates.append(full_url)

  # فحص المقاسات الفعلية للصورة
  for u in candidates:
    try:
      resp = session.get(u, headers=HEADERS, timeout=15, verify=False)
      if resp.status_code == 200:
        im = Image.open(io.BytesIO(resp.content))
        w, h = im.size
        if w >= 300 and h >= 200:
          return u
    except Exception:
      continue

  return candidates[0] if candidates else ""


def adjust_and_upload_image(image_url):
  """فحص أبعاد الصورة وضبطها لتوافق شروط إنستجرام وتوسيطها في إطار أبيض ورفعها عبر ImgBB."""
  try:
    resp = session.get(image_url, headers=HEADERS, timeout=25, verify=False)
    if resp.status_code != 200:
      return image_url

    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    w, h = img.size
    ratio = w / h

    if 0.8 <= ratio <= 1.91 and w >= 320:
      return image_url

    max_side = max(w, h, 600)
    new_img = Image.new("RGB", (max_side, max_side), (255, 255, 255))
    offset = ((max_side - w) // 2, (max_side - h) // 2)
    new_img.paste(img, offset)

    buffer = io.BytesIO()
    new_img.save(buffer, format="JPEG", quality=92)
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    if IMGBB_KEY:
      up_res = session.post(
          "https://api.imgbb.com/1/upload",
          data={"key": IMGBB_KEY, "image": img_b64},
          timeout=30,
      ).json()
      if up_res.get("success"):
        hosted = up_res["data"]["url"]
        print(f"تم رفع صورة الخبر المعدلة بنجاح: {hosted}")
        return hosted
      else:
        print(f"تنبيه ImgBB: {up_res}")
  except Exception as e:
    print(f"خطأ أثناء معالجة الصورة: {e}")

  return image_url


def post_to_facebook(message, link):
  url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
  full_message = f"{message}\n\n{link}" if link not in message else message
  payload = {"message": full_message, "access_token": ACCESS_TOKEN}
  return session.post(url, data=payload, timeout=25).json()


def post_to_instagram(image_url, caption):
  if not image_url or not IG_USER_ID:
    return None

  final_img = adjust_and_upload_image(image_url)

  container_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
  c_payload = {
      "image_url": final_img,
      "caption": caption,
      "access_token": ACCESS_TOKEN,
  }
  c_res = session.post(container_url, data=c_payload, timeout=25).json()
  creation_id = c_res.get("id")
  if not creation_id:
    print(f"خطأ حاوية إنستجرام: {c_res}")
    return c_res

  time.sleep(5)
  publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
  return session.post(
      publish_url,
      data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
      timeout=25,
  ).json()


def fetch_all_items():
  sources = [
      "https://www.fayoum.edu.eg/ar/News?tab=news&pageNumber=1&pageSize=12",
      "https://www.fayoum.edu.eg/ar/Announcements?pageNumber=1&pageSize=12",
      "https://www.fayoum.edu.eg/ar/News?tab=events&pageNumber=1&pageSize=12",
  ]

  found_links = []
  for src in sources:
    try:
      r = session.get(src, headers=HEADERS, verify=False, timeout=40)
      soup = BeautifulSoup(r.text, "html.parser")
      for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if re.search(
            r"/(?:News|announcements|events)/Details/\d+", href, re.IGNORECASE
        ):
          full = (
              href
              if href.startswith("http")
              else f"https://www.fayoum.edu.eg{href}"
          )
          clean = full.split("?")[0]
          if clean not in found_links:
            found_links.append(clean)
    except Exception as e:
      print(f"تنبيه أثناء فحص المصدر {src}: {e}")

  return found_links


def run():
  print(f"--- بدء دورة الفحص اليومي (المنصة المستهدفة: {TARGET_PLATFORM}) ---")
  all_links = fetch_all_items()
  print(f"إجمالي الروابط المرصودة من كافة الأقسام: {len(all_links)}")

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
      det_res = session.get(link, headers=HEADERS, verify=False, timeout=35)
      det_soup = BeautifulSoup(det_res.text, "html.parser")

      # التحقق من أن الخبر صادر اليوم فقط
      if not is_today_item(det_soup):
        print(f"تخطي الرابط {link}: ليس بتاريخ اليوم.")
        continue

      print(f"\n--- رصد عنصر بتاريخ اليوم وجاري نشره: {link} ---")

      title_el = (
          det_soup.find("h1")
          or det_soup.find("h2")
          or det_soup.find("title")
      )
      title = (
          title_el.get_text(strip=True)
          if title_el
          else "تحديث جديد من جامعة الفيوم"
      )

      # استخراج الصورة الأصلية للخبر
      img_url = extract_real_article_image(det_soup)

      # 1. النشر على فيسبوك
      if need_fb:
        fb_msg = f"{title}\n\nالتفاصيل كاملة عبر الرابط:\n{link}"
        fb_res = post_to_facebook(fb_msg, link)
        print(f"استجابة فيسبوك: {fb_res}")
        if fb_res and "id" in fb_res:
          save_posted_link(FB_HISTORY_FILE, link)
          print(f"تم توثيق الرابط على فيسبوك بنجاح: {link}")

      # 2. النشر على إنستجرام
      if need_ig:
        if img_url:
          ig_cap = f"{title}\n.\n.\n#جامعة_الفيوم #أخبار_الجامعة"
          ig_res = post_to_instagram(img_url, ig_cap)
          print(f"استجابة إنستجرام: {ig_res}")
          if ig_res and "id" in ig_res:
            save_posted_link(IG_HISTORY_FILE, link)
            print(f"تم توثيق الرابط على إنستجرام بنجاح: {link}")
        else:
          print("لا توجد صورة خبرية صالحة؛ تم تخطي إنستجرام لهذا الخبر.")

      time.sleep(12)

    except Exception as e:
      print(f"خطأ أثناء معالجة الرابط {link}: {e}")


if __name__ == "__main__":
  run()
