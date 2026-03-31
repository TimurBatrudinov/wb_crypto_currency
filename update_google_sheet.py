import requests
import json
import gspread
from google.oauth2.service_account import Credentials
import datetime

# Получаем курс RUB→USDT
url = "https://admin-service.whitebird.io/api/v1/exchange/calculation"
payload = {
    "currencyPair": {"fromCurrency": "RUB", "toCurrency": "USDT"},
    "calculation": {"inputAsset": "1000"}
}
headers = {"Content-Type": "application/json", "Accept": "application/json"}

response = requests.post(url, json=payload, headers=headers, timeout=20)
response.raise_for_status()
data = response.json()
ratio = data.get("rate", {}).get("ratio")

if ratio is None:
    print("Ошибка: поле rate.ratio не найдено")
    exit(1)

print(f"Получено значение ratio = {ratio}")

# Подключение к Google Sheets
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(credentials)

SPREADSHEET_ID = "1QcgQyiTsPKTkHvPRGAIibd3EoZ-GuCh4uorpLEAr9SI"
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

# Записываем новую строку
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
sheet.append_row([now, ratio])
print("Записано в Google Sheet")
