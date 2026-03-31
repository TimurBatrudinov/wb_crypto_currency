import os
import json
import logging
import datetime
from typing import Optional, Dict, Any

import requests
import gspread
from google.oauth2.service_account import Credentials

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
API_URL = "https://admin-service.whitebird.io/api/v1/exchange/calculation"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_exchange_rate(from_currency: str = "RUB", to_currency: str = "USDT") -> float:
    """Fetches the exchange rate from the Whitebird API."""
    payload = {
        "currencyPair": {"fromCurrency": from_currency, "toCurrency": to_currency},
        "calculation": {"inputAsset": "1000"}
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        
        ratio = data.get("rate", {}).get("ratio")
        if ratio is None:
            raise ValueError("Field 'rate.ratio' not found in API response")
        
        logger.info(f"Successfully fetched ratio: {ratio}")
        return float(ratio)
    except Exception as e:
        logger.error(f"Error fetching exchange rate: {e}")
        raise


def update_google_sheet(ratio: float) -> None:
    """Connects to Google Sheets and appends a new row with the ratio."""
    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")

    if not service_account_json or not spreadsheet_id:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON or SPREADSHEET_ID environment variables are not set")

    try:
        service_account_info = json.loads(service_account_json)
        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        gc = gspread.authorize(credentials)
        sheet = gc.open_by_key(spreadsheet_id).sheet1
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([now, ratio])
        logger.info(f"Successfully recorded to sheet: {now} | {ratio}")
    except Exception as e:
        logger.error(f"Error updating Google Sheet: {e}")
        raise


def main():
    try:
        ratio = get_exchange_rate()
        update_google_sheet(ratio)
    except Exception:
        exit(1)


if __name__ == "__main__":
    main()
