# intervals-sync

Synchronizacja aktywności z [intervals.icu](https://intervals.icu) do Obsidian vaulta.

- Notatki per aktywność → `Human/02_life/sport/activities/YYYY/MM/`
- Tygodniówki → `Machine/reports/weekly/YYYY-Www-sport.md`
- Tylko stdlib Pythona (bez zależności, bez venv).

## Konfiguracja

Skopiuj `secrets.json.example` → `secrets.json` (gitignorowany) i uzupełnij `athlete_id`
oraz `api_key` z intervals.icu (Settings → Developer). Alternatywnie zmienne środowiskowe
`INTERVALS_ATHLETE_ID` / `INTERVALS_API_KEY`.

## Uruchomienie

```bash
python3 intervals_sync.py          # sync ostatnich 60 dni (pomija już zsynchronizowane)
python3 intervals_sync.py --force  # regeneruje wszystkie notatki w oknie
```

Codzienny przebieg: launchd `~/Library/LaunchAgents/com.michaldomarus.intervals-sync.plist` (07:00).

## Zasady działania

- **ID = źródło prawdy.** Każda notatka ma `activity_id` we frontmatterze; mapa zmiany
  nazwy/kolizji budowana jest ze skanu notatek (`scan_existing_notes`), nie z pliku stanu.
  Zmiana nazwy aktywności → notatka jest przenoszona (stara usuwana), bez duplikatu.
  Kolizja (różne aktywności, ta sama nazwa+data) → sufiks `__{strava_id}`.
- **Przewyższenie z zegarka.** Skrypt wyłącza `use_elevation_correction` (DEM) na
  intervals.icu per aktywność, żeby `total_elevation_gain` był wartością barometryczną
  zgodną ze Stravą/Garminem.
- **Zapis atomowy** (`write_text_safe`) — temp + `os.replace`, odporny na lock File Providera iCloud.

Stan: `~/.intervals_sync_state.json` (tylko `last_sync`).
