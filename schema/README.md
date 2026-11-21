# Wzorcowy zakres danych o defibrylatorach AED

Akcja **„Znajdź AEDres”** – *Udostępnij. Uratuj.*

Jednolity zakres danych, w którym **każdy dysponent** (gmina, szpital, przewoźnik, firma, uczelnia…)
udostępnia informacje o swoich AED w portalu dane.gov.pl. Dzięki wspólnemu schematowi dane z wielu
rozproszonych źródeł można połączyć w **jeden ogólnopolski zbiór**.

## Pliki (wszystkie czytelne maszynowo)

| Plik | Zawartość |
|---|---|
| `aed.schema.json` | Schemat w formacie [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/): nazwy, typy, wymagalność, wzorce, zakresy, słowniki, polskie opisy |
| `aed-template.csv` | Pusty szablon dla dysponenta (bez kolumn nadawanych przez system) |
| `aed-example.csv` | 5 rekordów przykładowych – **dane fikcyjne**, oznaczone `[PRZYKŁAD]` |
| `dictionaries/*.csv` | Słowniki wartości: `access`, `device_status`, `pediatric`, `building_types`, `manufacturers`, `street_types`, `voivodeships` |

## Zasady techniczne

- Jeden wiersz to jedno urządzenie. Kodowanie **UTF-8**, separator pól to przecinek, wartości z
  przecinkiem ujmuje się w cudzysłów, separator dziesiętny to **kropka**.
- Daty w formacie **ISO 8601** (`2026-11-21`), data i czas w UTC (`2026-11-21T10:15:00Z`).
- Współrzędne w **WGS84 (EPSG:4326)** w stopniach dziesiętnych, do 6 miejsc po przecinku.
- Adres w **osobnych polach**: `voivodeship`, `county`, `commune`, `city`, `street_type`, `street`,
  `street_number`, `postal_code` (nazwy jak w modelu instytucji w portalu). Kodów TERYT nie stosujemy.
- Wartości słownikowe to stałe kody (`public`, `operational`…). Polskie etykiety są w słownikach.
- Pusta komórka oznacza brak danych. Nie wpisuj „brak”, „-” ani „n/d”.
- Kolumny `id`, `source` i `verified_at` (oznaczone w schemacie `x-system`) nadaje system:
  dysponent ich nie wypełnia.
- **Dysponent i kontakt publiczny** (`operator_name`, `operator_regon`, `contact_phone`, `contact_email`,
  oznaczone `x-from-institution`) zawsze pochodzą z **profilu instytucji** zgłaszającej w portalu – dostawca ich
  nie wpisuje, a wartości z formularza lub pliku są ignorowane. Dzięki temu nazwa i REGON są spójne w całym
  zbiorze, a dostawca nie przepisuje danych, które portal już zna.
- **Producent** (`manufacturer`) wybiera się ze słownika `dictionaries/manufacturers.csv`; dla „Inny producent”
  (`other`) wymagana jest nazwa w `manufacturer_other` (reguła `x-requiredIf`: pole wymagane i dozwolone tylko
  przy tej wartości).
- **Numer seryjny** (`serial_number`, `x-internal`) jest wymagany i – razem z producentem – identyfikuje
  urządzenie. Widzi go tylko administrator portalu; nie jest publikowany.
- **Telefon do osoby odpowiedzialnej za AED** (`internal_contact_phone`, oznaczony `x-internal`) zbieramy tylko
  dla administratora portalu – **nie jest publikowany** w zbiorze ani na mapie (minimalizacja danych osobowych).
- Schemat steruje też prototypem: `x-group`/`x-groups` wyznaczają sekcje formularza, a
  `x-enumLabels` – polskie etykiety kodów, takie same jak w słownikach CSV. Walidator w Pythonie i w JS
  czyta reguły wyłącznie z tego pliku.

## Zakres – pola wymagane

