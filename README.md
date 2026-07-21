# Community App – Backend

Das Backend bildet ein kommunales Fachverfahren für Bürgeranliegen, behördliche Bearbeitungsabläufe, öffentliche Informationen und Terminverwaltung ab. Es basiert auf FastAPI, SQLAlchemy, PostgreSQL und Alembic.

Die Anwendung enthält insbesondere:

- einen rollenbasierten Authentifizierungs- und Benutzerbereich,
- einen variablen Ad-hoc-Workflow für Bürger-Tickets,
- Event Sourcing für Tickets und Termine,
- eine klassische CRUD-Entität für öffentliche Informationen,
- Termin-Slots und versionierte PDF-Dokumente,
- Bilder für Tickets und Informationen,
- serverseitige Validierung und einheitliche Fehlerantworten,
- Suche, Filterung, Sortierung und Pagination,
- idempotentes Demo-Seeding mit unterschiedlichen Rollen, Zuständen und Eventhistorien.

## Technischer Überblick

- Python 3.11 oder neuer
- FastAPI und Pydantic 2
- SQLAlchemy 2 mit asynchronem PostgreSQL-Treiber `asyncpg`
- Alembic für Datenbankmigrationen
- PostgreSQL 15 über Docker Compose oder eine lokal installierte PostgreSQL-Instanz
- Lokales Dateisystem für Bilder und Appointment-PDFs
- Pytest und Ruff für Qualitätssicherung

## Projektstruktur

```text
.
├── alembic/                 # Alembic-Umgebung und Schema-Migrationen
│   └── versions/            # Lineare Migrationshistorie
├── docs/
│   └── module_requirements.md
│                              # Zuordnung der Implementierung zu den Modulanforderungen
├── scripts/
│   ├── seed/                 # Idempotentes Demo-Seeding
│   └── verify_backend.sh     # Kompilierung, Linting, Tests und Migrationsprüfung
├── src/
│   ├── address/              # Wiederverwendbare Adressmodelle und Services
│   ├── appointment/          # Termine, Slots, Events und versionierte Dokumente
│   ├── auth/                 # Login, Tokens, Logout und Passwort-Reset
│   ├── core/                 # Config, Datenbank, Fehler, Security und gemeinsame Helfer
│   ├── info/                 # Klassische CRUD-Infos inklusive Status und Bildern
│   ├── media/                # Gemeinsame Bild- und Dokumentablage
│   ├── office/               # Behördenstellen, Öffnungszeiten und Adressen
│   ├── ticket/               # Bürger-Tickets und behördlicher Ad-hoc-Workflow
│   ├── user/                 # Benutzer, Rollen und Berechtigungen
│   ├── main.py               # FastAPI-Anwendung und Router-Registrierung
│   └── models.py             # Gemeinsame SQLAlchemy-Modellregistrierung
├── tests/                    # Unit- und optionale PostgreSQL-Integrationstests
├── .env.example             # Vollständige Beispielkonfiguration
├── compose.yml              # PostgreSQL-Container
├── pyproject.toml           # Ruff- und Pytest-Konfiguration
├── requirements.txt         # Laufzeitabhängigkeiten
└── requirements-dev.txt     # Laufzeit- und Entwicklungsabhängigkeiten
```

Innerhalb der Fachmodule folgt der Code grundsätzlich einer Schichtung aus Router, Request-/Response-Schemas, Services, Repositories und SQLAlchemy-Modellen. Die eventgesourcten Bereiche enthalten zusätzlich Aggregate, typisierte Event-Payloads und Event Stores.

# Installation und Erststart

Die folgenden Schritte starten das Backend einschließlich einer neuen PostgreSQL-Datenbank und vollständiger Demo-Daten.

## 1. Voraussetzungen

Benötigt werden:

- Python 3.11 oder neuer,
- Docker mit Docker Compose,
- Git,
- ein Terminal im Projektverzeichnis.

Eine lokale PostgreSQL-Installation kann anstelle von Docker verwendet werden. In diesem Fall müssen die `POSTGRES_*`-Variablen auf diese Instanz zeigen.

