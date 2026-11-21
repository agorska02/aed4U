# Podłączenie modułu AED do portalu

Wszystkie polecenia uruchamiaj z **katalogu głównego portalu** (tam, gdzie `docker-compose.local.yml`).

## 1. Zmiany w kodzie portalu (9 linii)

`portal.patch` dodaje:

- `mcod/settings/base.py` – `"mcod.aed"` w `INSTALLED_APPS` (po `"mcod.suggestions"`) oraz pozycję
  „AED availability reports” w menu Panelu Administratora (`SUIT_CONFIG["MENU"]`, przed „Konfiguracja”),
- `mcod/routes.py` – import `aed_routes` i `routes.extend(aed_routes)` **przed** linią dodającą
  prefiks `/{api_version}`, dzięki czemu endpointy (`/aed-reports`, `/aed-report-imports`, `/aed-devices`)
  działają też z wersją, np. `/1.4/aed-reports`. Nowe trasy modułu nie wymagają zmian w patchu.

Uprawnienia edytorów (`backend/aed/rules.py`) ładują się automatycznie przez
`rules.apps.AutodiscoverRulesConfig` – bez zmian w portalu.

```sh
git apply --check hackathon/integration/portal.patch   # sprawdzenie na sucho
git apply hackathon/integration/portal.patch           # nałożenie
git apply -R hackathon/integration/portal.patch        # wycofanie
```

Bez gita można dopisać te linie ręcznie – patch jest czytelny.

## 2. Kod modułu w kontenerach

`docker-compose.hackathon.yml` montuje `hackathon/backend/aed` jako `mcod/aed` oraz
`hackathon/schema` (wzorcowy zakres danych, z którego korzysta `mcod.aed.validation`) jako
`mcod/aed/schema` we wszystkich kontenerach z kodem (admin, api, cms, celery, run, tests*), więc
w drzewie portalu nie trzeba nic kopiować. Zawsze podawaj oba pliki:

```sh
alias dc='docker compose -f docker-compose.local.yml -f hackathon/integration/docker-compose.hackathon.yml'
dc run --rm mcod-local-run python manage.py migrate aed
dc up -d mcod-local-api mcod-local-admin aed-frontend
```

Uwaga: Docker może utworzyć na hoście puste katalogi `mcod/aed` i `hackathon/backend/aed/schema`
jako punkty montowania – można je zignorować (nie commitować).

Przy wdrożeniu na stałe: skopiuj `hackathon/schema/aed.schema.json` do `mcod/aed/schema/` albo ustaw
zmienną `AED_SCHEMA_PATH`.

## 3. Podstrona

`aed-frontend` (nginx) serwuje `hackathon/frontend` na http://localhost:8090 (oraz `hackathon/schema`
pod `/schema/` – szablony do pobrania) i przekazuje `/api/*` do `mcod-local-api:8000`. Zmiany w HTML/CSS/JS widać po odświeżeniu strony.

Zamiast `frontend/config.js` (tryb demo z atrapą API) podmontowany jest `config.portal.js`
(`mode: "api"`, `demo: false`), więc podstrona loguje kontem portalu i zapisuje do jego bazy.
Weryfikacja zgłoszeń: Panel Administratora → „AED availability reports”.
