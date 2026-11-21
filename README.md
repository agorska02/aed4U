 Sprawdź AEDres – zbieranie danych o defibrylatorach

Akcja **„Sprawdź AEDres”** 
Twoje zgłoszenie może przywrócić komuś puls
Udostępnij. Uratuj.

Prototyp mechanizmu, który zbiera w portalu
dane.gov.pl dane o defibrylatorach AED od wszystkich dysponentów w **jednym, jednolitym zbiorze**:

- **wzorcowy zakres danych** – [`schema/`](schema/README.md): Table Schema, słowniki, szablon CSV;
- **dostawcy danych** (edytorzy instytucji) zgłaszają urządzenia przez podstronę
  „Zgłoś dostępność urządzenia AED”, formularz jest generowany ze schematu; dysponent (nazwa, REGON) i kontakt
  publiczny pochodzą zawsze z profilu instytucji w portalu, a telefon do osoby odpowiedzialnej za AED widzi
  tylko administrator;
- dysponenci z własnym rejestrem **importują plik** CSV/JSON/GeoJSON – z podglądem błędów; urządzenie
  identyfikuje **producent (słownik) + numer seryjny**: to samo urządzenie tej instytucji jest **aktualizowane**,
  a zgłoszone już przez inną instytucję – **odrzucane** (jedno urządzenie nie może być w dwóch miejscach);
  urządzenia blisko siebie (15 m) są oznaczane jako **możliwe duplikaty**;
- **administrator portalu** weryfikuje zgłoszenia i duplikaty, a zweryfikowane rekordy tworzą
  **jeden publiczny zbiór** (`GET /aed-devices?format=csv|json|geojson`) gotowy do dane.gov.pl;
- **służby ratunkowe i każdy z nas** korzystają z publicznej **mapy z listą** (`mapa.html`): „dostępne teraz”
  (z godzin w składni OSM), najbliższe urządzenia (geolokalizacja na żądanie), trasa, pobranie danych.

> Etapy: ✅ 1. zakres danych · ✅ 2. model, walidacja, formularz · ✅ 3. import z wielu źródeł,
> deduplikacja, eksport CSV/JSON/GeoJSON · ✅ 4. widok publiczny z mapą · ⏳ 5. logotyp i księga znaku.

Ten katalog zawiera **wyłącznie dodatki** – kod portalu nie jest jego częścią. Prototyp działa
**samodzielnie** (dwa tryby demo), a moduł `backend/aed/` jest gotowym wzorem wdrożenia do portalu.

## Uruchomienie demo