## 2. Repository klonen und Projektverzeichnis öffnen

```bash
git clone <REPOSITORY-URL>
cd Backend
```

Der genaue Verzeichnisname kann je nach Checkout abweichen. Alle weiteren Befehle müssen aus dem Backend-Projektverzeichnis ausgeführt werden.

## 3. Virtuelle Python-Umgebung erstellen

Linux und macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Anschließend die Paketwerkzeuge und Abhängigkeiten installieren:

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Für einen reinen Produktivbetrieb ohne Test- und Lint-Werkzeuge genügt:

```bash
pip install -r requirements.txt
```

## 4. Umgebungsdatei anlegen

```bash
cp .env.example .env
```

Unter Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Die Beispielwerte sind für eine lokale Entwicklungsumgebung vorgesehen. Mindestens die Passwörter und das JWT-Secret sollten angepasst werden.

`DATABASE_URL` wird automatisch aus den fünf `POSTGRES_*`-Variablen zusammengesetzt und darf nicht zusätzlich definiert werden.

## 5. PostgreSQL starten

`compose.yml` startet ausschließlich die Datenbank. Das Backend selbst wird später im lokalen Python-Environment gestartet.

```bash
docker compose up -d db
```

Datenbankbereitschaft prüfen:

```bash
docker compose exec db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Da das Backend auf dem Host läuft, muss in `.env` gelten:

```dotenv
POSTGRES_HOST="localhost"
```

## 6. Datenbankschema migrieren

```bash
alembic upgrade head
```

Aktuellen Stand prüfen:

```bash
alembic current
alembic heads
```

Das Seeding darf erst nach erfolgreicher Migration ausgeführt werden.

## 7. Demo-Daten erzeugen

Empfohlen ist der explizite einmalige Seed-Aufruf:

```bash
python -m scripts.seed.run_seed
```

Voraussetzungen:

- `ENVIRONMENT` darf nicht `production` sein,
- `SEED_DEFAULT_PASSWORD` muss gesetzt sein,
- das Passwort muss mindestens acht Zeichen enthalten,
- das Datenbankschema muss bereits auf dem aktuellen Alembic-Stand sein.

Das Seeding ist idempotent. Ein erneuter Aufruf überspringt bereits vorhandene stabile Demo-Szenarien, anstatt sie zu duplizieren.

Alternativ kann in `.env` gesetzt werden:

```dotenv
RUN_SEED_ON_STARTUP=true
```

Dann wird das Seed-Verfahren bei jedem Anwendungsstart ausgeführt. In `production` wird Startup-Seeding von der Konfiguration abgelehnt.

## 8. Backend starten

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Danach sind unter anderem erreichbar:

```text
API-Status:       http://localhost:8000/
Swagger UI:       http://localhost:8000/docs
ReDoc:            http://localhost:8000/redoc
OpenAPI-JSON:     http://localhost:8000/api/v1/openapi.json
```

Die API-Routen beginnen standardmäßig mit:

```text
/api/v1
```

# Schnellstart in einem Block

Nach dem Anlegen und Prüfen der `.env`-Datei:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

docker compose up -d db
docker compose exec db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

alembic upgrade head
python -m scripts.seed.run_seed

uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

# Demo-Benutzer

Alle geseedeten Benutzer verwenden das Passwort aus:

```dotenv
SEED_DEFAULT_PASSWORD=...
```

Stabile Demo-Adressen:

| Rolle | Benutzer |
|---|---|
| Admin | `admin@test.com` |
| Manager Bauamt | `manager1@bauamt.com`, `manager2@bauamt.com` |
| Manager Bürgeramt | `manager3@buergeramt.com` |
| Dispatcher Bauamt | `dispatcher1@bauamt.com` |
| Dispatcher Bürgeramt | `dispatcher2@buergeramt.com`, `dispatcher3@buergeramt.com` |
| Officer Bauamt | `officer1@bauamt.com`, `officer2@bauamt.com` |
| Officer Bürgeramt | `officer3@buergeramt.com` |
| Citizens | `citizen1@test.com`, `citizen2@test.com`, `citizen3@test.com` |

Der Login-Endpunkt verwendet OAuth2-Formulardaten. Das Feld `username` enthält dabei die E-Mail-Adresse:

```bash
curl -X POST 'http://localhost:8000/api/v1/auth/login' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin@test.com&password=ChangeThisDemoPassword123!'
```

Die Antwort enthält ein Access- und ein Refresh-Token. Für geschützte API-Aufrufe wird das Access-Token als Bearer-Token verwendet:

```bash
curl 'http://localhost:8000/api/v1/users/me' \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

