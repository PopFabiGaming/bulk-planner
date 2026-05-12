# Bulk-planner

Automatiseret ugentlig madplan-generator. Kører på GitHub Actions hver lørdag morgen, henter aktuelle tilbud fra dine foretrukne butikker i Odder, vælger billigste høj-protein-kombination ud fra en kurateret opskriftsdatabase, og skriver en Obsidian-venlig Markdown-fil til din OneDrive.

**Mål:** høj kalorie- og proteinindtag på et lille budget med minimal vedligeholdelse.

## Hvad det gør hver uge

1. Henter tilbud fra Netto, Løvbjerg, Kvickly, Rema og Lidl via Tjek/eTilbudsavis
2. Matcher rå produktnavne til kendte ingredienser (deterministisk + Gemini AI som backup)
3. Beregner pris per portion for hver opskrift med automatisk ingrediens-swap (kylling → kalkun hvis billigere)
4. Vælger de 4 opskrifter med højest protein-per-krone, sikrer makro-variation
5. Fordeler portioner over ugen så ~2900 kcal/dag og ~140g protein/dag rammes
6. Skriver indkøbsliste sorteret efter butik
7. Uploader Markdown-fil til din Obsidian vault i OneDrive
8. Sender resumé på mail

## Struktur

```
bulk-planner/
├── config.yaml            ← Dine personlige mål, budget, butikker
├── data/
│   ├── recipes.json       ← Opskriftsbase (12 opskrifter, udvidbar)
│   ├── ingredients.json   ← Ingrediens-master (makroer + default-priser)
│   └── mock_offers.json   ← Testdata
├── src/
│   ├── main.py            ← Orchestrator
│   ├── scraper.py         ← Tjek API + cache
│   ├── matcher.py         ← Match produktnavne → ingredienser (Gemini/OpenAI)
│   ├── optimizer.py       ← Vælg opskrifter, beregn portioner
│   ├── markdown_writer.py ← Render Obsidian Markdown
│   ├── onedrive_upload.py ← Microsoft Graph upload
│   ├── mailer.py          ← SMTP email
│   └── config.py          ← Load .env + yaml
├── .github/workflows/weekly.yml  ← Hver lørdag kl. 09:00
└── smoke_test.py          ← Kør lokalt med mock-data
```

## Quick start

```bash
# Klon eller download projektet
cp .env.example .env
# Udfyld .env med dine secrets

pip install -r requirements.txt

# Test lokalt uden secrets (bruger mock-data):
python smoke_test.py

# Kør den ægte pipeline (kræver secrets):
python -m src.main
```

For at få det op at køre automatisk hver uge: **se SETUP.md** for den komplette opsætning.

## Tilpasning

**Justér dine mål:** rediger `config.yaml` (kalorier, protein, budget, antal opskrifter).

**Tilføj opskrifter:** tilføj entries i `data/recipes.json`. Mønstret er:
- `ingredients` med `grams` og `swaps` (alternative ingredienser hvis de er billigere)
- `per_portion` med makroer
- `instructions` som ren tekst

Systemet vælger automatisk billigste swap, så du behøver ikke 5 varianter af samme ret.

**Tilføj ingrediens:** tilføj i `data/ingredients.json` med makroer per 100g, default-pris per kg, og `search_terms` til matching.

## Kendte begrænsninger

- **Tjek's API er ikke officielt** — endpoints kan ændres. Hvis scraperen knækker, se `src/scraper.py` (sæt `LOG_LEVEL=DEBUG`).
- **Frisk frugt og grønt** er ikke altid på tilbudsaviser → systemet bruger default-priser for de varer.
- **Opskriftsbasen er bevidst kompakt** (12 retter). Du roterer mellem 4 om ugen, så du ser de samme retter ofte. Dette er meal-prep design, ikke en fejl.

Se `SETUP.md` for komplet deployment-guide.
