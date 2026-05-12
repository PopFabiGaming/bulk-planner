"""Orchestrator. Køres ugentligt af GitHub Actions (eller manuelt lokalt)."""
from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import date
from pathlib import Path

from .config import Config
from .scraper import fetch_all_offers
from .matcher import match_offers_to_ingredients
from .optimizer import plan_week
from .markdown_writer import render_markdown
from .onedrive_upload import upload_markdown
from .mailer import send_summary, send_error


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run() -> int:
    setup_logging()
    log = logging.getLogger("main")

    root = Path(__file__).resolve().parent.parent
    cfg = Config.load(root / "config.yaml")

    # Load data
    recipes_data = json.loads((root / "data" / "recipes.json").read_text(encoding="utf-8"))
    ingredients_data = json.loads((root / "data" / "ingredients.json").read_text(encoding="utf-8"))
    recipes = recipes_data["recipes"]
    ingredients = ingredients_data["ingredients"]

    # 1) Hent tilbud
    log.info("Henter tilbud...")
    stores = cfg.get("stores", default=[])
    offers = fetch_all_offers(
        stores=stores,
        use_mock=cfg.get("scraping", "use_mock", default=False),
        cache_ttl=cfg.get("scraping", "cache_ttl_seconds", default=3600),
        mock_path=root / "data" / "mock_offers.json",
    )
    log.info("Fandt %d rå tilbud", len(offers))

    # 2) Match til ingredient_keys
    provider = cfg.get("ai", "provider", default="gemini")
    api_key = cfg.secrets.get("GEMINI_API_KEY") if provider == "gemini" else cfg.secrets.get("OPENAI_API_KEY")
    matched, total = match_offers_to_ingredients(
        offers, ingredients,
        api_key=api_key or "",
        ai_enabled=cfg.get("ai", "enabled", default=True),
        provider=provider,
        model=cfg.get("ai", "model", default="gemini-1.5-flash"),
    )
    log.info("Matchede %d/%d tilbud til ingredienser", matched, total)

    # 3) Lav plan
    plan = plan_week(recipes, offers, ingredients, cfg)
    log.info("Plan: %d opskrifter, %.0f kr, %.0f kcal/dag, %.0fg protein/dag",
             len(plan.chosen_recipes), plan.totals["total_cost_kr"],
             plan.totals["daily_kcal_avg"], plan.totals["daily_protein_g_avg"])
    if plan.issues:
        for iss in plan.issues:
            log.warning("Issue: %s", iss)

    # 4) Render markdown
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    markdown = render_markdown(plan, {r["id"]: r for r in recipes}, iso_week, iso_year, stores)

    # Gem lokalt for debugging
    local_out = root / "output"
    local_out.mkdir(exist_ok=True)
    filename = cfg.get("output", "filename_template", default="Madplan-uge-{week}-{year}.md")
    filename = filename.format(week=iso_week, year=iso_year)
    (local_out / filename).write_text(markdown, encoding="utf-8")
    log.info("Skrev lokal kopi: %s", local_out / filename)

    # 5) Upload til OneDrive
    try:
        web_url = upload_markdown(
            content=markdown,
            onedrive_path=cfg.get("output", "onedrive_folder", default="/Obsidian/Madplan"),
            filename=filename,
            client_id=cfg.secrets["MS_CLIENT_ID"],
            refresh_token=cfg.secrets["MS_REFRESH_TOKEN"],
            tenant=cfg.secrets["MS_TENANT_ID"],
        )
    except Exception as e:  # noqa: BLE001
        log.error("OneDrive upload fejlede: %s", e)
        web_url = ""

    # 6) Send mail
    if cfg.get("notifications", "email_enabled", default=True) and cfg.secrets.get("SMTP_PASSWORD"):
        t = plan.totals
        text_body = (
            f"Madplan uge {iso_week} er klar.\n\n"
            f"- {len(plan.chosen_recipes)} opskrifter\n"
            f"- {t['daily_kcal_avg']} kcal/dag · {t['daily_protein_g_avg']}g protein/dag\n"
            f"- {t['total_cost_kr']:.0f} kr i alt (budget: {t['budget_kr']} kr)\n\n"
            f"OneDrive: {web_url or '(upload fejlede - se vedhæftede)'}\n\n"
            "Hele planen ligger i din Obsidian-vault."
        )
        html_body = f"<pre>{text_body}</pre>"
        try:
            send_summary(
                to=cfg.get("notifications", "email_to", default=""),
                subject=f"Madplan uge {iso_week} klar",
                body_text=text_body,
                body_html=html_body,
                host=cfg.secrets["SMTP_HOST"],
                port=cfg.secrets["SMTP_PORT"],
                user=cfg.secrets["SMTP_USER"],
                password=cfg.secrets["SMTP_PASSWORD"],
            )
        except Exception as e:  # noqa: BLE001
            log.error("Mail-fejl: %s", e)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        # Sidste-udvejs fejl-mail
        try:
            cfg = Config.load(Path(__file__).resolve().parent.parent / "config.yaml")
            if cfg.secrets.get("SMTP_PASSWORD") and cfg.get("notifications", "email_to"):
                send_error(
                    to=cfg.get("notifications", "email_to"),
                    error_text=tb,
                    host=cfg.secrets["SMTP_HOST"],
                    port=cfg.secrets["SMTP_PORT"],
                    user=cfg.secrets["SMTP_USER"],
                    password=cfg.secrets["SMTP_PASSWORD"],
                )
        except Exception:
            pass
        sys.exit(1)
