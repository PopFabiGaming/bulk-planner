# Setup-guide: få bulk-planner op at køre

Følg dette i rækkefølge. Forventet tid: 30-45 minutter første gang.

## 0. Forudsætninger

Du skal bruge:
- En GitHub-konto (gratis)
- En Microsoft-konto (din OneDrive-konto)
- En Google-konto (til gratis Gemini API)
- En Gmail-konto (til at sende notifikations-mail)

Du behøver IKKE betale for noget. Alt kører på gratis tiers.

---

## 1. Læg projektet på GitHub

1. Gå til https://github.com/new
2. Lav et nyt **privat** repo - kald det fx `bulk-planner`
3. På din egen PC, åbn en terminal i `bulk-planner`-mappen og kør:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<dit-brugernavn>/bulk-planner.git
git push -u origin main
```

Hvis du ikke har brugt git før: download GitHub Desktop fra https://desktop.github.com - det giver dig en knap-baseret oplevelse.

---

## 2. Gemini API-key (gratis, til ingrediens-matching)

1. Gå til https://aistudio.google.com/apikey
2. Log ind med din Google-konto
3. Klik **"Create API key"** -> **"Create API key in new project"**
4. Kopier key'en. Gem den et sikkert sted (fx en password manager, IKKE i kode)

Gratis tier: 1500 requests/dag, langt mere end nok.

---

## 3. Microsoft Graph API (OneDrive-upload)

Det her er det mest fiklede skridt. Tag det roligt.

### 3a. Lav en Azure app-registrering

1. Gå til https://portal.azure.com (log ind med din Microsoft-konto)
2. Søg efter "App registrations" i søgefeltet
3. Klik **"+ New registration"**
4. Udfyld:
   - Name: `bulk-planner`
   - Supported account types: **"Personal Microsoft accounts only"**
   - Redirect URI: vælg **"Public client/native"** og indtast `http://localhost:8000`
5. Klik **"Register"**

Du står nu på app-siden. Noter **Application (client) ID** - du skal bruge den om lidt.

### 3b. Tillad refresh tokens

1. I venstre menu, klik **"Authentication"**
2. Under "Advanced settings", find **"Allow public client flows"** og sæt til **Yes**
3. Klik **Save**

### 3c. Tilføj API-tilladelser

1. I venstre menu, klik **"API permissions"**
2. Klik **"+ Add a permission"** -> **"Microsoft Graph"** -> **"Delegated permissions"**
3. Søg og tilføj: `Files.ReadWrite` og `offline_access`
4. Klik **"Add permissions"**

### 3d. Hent dit refresh token (en gang for alle)

På din PC, kør dette Python-script (gem som `get_token.py`):

```python
import urllib.parse, webbrowser, http.server, requests, sys

CLIENT_ID = input("Indsæt din Application (client) ID: ").strip()
REDIRECT = "http://localhost:8000"
SCOPE = "Files.ReadWrite offline_access"
AUTH_URL = (
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
    f"?client_id={CLIENT_ID}&response_type=code&redirect_uri={urllib.parse.quote(REDIRECT)}"
    f"&scope={urllib.parse.quote(SCOPE)}&prompt=consent"
)

code_holder = {}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        if "code" in q:
            code_holder["code"] = q["code"][0]
            self.send_response(200); self.end_headers()
            self.wfile.write(b"Du kan lukke vinduet.")
        else:
            self.send_response(400); self.end_headers()

print("Åbner browser - log ind og giv adgang...")
webbrowser.open(AUTH_URL)
srv = http.server.HTTPServer(("localhost", 8000), H)
while "code" not in code_holder:
    srv.handle_request()
print("Fik auth-kode, henter refresh token...")

r = requests.post(
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
    data={
        "client_id": CLIENT_ID,
        "code": code_holder["code"],
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
        "scope": SCOPE,
    },
)
data = r.json()
if "refresh_token" not in data:
    print("FEJL:", data); sys.exit(1)
print("\n*** Din refresh token (gem den sikkert): ***")
print(data["refresh_token"])
```