| Tryb | Jak uruchomić | Dane | Wymaga |
|---|---|---|---|
| **Demo w przeglądarce** | otwórz `frontend/mapa.html` (widok publiczny) lub `frontend/index.html` (dostawca) albo opublikuj katalog `frontend/` na dowolnym hostingu statycznym (np. GitHub Pages) | atrapa API (`api-mock.js`), dane w `localStorage` tej przeglądarki | nic |
| **Demo z serwerem** | `python standalone/server.py` → http://127.0.0.1:8090 | baza SQLite (`standalone/`) | Python 3.8+ (bez pakietów) |
| **Demo z PostgreSQL** | `docker compose -f standalone/docker-compose.yml up -d`, potem `python standalone/server.py --db postgresql://aed:aed@127.0.0.1:5433/aed_demo` | PostgreSQL 16 w kontenerze | Docker + `psycopg2` |
| **Portal** (wzór wdrożenia) | patrz [Uruchomienie w portalu](#uruchomienie-w-portalu) | PostgreSQL portalu | repozytorium `mcod` + Docker |

Mapa i wybór punktu w formularzu ładują Leaflet z cdnjs (z SRI) i kafelki OpenStreetMap – wymagają
internetu. Bez niego mapa się nie pokazuje, a lista urządzeń i cała reszta działa dalej.

Konta demo: `dostawca@demo.local` / `Demo123!` (instytucja A), `dostawca2@demo.local` / `Demo123!`
(instytucja B), `admin@demo.local` / `Admin123!` (administrator). Scenariusz pokazu:

0. Otwórz **Mapa AED** (`mapa.html`) bez logowania: lista + mapa zweryfikowanych urządzeń, filtry
   „dostępne teraz”, „24/7”, „dla dzieci”, „Pokaż najbliższe”; na telefonie przełącznik Lista/Mapa.
1. Zaloguj się jako **dostawca A** na `index.html`, wyślij zgłoszenie (położenie możesz wskazać na mapie)
   – status *Przesłane do weryfikacji*.
2. W sekcji **Import** pobierz „plik do pokazu z błędami” i sprawdź go – raport wskazuje wiersz, kolumnę
   i błąd (m.in. brak nazwy „innego producenta” i urządzenie, które ma już instytucja B), nic nie jest
   zapisywane. Potem sprawdź „poprawny” plik: 1 aktualizacja (ten sam producent i numer seryjny co urządzenie
   instytucji A – dłuższe godziny), 2 nowe urządzenia, w tym 1 możliwy duplikat (inne urządzenie w tym samym
   miejscu co urządzenie instytucji B) → **Importuj**.
3. Przejdź do **Weryfikacja (admin)** (`admin.html`), zaloguj się jako **admin**: filtr „Tylko możliwe
   duplikaty”, zatwierdź lub odrzuć z komentarzem; na dole pobierz zbiór CSV/JSON/GeoJSON.
4. Wróć na `index.html` jako dostawca A – widać nowy status i komentarz.
5. Zaloguj się jako **dostawca B** – widać tylko zgłoszenia instytucji B.
6. Zatwierdzone przez admina urządzenia pojawiają się na **Mapie AED** i w pobieranym zbiorze.

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
| `schema/` | **Wzorcowy zakres danych**: `aed.schema.json` (Frictionless Table Schema), słowniki CSV, szablon i przykład CSV. Jedyne źródło reguł – czytają je walidatory, formularz i admin. |
| `backend/aed/` | Aplikacja Django `mcod.aed` w konwencjach portalu (wzór: `mcod/suggestions`): model `AedReport` (kolumny ze schematu, źródło, możliwy duplikat, obieg weryfikacji), migracja, `rules.py`, admin (sekcje ze schematu, filtr duplikatów), deserializer/serializer generowane ze schematu, widoki Falcon `GET`/`POST /aed-reports`, `POST /aed-report-imports`, `GET /aed-devices`; w czystym Pythonie (bez Django): **`validation.py`** – walidator schematu, **`importing.py`** – parsowanie plików, plan importu, duplikaty, eksport; testy. |
| `frontend/` | Podstrona (HTML + CSS + JS, bez zależności): `index.html` – dostawca (formularz generowany ze schematu, zgłoszenia instytucji ze statusem i szczegółami); `admin.html` – weryfikacja (w trybach demo); `aed-validator.js` / `aed-import.js` – te same reguły co `validation.py` / `importing.py`; `provider-import.js` – import pliku; `location-picker.js` – wybór punktu na mapie; `mapa.html` + `map.js` – widok publiczny (mapa i lista); `aed-hours.js` – „dostępne teraz” z `opening_hours`; `demo/` – pliki do pokazu importu; `aed-schema.js` – schemat dla przeglądarki (generowany); `config.js` – wybór trybu; `api-mock.js` – atrapa API. |
| `tests/` | Testy walidatorów i importu – wspólne przypadki `validation_cases.json` i `import_cases.json` uruchamiane dla Pythona i JS (JS w headless Chrome/Edge), godzin dostępności (`opening_hours_cases.json`) oraz spójności plików schematu i eksportu. |
| `tools/` | `build_frontend_schema.py` – generuje `frontend/aed-schema.js` po zmianie schematu. |
| `standalone/` | Serwer demo: biblioteka standardowa Pythona + SQLite albo PostgreSQL (`db.py`, `schema.sql` / `schema.postgres.sql`, `docker-compose.yml`), to samo API co moduł portalu; testy na obu bazach. Szczegóły: [standalone/README.md](standalone/README.md). |
| `integration/` | Podłączenie do portalu: `portal.patch` (`INSTALLED_APPS`, trasy API, pozycja w menu panelu), `docker-compose.hackathon.yml` (wolumeny + serwer podstrony), `config.portal.js` (tryb portal). Szczegóły: [integration/README.md](integration/README.md). |

## Architektura

```
przeglądarka ──► aed-frontend (nginx, :8090)
                   ├── /        → frontend/ (statyczne pliki)
                   └── /api/*   → mcod-local-api:8000 (Falcon)
                                     ├── POST /auth/login  → JWT (konto portalu)
                                     ├── GET|POST /aed-reports → mcod.aed → PostgreSQL (aed_aedreport)
                                     ├── POST /aed-report-imports  (plik dysponenta: podgląd / import)
                                     └── GET /aed-devices?format=…  (publiczny zbiór, bez logowania)
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
| Daty ISO 8601 (`yyyy-mm-dd`) | Std. techniczny 3 | typ `date` w schemacie, `DateField`, `<input type="date">` | ✅ |
| „Dane na dzień” – wskazanie aktualności danych | Przewodnik 5.2.5, Std. bezpieczeństwa 5, Std. prawny 3.3 | `data_date` (wymagane, domyślnie dziś) | ✅ |
| Obieg szkic / weryfikacja, rozliczalność zmian | Przewodnik 4.1.11, 5.2.6 | `status`, `verified_by/at`, `created_by/modified_by` | ✅ |
| Sanityzacja treści od użytkowników | konwencja repo | `SanitizedCharField` / `SanitizedTextField` | ✅ |
| Dostępność cyfrowa (WCAG 2.2) | Przewodnik 14 | etykiety i podpowiedzi powiązane z polami, podsumowanie błędów z linkami do pól, `aria-invalid`, `autocomplete` (1.3.5), pola Tak/Nie jako `fieldset`, cele ≥ 24 px (2.5.8), focus, skip link, kontrast, `lang="pl"`; mapa ma równoważną listę tekstową, wynik filtrowania ogłaszany (`role="status"`), geolokalizacja tylko na żądanie, punkt na mapie wybieralny też klawiaturą („Użyj środka mapy”) lub przez wpisanie współrzędnych; układ bez przewijania w poziomie przy 320–390 px (1.4.10) | ✅ (pełny audyt w etapie 5) |
| Adres w odrębnych polach | Std. techniczny 3.2 | `voivodeship`/`county`/`commune`/`city`/`street_type`/`street`/`street_number`/`postal_code`, słowniki województw i rodzajów ulic | ✅ (kody TERYT świadomie pominięte – zbiór nie korzysta z rejestru TERYT) |
| Współrzędne WGS84, pola liczbowe, kropka dziesiętna (wizualizacja na mapie) | Przewodnik 10, Std. techniczny 3 | `latitude`/`longitude` (`DecimalField`, 6 miejsc, zakres Polski) | ✅ |
| Granularność – bez łączenia kilku danych w jednym polu | Std. techniczny 3 | adres, położenie, dostępność, urządzenie, kontakt w osobnych polach; godziny w składni OSM `opening_hours` | ✅ |
| Telefon: 9 cyfr | Std. techniczny 3 | wzorzec `^[0-9]{9}$` | ✅ |
| Minimalizacja danych osobowych | Przewodnik 15, Std. bezpieczeństwa | tylko kontakt instytucjonalny, bez kodów do szafek; opisy pól to przypominają | ✅ |
| Publikacja jako zbiór w formatach czytelnych maszynowo | Std. techniczny 4–5 | `GET /aed-devices`: CSV (RFC 4180, UTF-8, `\r\n`), JSON, GeoJSON (WGS84); tylko rekordy zweryfikowane; „dane na dzień” w `meta`/`metadata` | ✅ (licencja i harmonogram aktualizacji – przy zakładaniu zbioru w portalu) |
| Wiele źródeł w jednym zbiorze, wskazanie źródła | wyzwanie | import plików + formularz + API (`source`), dysponent i REGON z profilu instytucji, jedno urządzenie = jeden rekord (producent ze słownika + numer seryjny): aktualizacja zamiast duplikatu, odrzucenie urządzenia innej instytucji, ostrzeżenie o urządzeniach blisko siebie | ✅ |
| Tłumaczenie EN metadanych | Przewodnik 4.2, 5.3 | – | ⏳ poza szkieletem |

### Zakres danych

Pełny opis pól, uzasadnienie i mapowanie na OpenStreetMap: [schema/README.md](schema/README.md).

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
dc run --rm mcod-local-tests -n1 --no-cov mcod/aed/tests/test_admin.py mcod/aed/tests/test_schema.py
```

Testy prototypu (bez portalu, Python 3.8+):

```sh
python -m unittest discover -s tests        # walidatory Python + JS (JS: headless Chrome/Edge), pliki schematu
python -m unittest discover -s standalone   # API serwera demo
python tools/build_frontend_schema.py       # po każdej zmianie schema/aed.schema.json lub aed-example.csv
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
- Aktualizacja zweryfikowanego rekordu importem wraca do weryfikacji i do tego czasu znika z publicznego
  zbioru. Docelowo warto publikować ostatnią zweryfikowaną wersję aż do ponownej weryfikacji.
- Wykrywanie duplikatów porównuje każdy rekord ze wszystkimi (O(n²)) – wystarcza do kilkudziesięciu tysięcy
  urządzeń; przy większej skali indeks przestrzenny (PostGIS / Elasticsearch `geo_distance`, jak w portalu).
- Eksport w portalu jest endpointem; docelowo pliki zasobów generowałoby cyklicznie zadanie Celery.
- **Moduł portalu (`backend/aed`) nie ma jeszcze** reguły „dysponent i kontakt z profilu instytucji” ani pola
  `internal_contact_phone`, a wciąż ma usunięte z zakresu pole `source_id` (demo: `standalone/`, `frontend/` jest
  aktualne), ma też usunięte z zakresu kody TERYT (`teryt_terc`, `teryt_simc`), nie ma słownika producentów,
  `manufacturer_other`, `serial_number` ani unikalności urządzenia – do dopisania przy integracji: kolumny w modelu i migracji, wypełnianie z `Organization` (`title`, `regon`, `tel`, `email`), ukrycie pola przed
  edytorami w API i eksporcie, endpoint z profilem instytucji dla formularza.
- Wygląd odwzorowuje styl portalu (kolory, układ, typografia) bez oficjalnych logotypów.

## Uwaga do kodu portalu (poza zakresem modułu)

`mcod/core/api/middleware_loader.py`: stała `FALCON_CSRF_MIDDLEWARE` wskazuje na
`ContentTypeMiddleware` zamiast `CsrfMiddleware`, więc ochrona CSRF w API nie jest ładowana mimo
`ENABLE_CSRF = True`. Uwierzytelnianie nagłówkiem `Authorization` jest na CSRF odporne, ale warto to
zgłosić opiekunom portalu.
