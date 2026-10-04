# Lexware Office MCP auf Render

Eigener Render-Dienst im bestehenden Workspace von Jonas Böttcher.
Quellcode und Bereitstellung liegen auf dem isolierten Branch `lexware-mcp` dieses
Repositories. Der Mail-Dienst verwendet weiterhin `main`.

Basis: [marselsel/Lexware-MCP-Server](https://github.com/marselsel/Lexware-MCP-Server),
Commit `8da792d08146665036943a9ee7d1b7f444225939`.
Die OAuth-Anmeldung stammt aus dem iCloud-Mail-Projekt, verwendet aber eigene
Schlüssel, Berechtigungen und Daten. Kein Zugriff auf das Mailkonto.

## Render-Einstellungen

- Region Frankfurt; Runtime Node; Branch `lexware-mcp`; automatische Deployments aus.
- Build: `bash lexware_gateway/build.sh`
- Start: `.lexware-venv/bin/python -m lexware_gateway.server`
- Health: `/healthz`; MCP: `/mcp`; OAuth mit dynamischer Clientregistrierung und PKCE.
- `NODE_VERSION=24.19.0`
- `LEXWARE_LOGIN_KEY`: eigener zufälliger Verbindungsschlüssel, mindestens 32 Zeichen.
- `LEXWARE_API_KEY`: im [Lexware-API-Bereich](https://app.lexware.de/addons/public-api)
  erzeugen und ausschliesslich in Render als geheime Umgebungsvariable speichern.

Nach Eintragen des API-Schlüssels die Render-Änderung mit Deployment speichern.
Ohne den Schlüssel funktionieren Dienst, OAuth und Werkzeug-Erkennung; sämtliche
Werkzeugaufrufe sind vor jedem Lexware-Zugriff gesperrt. Der Health-Status nennt
`lexware_configured`, enthält aber keine Zugangsdaten.

## ChatGPT

MCP-URL des Dienstes mit `/mcp` verwenden; Authentifizierung OAuth wählen.
Auf der Anmeldeseite den `LEXWARE_LOGIN_KEY` aus Render eingeben. Der Lexware-
API-Schlüssel wird niemals in ChatGPT, GitHub oder das Plugin-Paket eingetragen.

## Umfang und 2024

17 Werkzeuge: gezielte Beleg-/Dokument-/Dateiabfragen, Kontaktabfragen,
Beleglisten, Zahlungsinformationen und Profildaten; Buchungsbelege anlegen oder
ändern; Dateien hochladen und Belegen anhängen. Rechnungen und Rechnungskorrekturen
erzeugen, Artikel verändern, Webhooks verändern und Löschwerkzeuge fehlen in der
tatsächlich registrierten Werkzeugliste.

Die [exportbasierte Checkliste 2024](https://github.com/tradmusica/organisation/blob/main/processes/lexware-checkliste-2024-exportbasiert.md)
bleibt massgeblich. Keine fachliche Live-Prüfung. Korrekturen nur anhand der
verifizierten Anweisung in `03_Korrekturen`, mit Versionsabgleich und Nachkontrolle.
Zahlungszuordnungen, Stornos und festgeschriebene Belege erfordern weiterhin die
Lexware-Oberfläche.

## Betrieb

Die erste Bereitstellung verwendet den kostenlosen Render-Plan. OAuth-Zustand
liegt auf dem temporären Dateisystem; nach Neustart oder Deployment muss ChatGPT
neu verbunden werden. Für dauerhafte Verbindungen einen persistenten Datenträger
unter `/var/data` und `LEXWARE_STATE_DIR=/var/data/lexware-oauth` konfigurieren.
Der optionale Blueprint `lexware_gateway/render.yaml` beschreibt diese Variante.
Genau eine Instanz betreiben. Keine Zugangsdaten oder OAuth-Daten versionieren.

Tests: unveränderte Upstream-Tests vor der Anpassung; danach TypeScript-Build und
Gateway-Tests mit OAuth/PKCE, CSRF, Tokenrotation, Sperre ohne API-Schlüssel und
Prüfung der echten MCP-Werkzeugliste. Keine Live-Buchung durch diese Tests.
