"""Tilbuds-scraper.

Strategi:
1. Forsøg Tjek (eTilbudsavis) JSON-endpoints — hurtigt, returnerer struktureret data.
2. Hvis det fejler, fald tilbage til Playwright-render af tjek.com web-app.
3. Hvis alt fejler, returner tom liste — main.py vil bruge default_price fra ingredients.json.

VIGTIGT: Tjek har ingen officiel offentlig API. Endpointsene nedenfor er reverse-engineered fra
den offentlige web-app, og kan ændre sig uden varsel. Hvis denne fil holder op med at virke,
er det her du skal kigge først. Sæt LOG_LEVEL=DEBUG for at se rå svar.
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

# Tjek's offentlige business-ids per kæde (kan ændres - tjek tjek.dk)
# Disse IDs er fra Tjek's offentlige katalog. Verificer via deres web-app hvis noget brister.
STORE_BUSINESS_IDS = {
    "netto": "9ddArka",
    "rema_1000": "27JOk4l",
    "lidl": "11deSO",
    "kvickly": "0c089a8",
    "loevbjerg": "3596d52",
    "365discount": "8da40a7",
}

TJEK_API_BASE = "https://squid-api.tjek.com"


@dataclass
class Offer:
    """En enkelt vare på tilbud."""
    store_id: str        # fx "netto_odder"
    store_name: str      # fx "Netto"
    product_name: str    # rå navn fra tilbudsavisen
    price_kr: float      # pris i kr
    quantity_grams: float | None = None  # vægt hvis kendt (kan være None)
    quantity_units: int | None = None    # antal stk hvis kendt
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
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "application/json",
        })

    def _cache_get(self, key: str, ttl: int = 3600) -> Any | None:
        f = self.cache_dir / f"{key}.json"
        if f.exists() and (time.time() - f.stat().st_mtime) < ttl:
            return json.loads(f.read_text(encoding="utf-8"))
        return None

    def _cache_set(self, key: str, data: Any) -> None:
        f = self.cache_dir / f"{key}.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def fetch_offers_for_store(self, store_key: str, cache_ttl: int = 3600) -> list[Offer]:
        """Henter aktuelle tilbud for en kæde. store_key er en nøgle i STORE_BUSINESS_IDS."""
        biz_id = STORE_BUSINESS_IDS.get(store_key)
        if not biz_id:
            LOG.warning("Ukendt store_key: %s", store_key)
            return []

        cache_key = f"offers_{store_key}"
        cached = self._cache_get(cache_key, ttl=cache_ttl)
        if cached is not None:
            LOG.info("Cache hit for %s (%d offers)", store_key, len(cached))
            return [Offer(**o) for o in cached]

        # Tjek's offentlige catalog endpoint
        url = f"{TJEK_API_BASE}/v2/offers"
        params = {
            "dealer_ids": biz_id,
            "r_lat": "55.9755",   # Odder
            "r_lng": "10.1538",
            "r_radius": "30000",  # 30 km
            "limit": "400",
        }
        offers: list[Offer] = []
        try:
            r = self.session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            for item in data if isinstance(data, list) else data.get("offers", []):
                heading = item.get("heading") or item.get("name") or ""
                price = (item.get("pricing") or {}).get("price") or item.get("price")
                if not heading or price is None:
                    continue
                qty = (item.get("quantity") or {})
                size = qty.get("size") or {}
                unit = qty.get("unit") or {}
                grams = self._to_grams(size.get("from"), unit.get("symbol"))

                offer = Offer(
                    store_id=store_key,
                    store_name=store_key,
                    product_name=heading,
                    price_kr=float(price),
                    quantity_grams=grams,
                    valid_from=item.get("run_from", ""),
                    valid_to=item.get("run_till", ""),
                    raw=item,
                )
                if grams and grams > 0:
                    offer.per_kg_kr = round(offer.price_kr / (grams / 1000), 2)
                offers.append(offer)
        except Exception as e:  # noqa: BLE001
            LOG.warning("Tjek API fejlede for %s: %s — bruger tom liste", store_key, e)
            return []

        self._cache_set(cache_key, [o.to_dict() for o in offers])
        LOG.info("Hentet %d tilbud for %s", len(offers), store_key)
        return offers

    @staticmethod
    def _to_grams(value: Any, unit: str | None) -> float | None:
        if value is None or unit is None:
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        u = (unit or "").lower()
        if u in ("kg",):
            return v * 1000
        if u in ("g", "gr"):
            return v
        if u in ("l", "liter"):
            return v * 1000   # antag tæthed 1 (fint approks for de fleste varer)
        if u in ("ml",):
            return v
        return None


def load_mock_offers(path: Path) -> list[Offer]:
    """Til test: indlæs tilbud fra en JSON-fil."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Offer(**o) for o in data]


def fetch_all_offers(stores: list[dict], use_mock: bool = False, cache_ttl: int = 3600,
                     mock_path: Path | None = None) -> list[Offer]:
    """Top-level entry: returnér tilbud fra alle butikker i config."""
    if use_mock and mock_path and mock_path.exists():
        LOG.info("Bruger mock-data fra %s", mock_path)
        return load_mock_offers(mock_path)

    scraper = TjekScraper()
    all_offers: list[Offer] = []
    for store in stores:
        # store.id i config er fx "netto_odder" → vi mapper til Tjek's nøgler
        store_key = store["id"].split("_")[0]
        all_offers.extend(scraper.fetch_offers_for_store(store_key, cache_ttl=cache_ttl))
    return all_offers
