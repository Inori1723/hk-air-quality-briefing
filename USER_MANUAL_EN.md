# Hong Kong Air Quality Briefing System — User Manual (Groupby)

> **Course**: HKBU AIDM7360 — Big Data Management and Analytics  
> **Edition**: Consolidated Release (matching `main.ipynb`, the 8-table `air_quality.db`, and the static `docs/` site)

---

## 1. System Overview & Team Module Mapping

Built with **Python and SQLite**, this system provides an automated pipeline for ingesting 2025 Hong Kong air quality, pollutant, meteorological, spatial, and demographic datasets, executing parameterized SQL queries, rendering multi-format briefings, generating static charts and interactive maps, and exporting a verified website for GitHub Pages.

| Task | Owner | Role | Core Files & Deliverables |
| :--- | :--- | :--- | :--- |
| **Task A (Leader)** | Feng Junjie | Data Engineering & Master Integration | `src/schema.py`, `src/etl_aqhi.py`, `src/etl_extra.py`, `src/etl.py`, `scripts/seed_project_db.py`, `main.ipynb` |
| **Task B** | Huang Zhengying | Database Schema & SQL Architecture | `src/crud.py`, `src/queries.py`, `src/task_b_demo.ipynb`, `Groupby_Task_B_ER.pptx` |
| **Task C** | Chen Hanci | Shared Template Engine & Rendering | `src/templates.py`, `src/report_templates/` (`t1`–`t8` template definitions) |
| **Task D** | Hou Jieyu | Charts, Maps, Interactive UI & Site Export | `src/viz.py`, `src/task_d_integration.py`, `src/site_export.py`, `task_d_demo.ipynb`, `docs/` |

**Database Scale (`data/db/air_quality.db`)**:
- **5 Core Fact & Dimension Tables**: `districts` (18 districts), `stations` (18 stations: 15 General + 3 Roadside), `hourly_aqhi` (157,680 rows), `hourly_pollutants` (157,680 rows), `daily_weather` (365 days).
- **3 Query & Reporting Tables**: `saved_queries` (9 core SQL queries), `report_templates` (8 reusable templates), `generated_reports` (8 pre-seeded showcase briefings).

---

## 2. Environment Setup

### 2.1 Local Machine (Windows / macOS / Linux, Python 3.10+ recommended)

> **Lightweight Note**: Schema creation, ETL, CRUD, SQL queries, and plain-text/Markdown/HTML briefing generation (`src.schema`, `src.etl*`, `src.crud`, `src.queries`, `src.templates`) rely **only on the Python standard library** and require no third-party packages. Installing `requirements.txt` is required for charts, Folium maps, Jupyter Notebook execution, and `pytest`.

From the project root (`AIDM7360_group_project/`), run:

```powershell
# 1. Create and activate a virtual environment (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install all dependencies
pip install -r requirements.txt
```

### 2.2 Google Colab

1. Upload the complete project root folder (containing `data/`, `src/`, `scripts/`, `main.ipynb`, `requirements.txt`) to Google Drive (e.g., `MyDrive/AIDM7360_group_project`).
2. Open `main.ipynb` in Colab, mount Google Drive, switch into the project root, and install dependencies:
   ```python
   from google.colab import drive
   drive.mount("/content/drive")
   %cd /content/drive/MyDrive/AIDM7360_group_project
   %pip install -r requirements.txt
   ```
3. If the notebook is launched outside the root folder, set `AQHI_PROJECT_ROOT` before running cells:
   ```python
   import os
   os.environ["AQHI_PROJECT_ROOT"] = "/content/drive/MyDrive/AIDM7360_group_project"
   ```

---

## 3. Five Core Workflows

### 3.1 Running the Master Notebook (`main.ipynb`)

1. Open `main.ipynb` from the project root in JupyterLab / Jupyter Notebook / VS Code (select the `.venv` kernel) or Google Colab.
2. Run all cells sequentially from top to bottom to execute:
   - **Environment & Data Quality Verification**: Checks row counts across all 8 tables alongside valid, missing, substitute, and `10+` AQHI totals.
   - **9 Saved SQL Queries (`Q01`–`Q09`)**: Demonstrates daily briefings, risk category breakdowns, station comparisons, weather-pollution context, 18-district map queries, monthly summaries, high-risk episode bulletins, territory-wide news flashes, and report history counts.
   - **8-Table Parameterized CRUD & FK Protection**: Executes full create/read/update/delete roundtrips across all 8 tables on a temporary snapshot and verifies `ReferencedRowError` when deleting a referenced parent template.
   - **8-Template Engine & Edge Cases**: Renders Plain Text, Markdown, and HTML outputs and tests `10+`, zero high-risk hours, and out-of-coverage dates (no error, no fabricated zeros, never persisted to `generated_reports`).
   - **Interactive Explorer UI**: Select any station, comparison station, 2025 date (all 365 days), month, or date range to generate briefings, 4 Matplotlib charts, and an interactive Folium 18-district map on demand.
   - **Static Site Export & Link Check**: Builds a temporary site and validates every local HTML/Markdown/chart/map link.
