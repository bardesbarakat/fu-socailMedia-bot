# Fayoum University Website Social Media Automation Bot 

An advanced, automated Python-based pipeline that scrapes official news, announcements, and events from Fayoum University's portal (`fayoum.edu.eg`) and seamlessly cross-posts them to social media platforms (Facebook & Instagram).

---

## 💼 Engineering Highlights & Key Features

* **Resilient Web Scraping:** Built with `BeautifulSoup` and a custom-engineered `requests.Session` utilizing `urllib3` retry adapters and backoff factors to gracefully handle network drops, server timeouts, and SSL certificate bypasses.
* **Cloud-Based Image Processing Pipeline:** Integrates **Cloudinary API** to dynamically fetch, filter out UI noise (logos, icons, banners), and transform images to standardized dimensions (1080x1080 with automated padding and background matching) before publishing.
* **Multi-Platform Publishing (Meta Graph API v18.0):**
  * Automated publishing to **Facebook Pages** (supporting both image posts with captions and fallback link posts).
  * Robust **Instagram Graph API** integration supporting single-image posts and multi-item Carousel containers.
* **Idempotency & Duplicate Prevention:** Implements local text-based state logging (`posted_news.txt`) integrated with CI/CD workflows to ensure news items are never published twice.
* **CI/CD & Serverless Automation:** Fully containerized/scheduled to run autonomously via **GitHub Actions**, eliminating the need for dedicated server infrastructure.

---

## 🛠️ Tech Stack

* **Language:** Python 3.x
* **Network & Parsing:** `Requests`, `Urllib3`, `BeautifulSoup4`
* **Media Management:** `Cloudinary SDK`
* **APIs:** Meta Graph API (Facebook & Instagram)
* **Automation & DevOps:** GitHub Actions, Git

---

## ⚙️ Environment Variables

To run this project, the following environment variables must be securely configured (e.g., via GitHub Secrets or local `.env` file):

| Variable Name | Description |
| :--- | :--- |
| `PAGE_ACCESS_TOKEN` | Meta Page Access Token with proper publishing permissions |
| `PAGE_ID` | Facebook Page ID |
| `IG_USER_ID` | Instagram Business/Creator Account ID |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary Cloud Name |
| `CLOUDINARY_API_KEY` | Cloudinary API Key |
| `CLOUDINARY_API_SECRET` | Cloudinary API Secret |

---

## 🚀 Getting Started Locally

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/bardesbarakat/fu-socailMedia-bot.git](https://github.com/bardesbarakat/fu-socailMedia-bot.git)
   cd fu-socailMedia-bot
