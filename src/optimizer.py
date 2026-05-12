"""Vælger ugens opskrifter ud fra ugens tilbud."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

LOG = logging.getLogger("optimizer")


@dataclass
class PricedIngredient:
    key: str
    display: str
    price_per_kg: float
    source: str
    offer_product: str = ""
    store_id: str = ""


@dataclass
class CostedRecipe:
    recipe: dict
    cost_per_portion_kr: float
    protein_per_kr: float
    chosen_ingredients: dict
    actual_per_portion: dict


@dataclass
class WeekPlan:
    chosen_recipes: list
    portions_per_recipe: list
    shopping_list: dict
    totals: dict
    issues: list = field(default_factory=list)


def build_price_index(offers, ingredients, stores_priority):
    best = {}
    for key, meta in ingredients.items():
        best[key] = PricedIngredient(
            key=key,
            display=meta.get("display", key),
            price_per_kg=meta["default_price_per_kg"],
            source="default",
        )
    for o in offers:
        key = getattr(o, "ingredient_key", None)
        if not key or key not in best or o.per_kg_kr is None:
            continue
        current = best[key]
        prio_penalty = stores_priority.get(o.store_id, 99) * 0.5
        adjusted_new = o.per_kg_kr + prio_penalty
        adjusted_current = current.price_per_kg + (
            0 if current.source == "default"
            else stores_priority.get(current.store_id, 99) * 0.5
        )
        if adjusted_new < adjusted_current:
            best[key] = PricedIngredient(
                key=key,
                display=ingredients[key].get("display", key),
                price_per_kg=o.per_kg_kr,
                source=f"offer:{o.store_id}",
                offer_product=o.product_name,
                store_id=o.store_id,
            )
    return best


def cost_recipe(recipe, prices, ingredients):
    chosen = {}
    total_kcal = 0.0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0
    total_cost = 0.0

    for ing in recipe["ingredients"]:
        orig_key = ing["key"]
        candidates = [orig_key] + ing.get("swaps", [])
        best_key = orig_key
        best_price = prices[orig_key].price_per_kg if orig_key in prices else 100
        for c in candidates:
            if c in prices and prices[c].price_per_kg < best_price:
                best_price = prices[c].price_per_kg
                best_key = c
        chosen[orig_key] = prices[best_key]
        grams = ing["grams"]
        cost = (grams / 1000) * best_price
        total_cost += cost
        macro = ingredients.get(best_key, {}).get("macro_per_100g", {})
        scale = grams / 100
        total_kcal += macro.get("kcal", 0) * scale
        total_protein += macro.get("protein_g", 0) * scale
        total_carbs += macro.get("carbs_g", 0) * scale
        total_fat += macro.get("fat_g", 0) * scale

    portions = recipe["portions"]
    cost_per_portion = total_cost / portions
    actual = {
        "kcal": round(total_kcal / portions, 1),
        "protein_g": round(total_protein / portions, 1),
        "carbs_g": round(total_carbs / portions, 1),
        "fat_g": round(total_fat / portions, 1),
    }
    protein_per_kr = actual["protein_g"] / max(cost_per_portion, 0.01)

    return CostedRecipe(
        recipe=recipe,
        cost_per_portion_kr=round(cost_per_portion, 2),
        protein_per_kr=round(protein_per_kr, 3),
        chosen_ingredients=chosen,
        actual_per_portion=actual,
    )


def select_recipes(costed, n):
    ranked = sorted(costed, key=lambda x: -x.protein_per_kr)
    chosen = []
    seen_tags = set()
    for c in ranked:
        if "morgenmad" in c.recipe.get("tags", []):
            chosen.append(c)
            seen_tags.update(c.recipe.get("tags", []))
            break
    for c in ranked:
        if c in chosen or len(chosen) >= n:
            continue
        protein_tags = {"kylling", "oksekoed", "kalkun", "fisk", "aeg"}
        my_protein = set(c.recipe.get("tags", [])) & protein_tags
        already_protein = seen_tags & protein_tags
        if my_protein and my_protein.issubset(already_protein) and len(chosen) < n - 1:
            continue
        chosen.append(c)
        seen_tags.update(c.recipe.get("tags", []))
    for c in ranked:
        if len(chosen) >= n:
            break
        if c not in chosen:
            chosen.append(c)
    return chosen[:n]


def allocate_portions(chosen, daily_kcal, daily_protein_g, meals_per_day,
                     days=7, max_repeats=9):
    target_kcal_week = daily_kcal * days
    target_protein_week = daily_protein_g * days
    n = len(chosen)
    portions = [0] * n
    kcal_used = 0.0
    protein_used = 0.0
    safety = 0
    while kcal_used < target_kcal_week and any(p < max_repeats for p in portions):
        safety += 1
        if safety > 200:
            break
        cands = [(i, portions[i]) for i in range(n) if portions[i] < max_repeats]
        if not cands:
            break
        if protein_used < target_protein_week * 0.85:
            i = max(cands, key=lambda c: chosen[c[0]].actual_per_portion["protein_g"])[0]
        else:
            i = min(cands, key=lambda c: c[1])[0]
        portions[i] += 1
        kcal_used += chosen[i].actual_per_portion["kcal"]
        protein_used += chosen[i].actual_per_portion["protein_g"]
    return portions


def build_shopping_list(chosen, portions, prices):
    shop = {}
    for c, n in zip(chosen, portions):
        scale = n / c.recipe["portions"]
        for ing in c.recipe["ingredients"]:
            chosen_ing = c.chosen_ingredients[ing["key"]]
            key = chosen_ing.key
            grams = ing["grams"] * scale
            if key not in shop:
                shop[key] = {
                    "display": chosen_ing.display,
                    "grams": 0,
                    "price_per_kg": chosen_ing.price_per_kg,
                    "source": chosen_ing.source,
                    "store_id": chosen_ing.store_id,
                    "offer_product": chosen_ing.offer_product,
                }
            shop[key]["grams"] += grams
    for v in shop.values():
        v["grams"] = math.ceil(v["grams"])
        v["cost_kr"] = round(v["grams"] / 1000 * v["price_per_kg"], 2)
    return shop


def plan_week(recipes, offers, ingredients, cfg):
    targets = cfg.get("targets", default={})
    plan_cfg = cfg.get("plan", default={})
    stores_priority = {s["id"]: s["priority"] for s in cfg.get("stores", default=[])}

    prices = build_price_index(offers, ingredients, stores_priority)
    costed = [cost_recipe(r, prices, ingredients) for r in recipes]
    chosen = select_recipes(costed, plan_cfg.get("recipes_per_week", 4))
    portions = allocate_portions(
        chosen,
        targets.get("daily_kcal", 2900),
        targets.get("daily_protein_g", 140),
        plan_cfg.get("meals_per_day", 3),
        days=7,
        max_repeats=plan_cfg.get("max_repeats_per_recipe", 9),
    )
    shopping = build_shopping_list(chosen, portions, prices)

    total_kcal = sum(c.actual_per_portion["kcal"] * p for c, p in zip(chosen, portions))
    total_protein = sum(c.actual_per_portion["protein_g"] * p for c, p in zip(chosen, portions))
    total_cost = sum(v["cost_kr"] for v in shopping.values())
    days = 7
    avg_kcal = total_kcal / days
    avg_protein = total_protein / days
    target_kcal = targets.get("daily_kcal", 2900)
    target_protein = targets.get("daily_protein_g", 140)
    kcal_tol = target_kcal * targets.get("kcal_tolerance_pct", 8) / 100
    prot_tol = target_protein * targets.get("protein_tolerance_pct", 10) / 100
    budget = targets.get("weekly_budget_kr", 420)

    issues = []
    if avg_kcal < target_kcal - kcal_tol:
        issues.append(f"Dagligt kalorieindtag for lavt: {avg_kcal:.0f} vs maal {target_kcal}")
    if avg_kcal > target_kcal + 3 * kcal_tol:
        issues.append(f"Dagligt kalorieindtag for hojt: {avg_kcal:.0f} vs maal {target_kcal}")
    if avg_protein < target_protein - prot_tol:
        issues.append(f"Dagligt protein for lavt: {avg_protein:.0f}g vs maal {target_protein}g")
    if total_cost > budget * 1.1:
        issues.append(f"Budget overskredet: {total_cost:.0f} kr vs maal {budget} kr")

    return WeekPlan(
        chosen_recipes=chosen,
        portions_per_recipe=portions,
        shopping_list=shopping,
        totals={
            "weekly_kcal": round(total_kcal),
            "daily_kcal_avg": round(avg_kcal),
            "weekly_protein_g": round(total_protein),
            "daily_protein_g_avg": round(avg_protein, 1),
            "total_cost_kr": round(total_cost, 2),
            "budget_kr": budget,
        },
        issues=issues,
    )