Kør med `pip install requests && python get_token.py`. Log ind med din Microsoft-konto, godkend tilladelserne. Når browseren viser "Du kan lukke vinduet", står dit refresh token i terminalen. Kopier det.

---

## 4. Gmail App Password (til notifikations-mail)

Almindeligt Gmail-password virker IKKE - du skal lave et "App password":

1. Gå til https://myaccount.google.com/apppasswords
2. Du skal have 2FA slået til først (https://myaccount.google.com/security)
3. Lav en app-password kaldet "bulk-planner"
4. Kopier den 16-tegns kode. Gem den sikkert.

---

## 5. Tilføj secrets til GitHub

1. Gå til dit GitHub repo
2. Klik **Settings** -> **Secrets and variables** -> **Actions**
3. Klik **"New repository secret"** for hver af disse:

| Navn | Værdi |
|------|-------|
| `GEMINI_API_KEY` | Din Gemini key fra trin 2 |
| `MS_CLIENT_ID` | Application (client) ID fra trin 3a |
| `MS_TENANT_ID` | `consumers` |
| `MS_REFRESH_TOKEN` | Refresh token fra trin 3d |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Din Gmail-adresse |
| `SMTP_PASSWORD` | App password fra trin 4 (uden mellemrum) |

---

## 6. Aktivér GitHub Actions

1. På GitHub, klik fanen **Actions**
2. Hvis du ser "I understand my workflows, go ahead and enable them", klik den
3. Du burde se "weekly-bulk-planner" i workflow-listen
4. Klik på den, klik **"Run workflow"** -> **"Run workflow"** (manuel test-kørsel)
5. Vent 1-3 minutter. Klik på kørslen for at se logs

Hvis alt går vel:
- Du får en mail på din Gmail om at planen er klar
- Filen `Madplan-uge-XX-2026.md` ligger i `/Obsidian/Madplan/` i din OneDrive

Hvis Obsidian-mappestien ikke matcher din vault, ret `output.onedrive_folder` i `config.yaml`.

Fra nu af kører den **automatisk hver lørdag kl. 09:00** uden at du skal gøre noget.

---

## 7. Lokal test (valgfri)

Vil du teste lokalt før du pusher til GitHub?

```bash
cp .env.example .env
# Udfyld .env med samme værdier som GitHub secrets

pip install -r requirements.txt

# Hurtig test med mock-data (ingen secrets nødvendige):
python smoke_test.py

# Ægte kørsel:
python -m src.main
```

---

## Hvad nu hvis noget går galt?

**Mailen kommer ikke:** tjek GitHub Actions-loggen. Den fortæller hvad der fejlede. Send-error-mail prøver at sende selv hvis hovedpipelinen fejler.

**Filen er ikke i OneDrive:** tjek at `onedrive_folder` i `config.yaml` matcher en eksisterende mappe i din OneDrive (relativt fra rod).

**Tilbud ser ikke ud til at være med:** Tjeks API kan ændres uden varsel. Sæt `scraping.use_mock: true` i config og verificér at resten virker. Find evt. ny endpoint på tjek.dk/web-app.

**Refresh token udløb:** Microsoft refresh tokens er typisk gyldige i 90 dage med inaktivitet, men fornys hver gang de bruges. Hvis du ikke har kørt pipelinen i 90+ dage, må du lave et nyt token via `get_token.py`.

---

## Næste skridt (når basisen virker)

- **Tilføj flere opskrifter:** rediger `data/recipes.json`. Brug eksisterende som mønster.
- **Tilføj allergi/restriktioner:** udfyld `restrictions.exclude_ingredients` i `config.yaml`.
- **Slå AI fra:** sæt `ai.enabled: false` hvis du vil køre helt deterministisk.
- **Skift dag/tid:** ret `cron`-udtrykket i `.github/workflows/weekly.yml`.
