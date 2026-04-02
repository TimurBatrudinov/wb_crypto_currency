#!/usr/bin/env python3
import subprocess
import json
import re
import os
import sys

session = "rate01"

if os.name == 'nt':
    chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    base = f'agent-browser --executable-path "{chrome_path}" --session {session}'
else:
    base = f'agent-browser --session {session}'

print("Opening browser...")
first_cmd = f'{base} open https://skycapital.group/?baseAsset=USDT&quoteAsset=RUB'
subprocess.run(first_cmd, shell=True, capture_output=True, timeout=30)

print("Getting token...")
cookie_result = subprocess.run(f'agent-browser --session {session} cookies get access_token', shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)

m = re.search(r'access_token=([^\s]+)', cookie_result.stdout)
token = m.group(1) if m else None

if not token:
    print("No token found")
    exit(1)

print(f"Token: {token[:20]}...")

print("Fetching...")
fetch_cmd = f'agent-browser --session {session} eval "fetch(\'https://api.skycapital.group/exchange-rates/instant\', {{headers: {{\'Authorization\': \'Bearer {token}\'}}}}) .then(r=>r.json()).then(d=>console.log(JSON.stringify(d)))"'
subprocess.run(fetch_cmd, shell=True, capture_output=True, timeout=15)

import time
time.sleep(2)

print("Getting console...")
console_result = subprocess.run(f'agent-browser --session {session} console', shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)

for line in console_result.stdout.split('\n'):
    line = line.strip()
    if line.startswith('[log]'):
        line = line[5:].strip()
        try:
            data = json.loads(line)
            for item in data:
                if item['baseAsset'] == 'USDT_SPL' and item['quoteAsset'] == 'RUB':
                    print(f"USDT_SPL-RUB rate: {item['sell']}")
                    exit(0)
        except Exception as e:
            pass

print("Not found")
