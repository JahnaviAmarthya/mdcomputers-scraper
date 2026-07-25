import argparse
import csv
import re
import sys
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mdcomputers.in/"
SEARCH_ROUTE = "index.php?route=product/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def build_search_url(term, page=1):
    """Build a MDComputers search URL for a given term and page number."""
    params = {"search": term, "page": page}
    return BASE_URL + SEARCH_ROUTE + "&" + urlencode(params)


def clean_text(text):
    """Collapse whitespace in scraped text."""
    return re.sub(r"\s+", " ", text or "").strip()


def parse_price_block(product):
    """
    Extract current price / old (struck-through) price / discount % from a
    product card. Handles both the "single price" and "old + new price"
    layouts used on the site.
    """
    price_new, price_old, discount = "", "", ""

    price_container = product.select_one(".price")
    if price_container:
        old_el = price_container.select_one(".price-old")
        new_el = price_container.select_one(".price-new")
        if new_el:
            price_new = clean_text(new_el.get_text())
            if old_el:
                price_old = clean_text(old_el.get_text())
        else:
            # Single price, no discount — grab all text and take the
            # first currency-looking token.
            raw = clean_text(price_container.get_text())
            match = re.search(r"₹[\d,]+", raw)
            price_new = match.group(0) if match else raw

    # Discount badge, e.g. "-41%"
    discount_el = product.select_one(".product-badge, .badge, .label-discount")
    if discount_el:
        discount = clean_text(discount_el.get_text())
    else:
        # Fall back to scanning the whole card for a "-NN%" pattern.
        card_text = clean_text(product.get_text())
        match = re.search(r"-\d{1,2}%", card_text)
        if match:
            discount = match.group(0)

    return price_new, price_old, discount


def parse_product_card(product):
    """Extract fields from a single product card element."""
    # Name + product URL — usually an <h4>/<h3> inside the caption block,
    # falling back to the image's wrapping <a> tag.
    name, url = "", ""
    name_el = product.select_one(".caption h4 a, .caption h3 a, h4 a, h3 a")
    if not name_el:
        name_el = product.select_one("a[href*='route=product/product']") or product.select_one(
            ".product-thumb a"
        )
    if name_el:
        name = clean_text(name_el.get_text())
        url = name_el.get("href", "")

    # Image
    img_el = product.select_one("img")
    image_url = ""
    if img_el:
        image_url = img_el.get("data-src") or img_el.get("src") or ""

    price_new, price_old, discount = parse_price_block(product)

    # Availability (some OpenCart themes show "In Stock"/"Out of Stock")
    avail_el = product.select_one(".stock, .availability")
    availability = clean_text(avail_el.get_text()) if avail_el else ""

    return {
        "name": name,
        "price": price_new,
        "old_price": price_old,
        "discount": discount,
        "availability": availability,
        "product_url": url,
        "image_url": image_url,
    }


def get_total_pages(soup, requested_pages=None):
    """
    Figure out how many result pages exist from the "Showing X to Y of Z"
    text or the pagination links, capped by --pages if the user set one.
    """
    total_pages = 1

    pagination_text = soup.find(string=re.compile(r"Showing\s+\d+\s+to\s+\d+\s+of\s+\d+"))
    if pagination_text:
        match = re.search(r"\((\d+)\s*Pages?\)", pagination_text)
        if match:
            total_pages = int(match.group(1))

    if total_pages == 1:
        # Fall back to counting numbered pagination links.
        page_links = soup.select(".pagination a, ul.pagination a")
        nums = [int(a.get_text()) for a in page_links if a.get_text().strip().isdigit()]
        if nums:
            total_pages = max(nums)

    if requested_pages:
        total_pages = min(total_pages, requested_pages)

    return total_pages


def scrape_page(term, page, session):
    url = build_search_url(term, page)
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    cards = soup.select(".product-layout, .product-thumb, .product-grid .product-thumb")
    # De-duplicate: some themes nest .product-thumb inside .product-layout,
    # which would otherwise double-count each card.
    seen_ids = set()
    unique_cards = []
    for card in cards:
        marker = id(card)
        # Skip a .product-layout wrapper if it contains a nested
        # .product-thumb that will be picked up separately.
        if card.select_one(".product-thumb") and "product-layout" in (card.get("class") or []):
            continue
        if marker not in seen_ids:
            seen_ids.add(marker)
            unique_cards.append(card)

    products = [parse_product_card(card) for card in unique_cards]
    products = [p for p in products if p["name"]]  # drop empty/junk matches
    return products, soup


def scrape_search(term, max_pages=None, delay=1.5):
    session = requests.Session()
    all_products = []

    first_page_products, first_soup = scrape_page(term, 1, session)
    all_products.extend(first_page_products)

    total_pages = get_total_pages(first_soup, requested_pages=max_pages)
    print(f"Found {total_pages} page(s) of results for '{term}'.", file=sys.stderr)

    for page in range(2, total_pages + 1):
        time.sleep(delay)  # be polite to the server
        print(f"Fetching page {page}/{total_pages}...", file=sys.stderr)
        try:
            products, _ = scrape_page(term, page, session)
            all_products.extend(products)
        except requests.RequestException as exc:
            print(f"  Failed to fetch page {page}: {exc}", file=sys.stderr)
            continue

    return all_products


def save_to_csv(products, out_path):
    fieldnames = ["name", "price", "old_price", "discount", "availability", "product_url", "image_url"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)


def main():
    parser = argparse.ArgumentParser(description="Scrape product listings from MDComputers.in")
    parser.add_argument("search_term", help="Search term, e.g. 'external harddrive'")
    parser.add_argument("--pages", type=int, default=None, help="Max number of result pages to fetch (default: all)")
    parser.add_argument("--out", default="products.csv", help="Output CSV file path (default: products.csv)")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay in seconds between page requests (default: 1.5)")
    args = parser.parse_args()

    products = scrape_search(args.search_term, max_pages=args.pages, delay=args.delay)

    if not products:
        print("No products found (or the site markup has changed). Nothing written.", file=sys.stderr)
        sys.exit(1)

    save_to_csv(products, args.out)
    print(f"Saved {len(products)} products to {args.out}")


if __name__ == "__main__":
    main()
