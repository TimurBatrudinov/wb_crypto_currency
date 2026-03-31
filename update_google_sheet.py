import os
import json
import logging
import datetime
import sys
from typing import Optional, Dict, Any, List

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
WHITEBIRD_API_URL = "https://admin-service.whitebird.io/api/v1/exchange/calculation"
ALTYN_API_URL = "https://api.lk.altyn.one/website/rates/"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_whitebird_rate(from_currency: str = "RUB", to_currency: str = "USDT") -> float:
    """Fetches the exchange rate from the Whitebird API."""
    payload = {
        "currencyPair": {"fromCurrency": from_currency, "toCurrency": to_currency},
        "calculation": {"inputAsset": "1000"}
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(WHITEBIRD_API_URL, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        
        ratio = data.get("rate", {}).get("ratio")
        if ratio is None:
            raise ValueError("Field 'rate.ratio' not found in Whitebird API response")
        
        logger.info(f"Whitebird ratio: {ratio}")
        return float(ratio)
    except Exception as e:
        logger.error(f"Error fetching Whitebird rate: {e}")
        raise


def get_altyn_rate() -> float:
    """Fetches the exchange rate from the Altyn API (translated from JS)."""
    try:
        response = requests.get(ALTYN_API_URL, timeout=20)
        response.raise_for_status()
        data = response.json()
        
        # Taking the second element as per ALTYN.md logic (json[1])
        if len(data) < 2:
            raise ValueError("Altyn API returned less than 2 elements")
            
        rate_val = float(data[1]["rate"])
        altyn_ratio = 1 / rate_val
        
        logger.info(f"Altyn ratio: {altyn_ratio}")
        return altyn_ratio
    except Exception as e:
        logger.error(f"Error fetching Altyn rate: {e}")
        raise


def update_google_sheet(rates: List[float]) -> None:
    """Connects to Google Sheets and appends a new row with timestamp and provided rates."""
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
        # Appending [timestamp, rate1, rate2, ...]
        row = [now] + rates
        sheet.append_row(row)
        logger.info(f"Successfully recorded to sheet: {row}")
    except Exception as e:
        logger.error(f"Error updating Google Sheet: {e}")
        raise


def main():
    try:
        # Fetching rates from both sources
        whitebird_ratio = get_whitebird_rate()
        altyn_ratio = get_altyn_rate()
        
        # Updating the sheet
        update_google_sheet([whitebird_ratio, altyn_ratio])
        
    except Exception as e:
        logger.error("Execution failed", exc_info=True)
        print(f"\nCRITICAL ERROR: {e}", file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    main()
