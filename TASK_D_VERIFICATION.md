# Task D verification

## Version 2 verification

The v2 change connects the Notebook's Date dropdown directly to
`build_district_map()` through the **Show District Map** button. The editable
`interactive_inputs["day"]` path calls the same map function. The two April
maps remain available as optional examples. The dropdown always derives its
dates from SQLite. Month and date range remain independent controls for
monthly and range-based outputs.

| Check | Result |
|---|---|
| `python -m src.site_export` | PASS. Rebuilt the default two-case site. Its examples section identifies the files as selected pre-generated examples and describes the full-year Notebook workflow. |
| `python -m pytest -v -p no:cacheprovider tests/test_task_d.py --basetemp .task-d-temp/pytest-v2-stage` | PASS. **30 passed in 86.99 s** in the isolated project copy. All 27 original tests were retained. |
| `test_notebook_uses_selected_dates[widgets]` | PASS. The dropdown contains all 365 consecutive dates in 2025. The actual briefing, charts and map button callbacks were invoked for 2025-01-02, 2025-07-16 and 2025-12-31 in a running Jupyter kernel. |
| `test_notebook_uses_selected_dates[parameter-fallback]` | PASS. The same three dates were run through the actual editable parameter cell with widgets disabled. |
| `test_custom_site_dates_and_reexport_cleanup` | PASS. Exported January 2 and July 16, then re-exported July 16 to the same folder. Assets shrank from 2 to 1 maps, 8 to 4 charts and 16 to 8 report pairs. A separate field-notes file remained intact, both sets of relative links resolved, and the input snapshot hash matched. |
| Desktop project retest | PASS. **30 passed in 110.42 s** after syncing. The desktop site links resolve, the source database SHA-256 matches the baseline, and the saved-query, template and report tables still each contain zero rows. |
| Headless Chrome over local HTTP | PASS. Date navigation, collapse and expand, responsive layout, report links, Leaflet layers, station popup and basemap tiles. |

For each selected date, the Notebook regression compares the formal daily
briefing's coverage and peak hours with Q01, checks that three daily chart
titles use the selected date and the fourth uses the selected month, and
compares all 18 rendered district maxima with Q05 for the same date.
The original Notebook execution tests also invoke the optional April
examples explicitly in both modes.

The static `demo_cases` example is in [docs/README_EXPORT.md](docs/README_EXPORT.md).
Custom cases with empty report history generate real briefings for every chosen
day or month. Existing valid report history retains its original periods.
The exporter removes obsolete numbered assets after verifying and publishing
the new site. The default delivery retains the April 1 and April 14 examples.

## Initial release verification

Verified on 2026-11-20 (Hong Kong time) with Windows and Python 3.12.14.
The baseline database was taken from the supplied desktop project. The tests
ran in an isolated project copy with Matplotlib 3.11.2, Folium 0.20.0,
pandas 3.0.1, notebook 7.6.5, ipywidgets 8.1.9, nbformat 5.11.1,
nbclient 0.11.0 and pytest 9.2.0.

## Commands and results

| Command or check | Result |
|---|---|
| `python -m pip install` with the Task D packages in an isolated dependency directory | PASS. Installed the missing packages. pandas and Pillow were already available in the bundled Python. |
| `python -m src.site_export` | PASS. Built default `docs/` against the unseeded database baseline. |
| `python -m pytest -v tests/test_task_d.py --basetemp .task-d-temp/pytest-final` | PASS. **27 passed in 43.83 s**. |
| Headless Chrome via Playwright over local HTTP | PASS. Desktop 1365 px and mobile 390 px viewport, date links, collapsible charts, local assets, report HTML and Markdown. |
| Leaflet in Chrome on 2025-04-14 | PASS. 18 polygons, 18 station markers, Roadside layer toggling, station popup and OpenStreetMap tiles. |

The commands above use the bundled Python executable in this run. The test
process used a writable workspace temporary directory and permission to start
the local Jupyter kernel. After an initial stalled sandboxed kernel run, both
execution modes passed in the final permission-enabled run. The first core run
counted Folium's extra render-time layer registration child as a marker. The
final test counts actual CircleMarker objects and verifies their coordinates.

