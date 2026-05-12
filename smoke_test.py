"""Quick smoke test - kører optimizer + markdown med mock data, ingen secrets nødvendige."""
import json
from datetime import date
from pathlib import Path

from src.config import Config
from src.scraper import load_mock_offers
from src.optimizer import plan_week
from src.markdown_writer import render_markdown


def main():
    root = Path(__file__).parent
    cfg = Config.load(root / "config.yaml")
    # Tving mock + disable AI
    cfg.raw["scraping"]["use_mock"] = True
    cfg.raw["ai"]["enabled"] = False

    recipes = json.loads((root / "data" / "recipes.json").read_text(encoding="utf-8"))["recipes"]
    ingredients = json.loads((root / "data" / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]
    offers = load_mock_offers(root / "data" / "mock_offers.json")

    # Lab match: mock data har allerede rigtige produktnavne, så vi matcher direkte
    from src.matcher import match_offers_to_ingredients
    matched, total = match_offers_to_ingredients(
        offers, ingredients, api_key="", ai_enabled=False
    )
    print(f"Matched {matched}/{total} offers via deterministic matching")
    for o in offers:
        print(f"  - '{o.product_name}' -> {getattr(o, 'ingredient_key', None)}")

    plan = plan_week(recipes, offers, ingredients, cfg)
    print(f"\nValgte {len(plan.chosen_recipes)} opskrifter:")
    for c, n in zip(plan.chosen_recipes, plan.portions_per_recipe):
        print(f"  - {c.recipe['name']}: {n} portioner @ {c.cost_per_portion_kr:.0f} kr/p, "
              f"{c.actual_per_portion['protein_g']:.0f}g protein/p, "
              f"score: {c.protein_per_kr:.2f} g_protein/kr")

    print(f"\nTotaler:")
    for k, v in plan.totals.items():
        print(f"  {k}: {v}")

    if plan.issues:
        print(f"\nIssues:")
        for iss in plan.issues:
            print(f"  - {iss}")

    today = date.today()
    _, week, _ = today.isocalendar()
    md = render_markdown(plan, {r["id"]: r for r in recipes}, week, today.year, cfg.get("stores", default=[]))
    out_path = root / "output" / "smoke_test_madplan.md"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"\nMarkdown skrevet til: {out_path}")
    print(f"Længde: {len(md)} tegn")


if __name__ == "__main__":
    main()
