"""Bygger en pæn Obsidian-venlig Markdown-fil ud af en WeekPlan."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable


def _group_shopping_by_store(shopping: dict, stores: list[dict]) -> dict[str, list[tuple[str, dict]]]:
    by_store: dict[str, list[tuple[str, dict]]] = {}
    store_lookup = {s["id"]: s["name"] for s in stores}
    for key, info in shopping.items():
        store_id = info.get("store_id") or "default"
        store_name = store_lookup.get(store_id, "Andet / billigste sted")
        by_store.setdefault(store_name, []).append((key, info))
    return by_store


def render_markdown(plan, recipes_by_id: dict, week_iso: int, year: int, stores: list[dict]) -> str:
    out: list[str] = []
    out.append("---")
    out.append(f"week: {week_iso}")
    out.append(f"year: {year}")
    out.append(f"generated: {datetime.now().isoformat(timespec='minutes')}")
    out.append("tags: [madplan, bulk]")
    out.append("---")
    out.append("")
    out.append(f"# Madplan — Uge {week_iso} ({year})")
    out.append("")

    # Resumé
    t = plan.totals
    out.append("## Resumé")
    out.append("")
    out.append(f"- **Pris i alt:** {t['total_cost_kr']:.0f} kr (budget: {t['budget_kr']} kr)")
    out.append(f"- **Kalorier:** {t['daily_kcal_avg']} kcal/dag ({t['weekly_kcal']} for ugen)")
    out.append(f"- **Protein:** {t['daily_protein_g_avg']} g/dag ({t['weekly_protein_g']} g for ugen)")
    out.append(f"- **Antal opskrifter:** {len(plan.chosen_recipes)}")
    out.append("")

    if plan.issues:
        out.append("> [!warning] Bemærk")
        for iss in plan.issues:
            out.append(f"> - {iss}")
        out.append("")

    # Plan for ugen (rotation)
    out.append("## Ugeplan")
    out.append("")
    out.append("| # | Opskrift | Portioner | Pris/portion | Protein/portion |")
    out.append("|---|----------|-----------|--------------|-----------------|")
    for c, n in zip(plan.chosen_recipes, plan.portions_per_recipe):
        out.append(
            f"| {plan.chosen_recipes.index(c)+1} | {c.recipe['name']} | {n} | "
            f"{c.cost_per_portion_kr:.0f} kr | {c.actual_per_portion['protein_g']:.0f} g |"
        )
    out.append("")
    out.append("**Sådan bruger du den:** lav store batches af opskrifterne i weekenden, "
               "spis dem i rotation. Antallet af portioner ovenfor dækker hele ugen.")
    out.append("")

    # Indkøbsliste
    out.append("## Indkøbsliste")
    out.append("")
    by_store = _group_shopping_by_store(plan.shopping_list, stores)
    for store_name in sorted(by_store.keys(), key=lambda s: (s == "Andet / billigste sted", s)):
        items = by_store[store_name]
        out.append(f"### {store_name}")
        out.append("")
        for key, info in sorted(items, key=lambda x: -x[1]["cost_kr"]):
            grams = info["grams"]
            cost = info["cost_kr"]
            source = info.get("source", "")
            tag = ""
            if source.startswith("offer:"):
                offer_name = info.get("offer_product", "")
                tag = f" *(tilbud: {offer_name})*" if offer_name else " *(tilbud)*"
            out.append(f"- [ ] {info['display']} — **{grams} g** — {cost:.0f} kr{tag}")
        out.append("")

    # Opskrifter
    out.append("## Opskrifter")
    out.append("")
    for c in plan.chosen_recipes:
        r = c.recipe
        out.append(f"### {r['name']}")
        out.append("")
        out.append(f"*Tid: {r['prep_minutes']} min · {r['portions']} portioner pr. batch · "
                   f"Pris/portion: {c.cost_per_portion_kr:.0f} kr*")
        out.append("")
        out.append(f"**Makroer pr. portion:** "
                   f"{c.actual_per_portion['kcal']:.0f} kcal · "
                   f"{c.actual_per_portion['protein_g']:.0f}g protein · "
                   f"{c.actual_per_portion['carbs_g']:.0f}g kulhydrat · "
                   f"{c.actual_per_portion['fat_g']:.0f}g fedt")
        out.append("")
        out.append("**Ingredienser (pr. batch):**")
        out.append("")
        for ing in r["ingredients"]:
            chosen = c.chosen_ingredients[ing["key"]]
            swap_note = ""
            if chosen.key != ing["key"]:
                swap_note = f" *(swap fra {ing['key']})*"
            out.append(f"- {chosen.display}: {ing['grams']} g{swap_note}")
        out.append("")
        out.append("**Sådan gør du:**")
        out.append("")
        out.append(r["instructions"])
        out.append("")

    out.append("---")
    out.append("*Genereret automatisk af bulk-planner.*")
    return "\n".join(out)
