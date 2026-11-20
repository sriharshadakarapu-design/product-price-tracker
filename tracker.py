import os
import json
import csv
import re
import smtplib
import requests

from bs4 import BeautifulSoup
from email.message import EmailMessage
from datetime import datetime, timezone
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

PRODUCTS_FILE = "products.json"
HISTORY_FILE = "price_history.csv"

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

DEFAULT_LIMIT = float(os.getenv("PRICE_LIMIT", "150"))

ALLOWED_DOMAINS = {
    "amazon.com",
    "walmart.com",
    "bestbuy.com",
    "apple.com"
}

def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []

    with open(PRODUCTS_FILE, encoding="utf-8") as file:
        return json.load(file)

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as file:
        json.dump(products, file, indent=4)

def valid_url(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()

        return (
            parsed.scheme == "https"
            and any(
                host == domain or host.endswith("." + domain)
                for domain in ALLOWED_DOMAINS
            )
        )
    except ValueError:
        return False

def get_price(product):
    url = product["url"]

    if not valid_url(url):
        print("Unsupported retailer URL:", url)
        return None

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=20
        )

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        selector = product.get("selector", "")
        element = soup.select_one(selector) if selector else None

        if not element:
            print("Price selector not found:", product["name"])
            return None

        raw_price = element.get("content") or element.get_text()
        match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", raw_price)

        if not match:
            return None

        return float(match.group().replace(",", ""))

    except requests.RequestException as error:
        print("Website request failed:", error)
        return None

def send_email(product, price):
    if not all([EMAIL_ADDRESS, EMAIL_PASSWORD, RECEIVER_EMAIL]):
        print("Email credentials are not configured.")
        return False

    message = EmailMessage()
    message["Subject"] = "Product Price Drop Alert!"
    message["From"] = EMAIL_ADDRESS
    message["To"] = RECEIVER_EMAIL

    message.set_content(
        f"Price alert!\n\n"
        f"Product: {product['name']}\n"
        f"Current price: ${price:.2f}\n"
        f"Target price: ${product['target_price']:.2f}\n"
        f"Product URL: {product['url']}"
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(message)

        print("Email alert sent for:", product["name"])
        return True

    except Exception as error:
        print("Email sending failed:", error)
        return False

def save_history(product, price):
    new_file = not os.path.exists(HISTORY_FILE)

    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if new_file:
            writer.writerow([
                "Date",
                "Product",
                "Retailer",
                "Price",
                "Target Price"
            ])

        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            product["name"],
            product["retailer"],
            price,
            product["target_price"]
        ])

def main():
    products = load_products()

    for product in products:
        print("Checking:", product["name"])

        price = get_price(product)

        if price is None:
            continue

        product["current_price"] = price
        product["last_checked"] = datetime.now(
            timezone.utc
        ).isoformat()

        save_history(product, price)

        target = float(product.get("target_price", DEFAULT_LIMIT))

        print(f"Current price: ${price:.2f}")
        print(f"Target price: ${target:.2f}")

        previous_alert = product.get("last_alert_price")

        if price <= target and previous_alert != price:
            if send_email(product, price):
                product["last_alert_price"] = price

    save_products(products)
    print("Price tracking completed!")

if __name__ == "__main__":
    main()
