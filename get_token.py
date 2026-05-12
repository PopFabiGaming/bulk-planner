"""Hent Microsoft Graph refresh token til OneDrive-upload.
Koeres een gang. Gemmer token til refresh_token.txt og venter paa Enter."""
import urllib.parse
import webbrowser
import http.server
import requests
import sys
from pathlib import Path


def pause_and_exit(code=0):
    try:
        input("\nTryk Enter for at lukke vinduet...")
    except EOFError:
        pass
    sys.exit(code)


print("=" * 60)
print(" Microsoft Graph refresh token hjaelper")
print("=" * 60)

try:
    CLIENT_ID = input("\nIndsaet din Application (client) ID: ").strip()
    if not CLIENT_ID or len(CLIENT_ID) < 20:
        print("\nFEJL: Application ID ser ikke rigtig ud (skal vaere en lang UUID-streng).")
        pause_and_exit(1)

    REDIRECT = "http://localhost:8000"
    SCOPE = "Files.ReadWrite offline_access"
    AUTH_URL = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT)}"
        f"&scope={urllib.parse.quote(SCOPE)}"
        f"&prompt=consent"
    )

    code_holder = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass

        def do_GET(self):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            if "code" in q:
                code_holder["code"] = q["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<h1>Det virkede!</h1><p>Du kan lukke vinduet og gaa tilbage til terminalen.</p>".encode("utf-8")
                )
            else:
                self.send_response(400)
                self.end_headers()

    print("\nAabner browser - log ind med din Microsoft-konto og godkend...")
    webbrowser.open(AUTH_URL)

    srv = http.server.HTTPServer(("localhost", 8000), H)
    print("Venter paa at du godkender i browseren...")
    while "code" not in code_holder:
        srv.handle_request()

    print("Fik auth-kode, henter refresh token...")
    r = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={
            "client_id": CLIENT_ID,
            "code": code_holder["code"],
            "redirect_uri": REDIRECT,
            "grant_type": "authorization_code",
            "scope": SCOPE,
        },
        timeout=30,
    )
    data = r.json()

    if "refresh_token" not in data:
        print("\n" + "=" * 60)
        print(" FEJL fra Microsoft:")
        print("=" * 60)
        print(data)
        print("\nTjek SETUP.md trin 3a-3c. Almindelige fejl:")
        print("  - 'Allow public client flows' er ikke slaaet til (trin 3b)")
        print("  - Permissions 'Files.ReadWrite' og 'offline_access' mangler (trin 3c)")
        pause_and_exit(1)

    token = data["refresh_token"]

    # Gem til fil saa du kan finde den selv hvis vinduet alligevel lukker
    out_file = Path(__file__).parent / "refresh_token.txt"
    out_file.write_text(token, encoding="utf-8")

    print("\n" + "=" * 60)
    print(" SUCCES")
    print("=" * 60)
    print(f"\nDit refresh token er gemt i:\n  {out_file}")
    print("\nAabn den fil og kopier hele indholdet ind som GitHub secret MS_REFRESH_TOKEN.")
    print("\nVIGTIGT: Slet refresh_token.txt naar du har kopieret den - eller behold den")
    print("et SIKKERT sted. Den maa ALDRIG comittes til git.")
    print(f"\nToken (foerste 40 tegn): {token[:40]}...")

except KeyboardInterrupt:
    print("\nAfbrudt.")
    pause_and_exit(130)
except Exception as e:
    print(f"\nUventet fejl: {e}")
    import traceback
    traceback.print_exc()
    pause_and_exit(1)

pause_and_exit(0)
