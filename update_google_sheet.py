import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import datetime
from io import StringIO

# --- 1. Получаем курс RUB→USDT ---
url = "https://admin-service.whitebird.io/api/v1/exchange/calculation"
payload = {
    "currencyPair": {"fromCurrency": "RUB", "toCurrency": "USDT"},
    "calculation": {"inputAsset": "1000"}
}
headers = {"Content-Type": "application/json", "Accept": "application/json"}

try:
    response = requests.post(url, json=payload, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()
    ratio = data.get("rate", {}).get("ratio")
    if ratio is None:
        print("Ошибка: поле rate.ratio не найдено")
        exit(1)
    print(f"Получено значение ratio = {ratio}")
except Exception as e:
    print("Ошибка при получении курса:", e)
    exit(1)

# --- 2. Подключаемся к Google Sheets напрямую из строки JSON ---
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")

if not SERVICE_ACCOUNT_JSON or not SPREADSHEET_ID:
    print("Ошибка: GOOGLE_SERVICE_ACCOUNT_JSON или SPREADSHEET_ID не заданы")
    exit(1)

try:
    # Восстанавливаем переносы строк в private_key
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    credentials = Credentials.from_service_account_info(service_account_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
except Exception as e:
    print("Ошибка при подключении к Google Sheets:", e)
    exit(1)

# --- 3. Добавляем новую строку с timestamp и ratio ---
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
try:
    sheet.append_row([now, ratio])
    print(f"Записано в таблицу: {now} | {ratio}")
except Exception as e:
    print("Ошибка при записи в таблицу:", e)
    exit(1)
