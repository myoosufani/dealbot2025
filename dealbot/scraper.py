# dealbot/scraper.py

import requests
from bs4 import BeautifulSoup
import pandas as pd
import os

# Discord webhook from GitHub secrets
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

# List of products to track
# Replace 'url' with real product pages
products = [
    {"name": "PlayStation 5", "url": "https://www.kijiji.ca/v-playstation5-link", "price_selector": ".price"}, 
    {"name": "iPhone 15", "url": "https://www.kijiji.ca/v-iphone15-link", "price_selector": ".price"}
]

deals = []

for product in products:
    try:
        response = requests.get(product["url"], headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except requests.RequestException:
        print(f"Failed to fetch {product['name']}")
        continue

    soup = BeautifulSoup(response.text, "html.parser")
    price_tag = soup.select_one(product["price_selector"])

    if not price_tag:
        print(f"Price not found for {product['name']}")
        continue

    # Clean price string and convert to float
    price_text = price_tag.text.replace("$", "").replace(",", "").strip()
    try:
        price = float(price_text)
    except ValueError:
        print(f"Invalid price for {product['name']}: {price_text}")
        continue

    # Define your "price glitch" threshold
    threshold = 50  # change this per product if needed
    if price < threshold:
        deals.append({"name": product["name"], "price": price, "url": product["url"]})

# Save deals to CSV
if deals:
    df = pd.DataFrame(deals)
    df.to_csv("deals.csv", index=False)
    print(f"Found {len(deals)} deal(s), saved to deals.csv")

    # Send Discord notification
    if DISCORD_WEBHOOK:
        import requests
        message = "💰 Killer Deals Found:\n" + "\n".join(
            [f"{d['name']} - ${d['price']} - {d['url']}" for d in deals]
        )
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": message})
            print("Discord notification sent!")
        except requests.RequestException:
            print("Failed to send Discord notification")
else:
    print("No deals found today.")
