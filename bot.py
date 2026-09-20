# ==========================================
# 3. دوال النشر على فيسبوك (معدلة لتشبه الصورة)
# ==========================================
def publish_to_facebook(message, link_url):
    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("⚠️ لم يتم العثور على PAGE_ACCESS_TOKEN أو PAGE_ID في البيئة.")
        return False

    try:
        # إرسال المتغير link هو ما يصنع شكل (المعاينة) الظاهر في صورتك
        url = f"https://graph.facebook.com/v26.0/{PAGE_ID}/feed"
        payload = {
            "message": message,      # النص الذي سيظهر فوق الخبر
            "link": link_url,        # الرابط الذي سيولد الصورة والعنوان من الموقع
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
# 4. دوال النشر على إنستغرام (كما هي لم تتغير)
# ==========================================
def publish_to_instagram(image_url, caption):
    if not PAGE_ACCESS_TOKEN or not IG_USER_ID or not image_url:
        print("⚠️ توكن إنستجرام أو الصورة مفقودة.")
        return False

    try:
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
        print("⏳ جاري معالجة الصورة في إنستجرام...")
        time.sleep(10)  # زيادة وقت الانتظار لضمان معالجة الصورة

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
# 5. جلب الأخبار من الموقع (معدلة لدعم إنستجرام)
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
        links = soup.find_all("a", href=True)
        
        for link in links:
            href = link["href"]
            if "/News/Details/" in href or "/Announcements/Details/" in href:
                full_url = href if href.startswith("http") else f"https://www.fayoum.edu.eg{href}"
                title = link.get_text(strip=True) or "خبر جديد من جامعة الفيوم"
                print(f"⚡ رصد خبر: {full_url}")
                
                # --- الخطوة الإضافية: جلب صورة الخبر من أجل إنستجرام ---
                image_url = None
                article_html = fetch_url(full_url)
                if article_html:
                    article_soup = BeautifulSoup(article_html, "html.parser")
                    # محاولة البحث عن أي صورة داخل صفحة تفاصيل الخبر
                    img_tag = article_soup.find("img")
                    if img_tag and img_tag.get("src"):
                        img_src = img_tag["src"]
                        image_url = img_src if img_src.startswith("http") else f"https://www.fayoum.edu.eg{img_src}"

                # --- 1. تنفيذ النشر على فيسبوك ---
                publish_to_facebook(message=title, link_url=full_url)

                # --- 2. تنفيذ النشر على إنستجرام ---
                if image_url:
                    ig_caption = f"{title}\n\nالتفاصيل: {full_url}"
                    publish_to_instagram(image_url=image_url, caption=ig_caption)
                else:
                    print("⚠️ لم يتم النشر على إنستجرام لعدم العثور على صورة في الخبر.")

                time.sleep(2)
                break  # يكتفي بأحدث خبر من كل مصدر للتجربة
