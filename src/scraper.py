"""Tjek/eTilbudsavis tilbuds-scraper - ny, virkende version.

Bruger squid-api.tjek.com som er offentlig og ikke kraever API-key.
Verificeret virkende: maj 2026.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

LOG = logging.getLogger("scraper")

DEALER_IDS_BY_STORE_ID = {
    "netto_odder": "9ba51",
    "rema_odder": "11deC",
    "lidl_odder": "71c90",
    "loevbjerg_odder": "65caN",
    "foetex_odder": "bdf5A",
    "meny_odder": "267e1m",
    "bilka_aarhus": "93f13",
    "spar_odder": "33",
}

TJEK_API_BASE = "https://squid-api.tjek.com"
ODDER_LAT = 55.9755
ODDER_LNG = 10.1538


@dataclass
class Offer:
    store_id: str
    store_name: str
    product_name: str
    price_kr: float
    quantity_grams: float | None = None
    quantity_units: int | None = None
    per_kg_kr: float | None = None
    valid_from: str = ""
    valid_to: str = ""
    raw: dict = None  # type: ignore

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        return d


class TjekScraper:
    def __init__(self, cache_dir: Path = Path(".cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; bulk-planner/1.0)",
            "Accept": "application/json",
        })

    def _cache_get(self, key: str, ttl: int = 3600):
        f = self.cache_dir / f"{key}.json"
        if f.exists() and (time.time() - f.stat().st_mtime) < ttl:
            return json.loads(f.read_text(encoding="utf-8"))
        return None

    def _cache_set(self, key: str, data):
        f = self.cache_dir / f"{key}.json"
        try:
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            LOG.warning("Cache write fejlede: %s", e)

    def fetch_offers_for_dealer(self, dealer_id, dealer_label,
                                 lat=ODDER_LAT, lng=ODDER_LNG,
                                 radius_m=30000, cache_ttl=3600):
        cache_key = f"offers_{dealer_id}"
        cached = self._cache_get(cache_key, ttl=cache_ttl)
        if cached is not None:
            LOG.info("Cache hit for %s (%d tilbud)", dealer_label, len(cached))
            return [Offer(**o) for o in cached]

        offers = []
        for offset in range(0, 1000, 100):
            url = f"{TJEK_API_BASE}/v2/offers"
            params = {
                "dealer_ids": dealer_id,
                "r_lat": lat, "r_lng": lng, "r_radius": radius_m,
                "limit": 100, "offset": offset,
            }
            try:
                r = self.session.get(url, params=params, timeout=20)
                if r.status_code != 200:
                    LOG.warning("%s HTTP %d: %s", dealer_label, r.status_code, r.text[:200])
                    break
                page = r.json()
                if not isinstance(page, list) or not page:
                    break
                for item in page:
                    o = self._parse_item(item, dealer_label)
                    if o:
                        offers.append(o)
                if len(page) < 100:
                    break
            except Exception as e:
                LOG.warning("%s fejl ved offset %d: %s", dealer_label, offset, e)
                break

        LOG.info("Hentet %d tilbud for %s", len(offers), dealer_label)
        self._cache_set(cache_key, [o.to_dict() for o in offers])
        return offers

    @staticmethod
    def _parse_item(item, dealer_label):
        heading = item.get("heading")
        pricing = item.get("pricing") or {}
        price = pricing.get("price")
        # Skip gratis-tilbud og data-fejl
        if not heading or price is None or not isinstance(price, (int, float)) or price <= 0:
            return None
        dealer = item.get("dealer") or {}
        store_name = dealer.get("name") or dealer_label
        qty = item.get("quantity") or {}
        unit = qty.get("unit") or {}
        size = qty.get("size") or {}
        pieces = qty.get("pieces") or {}

        si = unit.get("si") or {}
        si_symbol = (si.get("symbol") or "").lower()
        si_factor = si.get("factor") or 1
        unit_symbol = (unit.get("symbol") or "").lower()
        size_from = size.get("from")
        pieces_from = pieces.get("from") or 1

        quantity_grams = None
        per_kg = None

        if size_from is not None and isinstance(size_from, (int, float)):
            total_in_si = size_from * si_factor * pieces_from
            if si_symbol == "kg":
                quantity_grams = total_in_si * 1000
            elif si_symbol == "l":
                quantity_grams = total_in_si * 1000

            # Tjek-data har en bug: nogle gange er unit_symbol="kg" mens size er i gram
            # (fx rugbroed 850 'kg' i stedet for 850 g). Hvis "vaegten" > 50 kg er det
            # naesten sikkert data-fejl - antag det er gram.
            if quantity_grams and quantity_grams > 50000 and unit_symbol == "kg":
                quantity_grams = quantity_grams / 1000

            if quantity_grams and quantity_grams > 0:
                per_kg = round(float(price) / (quantity_grams / 1000), 2)

            # Sanity-check: kg-priser under 0.50 kr er naesten sikkert data-fejl.
            # Ignorer for at undgaa at tilbudet "vinder" alle sammenligninger.
            if per_kg is not None and per_kg < 0.5:
                per_kg = None
                quantity_grams = None

        return Offer(
            store_id=dealer.get("id", ""),
            store_name=store_name,
            product_name=heading,
            price_kr=float(price),
            quantity_grams=quantity_grams,
            quantity_units=pieces_from if si_symbol == "pcs" else None,
            per_kg_kr=per_kg,
            valid_from=item.get("run_from", ""),
            valid_to=item.get("run_till", ""),
            raw=None,
        )


def load_mock_offers(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Offer(**o) for o in data]


def fetch_all_offers(stores, use_mock=False, cache_ttl=3600, mock_path=None):
    if use_mock and mock_path and mock_path.exists():
        LOG.info("Bruger mock-data fra %s", mock_path)
        return load_mock_offers(mock_path)

    scraper = TjekScraper()
    all_offers = []
    for store in stores:
        store_id = store["id"]
        dealer_id = DEALER_IDS_BY_STORE_ID.get(store_id)
        if not dealer_id:
            LOG.info("Springer over %s (ikke i Tjek for omraadet)", store["name"])
            continue
        offers = scraper.fetch_offers_for_dealer(dealer_id, store["name"], cache_ttl=cache_ttl)
        for o in offers:
            o.store_id = store_id
        all_offers.extend(offers)

    LOG.info("I alt %d tilbud fra %d butikker", len(all_offers), len(stores))
    return all_offers
