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

# Dealer-IDs verificeret mod tjek.com's API (maj 2026)
# Find nye IDs ved: GET https://squid-api.tjek.com/v2/offers?r_lat=X&r_lng=Y&r_radius=Z&limit=100
DEALER_IDS_BY_STORE_ID = {
    "netto_odder": "9ba51",
    "rema_odder": "11deC",
    "lidl_odder": "71c90",
    "loevbjerg_odder": "65caN",
    "foetex_odder": "bdf5A",
    "meny_odder": "267e1m",
    "bilka_aarhus": "93f13",
    "spar_odder": "33",
    # Bemaerk: Kvickly og 365discount er ikke i Tjek's database for Odder-omraadet
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

    def _cache_get(self, key: str, ttl: int = 3600) -> Any | None:
        f = self.cache_dir / f"{key}.json"
        if f.exists() and (time.time() - f.stat().st_mtime) < ttl:
            return json.loads(f.read_text(encoding="utf-8"))
        return None

    def _cache_set(self, key: str, data: Any) -> None:
        f = self.cache_dir / f"{key}.json"
        try:
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            LOG.warning("Cache write fejlede: %s", e)

    def fetch_offers_for_dealer(self, dealer_id: str, dealer_label: str,
                                 lat: float = ODDER_LAT, lng: float = ODDER_LNG,
                                 radius_m: int = 30000, cache_ttl: int = 3600) -> list[Offer]:
        """Henter ALLE tilbud for én butik (pagineret)."""
        cache_key = f"offers_{dealer_id}"
        cached = self._cache_get(cache_key, ttl=cache_ttl)
        if cached is not None:
            LOG.info("Cache hit for %s (%d tilbud)", dealer_label, len(cached))
            return [Offer(**o) for o in cached]

        offers: list[Offer] = []
        for offset in range(0, 1000, 100):
            url = f"{TJEK_API_BASE}/v2/offers"
            params = {
                "dealer_ids": dealer_id,
                "r_lat": lat,
                "r_lng": lng,
                "r_radius": radius_m,
                "limit": 100,
                "offset": offset,
            }
            try:
                r = self.session.get(url, params=params, timeout=20)
                if r.status_code != 200:
                    LOG.warning("%s HTTP %d ved offset %d: %s",
                                dealer_label, r.status_code, offset, r.text[:200])
                    break
                page = r.json()
                if not isinstance(page, list) or not page:
                    break
                for item in page:
                    offer = self._parse_item(item, dealer_label)
                    if offer:
                        offers.append(offer)
                if len(page) < 100:
                    break
            except Exception as e:  # noqa: BLE001
                LOG.warning("%s fejl ved offset %d: %s", dealer_label, offset, e)
                break

        LOG.info("Hentet %d tilbud for %s", len(offers), dealer_label)
        self._cache_set(cache_key, [o.to_dict() for o in offers])
        return offers

    @staticmethod
    def _parse_item(item: dict, dealer_label: str) -> Offer | None:
        heading = item.get("heading")
        pricing = item.get("pricing") or {}
        price = pricing.get("price")
        if not heading or price is None:
            return None
        dealer = item.get("dealer") or {}
        store_name = dealer.get("name") or dealer_label
        qty = item.get("quantity") or {}
        unit = qty.get("unit") or {}
        size = qty.get("size") or {}
        pieces = qty.get("pieces") or {}

        # Total maengde i SI-enheder (kg eller liter typisk)
        si = unit.get("si") or {}
        si_symbol = (si.get("symbol") or "").lower()
        si_factor = si.get("factor") or 1
        size_from = size.get("from")
        pieces_from = pieces.get("from") or 1

        quantity_grams: float | None = None
        per_kg: float | None = None

        if size_from is not None and isinstance(size_from, (int, float)):
            total_in_si = size_from * si_factor * pieces_from
            if si_symbol == "kg":
                quantity_grams = total_in_si * 1000
            elif si_symbol == "l":
                quantity_grams = total_in_si * 1000  # antag taethed ~1 for de fleste varer
            # pcs (styk) springer vi over - kan ikke regne kg-pris

            if quantity_grams and quantity_grams > 0:
                per_kg = round(float(price) / (quantity_grams / 1000), 2)

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
            raw=None,  # Spar plads i cache
        )


def load_mock_offers(path: Path) -> list[Offer]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Offer(**o) for o in data]


def fetch_all_offers(stores: list[dict], use_mock: bool = False, cache_ttl: int = 3600,
                     mock_path: Path | None = None) -> list[Offer]:
    """Top-level entry: returner tilbud fra alle butikker i config."""
    if use_mock and mock_path and mock_path.exists():
        LOG.info("Bruger mock-data fra %s", mock_path)
        return load_mock_offers(mock_path)

    scraper = TjekScraper()
    all_offers: list[Offer] = []
    for store in stores:
        store_id = store["id"]
        # Map fra config store_id (fx 'netto_odder') til dealer-key i DEALER_IDS
        dealer_id_lookup = DEALER_IDS_BY_STORE_ID.get(store_id)
        if not dealer_id_lookup:
            LOG.info("Springer over %s (ikke i Tjek's database for omraadet)", store["name"])
            continue
        dealer_id = dealer_id_lookup
        # Bevar config's store_id paa offers saa de matches korrekt nedstroms
        offers = scraper.fetch_offers_for_dealer(dealer_id, store["name"], cache_ttl=cache_ttl)
        for o in offers:
            o.store_id = store_id  # overskriv med config-id
        all_offers.extend(offers)

    LOG.info("I alt %d tilbud fra %d butikker", len(all_offers), len(stores))
    return all_offers
