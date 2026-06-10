import os

BASE_URL = "https://cn.govopendata.com/xinwenlianbo"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
DAYS_TO_SCRAPE = 90  # default: last 90 days
CHROME_CDP_URL = "http://127.0.0.1:9222"
PAGE_LOAD_WAIT = 6  # seconds to wait for SPA content to render