## Database, charts and map

| Pytest case | Result and evidence |
|---|---|
| `test_database_coverage` | PASS. 18 districts and 18 stations (15 General, 3 Roadside). 157,680 AQHI records, 157,680 pollutant records and 365 weather records. AQHI covers 2025-01-01 through 2025-12-31 and hours 01–24. There are 333 missing records and 3,731 valid substitute records. |
| `test_april1_sql_and_plot_series` | PASS. Central/Western on 2025-04-01 has 24 valid hours, min 2 and max 4. The five peak hours are 17:00 through 21:00. Low 19 hours (79.2%), Moderate 5 (20.8%), other categories 0. |
| `test_serious_and_missing` | PASS. Central/Western on 2025-04-14 has 24 valid hours, 3 Serious readings with `raw_value='10+'`, `sort_rank=11`, and `numeric_value IS NULL`. Its AQHI mean uses 21 numeric observations. PM2.5 has 7 valid observations. Tap Mun on 2025-08-05 has 10 valid hours, 14 missing hours plotted as NaN, and 0 valid substitutes. |
| `test_pngs` hourly, 2025-04-01 | PASS. Central/Western PNG is readable, nonblank, and 300 dpi. |
| `test_pngs` hourly, 2025-04-14 | PASS. Central/Western Serious PNG is readable, nonblank, and 300 dpi. |
| `test_pngs` hourly, 2025-08-05 | PASS. Tap Mun missing-data PNG is readable, nonblank, and 300 dpi. |
| `test_pngs` distribution, 2025-04-01 | PASS. Central/Western five-category PNG is readable, nonblank, and 300 dpi. |
| `test_pngs` distribution, 2026-01-01 | PASS. Zero-coverage case renders with N/A percentages. |
| `test_pngs` comparison, 2025-04-14 | PASS. Central/Western and Central PNG is readable, nonblank, and 300 dpi. |
| `test_pngs` monthly, 2025-03 | PASS. Central/Western daily maxima and PM2.5 panel render at 300 dpi. |
| `test_chart_artists_preserve_gaps_serious_ticks_and_method_date` | PASS. 24 tick labels, 5 risk bands, 14 NaN gaps for Tap Mun and the `10+` tick. March O3 panel and AQHI panel each have a dashed March 22 line and the figure includes the method caveat. |
| `test_map_saved_query_layers_and_tai_po` | PASS. Q05 returns 18 district and 3 roadside rows. The map shows 18 district geometries, 15 General and 3 Roadside markers at the coordinates stored in SQLite. Wan Chai, Yau Tsim Mong, Kowloon City and Wong Tai Sin use `#D8DEE4`. Tai Po's fill uses the greater of Tai Po station (10+) and Tap Mun (9) on 2025-04-14. |
| `test_map_empty_valid_data_and_unseeded_fallback` | PASS. With saved queries empty, the map executes the original parameterized Q05 definition directly. On 2026-01-01 it shows 4 districts as No general station and 14 as No valid data using a second grey. |

## Template input, rendering and persistence

All eight tests named `test_templates_use_real_results_and_persist` ran the
linked Task B query, converted its real outputs, checked template inputs,
rendered Task C text, Markdown and HTML, and verified the saved outputs in a
temporary database. These eight types are also present in the exported site.

| Formal template | Result and evidence |
|---|---|
| Daily Station Briefing | PASS. Q01, Central/Western on 2025-04-01. 24/24 coverage, AQHI 2–4 and all 5 peak hours. |
| Daily Category Breakdown | PASS. Q02 pivots all 5 category rows, including Low 19 hours and Moderate 5. |
| Comparison of Two Stations | PASS. Q03 uses Central/Western (General) and Central (Roadside) on 2025-04-01. Both maxima are 4. Both have 0 hours at AQHI 7 or above. |
| Weather and Pollution Summary | PASS. Q04, Central/Western on 2025-03-21 to 2025-03-23. The March 22 note is present. Exact hourly PM2.5 mean is 22.88 µg/m³ from 72 measurements. Daily weather and per-pollutant counts are retained. |
| District Map Report | PASS. Q05, 2025-04-14. 18 districts listed, 14 with valid General observations and 12 tied at 10+. |
| Monthly Station Summary | PASS. Q06, Central/Western in 2025-03. 744 valid hours, 15 valid substitutes, maximum 7 and numeric AQHI mean 3.5. The March 22 note is present. |
| High Risk Episode Bulletin | PASS. Q07, Central/Western on 2025-04-14. 22 High-or-above hours, retaining 24:00 on the source date. |
| Air Quality News Flash | PASS. Q08, 2025-04-14. General-station peak 10+, with 12 stations at the peak from 16:00 to 21:00 and exact station-hour pairs. |

