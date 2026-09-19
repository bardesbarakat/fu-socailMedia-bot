import base64
import io
import os
import re
import time
from bs4 import BeautifulSoup
from PIL import Image
import requests
import urllib3

# Dhimmoota nageenya SSL marsariitii yuunivarsiitii dhiisuuf
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Mallattoolee fi teessoo icciitii GitHub Secrets irraa fudhachuu
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
  """Hammamtaa suuraa Instagram tiif mijeessee ImgBB irratti ol-fe'uu."""
  try:
    resp = requests.get(image_url, headers=HEADERS, timeout=25, verify=False)
    if resp.status_code != 200:
      return image_url

    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    w, h = img.size
    ratio = w / h

    # Ulaagaalee Instagram: reeshoon 0.8 fi 1.91 gidduu ta'uu qaba
    if 0.8 <= ratio <= 1.91 and w >= 320:
      return image_url

    # Suuraa sana gara boca iskuweerii (1:1) duubbee adii qabutti jijjiiruu
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
        print(f"Suuraan sirreeffamee milkaa'inaan ol-fe'ameera: {hosted_url}")
        return hosted_url
      else:
        print(f"Akeekkachiisa ImgBB: {up_res}")

  except Exception as e:
    print(f"Dogoggora suuraa qindeessuu keessatti: {e}")

  return image_url


def post_to_facebook(message, link):
  """Facebook New Pages Experience irratti ergaa fi hidhaa maxxansuu."""
  url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
  # New Pages Experience keessatti hidhaan ergaa keessatti qindaa'a
  full_message = f"{message}\n\n{link}" if link not in message else message
  payload = {"message": full_message, "access_token": ACCESS_TOKEN}
  return requests.post(url, data=payload, timeout=25).json()


def post_to_instagram(image_url, caption):
  """Suuraa fi barreeffama Instagram irratti maxxansuu."""
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
    print(f"Dogoggora qophii Instagram: {c_res}")
    return c_res

  time.sleep(5)
  publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
  return requests.post(
      publish_url,
      data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
      timeout=25,
  ).json()


def fetch_all_unposted():
  """Oduuwwan, beeksisa fi sagantaalee haaraa hin maxxanfamne hunda walitti qabuu."""
  posted_links = get_posted_links()

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
      print(f"Dogoggora marsariitii sakatta'uu keessatti {source_url}: {e}")

  print(f"Waliigala hidhaawwan argaman: {len(found_links)}")
  unposted = [link for link in found_links if link not in posted_links]
  return unposted


def run():
  print("--- Sakatta'iinsi eegalameera ---")
  unposted_items = fetch_all_unposted()
  print(f"Baay'ina oduu hin maxxanfamne: {len(unposted_items)}")

  if not unposted_items:
    print("Oduun haaraan maxxanfamu hin jiru.")
    return

  # Yeroo tokkotti baay'ee akka hin maxxansineef hanga 2 qofa maxxansa
  MAX_PER_RUN = 2
  items_to_post = list(reversed(unposted_items))[:MAX_PER_RUN]

  for link in items_to_post:
    print(f"\n--- Maxxansuun jalqabameera: {link} ---")
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
          else "Oduu Haaraa Yuunivarsiitii Fayoum"
      )

      img_elem = det_soup.find(
          "img",
          src=lambda s: s
          and any(
              k in s.lower()
              for k in [
                  "news",
                  "upload",
                  "announcement",
                  "events",
                  "images",
                  "details",
              ]
          ),
      )
      img_url = ""
      if img_elem and img_elem.get("src"):
        src = img_elem["src"]
        img_url = (
            src if src.startswith("http") else f"https://www.fayoum.edu.eg{src}"
        )

      fb_message = f"{title}\n\nOdeeffannoo guutuu argachuuf hidhaa kanaan seenaa:\n{link}"
      ig_caption = f"{title}\n.\n.\n#FayoumUniversity #News"

      # 1. Facebook irratti maxxansuu
      fb_res = post_to_facebook(fb_message, link)
      print(f"Deebii Facebook: {fb_res}")

      # 2. Instagram irratti maxxansuu
      ig_res = None
      if img_url:
        ig_res = post_to_instagram(img_url, ig_caption)
        print(f"Deebii Instagram: {ig_res}")

      # Lamaanuu ykn tokko yoo milkaa'e galmee irratti qabachuu
      if (fb_res and "id" in fb_res) or (ig_res and "id" in ig_res):
        save_posted_link(link)
        print(f"Milkaa'inaan galmeeffameera: {link}")

      time.sleep(15)

    except Exception as e:
      print(f"Dogoggora maxxansuu keessatti {link}: {e}")


if __name__ == "__main__":
  run()