| Grupa | Pola wymagane | Pola zalecane |
|---|---|---|
| Dysponent | `operator_name` (z profilu instytucji) | `operator_regon` (z profilu instytucji) |
| Miejsce | `location_name`, `building_type` (słownik; dla „Inny” – `building_type_other`), `location_description`, `indoor` | `floor` |
| Adres | `commune`, `city`, `street_number`, `postal_code` | `voivodeship`, `county`, `street_type`, `street` |
| Położenie | `latitude`, `longitude` | – |
| Dostępność | `access`, `opening_hours` | `access_notes` |
| Urządzenie | `device_status`, `manufacturer` (słownik; dla „Inny” – `manufacturer_other`), `serial_number` (tylko dla administratora) | `pediatric`, `model`, `last_inspection_date`, `electrodes_expiry_date`, `battery_expiry_date` |
| Kontakt | – | `contact_phone`, `contact_email` (z profilu instytucji); `internal_contact_phone` – tylko dla administratora, niepublikowany |
| Aktualność | `data_date` (dane na dzień) | – |

Pełny opis każdego pola (tytuł, opis, ograniczenia) jest w `aed.schema.json`.

Dlaczego te pola:
- Służby ratunkowe i świadek zdarzenia potrzebują przede wszystkim odpowiedzi na trzy pytania:
  **gdzie dokładnie** (współrzędne i opis miejsca), **czy mogę teraz skorzystać** (`access`,
  `opening_hours`, `device_status`) oraz **czy nadaje się dla dziecka** (`pediatric`).
- Daty przeglądu i terminy ważności elektrod i baterii pozwalają dysponentowi pilnować sprawności
  urządzenia, a koordynatorowi zbioru wykrywać rekordy wymagające uwagi.
- `data_date` i `verified_at` pokazują, na ile aktualna jest informacja.

## Jedno urządzenie – jeden rekord (producent + numer seryjny)

Urządzenie identyfikuje **producent i numer seryjny** (porównywany bez wielkości liter, spacji i znaków
`-./`, więc „ab-123 4” to „AB1234”). Przy ponownym przesłaniu danych (formularz lub plik):

- to samo urządzenie **tej samej instytucji** – rekord jest **aktualizowany** (także gdy urządzenie przeniesiono);
- to samo urządzenie **zgłoszone przez inną instytucję** – zgłoszenie jest **odrzucane** („to samo urządzenie
  nie może być w dwóch miejscach”); przekazanie AED między instytucjami wykonuje administrator;
- dwa wiersze jednego pliku z tym samym urządzeniem – błąd.

Dodatkowo urządzenia **o innych numerach** w promieniu **15 m** z podobną nazwą miejsca lub tym samym adresem
są oznaczane jako „możliwy duplikat” (np. literówka w numerze) – decyduje administrator.

## Zgodność z OpenStreetMap

Pole `x-osm` w schemacie wskazuje odpowiadający tag OSM dla obiektu `emergency=defibrillator`
(np. `location_description` odpowiada `defibrillator:location`, `floor` – `level`, `opening_hours` –
`opening_hours`, `data_date` – `check_date`). Zbiór da się więc porównywać z danymi społeczności OSM i
aplikacjami, które z nich korzystają.

## Zgodność ze standardami dane.gov.pl

| Wymóg | Realizacja |
|---|---|
| Format otwarty, czytelny maszynowo | CSV i JSON (schemat, słowniki), bez PDF i DOC |
| Opis struktury danych | Table Schema z typami i opisem każdej kolumny |
| Adres w osobnych polach | `voivodeship`, `county`, `commune`, `city`, `street_type`, `street`, `street_number`, `postal_code` |
| Współrzędne liczbowe WGS84 | `latitude`, `longitude` typu `number`, kropka dziesiętna |
| Daty ISO 8601, „dane na dzień” | typ `date`/`datetime`, `data_date` |
| Granulacja – jedna informacja w polu | brak pól łączonych (adres, godziny, kontakt rozdzielone) |
| Telefon 9 cyfr | wzorzec `^[0-9]{9}$` |
| Minimalizacja danych osobowych | tylko kontakty instytucjonalne. Bez nazwisk, prywatnych numerów i kodów do szafek |
| Stałe słowniki | kody w `enum` i słowniki CSV z etykietami |

## Wersjonowanie

`version` w schemacie wersjonowany jest semantycznie. Dodanie pola opcjonalnego podnosi wersję
**minor**, a zmiana nazwy, typu lub wymagalności pola – wersję **major**.
