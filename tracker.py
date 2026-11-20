
import os
import re
import json
import csv
import smtplib
import requests

from bs4 import BeautifulSoup
from email.message import EmailMessage
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

PRODUCTS_FILE = "products.json"
HISTORY_FILE = "price_history.csv"

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9"
}


def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []

    with open(PRODUCTS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as file:
        json.dump(products, file, indent=4)


def extract_price(value):
    """Convert a price value into a positive number."""
    if value is None:
        return None

    if isinstance(value, dict):
        value = value.get("price")

    if isinstance(value, list):
        for item in value:
            result = extract_price(item)
            if result is not None:
                return result
        return None

    match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", str(value))

    if not match:
        return None

    try:
        price = float(match.group().replace(",", ""))
        return price if price > 0 else None
    except ValueError:
        return None


def find_jsonld_price(data):
    """Search structured product data for an offer price."""
    if isinstance(data, list):
        for item in data:
            price = find_jsonld_price(item)
            if price is not None:
                return price

    elif isinstance(data, dict):
        item_type = data.get("@type", "")
        if isinstance(item_type, list):
            is_product = "Product" in item_type
        else:
            is_product = item_type == "Product"

        if is_product and "offers" in data:
            price = extract_price(data["offers"])
            if price is not None:
                return price

        for value in data.values():
            if isinstance(value, (dict, list)):
                price = find_jsonld_price(value)
                if price is not None:
                    return price

    return None


def get_walmart_price(product):
    url = product["url"]

    print("Reading Walmart product:", product["name"])

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=25
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # First try structured product data.
        scripts = soup.find_all(
            "script",
            type="application/ld+json"
        )

        for script in scripts:
            try:
                data = json.loads(script.string or script.get_text())
                price = find_jsonld_price(data)

                if price is not None:
                    print("Price retrieved from product data.")
                    return price

            except (json.JSONDecodeError, TypeError):
                continue

        # Try common public price metadata.
        selectors = [
            'meta[property="product:price:amount"]',
            'meta[itemprop="price"]',
            'meta[property="og:price:amount"]'
        ]

        for selector in selectors:
            element = soup.select_one(selector)

            if element:
                price = extract_price(
                    element.get("content")
                )

                if price is not None:
                    print("Price retrieved from metadata.")
                    return price

        print("Walmart did not expose a readable price.")
        return None

    except requests.RequestException as error:
        print("Walmart request failed:", error)
        return None


def save_history(product, price):
    new_file = not os.path.exists(HISTORY_FILE)

    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

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


def send_email(product, price):
    if not all([
        EMAIL_ADDRESS,
        EMAIL_PASSWORD,
        RECEIVER_EMAIL
    ]):
        print("Email credentials are missing.")
        return False

    message = EmailMessage()

    message["Subject"] = (
        f"Price Alert: {product['name']} is now ${price:.2f}"
    )

    message["From"] = EMAIL_ADDRESS
    message["To"] = RECEIVER_EMAIL

    message.set_content(
        f"""
Product Price Alert!

Product: {product['name']}
Retailer: {product['retailer']}

Current Price: ${price:.2f}
Target Price: ${product['target_price']:.2f}

Product Link:
{product['url']}

Your target price has been reached!

Product Price Tracker
"""
    )

    try:
        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=20
        ) as server:

            server.login(
                EMAIL_ADDRESS,
                EMAIL_PASSWORD
            )

            server.send_message(message)

        print("Email alert sent successfully!")
        return True

    except Exception as error:
        print("Email sending failed:", error)
        return False


def main():
    print("===================================")
    print("     PRODUCT PRICE TRACKER")
    print("===================================")

    products = load_products()

    if not products:
        print("No products found.")
        return

    for product in products:

        print("\nChecking:", product["name"])

        if product.get("retailer") != "Walmart":
            print("This free version supports Walmart only.")
            continue

        price = get_walmart_price(product)

        if price is None:
            print("Price unavailable. No alert sent.")
            continue

        target = float(product["target_price"])

        product["current_price"] = price
        product["last_checked"] = (
            datetime.now(timezone.utc).isoformat()
        )

        save_history(product, price)

        print(f"Current price: ${price:.2f}")
        print(f"Target price: ${target:.2f}")

        if price <= target:
            if not product.get("alert_sent", False):
                if send_email(product, price):
                    product["alert_sent"] = True
                    product["last_alert_price"] = price
            else:
                print("Alert already sent. No duplicate email.")

        else:
            product["alert_sent"] = False
            print("Price is still above target.")

    save_products(products)

    print("\nPrice checking completed!")
    print("===================================")


if __name__ == "__main__":
    main()