3. **Parameter-Cell Fallback (When Widgets Are Unavailable)**: If `ipywidgets` controls do not render (or when `AQHI_DISABLE_WIDGETS=1` is set), edit `interactive_inputs = dict(...)` in the parameter cell (`template`, `station`, `other`, `day`, `month`, `start`, `end`) and re-run that cell.

> **Database Safety**: All CRUD and write demonstrations inside `main.ipynb` run on an isolated `TemporaryDirectory` SQLite backup (`demo_db`), keeping the authoritative `data/db/air_quality.db` unmodified.

---

### 3.2 Executing Saved Queries & 8-Table CRUD (Python API)

#### Running the 9 Saved Queries (`src/queries.py`)

```python
from src.queries import seed_saved_queries, run_saved_query

# Ensure saved_queries is populated (idempotent; preserves query_id)
seed_saved_queries()

# Example 1: Daily station briefing (Q01)
rows = run_saved_query(
    "Q01_daily_briefing",
    {"station_name": "Central/Western", "obs_date": "2025-04-01"},
)

# Example 2: Weather & pollution range query (Q04)
range_rows = run_saved_query(
    "Q04_weather_pollution",
    {"station_name": "Central/Western", "start_date": "2025-03-21", "end_date": "2025-03-23"},
)

# Example 3: Generated report history summary (Q09)
history_rows = run_saved_query("Q09_report_history", {})
```

**Saved Query Codes & Required Parameters**:

| `query_code` | Required Keys in `params` | Purpose |
| :--- | :--- | :--- |
| `Q01_daily_briefing` | `station_name`, `obs_date` | Station-day AQHI range, peak hours, pollutant means, and daily weather |
| `Q02_category_breakdown` | `station_name`, `obs_date` | Hours and percentages across the 5 AQHI risk categories |
| `Q03_station_comparison` | `station_a`, `station_b`, `obs_date` | Same-day comparison keeping General and Roadside stations distinct |
| `Q04_weather_pollution` | `station_name`, `start_date`, `end_date` | Daily AQHI, 6 pollutant measurement counts, and HKO weather context |
| `Q05_district_map` | `obs_date` | 18 district rows (General maxima) + 3 Roadside marker rows with coordinates |
| `Q06_monthly_summary` | `station_name`, `month` (`YYYY-MM`) | Monthly coverage, risk distribution, AQHI mean/max, and pollutant means |
| `Q07_high_risk_bulletin` | `station_name`, `start_date`, `end_date` | Dates with AQHI >= 7 and their exact high-risk clock hours |
| `Q08_news_flash` | `obs_date` | Territory-wide peak across the 15 General stations, stations, and hours |
| `Q09_report_history` | `{}` (empty) | Counts of `generated_reports` grouped by template and creation month |

#### Full 8-Table Parameterized CRUD (`src/crud.py`)

Each of the 8 tables exposes parameterized `create_*`, `get_*`, `update_*`, and `delete_*` functions to prevent SQL injection:
- Supported tables: `district`, `station`, `hourly_aqhi`, `hourly_pollutant`, `daily_weather`, `saved_query`, `report_template`, `generated_report`.
- **Integrity Rules**:
  - Updates to `hourly_aqhi` must pass `raw_value` (e.g., `"4*"` or `"10+"`); `crud.update_hourly_aqhi()` automatically synchronizes `numeric_value`, `sort_rank`, `category`, `is_substitute`, and `is_missing`.
  - Deleting a parent row still referenced by child rows (e.g., deleting a template referenced by `generated_reports`) raises `crud.ReferencedRowError`; delete child records first.

---

### 3.3 Generating, Storing & Exporting Multi-Format Briefings (`src/templates.py`)

```python
from src.templates import generate_report, export_report_files

# 1. Preview without saving: returns dict (formal, report_id, text_output, markdown_output, html_output)
preview = generate_report(
    "Weather and Pollution Summary",
    {"station_name": "Central/Western", "start_date": "2025-03-21", "end_date": "2025-03-23"},
    save=False,
)
print(preview["text_output"])

# 2. Generate and persist to generated_reports (returns int report_id; returns formal=False without saving if no valid data)
report_id = generate_report(
    "Daily Station Briefing",
    {"station_name": "Central/Western", "obs_date": "2025-04-01"},
    save=True,
)

# 3. Export stored report to .txt, .md, and .html files
if isinstance(report_id, int):
    paths = export_report_files(report_id, out_dir="exported_reports")
    print(paths)
```

Standard Template Names (`TEMPLATE_NAMES`):
`Daily Station Briefing`, `Daily Category Breakdown`, `Comparison of Two Stations`, `Weather and Pollution Summary`, `District Map Report`, `Monthly Station Summary`, `High Risk Episode Bulletin`, `Air Quality News Flash`.

---

### 3.4 Rebuilding the Database from Raw Files & Refreshing Showcase Reports