# Umfang der Seed-Daten

Der vollständige Seed-Lauf erzeugt in einer gemeinsamen Transaktion:

- drei Behördenstellen mit unterschiedlichen Adress- und Servicekonfigurationen,
- Benutzer aller fünf Rollen,
- elf Tickets mit verschiedenen Citizens, Offices und verantwortlichen Mitarbeitenden,
- unterschiedliche Ticketzustände und unterschiedlich lange Eventhistorien,
- Weiterleitungen, Mitzeichnungen, Eskalationen, Bürger-Rückfragen und Abschlüsse,
- Ticketadressen, Kommentare und Bilder,
- sechs öffentliche Info-Einträge mit allen Kategorien und mehreren Statuswerten,
- Info-Adressen, Statushistorien, Updates und Bilder,
- freie, inaktive, gebuchte, freigegebene und verbrauchte Termin-Slots,
- geplante, verschobene, stornierte, abgeschlossene und als No-Show markierte Termine,
- eine Verknüpfung zwischen Ticket und Termin,
- interne und bürgersichtbare PDFs einschließlich ersetzter Dokumentversionen.

Fachliche Zustände werden über dieselben Services, Policies und Event Stores erzeugt, die auch von der API verwendet werden. Dadurch bleiben Projektionen, Eventhistorien, Relationen und Media-Metadaten konsistent.

# Funktionsübersicht

## Authentifizierung und Benutzer

- Registrierung von Citizen-Accounts,
- Login mit Access- und Refresh-Token,
- Refresh-Token-Rotation,
- Logout einzelner oder aller Sessions,
- Passwort-Reset per Einmalcode (nur demo),
- Benutzerverwaltung und rollenabhängige Sichtbarkeit,
- Rollen `CITIZEN`, `DISPATCHER`, `OFFICER`, `MANAGER` und `ADMIN`.

## Offices und Adressen

- öffentliche Office-Liste und Detailansichten,
- administrative Erstellung, Änderung und Deaktivierung,
- strukturierte Öffnungszeiten und Serviceangebote,
- optionale Adressen mit Geo-Koordinaten,
- historische Snapshots für Office-Änderungen.

## Tickets

Tickets sind eventgesourct und besitzen zusätzlich eine aktuelle Projektion für schnelle Abfragen.

Unterstützt werden unter anderem:

- öffentliche oder private Bürgeranliegen,
- Adressen und Bilder,
- öffentliche und interne Kommentare,
- Dispatch an ein Office,
- Zuweisung und Wechsel eines Hauptbearbeiters,
- Weiterleitung an andere Mitarbeitende,
- Mitzeichnungsanforderungen,
- Eskalationen und Managemententscheidungen,
- Rückfragen an Citizens,
- Rückgabe an Dispatch,
- erfolgreicher Abschluss oder fachliche Ablehnung,
- öffentliche Statushistorie und interne Eventhistorie.

Der Weg zwischen Einreichung und Abschluss ist nicht auf eine feste Sequenz begrenzt. Beteiligte Mitarbeitende und Zwischenschritte können abhängig von Zustand, Rolle und fachlicher Entscheidung gewählt werden.

## Appointments

Appointments sind ebenfalls eventgesourct. Termin-Slots werden als normale Kapazitätsobjekte verwaltet.

Unterstützt werden:

- öffentliche verfügbare Slots,
- Verwaltung von Office-Slots,
- Buchung durch Citizens,
- Verschiebung, Stornierung, Abschluss und No-Show,
- optionale Verbindung zu einem Ticket,
- bürgersichtbare und interne Dokumente,
- unveränderliche PDF-Versionen mit aktueller Dokumentversion,
- Appointment-Eventhistorie.

