# Serwer demo (SQLite albo PostgreSQL)

Samodzielny serwer prototypu – bez kodu portalu. Serwuje podstronę z `../frontend` oraz API zgodne
z modułem portalu (`../backend/aed`) i zapisuje dane w prawdziwej bazie:

- **SQLite** (domyślnie) – **tylko biblioteka standardowa Pythona** (3.8+), bez instalowania czegokolwiek;
- **PostgreSQL** – kontener z `docker-compose.yml` (albo dowolny serwer PostgreSQL), sterownik `psycopg2`.

Ten sam kod SQL działa na obu bazach dzięki adapterowi `db.py`; schematy: `schema.sql` (SQLite) i
`schema.postgres.sql` (PostgreSQL – natywne typy `uuid`, `boolean`, `numeric(8,6)`, `date`,
`timestamptz`, jak w migracji modułu portalu). Trzymaj oba pliki w zgodzie.

```sh
python standalone/server.py            # http://127.0.0.1:8090
python standalone/server.py --reset    # od nowa: usuwa bazę i wczytuje dane demo
python standalone/server.py --port 9000 --db /tmp/aed.sqlite3
python -m unittest discover -s standalone   # testy (28 na SQLite; 28 kolejnych na PostgreSQL – patrz niżej)
```

### PostgreSQL

```sh
pip install psycopg2-binary                              # jeśli nie masz sterownika
docker compose -f standalone/docker-compose.yml up -d    # postgres:16 na 127.0.0.1:5433 (aed/aed)
python standalone/server.py --db postgresql://aed:aed@127.0.0.1:5433/aed_demo
# albo: AED_DATABASE_URL=postgresql://aed:aed@127.0.0.1:5433/aed_demo python standalone/server.py

# testy na PostgreSQL (osobna baza aed_test, tworzona przy pierwszym starcie kontenera)
AED_TEST_DATABASE_URL=postgresql://aed:aed@127.0.0.1:5433/aed_test python -m unittest discover -s standalone

docker exec -it aed-postgres psql -U aed -d aed_demo     # podgląd danych
docker compose -f standalone/docker-compose.yml down -v  # usunięcie kontenera i danych
```

Hasło `aed/aed` jest wyłącznie demonstracyjne, port nasłuchuje tylko na localhost. Baner na stronie
pokazuje, z której bazy korzysta serwer.

Baza `standalone/aed_demo.sqlite3` tworzy się przy pierwszym uruchomieniu – **nie commituj jej**.
`--reset` usuwa i tworzy od nowa tabele demo (w obu bazach).

## Konta demo

| E-mail | Hasło | Rola |
|---|---|---|
| `dostawca@demo.local` | `Demo123!` | edytor instytucji A |
| `dostawca2@demo.local` | `Demo123!` | edytor instytucji B |
| `admin@demo.local` | `Admin123!` | administrator (weryfikacja: `/admin.html`) |

## Baza danych

`schema.sql` – tabela `aed_aedreport` ma **te same kolumny co migracja modułu portalu**
(`backend/aed/migrations/0001_initial.py`), czyli pola wzorcowego zakresu danych (`../schema/`) i obieg
weryfikacji; `organizations` i `users` to uproszczone odpowiedniki modeli portalu. Dane demo to rekordy
z `../schema/aed-example.csv`. Baza w starszej wersji jest tworzona od nowa automatycznie
(`PRAGMA user_version`). Podgląd: `sqlite3 standalone/aed_demo.sqlite3 "select * from aed_aedreport"`.

## API

| Metoda i ścieżka | Kto | Odpowiedź |
|---|---|---|
| `POST /api/auth/login` | każdy | `201`, token w `data.attributes.token` (+ `roles` – tylko w demo) |
| `POST /api/auth/logout` | zalogowany | `201` |
| `GET /api/auth/user` | edytor, admin | `200`, użytkownik i profile jego instytucji (`title`, `regon`, `phone`, `email`) – formularz pokazuje z nich dysponenta i kontakt |
| `GET /api/aed-reports` | edytor, admin | `200`, zgłoszenia własnej instytucji (admin: wszystkie) |
| `POST /api/aed-reports` | edytor, admin | `201`, status `submitted`; atrybuty = pola schematu (walidacja `backend/aed/validation.py`); błędy `422` – jeden na pole, z `source.pointer` |
| `POST /api/aed-report-imports` | edytor, admin | `201`; plik CSV/JSON/GeoJSON (tekst) lub XLSX (base64, `format: "xlsx"`) w `content`, `dry_run` (domyślnie `true`); `status`: `dry_run` / `imported` / `rejected`, raport `summary`, `errors` (wiersz, kolumna, komunikat), `actions` (w tym duplikaty) |
| `GET /api/aed-devices?format=csv\|json\|geojson` | każdy | publiczny zbiór – tylko rekordy zweryfikowane; bez `format` – JSON:API |
| `GET /schema/…` | każdy | pliki wzorcowego zakresu danych (szablon, słowniki) |
| `PATCH /api/aed-reports/{id}` | admin | `202`; **tylko w demo** – w portalu weryfikacja w Panelu Administratora |

Format: JSON:API (`application/vnd.api+json`), token w nagłówku `Authorization: Bearer …`.
Ścieżki z wersją (`/api/1.4/aed-reports`) też działają.

## Ograniczenia (to jest demo)

- Nasłuchuje domyślnie tylko na `127.0.0.1`; brak HTTPS, limitów zapytań i wygasania sesji.
- Hasła przechowywane jako PBKDF2-SHA256, ale konta i hasła demo są jawne.
- Brak edycji zgłoszeń przez dostawcę (w portalu: Panel Administratora).