To rebuild `data/db/air_quality.db` from `data/raw/` and refresh the 8 seeded showcase briefings, run from the project root:

```powershell
# 1. Rebuild all 5 base tables from raw files and seed saved_queries & report_templates
python -m src.etl

# 2. Idempotently insert (or pass --refresh to regenerate) the 8 default showcase briefings
python scripts/seed_project_db.py --refresh
```

---

### 3.5 Rebuilding the Static Site (`docs/`) & Publishing to GitHub Pages

```powershell
# 1. Export responsive index.html, 8 HTML/MD briefings, 8 300-dpi charts, and 2 Folium maps to docs/
python -m src.site_export

# 2. Preview locally at http://127.0.0.1:8000/
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

- To publish custom example dates on the homepage, call `export_static_site(demo_cases=[{"station_name": "Central/Western", "station_b": "Central", "obs_date": "2025-07-16"}])`; obsolete numbered assets are cleaned up automatically while unrelated files remain untouched.
- **GitHub Pages Deployment**: Commit and push the verified `docs/` tree (including `docs/.nojekyll`) to the team GitHub repository, then open **Settings → Pages → Build and deployment**, choose **Deploy from a branch**, select the target branch and **`/docs`**, and save (see [GITHUB_PAGES_PUBLISH.md](GITHUB_PAGES_PUBLISH.md)).
- **Network Note**: Folium maps load Leaflet assets and OpenStreetMap basemap tiles over the network in the browser.

---

## 4. Data Conventions & Edge-Case Reference

1. **`10+` (`Serious`) Handling**:
   - Stored as `raw_value='10+'`, `numeric_value=NULL`, `sort_rank=11`, `category='Serious'`.
   - Maxima and ordering use `sort_rank` (rendered as `'10+'` or `'10+ (Serious)'`), while averages exclusively use `AVG(numeric_value)` so `11` is never averaged.
2. **Missing & Substitute Readings**:
   - Blank cells, `-`, and `-*` are stored with `is_missing = 1` (never zero); valid `*` readings keep `is_substitute = 1, is_missing = 0`.
   - Category shares divide by valid hours (`NULLIF(valid_hours, 0)`), and hourly line charts leave `NaN` gaps for missing hours instead of connecting to zero.
3. **Six Pollutants & Units**:
   - `PM2.5`, `PM10`, `O3`, `NO2`, and `SO2` are stored in `ug/m3`; `CO` is stored in `10 ug/m3`. Missing pollutant hours stay `NULL` (`N/A (not available)` in briefings) with valid measurement counts printed alongside each mean.
4. **22 March 2025 EPD Calculation Update**:
   - Queries or monthly charts spanning `2025-03-22` automatically attach `METHOD_NOTE`; `Weather and Pollution Summary` and `Monthly Station Summary` additionally append `Pre-22 Mar` vs `From 22 Mar` AQHI period-split statistics, and `plot_monthly_trend()` draws a vertical dashed line at day 22.
5. **18-District Map & Weather Context**:
   - District choropleth shading uses **General** stations only (`15` stations across `14` districts). The `4` districts without a General station (`Kowloon City`, `Wan Chai`, `Wong Tai Sin`, `Yau Tsim Mong`) stay grey (`#D8DEE4`) without interpolation; hover Tooltips display C&SD 2025 mid-year land population and land area across all 18 districts. The `3` Roadside stations (`Causeway Bay`, `Central`, `Mong Kok`) appear in a separate toggleable layer with Popups.
   - Daily HKO meteorology provides same-day background context only and does not establish causation of hourly AQHI peaks.

---

## 5. Automated Testing & Troubleshooting

### Running the Full Test Suite

From the project root (ensure no external viewer is locking SQLite files):

```powershell
python -m pytest -v tests/test_task_d.py tests/test_integration.py
```

Coverage includes: base DB completeness, full ETL rebuild & clean connection closing, 8-table CRUD & FK protection, 8-template rendering/escaping/edge cases, 300-dpi chart & NaN-gap verification, Folium 18-district (including unmonitored district population Tooltips) & Roadside layer checks, `docs/` relative link validation, and full kernel execution of `task_d_demo.ipynb` and `main.ipynb` in both widget and fallback modes.

### Troubleshooting

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| `Locate the project root...` | Executed outside the repository root | `cd` into `AIDM7360_group_project/` or set `AQHI_PROJECT_ROOT` to that path |
| Notebook widget buttons do not appear | `ipywidgets` disabled in viewer | Edit the `interactive_inputs` dictionary cell and re-run it directly |
| Matplotlib font/config directory warning | User config folder not writable | Set `MPLCONFIGDIR=.matplotlib` before launching Python/Jupyter |
| Basemap tiles blank on Folium map | Offline browser environment | Connect to the internet to load Leaflet JS and OpenStreetMap tiles |
| Zip archive too large for submission | Virtual environment or caches included | **Exclude** `.venv/`, `.python_dependencies/`, `__pycache__/`, `.pytest_cache/`, `.ipynb_checkpoints/`, and backup zips/folders when packaging |