## Infos

`Info` ist bewusst eine klassische CRUD-Entität:

- Erstellung,
- Listen- und Detailabfrage,
- Änderung derselben Datenbankzeile,
- physisches Löschen,
- Statushistorie,
- optionale Office-Zuordnung,
- optionale Adresse,
- Bilder und Coverbild.

Es gibt keine Inhaltsversionierung, kein Soft Delete und kein Event Sourcing für Info-Inhalte.

## Gemeinsame API-Eigenschaften

- serverseitige Pydantic-Validierung,
- fachliche Servicevalidierung,
- Datenbankconstraints,
- einheitliche JSON-Fehlerantworten,
- rollen- und objektbezogene Berechtigungen,
- Suche, Filterung, Sortierung und Pagination,
- OpenAPI-Dokumentation,
- transaktionssichere Dateiverwaltung.


# Datenbank und Seed vollständig zurücksetzen

> Achtung: Die folgenden Befehle löschen die lokale Datenbank und alle lokalen Seed-Medien vollständig.

Backend zuerst beenden. Danach:

```bash
docker compose down -v
rm -rf data

docker compose up -d db
docker compose exec db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

alembic upgrade head
python -m scripts.seed.run_seed
```

Anschließend das Backend erneut starten:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

# Qualitätssicherung und Tests

Der vollständige nicht-destruktive Prüflauf wird über folgendes Skript gestartet:

```bash
./scripts/verify_backend.sh
```

Das Skript führt aus:

- Python-Kompilierung,
- Ruff-Linting,
- den normalen Pytest-Lauf,
- Prüfung des Alembic-Heads,
- vollständige Offline-Erzeugung des Upgrade-SQL,
- vollständige Offline-Erzeugung des Downgrade-SQL.

Die PostgreSQL-spezifischen Integrationstests werden bewusst nur explizit aktiviert:

```bash
RUN_POSTGRES_TESTS=1 pytest -q
```

Diese Tests sind destruktiv und dürfen nur gegen eine entbehrliche Testdatenbank ausgeführt werden. Sie dürfen nicht gegen eine Entwicklungs-, Demo- oder Produktivdatenbank laufen.

# Typische Probleme

## Verbindung zu PostgreSQL wird abgelehnt

Prüfen:

```bash
docker compose ps
docker compose logs db
docker compose exec db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Bei lokal gestartetem Backend muss `POSTGRES_HOST=localhost` gesetzt sein.

## Port 5432 ist bereits belegt

Einen freien Host-Port in `.env` wählen, beispielsweise:

```dotenv
POSTGRES_PORT=5433
```

Danach den Container neu erstellen:

```bash
docker compose down
docker compose up -d db
```

## Tabellen fehlen

Migrationen ausführen:

```bash
alembic upgrade head
```

## Seed bricht wegen fehlendem Passwort ab

In `.env` setzen:

```dotenv
SEED_DEFAULT_PASSWORD="ChangeThisDemoPassword123!"
```

## Seed bricht wegen `production` ab

Demo-Seeding ist in Produktion absichtlich gesperrt. Für lokale Demo-Daten muss gelten:

```dotenv
ENVIRONMENT="development"
```

## Bilder oder PDFs werden nicht gefunden

- Backend aus dem Projektstamm starten.
- Media-Pfade in `.env` prüfen.
- Schreibrechte auf den `data/`-Verzeichnissen prüfen.
- Datenbank und Dateiverzeichnisse immer gemeinsam sichern oder zurücksetzen.

# Bezug zu den Modulanforderungen

Die detaillierte Zuordnung befindet sich in:

```text
docs/module_requirements.md
```

Dort werden insbesondere nachgewiesen:

- Ad-hoc-Workflow im Ticketbereich,
- Event Sourcing für Tickets und Appointments,
- vollständiges CRUD für Infos,
- serverseitige Validierung und Fehlerausgabe,
- Benutzerverwaltung mit unterschiedlichen Rollen,
- SQLAlchemy ORM,
- Alembic-Migrationen,
- einheitliches, idempotentes Seeding.
