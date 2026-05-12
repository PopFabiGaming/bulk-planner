"""Matcher rå produktnavne fra scraper til vores ingredient_keys.

Pipeline:
1. Søgeord-match (deterministisk): brug 'search_terms' fra ingredients.json
2. Hvis tvivl, brug OpenAI som tiebreaker (én batch-prompt for alle uafklarede)

AI bruges KUN her — det er det ene sted hvor LLM faktisk øger robustheden.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable

LOG = logging.getLogger("matcher")


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-zæøå0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def deterministic_match(product_name: str, ingredients: dict) -> str | None:
    """Returnér ingredient_key hvis simpel ord-overlap matcher entydigt, ellers None."""
    n = _normalize(product_name)
    hits: list[tuple[str, int]] = []
    for key, meta in ingredients.items():
        for term in meta.get("search_terms", []) + [meta.get("display", "")]:
            t = _normalize(term)
            if not t:
                continue
            # Hvert ord i term skal være i produktnavn
            if all(w in n for w in t.split()):
                hits.append((key, len(t)))
                break
    if not hits:
        return None
    # Vælg længste/mest specifikke match
    hits.sort(key=lambda x: -x[1])
    return hits[0][0]


def _build_prompt(unmatched: list[str], ingredient_keys: list[str]) -> str:
    return (
        "Du matcher danske dagligvarer til kategorier. "
        "For hver produktbeskrivelse nedenfor, returnér den bedste matchende kategori "
        "fra listen, eller null hvis ingen passer rimeligt.\n\n"
        f"Kategorier: {json.dumps(ingredient_keys, ensure_ascii=False)}\n\n"
        f"Produkter:\n{json.dumps(unmatched, ensure_ascii=False)}\n\n"
        'Returnér KUN gyldigt JSON i formatet: {"produkt": "kategori_eller_null", ...}'
    )


def _ai_match_openai(unmatched: list[str], ingredient_keys: list[str],
                      api_key: str, model: str) -> dict[str, str | None]:
    try:
        from openai import OpenAI
    except ImportError:
        LOG.warning("openai-pakke ikke installeret")
        return {p: None for p in unmatched}
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Du svarer kun med kompakt gyldigt JSON."},
            {"role": "user", "content": _build_prompt(unmatched, ingredient_keys)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content or "{}")


def _ai_match_gemini(unmatched: list[str], ingredient_keys: list[str],
                      api_key: str, model: str) -> dict[str, str | None]:
    """Gemini gratis: https://aistudio.google.com/apikey"""
    import requests
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": _build_prompt(unmatched, ingredient_keys)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    }
    r = requests.post(url, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def ai_match_batch(unmatched: list[str], ingredient_keys: Iterable[str],
                   provider: str, api_key: str, model: str) -> dict[str, str | None]:
    """Dispatcher mellem AI-providers (openai|gemini)."""
    if not unmatched or not api_key:
        return {p: None for p in unmatched}
    keys_list = list(ingredient_keys)
    try:
        if provider == "openai":
            data = _ai_match_openai(unmatched, keys_list, api_key, model)
        elif provider == "gemini":
            data = _ai_match_gemini(unmatched, keys_list, api_key, model)
        else:
            LOG.warning("Ukendt AI-provider: %s", provider)
            return {p: None for p in unmatched}
        out: dict[str, str | None] = {}
        for p in unmatched:
            v = data.get(p)
            out[p] = v if v in keys_list else None
        return out
    except Exception as e:  # noqa: BLE001
        LOG.warning("AI-match fejlede: %s", e)
        return {p: None for p in unmatched}


def match_offers_to_ingredients(offers: list, ingredients: dict, api_key: str = "",
                                 ai_enabled: bool = True, provider: str = "gemini",
                                 model: str = "gemini-1.5-flash"):
    """Mutérer hver Offer ved at sætte attributten .ingredient_key.

    Returnér (matched_count, total_count).
    """
    unmatched: list = []
    for o in offers:
        key = deterministic_match(o.product_name, ingredients)
        o.ingredient_key = key
        if key is None:
            unmatched.append(o)

    if ai_enabled and api_key and unmatched:
        names = list({o.product_name for o in unmatched})
        result = ai_match_batch(names, list(ingredients.keys()), provider, api_key, model)
        for o in unmatched:
            o.ingredient_key = result.get(o.product_name)

    matched = sum(1 for o in offers if getattr(o, "ingredient_key", None))
    return matched, len(offers)