| Pytest case | Result and evidence |
|---|---|
| `test_no_high_vs_no_observations_and_bad_inputs` | PASS. The valid 2025-04-01 day has no High-or-above hours. An out-of-coverage day has no valid readings and returns a labeled fallback. Invalid dates, unknown station names, duplicate comparison stations and source database writes are rejected. |
| `test_template_defect_is_not_saved` | PASS. A deliberately unavailable field produces labeled query data with no formal report ID. |

## Export and Notebook

| Pytest case | Result and evidence |
|---|---|
| `test_site_from_empty_history_and_relative_links` | PASS. 8 PNGs, 2 maps, 8 HTML briefings, 8 Markdown briefings, CSS, export notes, index and `.nojekyll`. All relative file and anchor references resolve. No SQLite file is present in `docs/`. The source and input snapshot hashes match before and after. |
| `test_site_uses_existing_history` | PASS. An existing real report is exported from history with matching Markdown. The input snapshot hash is identical before and after. |
| `test_notebook_executes[widgets]` | PASS. nbformat validation and five code cells executed using a real ipykernel via nbclient. The run rendered widget controls, a formal report, four inline PNGs, two inline Folium maps and a verified temporary export. |
| `test_notebook_executes[parameter-fallback]` | PASS. Same end-to-end run with widgets disabled. The editable input dictionary runs the analysis and export. |

Local Notebook execution was verified. Colab setup instructions are included,
and runtime execution in Colab remains unverified.

## Task D adaptation and team coordination

Task D links seeded templates to saved queries, supplies the expected variable
names, pivots row-oriented results and validates each rendering. It preserves
all peak ties, distinguishes no coverage from a zero high-risk count, includes
the March 22 note, and escapes values rendered into HTML. Q04 uses the
saved query for daily weather and an additional bound SQLite query for exact
period concentration means because Q04 daily means are already rounded.
C's formal text, Markdown and HTML templates are used. Their source wording
is preserved, with coverage and scope details through the existing note field.

Task C's direct `generate_report(template_name, query_inputs)` currently
passes query inputs straight to the renderer. It can return missing-field
messages and can persist them with `save=True`. The minimal upstream fix is
to execute the template's linked saved query, share the result-to-template
conversion, validate all required fields, and persist only successful outputs.
Apply HTML escaping to interpolated values before rendering the HTML version.
Template seed currently uses `INSERT OR REPLACE` and defaults to query ID 1
when its query is missing. Use an ID-preserving upsert and report a missing
query code explicitly before reseeding a populated database.

The team leader can adopt the Task D notebook cells in `main.ipynb` and
coordinate the common report adapter with Task C. The Task B query interface,
including Q05's 18+3 rows, worked in this checkout. Follow
[GITHUB_PAGES_PUBLISH.md](GITHUB_PAGES_PUBLISH.md) for the approved team repo.

## Source protection

The desktop source database was checked before delivery and has SHA-256
`6329F7FCA4B7E51F161FA69C2B86512157064D04C325176DD5F1DF87FDA6DB43`.
The test suite verifies hashes across snapshot/export and notebook work.
Writes from the Task D adapter are restricted to its active temporary snapshots.
The baseline has zero rows in saved_queries, report_templates and generated_reports.
The supplied plotting script was read for style and its executable font-cache
and CSV steps were skipped. The assignment, proposal, division-of-work document
and ER deck were used as project references. This delivery covers the
requested runnable Task D modules, Notebook, static site and verification files.

The EPD method note follows its [AQHI FAQ, question 5](https://www.aqhi.gov.hk/en/what-is-aqhi/faqs.html).
