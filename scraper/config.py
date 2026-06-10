import os

BASE_URL = "https://cn.govopendata.com/xinwenlianbo"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
DAYS_TO_SCRAPE = 90

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
REQUEST_TIMEOUT = 30
