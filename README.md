# Zgłoś dostępność urządzenia AED – prototyp (HackNation)

Prototyp podstrony portalu otwartych danych (backend `mcod`): **dostawcy danych** (edytorzy instytucji)
zgłaszają lokalizację i dostępność automatycznych defibrylatorów zewnętrznych (AED), a **administrator
portalu** weryfikuje zgłoszenia w Panelu Administratora.

> Status: **szkielet**. Formularz ma pola tymczasowe (`location_name`, `notes`, `data_date`);
> docelowe pola AED i kolumny w bazie zostaną dodane w kolejnym kroku – patrz
> [Wymagania dla docelowych pól](#wymagania-dla-docelowych-pól).

Ten katalog zawiera **wyłącznie dodatki** – kod portalu nie jest jego częścią. Prototyp działa
**samodzielnie** (dwa tryby demo), a moduł `backend/aed/` jest gotowym wzorem wdrożenia do portalu.

## Uruchomienie demo

| Tryb | Jak uruchomić | Dane | Wymaga |
|---|---|---|---|
| **Demo w przeglądarce** | otwórz `frontend/index.html` albo opublikuj katalog `frontend/` na dowolnym hostingu statycznym (np. GitHub Pages) | atrapa API (`api-mock.js`), dane w `localStorage` tej przeglądarki | nic |
| **Demo z serwerem** | `python standalone/server.py` → http://127.0.0.1:8090 | baza SQLite (`standalone/`) | Python 3.8+ (bez pakietów) |
| **Portal** (wzór wdrożenia) | patrz [Uruchomienie w portalu](#uruchomienie-w-portalu) | PostgreSQL portalu | repozytorium `mcod` + Docker |

Konta demo: `dostawca@demo.local` / `Demo123!` (instytucja A), `dostawca2@demo.local` / `Demo123!`
(instytucja B), `admin@demo.local` / `Admin123!` (administrator). Scenariusz pokazu:

1. Zaloguj się jako **dostawca A** na `index.html`, wyślij zgłoszenie – status *Przesłane do weryfikacji*.
2. Przejdź do **Weryfikacja (admin)** (`admin.html`), zaloguj się jako **admin**, zatwierdź lub odrzuć z komentarzem.
3. Wróć na `index.html` jako dostawca A – widać nowy status i komentarz.
4. Zaloguj się jako **dostawca B** – widać tylko zgłoszenia instytucji B.

Tryb wybiera `frontend/config.js` (`mode: "mock"` domyślnie). Serwer demo podaje własny `config.js`
(`mode: "api"`), a w portalu `integration/config.portal.js` podmienia go przez wolumen – frontend we
wszystkich trybach woła to samo API (`/auth/login`, `/aed-reports`, JSON:API).

## Role i obieg zgłoszenia

Zgodnie z *Przewodnikiem dla dostawców danych* (v1.23, rozdz. 3–5) dostawca to zalogowany
**edytor** (`User.is_staff`) przypisany do **instytucji** (`User.organizations`).

```
dostawca (edytor)                          administrator (superuser)
─────────────────                          ─────────────────────────
podstrona :8090  ── POST /aed-reports ──►  [Przesłane do weryfikacji]
  lub panel :8001  (szkic → „Prześlij”)            │
                                     Panel Administratora: akcje
                                     „Zweryfikuj” / „Odrzuć” + komentarz
                                                   │
          ◄── status i komentarz widoczne ─────────┘
          [Zweryfikowane]  albo  [Odrzucone] → dostawca poprawia i przesyła ponownie
```

| | Dostawca (edytor) | Administrator |
|---|---|---|
| Widzi | zgłoszenia **swojej** instytucji | wszystkie zgłoszenia, filtr po instytucji |
| Tworzy / edytuje | tak; edycja tylko w statusie *Szkic* / *Odrzucone* | tak |
| Pola weryfikacji (status, komentarz) | tylko odczyt | edycja; kto i kiedy – zapisywane automatycznie |
| Usuwa | tylko *Szkic* | tak |

Uprawnienia: `backend/aed/rules.py` (`django-rules`, jak `datasets/rules.py`) + ograniczenia wierszy
w `backend/aed/admin.py`. API wymaga roli `editor` lub `admin` (`login_required`).

## Struktura

| Katalog | Zawartość |
|---|---|
| `backend/aed/` | Aplikacja Django `mcod.aed` w konwencjach portalu (wzór: `mcod/suggestions`): model `AedReport` z obiegiem weryfikacji, migracja, `rules.py`, admin, deserializer/serializer (marshmallow, JSON:API), widok Falcon `GET`/`POST /aed-reports`, testy API i admina. |
| `frontend/` | Podstrona (HTML + CSS + JS, bez zależności): `index.html` – dostawca (logowanie, formularz, zgłoszenia instytucji ze statusem); `admin.html` – weryfikacja (w trybach demo); `config.js` – wybór trybu; `api-mock.js` – atrapa API. |
| `standalone/` | Serwer demo: biblioteka standardowa Pythona + SQLite, to samo API co moduł portalu; testy. Szczegóły: [standalone/README.md](standalone/README.md). |
| `integration/` | Podłączenie do portalu: `portal.patch` (`INSTALLED_APPS`, trasy API, pozycja w menu panelu), `docker-compose.hackathon.yml` (wolumeny + serwer podstrony), `config.portal.js` (tryb portal). Szczegóły: [integration/README.md](integration/README.md). |

## Architektura

```
przeglądarka ──► aed-frontend (nginx, :8090)
                   ├── /        → frontend/ (statyczne pliki)
                   └── /api/*   → mcod-local-api:8000 (Falcon)
                                     ├── POST /auth/login  → JWT (konto portalu)
                                     └── GET|POST /aed-reports → mcod.aed → PostgreSQL (aed_aedreport)
Panel Administratora (:8001) → „Zgłoszenia AED”: /aed/aedreport/
```

- Uwierzytelnianie jak w portalu: JWT z `/auth/login` w nagłówku `Authorization: Bearer …`.
- Podstrona i API mają wspólny origin (proxy w nginx), więc nie potrzeba CORS.

## Zgodność ze standardami otwartości danych

Sprawdzone z: [Standardy otwartości danych](https://dane.gov.pl/pl/knowledgebase/useful-materials/standardy-otwartosci-danych)
(API, techniczny, bezpieczeństwa, prawny – wersje 2020),
[Przewodnik dla dostawców danych](https://dane.gov.pl/pl/knowledgebase/useful-materials/nowy-przewodnik-dla-dostawcow-danych) v1.23,
[Podręczniki](https://dane.gov.pl/pl/knowledgebase/useful-materials/podreczniki-dot-otwartosci-danych) (opis procesów organizacyjnych – bez wymagań dla kodu).

| Wymóg | Źródło | Realizacja | Stan |
|---|---|---|---|
| Dostawca = zalogowany edytor instytucji, praca w Panelu Administratora | Przewodnik 3–5 | `login_required(roles=["editor","admin"])`, `rules.py`, `organization` FK, filtr po instytucji | ✅ |
| Format JSON zgodny ze standardem JSON API | Std. techniczny 5.1, Std. API 6 | `mcod.core.api.jsonapi`, `application/vnd.api+json` | ✅ |
| Nazwy zasobów: rzeczownik l. mn., małe litery, łączniki, bez polskich znaków | Std. API 3 | `/aed-reports` | ✅ |
| Wersja w URL | Std. API 9 | trasa dodana przed prefiksem `/{api_version}` (np. `/1.4/aed-reports`) | ✅ |
| Kody HTTP 201/401/403/422, opis błędu w treści | Std. API 10 | standardowe handlery portalu, `source.pointer` dla pól | ✅ |
| Daty ISO 8601 (`yyyy-mm-dd`) | Std. techniczny 3 | `DateField`/`DateTimeField`, `<input type="date">` | ✅ |
| „Dane na dzień” – wskazanie aktualności danych | Przewodnik 5.2.5, Std. bezpieczeństwa 5, Std. prawny 3.3 | `data_date` (domyślnie dziś) | ✅ |
| Obieg szkic / weryfikacja, rozliczalność zmian | Przewodnik 4.1.11, 5.2.6 | `status`, `verified_by/at`, `created_by/modified_by` | ✅ |
| Sanityzacja treści od użytkowników | konwencja repo | `SanitizedCharField` / `SanitizedTextField` | ✅ |
| Dostępność cyfrowa (WCAG) | Przewodnik 14 | etykiety, `aria-live`, `aria-invalid`, focus, skip link, kontrast, `lang="pl"` | ✅ podstawy |
| Adres w odrębnych polach; zalecany adres uniwersalny (TERYT), wybór ze słownika | Std. techniczny 3.2 | – | ⏳ docelowe pola |
| Współrzędne WGS84, pola liczbowe, kropka dziesiętna (wizualizacja na mapie) | Przewodnik 10, Std. techniczny 3 | – | ⏳ docelowe pola |
| Granularność – bez łączenia kilku danych w jednym polu | Std. techniczny 3 | `notes` tylko na uwagi | ⏳ docelowe pola |
| Minimalizacja danych osobowych | Przewodnik 15, Std. bezpieczeństwa | brak danych osobowych w polach zgłoszenia | ✅ (pilnować przy nowych polach) |
| Publikacja jako zbiór: CSV RFC 4180 / JSON-LD, licencja, aktualizacja | Std. techniczny 4–5, Std. prawny | – | ⏳ poza szkieletem |
| Tłumaczenie EN metadanych | Przewodnik 4.2, 5.3 | – | ⏳ poza szkieletem |

### Wymagania dla docelowych pól

- **Adres** (wymóg): osobne pola – nazwy jak w `Organization`: `postal_code` (PNA), `city`, `street_type`
  (cecha), `street`, `street_number`, `flat_number`; opcjonalnie `universal_address`
  (adres uniwersalny, format `PNA|TERC|SIMC|SIMC|ULIC|x|y|nr|`). Najlepiej wybór ze słownika TERYT.
- **Lokalizacja**: `latitude`, `longitude` jako `DecimalField` (WGS84); etykieta mapy = `location_name`.
- **Dostępność**: osobne pola, np. `is_available_24h` (`true`/`false`), godziny w formacie `hh:mm`;
  nie w polu tekstowym.
- **Telefon** (jeśli potrzebny): 9 cyfr bez spacji; tylko kontakt instytucjonalny, bez imion i nazwisk.
- Walidację formatów można oprzeć na regułach portalu (`mcod/lib/data_rules.py`: PNA, adres
  uniwersalny, cecha adresu, telefon).

## Uruchomienie w portalu

Z katalogu głównego portalu, przy działającym stacku (`/mcod-run`):

```sh
git apply hackathon/integration/portal.patch
docker compose -f docker-compose.local.yml -f hackathon/integration/docker-compose.hackathon.yml \
  run --rm mcod-local-run python manage.py migrate aed
docker compose -f docker-compose.local.yml -f hackathon/integration/docker-compose.hackathon.yml \
  up -d mcod-local-api mcod-local-admin aed-frontend
```

- Podstrona dla dostawców: http://localhost:8090 (konto edytora przypisanego do instytucji)
- Weryfikacja: http://localhost:8001/aed/aedreport/ (np. `admin@mcod.local`)

Testy (API – kontener `api`, admin – kontener domyślny):

```sh
alias dc='docker compose -f docker-compose.local.yml -f hackathon/integration/docker-compose.hackathon.yml'
dc run --rm mcod-local-tests-api -n1 --no-cov mcod/aed/tests/test_api.py
dc run --rm mcod-local-tests -n1 --no-cov mcod/aed/tests/test_admin.py
```

## Uproszczenia prototypu (TODO przed integracją z produkcją)

- Gdy edytor należy do kilku instytucji, API wymaga pola `organization` – podstrona nie ma jeszcze
  listy wyboru instytucji (pokazuje błąd z API).
- Etykiety (`verbose_name`, komunikaty) są po angielsku jak w reszcie kodu; tłumaczenia PL trzeba
  dopisać do `translations/system/pl/LC_MESSAGES/django.po` portalu.
- Migracja `0001_initial.py` napisana ręcznie – po podłączeniu sprawdzić `makemigrations --check`
  (robi to automatycznie entrypoint testów).
- Token sesji podstrony trzymany w `sessionStorage` (znika po zamknięciu karty).
- `admin.html` weryfikuje przez `PATCH /aed-reports/{id}` – rozszerzenie **tylko w trybach demo**
  (atrapa, serwer SQLite). Moduł portalu go nie ma: w portalu weryfikacja odbywa się w Panelu
  Administratora, a `admin.html` pokazuje tylko link do niego. Pole `roles` w odpowiedzi logowania też
  występuje tylko w demo.
- W trybach demo dostawca nie edytuje wysłanych zgłoszeń (w portalu: Panel Administratora).
- Wygląd odwzorowuje styl portalu (kolory, układ, typografia) bez oficjalnych logotypów.

## Uwaga do kodu portalu (poza zakresem modułu)

`mcod/core/api/middleware_loader.py`: stała `FALCON_CSRF_MIDDLEWARE` wskazuje na
`ContentTypeMiddleware` zamiast `CsrfMiddleware`, więc ochrona CSRF w API nie jest ładowana mimo
`ENABLE_CSRF = True`. Uwierzytelnianie nagłówkiem `Authorization` jest na CSRF odporne, ale warto to
zgłosić opiekunom portalu.
