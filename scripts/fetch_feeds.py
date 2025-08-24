#!/usr/bin/env python3
import os, json, csv, datetime, urllib.request, urllib.error, io, sys
from typing import List, Dict

ROOT = os.path.dirname(os.path.dirname(__file__))  # repo root
DATA = os.path.join(ROOT, "site", "data")
FEEDS_PATH = os.path.join(DATA, "feeds.json")
OUT_PRODUCTS = os.path.join(DATA, "products.csv")

HEADER = ["sku","title","description","price","thumbnail_url","product_url","tags","status","publish_date"]

def fetch_url(url: str) -> bytes:
    if url.startswith("http://") or url.startswith("https://"):
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read()
    # local path relative to repo root
    path = os.path.join(ROOT, url) if not os.path.isabs(url) else url
    with open(path, "rb") as f:
        return f.read()

def normalize_item(item: dict, mapping: dict) -> dict:
    row = {}
    for out_field, in_field in mapping.items():
        val = item
        for part in str(in_field).split("."):
            if isinstance(val, dict):
                val = val.get(part, "")
            else:
                val = ""
        if out_field == "price":
            try: val = f"{float(val):.2f}"
            except: val = "0.00"
        elif out_field == "tags":
            if isinstance(val, list): val = ",".join(str(x) for x in val)
            else: val = str(val)
        row[out_field] = val
    return row

def write_csv(rows: List[Dict]):
    os.makedirs(DATA, exist_ok=True)
    with open(OUT_PRODUCTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k,"") for k in HEADER})
    print(f"Wrote {len(rows)} products -> {OUT_PRODUCTS}")

def main():
    with open(FEEDS_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    today = datetime.date.today().isoformat()
    rows = []
    for src in cfg.get("sources", []):
        if src.get("status","active") != "active": continue
        typ = src.get("type","json")
        raw = fetch_url(src["url"])
        mapping = src["mapping"]
        items = []
        if typ == "json":
            data = json.loads(raw.decode("utf-8"))
            items = data if isinstance(data, list) else data.get("items", [])
        elif typ == "csv":
            text = raw.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            items = list(reader)
        else:
            print(f"Unknown feed type: {typ}; skipping"); continue
        for it in items:
            r = normalize_item(it, mapping)
            r.setdefault("status","active")
            r.setdefault("publish_date", today if src.get("default_publish_date")=="today" else src.get("default_publish_date","1970-01-01"))
            if not r.get("sku"):
                r["sku"] = (r.get("title","")[:8] or "ITEM").upper().replace(" ","-")
            rows.append(r)
    write_csv(rows)

if __name__ == "__main__":
    main()
