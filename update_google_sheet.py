import os
import json
import logging
import datetime
import sys
import random
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
SKY_API_URL = "https://api.skycapital.group/exchange-rates/instant"
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

def get_sky_rate() -> Dict[str, float]:
    """Fetches the exchange rates from SkyCapital for USDT and USDT_ERC20."""
    import subprocess
    import re
    import time
    
    session = f"rate_{int(time.time())}"
    
    if os.name == 'nt':
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        base = f'agent-browser --executable-path "{chrome_path}" --session {session}'
    else:
        base = f'agent-browser --session {session}'

    try:
        logger.info("SkyCapital: Opening browser...")
        subprocess.run(f'{base} open https://skycapital.group/?baseAsset=USDT&quoteAsset=RUB', shell=True, capture_output=True, timeout=30)

        logger.info("SkyCapital: Getting token...")
        cookie_result = subprocess.run(f'agent-browser --session {session} cookies get access_token', shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)

        m = re.search(r'access_token=([^\s]+)', cookie_result.stdout)
        token = m.group(1) if m else None

        if not token:
            raise ValueError("No token found for SkyCapital")

        logger.info("SkyCapital: Fetching rates...")
        fetch_cmd = f'agent-browser --session {session} eval "fetch(\'{SKY_API_URL}\', {{headers: {{\'Authorization\': \'Bearer {token}\'}}}}) .then(r=>r.json()).then(d=>console.log(JSON.stringify(d)))"'
        subprocess.run(fetch_cmd, shell=True, capture_output=True, timeout=15)

        time.sleep(2)

        logger.info("SkyCapital: Getting console output...")
        console_result = subprocess.run(f'agent-browser --session {session} console', shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)

        tickers_to_find = ['USDT', 'USDT_ERC20', 'USDT_SPL']
        found_rates = {}

        for line in console_result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('[log]'):
                line = line[5:].strip()
                try:
                    data = json.loads(line)
                    for item in data:
                        if item['baseAsset'] in tickers_to_find and item['quoteAsset'] == 'RUB':
                            found_rates[item['baseAsset']] = float(item['sell'])
                    
                    if found_rates:
                        logger.info(f"SkyCapital rates: {found_rates}")
                        return found_rates
                except:
                    continue
        
        raise ValueError("SkyCapital rates not found in console output")
    except Exception as e:
        logger.error(f"Error fetching SkyCapital rate: {e}")
        raise

# Cell coordinates
RANGE_TO_UPDATE = "B2:B8"

def update_google_sheet(whitebird_rate: float, altyn_rate: float, cifra_rate: float, sky_rates: Dict[str, float]) -> None:
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
        sheet = gc.open_by_key(spreadsheet_id).worksheet("crypto_rates")
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get individual SkyCapital rates
        sky_usdt = sky_rates.get('USDT', 0.0)
        sky_erc20 = sky_rates.get('USDT_ERC20', 0.0)
        sky_spl = sky_rates.get('USDT_SPL', 0.0)
        
        # Batch update: column B, rows 1-7
        values = [[now], [whitebird_rate], [altyn_rate], [cifra_rate], [sky_usdt], [sky_erc20], [sky_spl]]
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
            future_sky = executor.submit(get_sky_rate)
            
            whitebird_ratio = future_whitebird.result()
            altyn_ratio = future_altyn.result()
            cifra_ratio = future_cifra.result()
            sky_ratios = future_sky.result()
        
        # Updating the sheet
        update_google_sheet(whitebird_ratio, altyn_ratio, cifra_ratio, sky_ratios)
        
    except Exception as e:
        logger.error("Execution failed", exc_info=True)
        print(f"\nCRITICAL ERROR: {e}", file=sys.stderr)
        exit(1)

if __name__ == "__main__":
    main()
