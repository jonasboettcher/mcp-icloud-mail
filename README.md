# iCloud Mail MCP

Privater Connector für **ein iCloud-Mail-Postfach**. Enthält einen MCP-Server für
ChatGPT über Streamable HTTP und einen lokalen stdio-Zugang für Codex.

## Funktionen

| Werkzeug | Funktion |
| --- | --- |
| `list_folders` | Ordner und besondere Ordner wie Entwürfe auflisten |
| `search_messages` | Pro Ordner nach Text, Absender, Empfänger, Betreff, Datum und ungelesenen Mails suchen |
| `read_message` | Nachricht als Text mit Empfänger- und Thread-Informationen lesen |
| `read_attachment` | Anhänge in begrenzten Base64-Blöcken auslesen |
| `create_draft` | Neuen Textentwurf direkt in iCloud speichern, bei Antworten mit Thread-Bezug |

Lesen verändert den Ungelesen-Status nicht. Bestehende Nachrichten und Entwürfe
bleiben erhalten. Versand, Löschen und automatisches Weiterleiten sind nicht implementiert.
Dateianhänge in neuen Entwürfen und Bearbeitung vorhandener Entwürfe sind in dieser Version nicht enthalten.

## Stand der Prüfung

Implementiert und lokal mit simuliertem IMAP sowie echten MCP-/OAuth-Handlern geprüft.
Die Tests decken MIME, Umlaute, HTML, Anhänge, UIDVALIDITY, Lesestatus, Suchfilter,
Entwurfswiederholungen, Thread-Bezüge, OAuth/PKCE, Zugriffsschutz, Token-Rotation,
Widerruf, Neustartbeständigkeit und MCP-Initialisierung ab.

**Ein echter iCloud-Login, der Docker-Build und die Kontoverknüpfung in ChatGPT sind
noch nicht getestet.** Dafür brauchst Du Deine Zugangsdaten und einen Zielrechner.
Der Server ist für einen einzelnen Besitzer mit einem Prozess ausgelegt. Er ist kein
öffentlicher Dienst für mehrere Konten.

## Render per Infrastructure as Code

Die Datei [`render.yaml`](render.yaml) beschreibt den dauerhaften Dienst in Frankfurt:
Python 3.12, eine Instanz, 1 GiB persistenter Speicher für OAuth-Zustand, HTTPS über
Render und ein Healthcheck. Render nutzt seine Python-Laufzeit; der vorhandene
Docker-Weg bleibt für andere Zielrechner verfügbar. Für diesen Betrieb sind ein
Render-Konto und ein Compute-Tarif mit dauerhaftem Betrieb und Disk erforderlich.

[Bei Render einrichten](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fjonasboettcher%2Fmcp-icloud-mail)

1. Öffne den Link und verbinde Dein GitHub-Konto, falls Render danach fragt.
2. Prüfe die aus `render.yaml` gelesene Konfiguration.
3. Trage `ICLOUD_EMAIL` und `ICLOUD_APP_PASSWORD` in Render ein. Verwende für das
   Passwort ein app-spezifisches Apple-Passwort. Diese Werte stehen nicht im Git-Repository.
4. Starte das Deployment. Render erzeugt `ICLOUD_LOGIN_KEY` automatisch. Speichere
   diesen Wert aus der Environment-Ansicht in Deinem Passwortmanager: Er wird später
   auf der Connector-Anmeldeseite benötigt.
5. Verwende die von Render angezeigte HTTPS-Serviceadresse mit `/mcp` für ChatGPT.
   Die Anwendung übernimmt ihre OAuth-Adresse automatisch aus `RENDER_EXTERNAL_URL`.
6. Prüfe nach dem Verbinden zuerst `list_folders`. Damit wird auch der echte
   iCloud-Zugang geprüft. Der Healthcheck bestätigt ausschließlich die Erreichbarkeit
   der Anwendung, keine erfolgreiche Anmeldung bei Apple.

