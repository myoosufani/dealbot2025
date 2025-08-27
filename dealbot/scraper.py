# dealbot/scraper.py
import os
import re
import json
import time
import math
import statistics
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
}

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

# 🔑 Edit this list any time
KEYWORDS = [
    "laptop", "headphones", "monitor", "SSD", "PlayStation 5", "AirPods", "LEGO"
]

# ------- Utilities -------

def fetch(url, retries=2, sleep=1.0):
    last_err = None
    for _ in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_err = e
            time.sleep(sleep)
    raise last_err

def parse_jsonld_products(soup, base_url):
    """Extract products using JSON-LD where possible (name/price/url)."""
    products = []
    for tag in soup.find_all("script", type="application/ld+json"):
        text = tag.string or tag.get_text(strip=True) or ""
        if not text:
            continue
        try:
            data = json.loads(text)
        except Exception:
            # Some sites have multiple JSON objects concatenated; try to salvage numbers
            continue

        # Normalize to list of dicts
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            try:
                # Best match: Product
                if isinstance(obj, dict) and obj.get("@type") in ("Product", ["Product"]):
                    name = obj.get("name")
                    url = obj.get("url")
                    offers = obj.get("offers", {})
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    price = None
                    if isinstance(offers, dict):
                        price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
                    # Fallback: scrape price from description if present
                    if price is None and isinstance(obj.get("offers"), list):
                        for o in obj["offers"]:
                            price = o.get("price")
                            if price:
                                break
                    # Clean & coerce
                    if name and price:
                        price_val = _to_price(price)
                        if price_val is not None:
                            abs_url = urljoin(base_url, url) if url else None
                            products.append({"name": name.strip(), "price": price_val, "url": abs_url or base_url})
            except Exception:
                continue
    return dedupe_products(products)

def _to_price(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    # strip currency and commas
    s = str(val)
    m = re.search(r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)", s.replace(",", ""))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None

def dedupe_products(items):
    seen = set()
    out = []
    for it in items:
        key = (it.get("name", "").lower(), round(it.get("price", 0), 2))
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out

def discord_notify(lines):
    if not DISCORD_WEBHOOK:
        print("⚠️ No DISCORD_WEBHOOK set; skipping Discord notify.")
        return
    # Discord has a 2000-char limit per message; chunk if needed
    chunk = []
    total_len = 0
    for line in lines:
        if total_len + len(line) + 1 > 1800:
            requests.post(DISCORD_WEBHOOK, json={"content": "\n".join(chunk)})
            chunk, total_len = [], 0
        chunk.append(line)
        total_len += len(line) + 1
    if chunk:
        requests.post(DISCORD_WEBHOOK, json={"content": "\n".join(chunk)})

# ------- Site scrapers -------

def search_walmart(keyword):
    """
    Walmart.ca search. We rely on JSON-LD blocks on search/listing pages.
    Example search: https://www.walmart.ca/search?q=laptop
    """
    url = f"https://www.walmart.ca/search?q={requests.utils.quote(keyword)}"
    try:
        r = fetch(url)
        soup = BeautifulSoup(r.text, "html.parser")
        products = parse_jsonld_products(soup, base_url="https://www.walmart.ca/")
        return [{"site": "Walmart", "keyword": keyword, **p} for p in products]
    except Exception as e:
        print(f"[Walmart] {keyword} -> error: {e}")
        return []

def search_bestbuy(keyword):
    """
    BestBuy.ca search. Many pages include JSON-LD product data per result.
    Example search: https://www.bestbuy.ca/en-ca/search?search=laptop
    """
    url = f"https://www.bestbuy.ca/en-ca/search?search={requests.utils.quote(keyword)}"
    try:
        r = fetch(url)
        soup = BeautifulSoup(r.text, "html.parser")
        products = parse_jsonld_products(soup, base_url="https://www.bestbuy.ca/")
        return [{"site": "BestBuy", "keyword": keyword, **p} for p in products]
    except Exception as e:
        print(f"[BestBuy] {keyword} -> error: {e}")
        return []

# Stubs for Kijiji / Facebook Marketplace (login/anti-bot protected)
def search_kijiji(keyword):
    # Placeholder: requires headless browser or a scraping API.
    return []

def search_fb_marketplace(keyword):
    # Placeholder: requires login & anti-bot handling; not feasible in Actions as-is.
    return []

# ------- Deal logic -------

def find_deals(rows, min_discount=0.20, min_price=10.0):
    """
    For each keyword, compute the median price across sites.
    A row is a "deal" if price <= (1 - min_discount) * median.
    We also ignore extremely low/noise prices (< min_price).
    """
    deals = []
    df = pd.DataFrame(rows)
    if df.empty:
        return deals

    for keyword, g in df.groupby("keyword"):
        # Filter out silly/zero prices
        g = g[g["price"] >= min_price]
        if g.empty:
            continue
        median_price = statistics.median(g["price"])
        threshold = (1.0 - min_discount) * median_price
        winners = g[g["price"] <= threshold].sort_values("price")
        for _, row in winners.iterrows():
            rowd = row.to_dict()
            rowd["median_price"] = round(median_price, 2)
            rowd["threshold"] = round(threshold, 2)
            rowd["discount_pct"] = round(100.0 * (1.0 - (row["price"] / median_price)), 1)
            deals.append(rowd)
    return deals

# ------- Main -------

def run():
    all_rows = []
    for kw in KEYWORDS:
        all_rows += search_walmart(kw)
        time.sleep(0.7)  # be polite
        all_rows += search_bestbuy(kw)
        time.sleep(0.7)

        # Later:
        # all_rows += search_kijiji(kw)
        # all_rows += search_fb_marketplace(kw)

    # Save raw scrape
    if all_rows:
        raw_df = pd.DataFrame(all_rows)
        raw_df.sort_values(["keyword", "site", "price"], inplace=True)
        raw_df.to_csv("scrape_raw.csv", index=False)

    # Compute deals
    deals = find_deals(all_rows, min_discount=0.20, min_price=10.0)

    if deals:
        deals_df = pd.DataFrame(deals)
        deals_df.sort_values(["keyword", "price"], inplace=True)
        deals_df.to_csv("deals.csv", index=False)

        # Build Discord message
        lines = ["💸 **Potential arbitrage deals (≥20% under median)**"]
        for d in deals[:25]:  # cap message length
            lines.append(
                f"- **{d['name']}** · ${d['price']:.2f} at {d['site']} "
                f"(median ${d['median_price']:.2f}, −{d['discount_pct']}%)\n{d.get('url','')}"
            )
        discord_notify(lines)
        print(f"✅ Found {len(deals)} potential deals. Wrote deals.csv and notified Discord.")
    else:
        print("No qualifying deals this run.")

if __name__ == "__main__":
    run()
