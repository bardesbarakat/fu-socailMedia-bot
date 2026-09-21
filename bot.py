name: Run University Social Media Bot

on:
  schedule:
    # يعمل البوت تلقائياً كل ساعة (يمكنك تعديلها لاحقاً إذا أردتِ)
    - cron: '0 * * * *'
  workflow_dispatch:
    # يتيح لكِ تشغيل البوت يدوياً من زر Run workflow

jobs:
  run-bot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run News Bot
        env:
          PAGE_ACCESS_TOKEN: ${{ secrets.PAGE_ACCESS_TOKEN }}
          PAGE_ID: ${{ secrets.PAGE_ID }}
          IG_USER_ID: ${{ secrets.IG_USER_ID }}
          CLOUDINARY_CLOUD_NAME: ${{ secrets.CLOUDINARY_CLOUD_NAME }}
          CLOUDINARY_API_KEY: ${{ secrets.CLOUDINARY_API_KEY }}
          CLOUDINARY_API_SECRET: ${{ secrets.CLOUDINARY_API_SECRET }}
        run: python bot.py

      - name: Commit and Push History
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add posted_news.txt
          git commit -m "Update posted news links" || echo "No changes to commit"
          git push
