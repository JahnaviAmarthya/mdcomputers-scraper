# MDComputers Product Scraper

A Python script that scrapes product listings from [MDComputers](https://mdcomputers.in) for a given search term (e.g. `external harddrive`), using their public product-search page:

```
https://mdcomputers.in/?route=product/search&search=<term>
```

## What it extracts

For each product on the results page(s):

- Product name
- Current price
- Original / struck-through price (if discounted)
- Discount badge (e.g. `-41%`)
- Availability (if shown)
- Product page URL
- Image URL

Results are written to a CSV file.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Scrape all result pages
python mdcomputers_scraper.py "external harddrive"

# Limit to the first 2 pages, custom output file
python mdcomputers_scraper.py "external harddrive" --pages 2 --out harddrives.csv

# Adjust the delay between page requests (default 1.5s)
python mdcomputers_scraper.py "graphics card" --delay 2
```

## How it works

- Builds the search URL from the given term.
- Parses each result page with BeautifulSoup, targeting the OpenCart-style
  `.product-layout` / `.product-thumb` product cards that the site uses.
- Follows pagination automatically (reads the "Showing X to Y of Z (N Pages)"
  text on the results page) unless `--pages` caps it.
- Adds a short delay between page requests to avoid hammering the server.

## Notes

- This only reads publicly available product-listing data — nothing behind
  a login.
- If MDComputers changes their site's HTML/CSS structure, the selectors in
  `parse_product_card()` / `parse_price_block()` may need updating.