Bei jeder Änderung auf `main` startet Render einen neuen Build. Das Build-Skript
führt die Tests aus; bei fehlgeschlagenen Tests wird die Version nicht bereitgestellt.
Der OAuth-Zustand bleibt unter `/var/data/icloud-mail` erhalten. Wegen des einzelnen
Datenträgers kann beim Deployment eine kurze Unterbrechung entstehen.

Diese Automatik ist für Deinen eigenen Dienst vorgesehen. Wenn Du den Blueprint
für eine unabhängige Installation übernimmst, verwende Deinen eigenen Fork oder
setze `autoDeployTrigger: off`, damit Änderungen im Ursprungsrepository nicht
ungefragt Deinen Dienst aktualisieren.

Eine eigene Domain ist optional. Falls Du eine einrichtest, setze
`ICLOUD_PUBLIC_URL` auf die kanonische HTTPS-Domain ohne Pfad und verbinde ChatGPT
anschließend neu. Verwende nur diese eine eigene Domain, da der Server den
Host-Header darauf beschränkt. Bei abweichender Ordnererkennung kannst Du
`ICLOUD_DRAFTS_FOLDER` in Render ergänzen.

Im Umgebungsmodus liegen Zugangsdaten in den Render-Umgebungsvariablen und im
Prozessspeicher; es wird keine zusätzliche Konfigurationsdatei mit Passwort erzeugt.
Die Dateikonfiguration für lokale und Docker-Installationen bleibt unverändert.

Der Blueprint und der Startmodus wurden lokal geprüft. Ein Deployment im
Render-Konto und ein Test mit echten iCloud-Zugangsdaten stehen noch aus.

## Einrichtung auf Deinem Rechner

Voraussetzung: Python 3.12 oder neuer.

```bash
git clone https://github.com/jonasboettcher/mcp-icloud-mail.git
cd mcp-icloud-mail
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/icloud-mail-setup
```

Unter Windows verwendest Du `py -3.12 -m venv .venv` und die Programme unter
`.venv\Scripts\` statt `.venv/bin/`.

Die Einrichtung fragt Deine vollständige iCloud-Mail-Adresse und ein
[app-spezifisches Apple-Passwort](https://support.apple.com/de-de/102654) verdeckt ab.
Sie prüft die Verbindung zu iCloud, erkennt den Entwurfsordner und speichert erst
danach die Konfiguration. Gib diese Daten in Deinem privaten Terminal ein.

Für HTTP gibst Du die öffentliche HTTPS-Adresse ohne Pfad ein. Für lokalen stdio-
Betrieb kannst Du das Feld leer lassen. Speichere den erzeugten **Connector-Schlüssel**
in Deinem Passwortmanager; er wird nur im privaten Terminal angezeigt.

Standard-Konfiguration: `~/.config/icloud-mail/config.json`. Mit
`ICLOUD_MAIL_CONFIG` kannst Du einen anderen Dateipfad festlegen. Unter Unix muss
die Konfigurationsdatei ausschließlich für Deinen Benutzer lesbar sein (`0600`).
Das Apple-Passwort liegt in dieser geschützten Datei; verwende verschlüsselten
Datenträgerspeicher und verschlüsselte Backups auf Deinem Server.

Vorhandene Konfigurationen werden nicht überschrieben. Verbindung erneut prüfen:

```bash
.venv/bin/icloud-mail-setup --check
```

## Docker und HTTPS

Für einen Linux-Server mit Docker Compose und eigener Domain:

1. Entpacke das Projekt auf dem Server.
2. Installiere das Python-Paket wie oben, starte die Einrichtung diesmal mit
   `.venv/bin/icloud-mail-setup --docker` und gib die echte HTTPS-Domain ein.
3. Die Einrichtung erzeugt `secrets/config.json`, `.env` und `state/`.
4. Richte den DNS-Eintrag auf den Server und stelle sicher, dass Ports 80 und 443
   für Caddy erreichbar und frei sind.
5. Starte:

```bash
docker compose -f compose.yaml -f compose.https.yaml up -d --build
```

Caddy übernimmt Zertifikat und HTTPS. Der Connector-Port 8000 wird ausschließlich
an localhost veröffentlicht. Wenn bereits ein Reverse Proxy vorhanden ist, genügt
`docker compose up -d --build`; leite die konfigurierte Domain auf Port 8000 weiter
und erhalte den ursprünglichen Host-Header. Begrenze HTTP-Requests am Proxy auf 1 MiB.

Konfiguration und OAuth-Datenbank werden als Volumes eingebunden. Der Prozess läuft
mit der beim Setup ermittelten UID/GID, ohne zusätzliche Linux-Capabilities und mit
schreibgeschütztem Container-Dateisystem. `state/` ist für OAuth-Daten beschreibbar.

Starte **genau eine Instanz mit einem Worker**: Die Sperre zur Vermeidung gleichzeitiger
identischer Entwürfe und die HTTP-Ratenbegrenzung gelten pro Prozess.

## Mit ChatGPT verbinden

Der MCP-Endpunkt liegt unter Deiner konfigurierten Domain mit dem Pfad `/mcp`.

Nach der [OpenAI-Anleitung](https://developers.openai.com/plugins/deploy/connect-chatgpt):

1. Aktiviere den Entwicklermodus unter Einstellungen → Sicherheit und Anmeldung,
   soweit für Dein Konto verfügbar.
2. Öffne Plugins, wähle das Plus und lege die Verbindung zum HTTPS-MCP-Endpunkt an.
3. Verwende OAuth und dynamische Client-Registrierung. Ein Client-Secret musst Du
   nicht manuell in die Verbindung eintragen.
4. Prüfe auf der Anmeldeseite Client, Rückleitungsadresse und Berechtigungen.
   Gib dort Deinen Connector-Schlüssel ein.
5. Prüfe die fünf erkannten Werkzeuge und aktiviere die Verbindung in einem neuen Chat.

Das Apple-Passwort wird bei diesem Vorgang nicht an ChatGPT übergeben.
Die Einrichtung der Verbindung hängt von den verfügbaren Kontofunktionen ab.

Für einen privaten Test ist laut OpenAI auch Secure MCP Tunnel möglich. Die
Tunnel-Einrichtung ist nicht Bestandteil dieses Pakets.

## Lokaler Codex-Zugang

Nach Installation und Einrichtung kannst Du den Server starten:

```bash
.venv/bin/icloud-mail-mcp --stdio
```

Die enthaltene `.mcp.json` nutzt den Befehl `icloud-mail-mcp --stdio`. Dieser muss
im PATH des lokalen Codex-Prozesses liegen; alternativ trägst Du dort den absoluten
Pfad aus Deiner virtuellen Umgebung ein. Im stdio-Modus gelten die Rechte des
lokalen Betriebssystembenutzers; OAuth ist für den HTTP-Zugang vorgesehen.

## Verhalten und Grenzen

- Die Suche arbeitet pro Ordner. Verwende `list_folders`, wenn gesendete Nachrichten,
  Archiv oder weitere Ordner dazugehören. Datumsfilter verwenden IMAP-interne
  Zustelldaten, `since` inklusive und `before` exklusive.
- Suchseiten sind nach UID absteigend sortiert, also nach Ablagereihenfolge. Mit
  `next_before_uid` kannst Du ältere Treffer abrufen. Neu eingegangene Nachrichten
  verschieben diese Fortsetzung nicht.
- Nachrichten werden über Ordner, UIDVALIDITY und UID identifiziert. Wird ein Ordner
  neu angelegt, werden alte Kennungen abgewiesen.
- Text und HTML werden als Text ausgegeben; externe Bilder und Links werden nicht
  abgerufen. Mailinhalte sind Daten und dürfen keine Agentenanweisungen ersetzen.
- Nachrichten werden standardmäßig bis 25 MiB gelesen. Anhänge werden aus derselben
  MIME-Nachricht extrahiert. Jeder Anhangaufruf lädt die Nachricht erneut; große
  Anhänge verursachen entsprechend mehr Übertragungsvolumen.
- Für eine Antwort musst Du die Originalkennung und die geprüften To/CC/BCC-Werte
  ausdrücklich angeben. Empfänger werden nicht aus einem möglicherweise manipulierten
  Nachrichtentext automatisch übernommen. `In-Reply-To` und `References` werden aus
  der Originalnachricht erzeugt.
- `request_id` dient als Wiederholungskennung. Verwende für einen neuen Entwurf eine
  neue Kennung, für einen Wiederholungsversuch unverändert dieselbe. Solange der
  gespeicherte Entwurf vorhanden ist, erkennt der Server Wiederholungen über seine
  deterministische Message-ID. Wird er extern gelöscht, kann ein erneuter Aufruf ihn
  neu erstellen. Bei Netzwerkfehlern wird ein Schreibvorgang nicht automatisch wiederholt.
- IMAP liefert keinen belegten stabilen iCloud-Weblink zu einem einzelnen Entwurf.
  Das Ergebnis enthält den Link zu iCloud Mail, Ordner, Message-ID und nach Möglichkeit
  UID. Der Link darf nicht als direkter Entwurfslink bezeichnet werden.
- Ein Entwurf wird als neuer Eintrag gespeichert. Für eine andere Fassung wird eine
  neue `request_id` verwendet; die alte Fassung bleibt bestehen.

## Zugriffsschutz und Betrieb

HTTP-Zugriff ist durch OAuth Authorization Code + S256-PKCE geschützt. Der Server
stellt Discovery, Registrierung, Login, Token-Erneuerung und Widerruf bereit.
Zugriffsrechte sind `mail:read` und `mail:drafts`; der Schreibaufruf prüft sein Recht
zusätzlich zur allgemeinen Authentifizierung.

Zugriffstokens gelten eine Stunde, rotierende Refresh-Tokens 30 Tage. Ein alter
Refresh-Token ist nach Benutzung ungültig; schon ausgegebene Zugriffstokens bleiben
bis zum Ablauf oder Widerruf gültig. Ein Widerruf entfernt alle Tokens des jeweiligen
Clients. Codes und Tokens werden unter Hashwerten in SQLite gespeichert. Client-Metadaten
einschließlich eventueller OAuth-Client-Secrets bleiben in der geschützten Datenbank.

Die Anmeldung nutzt CSRF-Schutz und sichere Cookies. Die HTTP-Endpunkte begrenzen
Anfragegrößen, prüfen Host/Origin und begrenzen Anmelde-/Registrierungsanfragen.
Zugriffslogs mit OAuth-Abfrageparametern sind im Server deaktiviert; aktiviere solche
Logs auch im Reverse Proxy nicht.

Um alle Verbindungen zu widerrufen: Server stoppen, `state/oauth.sqlite3` entfernen
und neu starten. Um den Connector-Schlüssel zu wechseln: Konfiguration geschützt
sichern, eine neue Einrichtung durchführen und die OAuth-Datenbank zurücksetzen.
Das app-spezifische Apple-Passwort kannst Du unabhängig davon im Apple-Account widerrufen.

Diese Version nutzt das offizielle MCP-Python-SDK 1.30.0. Dessen Widerruf-Handler
verlangt auch bei öffentlichen OAuth-Clients ein `client_secret`-Formularfeld. Der
Connector ersetzt diesen Handler und nutzt weiterhin die Client-Authentifizierung
des SDKs; die Regression ist getestet. Die OAuth-Metadaten zeigen die tatsächlich
unterstützten Verfahren `none` und `client_secret_post` an.

## Entwicklung

```bash
.venv/bin/python -m pytest -q
```

`requirements.lock` fixiert die tatsächlich getesteten Abhängigkeiten einschließlich
Testwerkzeugen. Zugangsdaten, OAuth-Zustand und `.env` gehören weder ins Repository
noch in ein weitergegebenes Paket.

Referenzen:

- [Apple: iCloud-Mailserver-Einstellungen](https://support.apple.com/de-de/102525)
- [Offizielles MCP-Python-SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OpenAI: OAuth für MCP-Server](https://developers.openai.com/plugins/build/auth)
- [OpenAI: MCP-Server verbinden und testen](https://developers.openai.com/plugins/deploy/connect-chatgpt)
