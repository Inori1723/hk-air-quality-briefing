# Regenerate the static briefing site

Run from the project root after installing `requirements_task_d.txt`.

```shell
python -m src.site_export
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open [the local home page](http://127.0.0.1:8000/) and use the date links or
expand each date's charts. Folium maps load Leaflet and basemap tiles over the
network. The reports and charts are served as static files.

## Export selected dates

Run this from the project root. Supply one entry per date. The monthly chart
uses the month of `obs_date` when `month` is omitted.

```python
from src.site_export import export_static_site

export_static_site(demo_cases=[
    {"station_name": "Central/Western", "station_b": "Central",
     "obs_date": "2025-07-16"},
])
```

When report history is empty, each custom case gets briefings for its chosen
day or month. Existing valid report history keeps its original reporting
periods. Re-exporting to the same directory removes old numbered map, chart
and briefing files that are no longer generated, and preserves unrelated
files. The selected static examples are a subset of the 2025 data. Open
`main.ipynb` in the project to query any 2025 date interactively.

The exporter reads SQLite through the project schema helper. When report history
is empty it snapshots the source database in a temporary directory, seeds the
saved queries and templates, runs real queries and renders the template inputs
before saving the briefings to the snapshot. The snapshot expires after export.
Missing-data and template conversion failures are labeled as query-data fallback
and excluded from generated report history. Existing valid report history is
exported directly. Exported HTML report fragments are filtered to basic markup.

Charts use Matplotlib and maps use Folium. Every relative file and fragment link
in the generated HTML is checked before the files are copied to the output
directory. The site uses CSS and native HTML controls for layout and date navigation.
