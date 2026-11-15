# Magic Town Mafia

[Launch the Streamlit app](https://magic-town-mafia-6nzdbduwka68mkxmsrubdj.streamlit.app/) · [View the GitHub repository](https://github.com/bbyambanaran-eng/magic-town-mafia)

Magic Town Mafia is a bilingual Streamlit social deduction game set in Ulaanbaatar, with a separate **Data & Insights** page for exploring real local weather data. Supabase stores multiplayer game data. Open-Meteo weather shapes the town's atmosphere, while the analytics page studies historical temperature and precipitation. Weather does not affect roles, votes, or game outcomes.

## Project goal

The project combines an interactive Mafia game with a data analysis of Ulaanbaatar weather.

**Research question:** How have Ulaanbaatar's daily mean temperature and precipitation varied by year and meteorological season from 1991 to 2025, and how does today's forecast compare with the historical daily average for the same month?

## Features

- **Multiplayer Mafia game:** Create or join a room, receive a secret role, discuss and vote by day, and take role-specific actions at night.
- **Private roles and chat:** Each player sees their own role. Mafia night chat is private to the Mafia team. All roles and the result are revealed after the game ends.
- **Observer support:** Eliminated or disconnected players become observers; the game continues for the remaining players.
- **Real Ulaanbaatar weather:** Live Open-Meteo conditions shape the game's background atmosphere. The Mayor controls game phases.
- **Separate weather analysis:** Explore annual and seasonal historical patterns, compare results with a 1991–2020 reference, filter charts, and download CSV data.
- **Game language control:** Switch the game interface between Mongolian and English. Data & Insights is in English.

## Data and methods

| Dataset | Source and fields | Coverage | Relevance and processing |
| --- | --- | --- | --- |
| Live weather | [Open-Meteo Forecast API](https://open-meteo.com/en/docs): current temperature, apparent temperature, precipitation, wind, weather code, and daily forecast values | Ulaanbaatar (47.92, 106.917), `Asia/Ulaanbaatar`; cached for 15 minutes | Supplies current conditions for the game's setting. Today's forecast daily mean temperature and precipitation are compared with historical daily averages for the same calendar month. |
| Historical weather | [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), ERA5 daily mean 2 m temperature and total precipitation | Ulaanbaatar (47.92, 106.917), 1991–2025. December 1990 is included only to complete winter 1991. | Answers the research question. Invalid dates and duplicate days are removed; missing measurements remain missing. Data is summarized by year and meteorological season, with valid-day coverage and differences from the 1991–2020 reference period. |

The live forecast and ERA5 are different weather products, so their comparison is descriptive rather than a direct station measurement. ERA5 is a model-based reanalysis on an approximately 25 km grid, not a thermometer at the displayed coordinate. The dataset represents one Ulaanbaatar grid point. The analysis describes patterns; it does not establish causes or prove a long-term climate trend. Missing values are not fabricated, and missing precipitation is never replaced with zero.

## How to read the charts

- **Annual temperature:** each point shows one year's mean temperature; the reference line marks the 1991–2020 average.
- **Annual precipitation:** each bar shows one year's total precipitation, compared with the reference average.
- **Seasonal differences:** values above zero are warmer or wetter than the same season's reference average; values below zero are cooler or drier.
- **Today's context:** today's forecast daily values are compared with daily historical averages for the same calendar month in 1991–2020.

Users can filter the year range and seasons, inspect chart values, and download processed summaries and cleaned daily records as CSV files.

## Game rules

- The Mayor creates the room and controls day/night transitions. The Mayor is a non-playing host and does not vote. There is no automatic round timer.
- At night, living Mafia players coordinate privately and choose a target. The Doctor protects a player. The Detective can secretly investigate one player once during the game.
- During the day, living players, including Mafia, can use public chat and vote by selecting a player's character card. The Mayor resolves the vote after everyone has voted. A tie eliminates nobody.
- Each player sees their own role and portrait. Other players' secret roles remain hidden until the game ends.
- The Town wins when all Mafia are eliminated. Mafia wins when no Citizen remains, even if the Doctor or Detective is still alive.
- Eliminated players and players disconnected for two minutes become observers. Remaining players can continue.

## Run locally

From PowerShell at the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Create `.streamlit/secrets.toml` with `SUPABASE_URL` and `SUPABASE_SECRET_KEY` to enable multiplayer. Do not commit this file or share its secret values. The game uses the existing Supabase tables `game_rooms`, `game_players`, `game_votes`, and `game_messages`. Open-Meteo weather data is public and does not require an API key.

## Deployment

The live app and source repository are linked at the top of this page. The app entry point is `app.py`. For a Streamlit Community Cloud deployment, connect the GitHub repository, configure `SUPABASE_URL` and `SUPABASE_SECRET_KEY` under **Settings → Secrets**, and verify that both **Game** and **Data & Insights** load after deployment.

## Code structure

| File | Purpose |
| --- | --- |
| `app.py` | Page navigation and game-only language control |
| `magic_town/game_lobby.py` | Supabase rooms, game rules, privacy, weather atmosphere, and character portraits |
| `magic_town/supabase_client.py` | Supabase client and secret loading |
| `magic_town/weather.py` | Open-Meteo forecast retrieval, normalization, and validation |
| `magic_town/analysis.py` | Historical data retrieval, cleaning, and annual/seasonal summaries |
| `magic_town/data_insights.py` | Historical analysis, comparisons, interactive charts, and CSV downloads |
| `magic_town/assets/` | Town and character images |
