import os
import json
import logging
import datetime
import sys
import random
import subprocess
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

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
CIFRA_API_BASE_URL = "https://api.cifra-broker.by/api/site/ticker"
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
    """Fetches the exchange rate from the Altyn API."""
    try:
        response = requests.get(ALTYN_API_URL, timeout=20)
        response.raise_for_status()
        data = response.json()
        if len(data) < 2:
            raise ValueError("Altyn API returned less than 2 elements")
        rate_val = float(data[1]["rate"])
        altyn_ratio = 1 / rate_val
        logger.info(f"Altyn ratio: {altyn_ratio}")
        return altyn_ratio
    except Exception as e:
        logger.error(f"Error fetching Altyn rate: {e}")
        raise

def get_cifra_rate() -> float:
    """Fetches the exchange rate from Cifra API directly using a POST request."""
    key = random.random()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://cifra.by/catalog/"
    }
    try:
        response = requests.post(f"{CIFRA_API_BASE_URL}?key={key}", headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        tickers = data.get("data", {}).get("ticker", [])
        for t in tickers:
            if t.get("ticker") == "USDT-RUB.IMEX":
                ltp = float(t.get("ltp"))
                logger.info(f"Cifra ratio: {ltp}")
                return ltp
        raise ValueError("USDT-RUB.IMEX ticker not found in Cifra response")
    except Exception as e:
        logger.error(f"Error fetching Cifra rate: {e}")
        raise

def get_skycapital_rate() -> float:
    """Fetches the exchange rate from SkyCapital using agent-browser."""
    url = "https://skycapital.group/?baseAsset=USDT&quoteAsset=RUB"
    try:
        subprocess.run(["agent-browser", "open", url], capture_output=True, timeout=30)
        subprocess.run(
            ["agent-browser", "wait", "--load", "networkidle"],
            capture_output=True, timeout=30
        )
        
        result = subprocess.run(
            ["agent-browser", "eval", "document.getElementById('instant')?.innerText || document.getElementById('instant')?.textContent"],
            capture_output=True, text=True, timeout=30
        )
        
        output = result.stdout.strip()
        json_start = output.find("{")
        if json_start == -1:
            json_start = output.find("[")
        if json_start != -1:
            data = json.loads(output[json_start:])
            for item in data:
                if item.get("baseAsset") == "USDT_SPL":
                    buy_rate = float(item.get("buy"))
                    logger.info(f"SkyCapital ratio: {buy_rate}")
                    return buy_rate
        raise ValueError("USDT_SPL not found in SkyCapital response")
    except Exception as e:
        logger.error(f"Error fetching SkyCapital rate: {e}")
        raise
    finally:
        subprocess.run(["agent-browser", "close"], capture_output=True)

# Cell coordinates
RANGE_TO_UPDATE = "B2:B5"

def update_google_sheet(whitebird_rate: float, altyn_rate: float, cifra_rate: float, skycapital_rate: float) -> None:
    """Updates the Google Sheet in a single batch call."""
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
        
        # Batch update: column B, rows 1-4
        values = [[whitebird_rate], [altyn_rate], [cifra_rate], [skycapital_rate]]
        sheet.update(RANGE_TO_UPDATE, values)
        
        logger.info(f"Successfully updated sheet range {RANGE_TO_UPDATE} with values: {values}")
    except Exception as e:
        logger.error(f"Error updating Google Sheet: {e}")
        raise

def main():
    try:
        # Fetching rates in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_whitebird = executor.submit(get_whitebird_rate)
            future_altyn = executor.submit(get_altyn_rate)
            future_cifra = executor.submit(get_cifra_rate)
            future_skycapital = executor.submit(get_skycapital_rate)
            
            whitebird_ratio = future_whitebird.result()
            altyn_ratio = future_altyn.result()
            cifra_ratio = future_cifra.result()
            skycapital_ratio = future_skycapital.result()
        
        # Updating the sheet
        update_google_sheet(whitebird_ratio, altyn_ratio, cifra_ratio, skycapital_ratio)
        
    except Exception as e:
        logger.error("Execution failed", exc_info=True)
        print(f"\nCRITICAL ERROR: {e}", file=sys.stderr)
        exit(1)

if __name__ == "__main__":
    main()
