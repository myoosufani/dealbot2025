import os
import requests
from bs4 import BeautifulSoup

def scrape_example():
    url = "https://books.toscrape.com/"  # example site, replace later with your real one
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # Example: get first 5 book titles
    books = [book.get_text() for book in soup.select(".product_pod h3 a")[:5]]
    return books

def notify_discord(message: str):
    webhook_url = os.environ.get("DISCORD_WEBHOOK")
    if not webhook_url:
        print("⚠️ No Discord webhook found")
        return

    data = {"content": message}
    requests.post(webhook_url, json=data)

if __name__ == "__main__":
    deals = scrape_example()
    if deals:
        notify_discord("📢 New deals found:\n" + "\n".join(deals))
    else:
        notify_discord("No deals found today.")
