# Hong Kong Air Quality Briefing System (AIDM7360 · Groupby)

An automated Python and SQLite content management and briefing system built for **HKBU AIDM7360 (Big Data Management and Analytics)**. It ingests full-year 2025 Hong Kong air quality, pollutant, meteorological, boundary, and demographic datasets into an 8-table relational database (`data/db/air_quality.db`), runs 9 parameterized SQL queries, renders 8 reusable templates simultaneously into Plain Text, Markdown, and HTML, visualizes hourly/monthly trends and 18-district spatial maps, and exports a verified static website (`docs/`) for GitHub Pages.

## Project Structure

```text
AIDM7360_group_project/
├── data/
│   ├── raw/
│   │   ├── aqhi_2025/                  # EPD 2025 hourly AQHI CSVs (Jan–Dec)
│   │   ├── air_hourly.csv              # EPIC 2025 hourly pollutant concentrations (157,680 rows)
│   │   ├── weather_2025/               # HKO & King's Park 2025 daily weather CSVs/XMLs
│   │   └── geo_population/             # 18-district GeoJSON boundaries, EPD coords, C&SD demographics
│   └── db/
│       └── air_quality.db              # Consolidated 8-table SQLite database
├── src/
│   ├── schema.py                       # 8-table DDL, indexes, and get_connection()
│   ├── etl_aqhi.py                     # AQHI, 18 districts, and 18 stations ETL
│   ├── etl_extra.py                    # Pollutants, HKO weather, coordinates, C&SD population ETL
│   ├── crud.py                         # Parameterized CRUD across all 8 tables + ReferencedRowError
│   ├── queries.py                      # 9 parameterized SQL queries (Q01–Q09) & seed_saved_queries()
│   ├── templates.py                    # Shared template engine, query adapter & generate_report()
│   ├── report_templates/               # 8 modular report template definitions (t1–t8)
│   ├── viz.py                          # Matplotlib 300 dpi charts & Folium 18-district interactive map
│   ├── task_d_integration.py           # Isolated snapshot adapter & Notebook UI bridge
│   └── site_export.py                  # Static site exporter & link validator -> docs/
├── scripts/
│   ├── fetch_remaining_data.py         # Source dataset fetcher
│   ├── plot_proposal_example.py        # Proposal prototype figure script
│   └── seed_project_db.py              # Idempotent seeding for saved_queries, templates & showcase reports
├── docs/                               # Pre-rendered GitHub Pages site (.nojekyll, HTML/MD, PNGs, maps)
├── tests/
│   ├── test_task_d.py                  # Task D unit, visualization, map, notebook & export tests
│   └── test_integration.py             # End-to-end DB, CRUD, Task C template & main.ipynb tests
├── main.ipynb                          # Unified master notebook (local Jupyter & Google Colab)
├── requirements.txt                    # Python package requirements
└── README.md
```

## Quick Start

1. **Create and activate a Python 3.10+ environment, then install dependencies:**

   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Re-seed queries, templates, and showcase reports (idempotent):**

   ```bash
   python scripts/seed_project_db.py
   ```

3. **Run the unified master notebook (`main.ipynb`):**

   Open `main.ipynb` in Jupyter Notebook / JupyterLab / VS Code (or upload the project folder to Google Drive and run in Colab). All write tests inside the notebook run against an isolated temporary SQLite snapshot so `data/db/air_quality.db` stays clean.

4. **Rebuild the static GitHub Pages site (`docs/`):**

   ```bash
   python -m src.site_export
   python -m http.server 8000 --bind 127.0.0.1 --directory docs
   ```

5. **Run the full automated test suite:**

   ```bash
   python -m pytest -v tests/test_task_d.py tests/test_integration.py
   ```

## Data Conventions & Methodology Safeguards

- **`10+` (`Serious`)**: Stored with `raw_value = '10+'`, `numeric_value = NULL`, `sort_rank = 11`, and `category = 'Serious'`. Maxima and sorting use `sort_rank` (displayed as `'10+'`), whereas AQHI means use `AVG(numeric_value)` exclusively so `11` is never averaged.
- **Missing & Substitute Readings**: Blank, `-`, and `-*` cells are stored as `is_missing = 1` (never zero); valid `*` readings retain `is_substitute = 1`. Percentages divide by valid hours (`NULLIF(valid_hours, 0)`).
- **22 March 2025 EPD Update**: Reports spanning or targeting `2025-03-22` automatically append the EPD calculation methodology note.
- **District Map Coverage**: District polygons shade General-station maxima only; the four districts without a General monitoring station (`Kowloon City`, `Wan Chai`, `Wong Tai Sin`, `Yau Tsim Mong`) remain unshaded (`#D8DEE4`) while Roadside stations (`Causeway Bay`, `Central`, `Mong Kok`) appear in a separate toggleable layer.
