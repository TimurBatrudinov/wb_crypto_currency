import requests
import json

def get_ratio(input_rub: str = "1000") -> str:
    url = "https://admin-service.whitebird.io/api/v1/exchange/calculation"

    payload = {
        "currencyPair": {
            "fromCurrency": "RUB",
            "toCurrency": "USDT"
        },
        "calculation": {
            "inputAsset": str(input_rub)
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()

        data = response.json()

        print("\nПолный ответ сервера:")
        print(json.dumps(data, indent=4, ensure_ascii=False))

        ratio = data.get("rate", {}).get("ratio")
        if not ratio:
            print("Ошибка: поле rate.ratio не найдено")
            return None

        print("\nИзвлечённое значение ratio:")
        print("ratio =", ratio)

        # Сохраняем ratio в файл, чтобы Actions мог использовать как артефакт
        with open("ratio.txt", "w", encoding="utf-8") as f:
            f.write(str(ratio))

        return ratio

    except requests.exceptions.RequestException as e:
        print("Ошибка запроса:", e)
        return None


if __name__ == "__main__":
    get_ratio("1000")
