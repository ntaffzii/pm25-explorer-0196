"""ดึงค่าคุณภาพอากาศล่าสุดจาก Air4Thai แล้วบันทึก JSON ดิบลง data/raw/

รัน:  python src/fetch_air4thai.py
"""
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:                                   # ใช้ certificate store ของระบบปฏิบัติการ (ดูตารางแก้ปัญหา: SSLError)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

URL = "http://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
HEADERS = {"User-Agent": "pm25-explorer/0.1 (student project; nattaphong.ph.67@ubu.ac.th)"}  # header ต้องเป็น ASCII ห้ามมีภาษาไทย
ROOT = Path(__file__).resolve().parents[1]          # root ของ repo
RAW_DIR = ROOT / "data" / "raw"
TZ = ZoneInfo("Asia/Bangkok")
RETRIES, WAIT = 3, 5
RETRY_STATUS = {429, 500, 502, 503, 504}          # ข้อผิดพลาดชั่วคราวที่ควรลองใหม่

RAW_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(RAW_DIR / "fetch.log", encoding="utf-8")],
)
log = logging.getLogger("fetch_air4thai")


def fetch(url: str) -> requests.Response:
    """GET พร้อม timeout และ retry เฉพาะข้อผิดพลาดชั่วคราว"""
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=(10, 60))
        except (requests.ConnectionError, requests.Timeout) as e:
            reason = str(e)                         # เครือข่ายมีปัญหา → ลองใหม่
        else:
            if r.status_code not in RETRY_STATUS:
                r.raise_for_status()                # 4xx อื่น ๆ → error ถาวร ไม่ retry
                return r
            reason = f"status {r.status_code}"      # 429/5xx → ลองใหม่
        log.warning("ครั้งที่ %d/%d ล้มเหลว: %s", attempt, RETRIES, reason)
        if attempt == RETRIES:
            raise RuntimeError(f"ล้มเหลวครบ {RETRIES} ครั้ง: {reason}")
        time.sleep(WAIT * attempt)


def validate(r: requests.Response) -> int:
    """ตรวจว่า body เป็น JSON ที่มีรายการสถานี คืนจำนวนสถานี"""
    data = r.json()                                 # ไม่ใช่ JSON → ValueError
    stations = data.get("stations") if isinstance(data, dict) else None
    if not isinstance(stations, list) or not stations:
        raise ValueError(f"ไม่พบรายการสถานี key ที่ได้: {list(data)[:10]}")
    return len(stations)


def main() -> int:
    fetched_at = datetime.now(TZ)
    try:
        r = fetch(URL)
        n = validate(r)
    except Exception as e:                          # บันทึกทุกความล้มเหลวลง log
        log.error("ดึงข้อมูลไม่สำเร็จ: %s", e)
        return 1

    path = RAW_DIR / f"air4thai_{fetched_at:%Y%m%dT%H%M%S}.json"
    path.write_bytes(r.content)                     # เก็บ body ดิบตามที่ server ส่งมา
    log.info("บันทึก %s (%d สถานี, %d bytes)", path.name, n, len(r.content))
    return 0


if __name__ == "__main__":
    sys.exit(main())