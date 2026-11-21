# Serwer demo (SQLite)

Samodzielny serwer prototypu – **tylko biblioteka standardowa Pythona** (3.8+), bez instalowania
pakietów i bez kodu portalu. Serwuje podstronę z `../frontend` oraz API zgodne z modułem portalu
(`../backend/aed`) i zapisuje dane w prawdziwej bazie SQLite.

```sh
python standalone/server.py            # http://127.0.0.1:8090
python standalone/server.py --reset    # od nowa: usuwa bazę i wczytuje dane demo
python standalone/server.py --port 9000 --db /tmp/aed.sqlite3
python -m unittest discover -s standalone   # testy (14)
```

Baza `standalone/aed_demo.sqlite3` tworzy się przy pierwszym uruchomieniu – **nie commituj jej**.

## Konta demo

| E-mail | Hasło | Rola |
|---|---|---|
| `dostawca@demo.local` | `Demo123!` | edytor instytucji A |
| `dostawca2@demo.local` | `Demo123!` | edytor instytucji B |
| `admin@demo.local` | `Admin123!` | administrator (weryfikacja: `/admin.html`) |

## Baza danych

`schema.sql` – tabela `aed_aedreport` ma **te same kolumny co migracja modułu portalu**
(`backend/aed/migrations/0001_initial.py`); `organizations` i `users` to uproszczone odpowiedniki
modeli portalu. Podgląd: `sqlite3 standalone/aed_demo.sqlite3 "select * from aed_aedreport"`.

## API

| Metoda i ścieżka | Kto | Odpowiedź |
|---|---|---|
| `POST /api/auth/login` | każdy | `201`, token w `data.attributes.token` (+ `roles` – tylko w demo) |
| `POST /api/auth/logout` | zalogowany | `201` |
| `GET /api/aed-reports` | edytor, admin | `200`, zgłoszenia własnej instytucji (admin: wszystkie) |
| `POST /api/aed-reports` | edytor, admin | `201`, status `submitted`; błędy `422` z `source.pointer` |
| `PATCH /api/aed-reports/{id}` | admin | `202`; **tylko w demo** – w portalu weryfikacja w Panelu Administratora |

Format: JSON:API (`application/vnd.api+json`), token w nagłówku `Authorization: Bearer …`.
Ścieżki z wersją (`/api/1.4/aed-reports`) też działają.

## Ograniczenia (to jest demo)

- Nasłuchuje domyślnie tylko na `127.0.0.1`; brak HTTPS, limitów zapytań i wygasania sesji.
- Hasła przechowywane jako PBKDF2-SHA256, ale konta i hasła demo są jawne.
- Brak edycji zgłoszeń przez dostawcę (w portalu: Panel Administratora).
