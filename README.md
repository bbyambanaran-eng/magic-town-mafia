# Magic Town Mafia

A bilingual Streamlit app with separate **Game** and **Data & Insights** pages. The game uses Supabase for rooms and play, and live Ulaanbaatar weather from Open-Meteo shapes its atmosphere. The separate analytics page explores real historical weather data. Navigation and analytics are in English; the game page can switch between English and Mongolian.

## Project goal

**Purpose:** Build a social deduction game grounded in Ulaanbaatar's real-time weather, and provide a separate, data-led exploration of the city's historical weather. **Research question:** How have Ulaanbaatar's daily mean temperature and precipitation varied by year and meteorological season since 1991, and how does today's forecast compare with the usual daily conditions for this month? Weather shapes the live game setting; it does not alter roles, votes, or outcomes.

## Run the app

From PowerShell at the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

To create an environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Configure `SUPABASE_URL` and `SUPABASE_SECRET_KEY` in `.streamlit/secrets.toml`. Do not commit that file. The game uses the existing Supabase tables `game_rooms`, `game_players`, `game_votes`, and `game_messages`.

## Streamlit Community Cloud deployment

1. Push the project to a GitHub repository that you control.
2. In Streamlit Community Cloud, create an app from that repository and set the entry point to `app.py`.
3. Add `SUPABASE_URL` and `SUPABASE_SECRET_KEY` under the app's **Settings → Secrets**. Do not put secret values in source code or commit them.
4. Deploy, then verify both **Game** and **Data & Insights** load. The game requires Supabase credentials; weather data comes from public Open-Meteo APIs.

## Game

- The Mayor creates the room and is a non-playing host. The Mayor starts the game, controls phase transitions, and does not vote. Mafia, Doctor, and Detective roles are assigned randomly; remaining players are Citizens.
- During the day, all living players, including Mafia, can use the public chat and vote by selecting a player's character card. The Mayor resolves the vote after all living players have voted. A tied vote eliminates nobody.
- At night, living Mafia players can use a separate private chat to coordinate. Private messages are hidden from the public day chat and are shown only in the Mafia players' night view. The Doctor protects a player, and the Detective can secretly investigate one player once during the game. The Mayor resolves the night after Mafia and Doctor actions are submitted.
- Each player sees their own name, role, and role portrait. Other players' secret roles stay hidden until the game ends, when all roles, survival status, and the outcome are revealed.
- The town wins when all Mafia are eliminated. The game continues while at least one Citizen is alive. The Mafia wins only when no Citizen remains, even if the Doctor or Detective is still alive. Day and night have no automatic timer; the Mayor advances the game after actions are ready.
- A player who is eliminated, leaves, or has been disconnected for two minutes becomes an observer. Remaining players can continue the game.
- Presence signals are stored in the existing `game_messages` table; no extra table is required.
- The start screen includes a plain-language glossary and privacy notice. The app stores display names and gameplay records in Supabase; chat messages are cleared as phases change, while room, player, vote, and action rows are not automatically deleted. Players should not enter sensitive personal details.

## Data and methods

| Dataset | Source and fields | Coverage | Use and processing |
| --- | --- | --- | --- |
| Live weather | [Open-Meteo Forecast API](https://open-meteo.com/en/docs): current temperature, apparent temperature, precipitation, wind, condition code, and daily mean/max/min temperature, precipitation, sunrise/sunset | Ulaanbaatar (47.92, 106.917), `Asia/Ulaanbaatar`; current snapshot cached for 15 minutes | The game uses current conditions for its atmosphere and the Mayor controls its day/night phase. The Data & Insights page compares today's forecast daily mean and precipitation with the ERA5 average daily values for the same calendar month in 1991–2020. |
| Historical weather | [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), ERA5: daily mean temperature at 2 m and daily total precipitation | Ulaanbaatar (47.92, 106.917), 1991–2025; December 1990 is included only to complete winter 1991 | Cleans invalid dates and duplicate dates; calculates annual and meteorological-season summaries, valid-day coverage, and differences from 1991–2020 averages. The page provides filtered charts and downloadable summaries and records. |

ERA5 is a model-based reanalysis, not a thermometer reading at the selected coordinate. Its grid is about 25 km. The one-point dataset describes Ulaanbaatar only. Forecast and ERA5 are different weather products, so the live-to-history comparison is descriptive rather than a direct station measurement. Missing API data stays missing; precipitation is never filled with zero. Comparisons are descriptive and do not establish causes or long-term climate trends.

## Code structure

| File | Purpose |
| --- | --- |
| `app.py` | English page navigation and game-only language control |
| `magic_town/game_lobby.py` | Supabase room, game rules, privacy, weather atmosphere, and role portraits |
| `magic_town/data_insights.py` | Separate historical weather analytics page |
| `magic_town/analysis.py` | Historical data retrieval, cleaning, and aggregation inputs |
| `magic_town/supabase_client.py` | Supabase client and secrets |
| `magic_town/weather.py` | Open-Meteo forecast retrieval and validation |
| `magic_town/assets/` | Town and character images |
