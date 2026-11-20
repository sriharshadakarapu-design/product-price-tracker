
import json
import os

from flask import Flask, render_template, request, redirect, url_for
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret")

PRODUCTS_FILE = "products.json"

RETAILERS = {
    "Amazon": "amazon.com",
    "Walmart": "walmart.com",
    "Best Buy": "bestbuy.com",
    "Apple": "apple.com"
}

def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []

    with open(PRODUCTS_FILE, encoding="utf-8") as file:
        return json.load(file)

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as file:
        json.dump(products, file, indent=4)

@app.route("/")
def home():
    return render_template(
        "index.html",
        products=load_products(),
        retailers=RETAILERS,
        price_limit=os.getenv("PRICE_LIMIT", "150"),
        check_interval=os.getenv("CHECK_INTERVAL", "1800")
    )

@app.route("/add", methods=["POST"])
def add_product():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    retailer = request.form.get("retailer", "").strip()
    selector = request.form.get("selector", "").strip()

    if not name or not selector or retailer not in RETAILERS:
        return "Please provide all product details.", 400

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    domain = RETAILERS[retailer]

    if parsed.scheme != "https" or not (
        host == domain or host.endswith("." + domain)
    ):
        return "Invalid retailer product URL.", 400

    products = load_products()

    products.append({
        "name": name,
        "url": url,
        "retailer": retailer,
        "selector": selector,
        "target_price": float(os.getenv("PRICE_LIMIT", "150")),
        "current_price": None,
        "last_checked": None,
        "last_alert_price": None
    })

    save_products(products)
    return redirect(url_for("home"))

@app.route("/check")
def check_prices():
    return (
        "Price checks run through GitHub Actions. "
        "Open the Actions tab in your repository."
    )

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )

