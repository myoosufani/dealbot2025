# dealbot/scraper.py

import requests
from bs4 import BeautifulSoup
import pandas as pd
import os

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

# Example products to scrape
products = [
    {"name": "Playstation 5", "url": "https://kijiji.ca/playstation 5"},
    {"name": "Product B", "url": "https://example.com/productB"}
]

deals = []

for product in products:
    response = requests.get(product["url"])
    if response.status_code != 200:
        continue

    soup = BeautifulSoup(response.text, "html.parser")

    # Example: scrape price (update selector based on actual site)
    price_tag = soup.select_one(".price")
    if not price_tag:
        continue
    price = float(price_tag.text.replace("$", "").strip())

    # Example price threshold
    if price < 50:  # "price glitch" threshold
        deals.append({"name": product["name"], "price": price, "url": product["url"]})

# Save to CSV
if deals:
    df = pd.DataFrame(deals)
    df.to_csv("deals.csv", index=False)

    # Send Discord notification
    if DISCORD_WEBHOOK:
        message = "💰 Killer Deals Found:\n" + "\n".join(
            [f"{d['name']} - ${d['price']} - {d['url']}" for d in deals]
        )
        requests.post(DISCORD_WEBHOOK, json={"content": message})


