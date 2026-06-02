# mail-client

Henter mails fra Microsoft Graph API ind i en MSSQL-database og gemmer vedhæftninger på disk. Eksponerer et HTTP API, som andre services kan bruge til at søge i mails, downloade vedhæftninger og sende nye mails.

## Arkitektur

To uafhængige processer deler en MSSQL-database og to volumes:

- **Worker** — poller Graph API efter en tidsplan, henter mails og vedhæftninger, sletter gamle
- **API** — FastAPI-service med endpoints til læsning af mails, download af vedhæftninger og afsendelse af mails

## Udvikling

Krav: Python 3.13, ODBC Driver 18 for SQL Server

Kopiér `.env.example` til `.env` og udfyld dine værdier:

```bash
cp .env.example .env
```

Start services:

```bash
cd src
python worker.py
uvicorn api:app --reload --port 8000
```

## Miljøvariabler

| Variabel | Påkrævet | Standard | Beskrivelse |
|---|---|---|---|
| `TENANT_ID` | ja | | Azure AD tenant-ID |
| `CLIENT_ID` | ja | | App registration-klient-ID |
| `CLIENT_SECRET` | ja | | App registration-klienthemmelighed |
| `USER_ID` | ja | | Mailbox-bruger-ID eller UPN der hentes fra |
| `MSSQL_SERVER` | ja | | Serverens hostnavn, f.eks. `localhost,1433` |
| `MSSQL_DATABASE` | ja | | Databasenavn |
| `MSSQL_USERNAME` | nej | | SQL-auth-brugernavn (udelad for trusted auth) |
| `MSSQL_PASSWORD` | nej | | SQL-auth-adgangskode (udelad for trusted auth) |
| `MSSQL_DRIVER` | nej | `ODBC Driver 18 for SQL Server` | ODBC-drivernavn |
| `FETCH_INTERVAL_SECONDS` | nej | `300` | Hvor ofte workeren poller Graph API |
| `RETENTION_DAYS` | nej | `30` | Hvor længe mails gemmes inden sletning |
| `API_KEY` | ja | | Nøgle der kræves i API-anmodningers header `X-API-Key` |

## Sletning

Worker'en kører én gang per cyklus og sletter automatisk data, der er ældre end `RETENTION_DAYS` dage regnet fra kørselsøjeblikket:

- Vedhæftningsfiler på `mail-client-internal-attachments` slettes fra disk
- Databaseposten slettes
- Mailen slettes fra Graph API (fejl logges, men stopper ikke øvrig oprydning)
- Evt. filer på `mail-client-external-attachments` slettes fra disk

## API

Alle endpoints kræver headeren `X-API-Key: <API_KEY>`.

### `GET /emails`

Returnerer hentede mails, nyeste først.

| Parameter | Type | Beskrivelse |
|---|---|---|
| `since` | ISO-dato/tid | Returner kun mails modtaget efter dette tidspunkt |
| `sender` | streng | Filtrer på nøjagtig afsenderadresse |
| `subject` | streng | Filtrer på emne (søger case-insensitivt på delstreng) |

**Svar**

```json
[
  {
    "id": "...",
    "sender": "afsender@example.com",
    "subject": "Emne",
    "body": "Beskedtekst...",
    "received_at": "2024-01-15T08:30:00",
    "attachments": [
      {
        "id": "uuid",
        "filename": "rapport.pdf",
        "content_type": "application/pdf",
        "size_bytes": 12345,
        "download_url": "/attachments/uuid/download"
      }
    ]
  }
]
```

**Eksempel**

```python
resp = requests.get("http://api:8000/emails",
    headers={"X-API-Key": "..."},
    params={"sender": "afsender@example.com", "subject": "faktura"})
mails = resp.json()
```

### `GET /attachments/{id}/download`

Downloader én vedhæftning via dens UUID. Returnerer filen med det originale filnavn og content type.

Returnerer `404` hvis UUID ikke eksisterer eller filen mangler på disk.

**Eksempel**

```python
resp = requests.get("http://api:8000/attachments/uuid/download",
    headers={"X-API-Key": "..."})
with open("rapport.pdf", "wb") as f:
    f.write(resp.content)
```

### `POST /send`

Sender en mail via Microsoft Graph. Accepterer et JSON-objekt.

| Felt | Type | Påkrævet | Beskrivelse |
|---|---|---|---|
| `to` | streng eller liste | ja | Modtageradresse(r) |
| `subject` | streng | ja | Emne |
| `body` | streng | ja | Beskedtekst (plain text) |
| `files` | liste af strenge | nej | Absolutte stier til filer på det delte volume |

Filstierne skal være tilgængelige fra API-containeren. Montér et delt volume mellem det kaldende script og API-containeren, og placér filerne der inden kaldet.

**Eksempel — uden vedhæftninger**

```python
requests.post("http://api:8000/send",
    headers={"X-API-Key": "..."},
    json={"to": "modtager@example.com", "subject": "Hej", "body": "Besked"}).raise_for_status()
```

**Eksempel — én vedhæftning**

```python
requests.post("http://api:8000/send",
    headers={"X-API-Key": "..."},
    json={
        "to": "modtager@example.com",
        "subject": "Rapport",
        "body": "Se vedhæftede fil.",
        "files": ["/shared/rapport.pdf"]}).raise_for_status()
```

**Eksempel — flere vedhæftninger og flere modtagere**

```python
requests.post("http://api:8000/send",
    headers={"X-API-Key": "..."},
    json={
        "to": ["person1@example.com", "person2@example.com"],
        "subject": "Månedlig rapport",
        "body": "Se vedhæftede filer.",
        "files": ["/shared/rapport.pdf", "/shared/data.xlsx"]}).raise_for_status()
```

## Arbejdsgang

### Download og videresend en vedhæftning

Skal en fil både behandles og sendes videre, skrives den til `mail-client-external-attachments` (`/shared`), så API-containeren har adgang til den via `POST /send`:

1. Download vedhæftningen til `/shared` — filen gemmes med det originale filnavn
2. Brug stien i `POST /send`

```python
# Trin 1 — download til /shared
resp = requests.get("http://api:8000/attachments/uuid/download",
    headers={"X-API-Key": "..."})
with open("/shared/rapport.xlsx", "wb") as f:
    f.write(resp.content)

# Trin 2 — send videre
requests.post("http://api:8000/send",
    headers={"X-API-Key": "..."},
    json={
        "to": "modtager@example.com",
        "subject": "Rapport",
        "body": "Se vedhæftede fil.",
        "files": ["/shared/rapport.xlsx"]})
```

Skal filen kun downloades til videre behandling uden at sendes videre, skrives den til et valgfrit volume eller lokal sti.

## Udrulning

Repoet indeholder `docker-compose.yaml` til lokal udvikling og Portainer-udrulning.

- **Lokalt** — `docker compose up --build`. Bruger `.env` og bygger billedet fra kildekode.
- **Portainer** — skift `build: .` ud med `image: ghcr.io/hjk-automatisering/mail-client:main` og brug `stack.env` i stedet for `.env`.

Opret følgende volumes manuelt i Portainer inden udrulning:

| Volume | Indhold |
|---|---|
| `mail-client-internal-attachments` | Indgående vedhæftninger fra postkassen |
| `mail-client-external-attachments` | Udgående filer til `POST /send` (monteres på `/shared`) |

Scripts der skal sende filer via `POST /send` skal montere `mail-client-external-attachments` og placere filer i `/shared`.
