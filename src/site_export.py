"""Generate a self-contained static briefing site from the project database."""

from html import escape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit
from shutil import copytree

from bleach import clean
from bs4 import BeautifulSoup

from src.schema import DEFAULT_DB_PATH, PROJECT_ROOT, get_connection
from src.task_d_integration import (
    METHOD_NOTE, TEMPLATE_NAMES, default_cases, demo_database, make_briefing, select,
)
from src.viz import (
    build_district_map, plot_category_distribution, plot_hourly_aqhi,
    plot_monthly_trend, plot_station_comparison,
)

EPD = "https://www.aqhi.gov.hk/en/past-data/past-aqhi.html"
EPD_FAQ = "https://www.aqhi.gov.hk/en/what-is-aqhi/faqs.html"

CSS = """
:root {
  color-scheme: light;
  --ink: #152e41;
  --muted: #445c6d;
  --line: #cad9df;
  --teal: #14545b;
  --paper: #f4f8fa;
  font-family: system-ui, sans-serif;
  line-height: 1.55;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); }
a { color: var(--teal); text-underline-offset: .2em; }
a:focus-visible, summary:focus-visible { outline: 3px solid #966111; outline-offset: 4px; }
header { background: #102f40; color: #fff; padding: 1rem 0 3.2rem; }
header a { color: #cbefed; }
.wrap { max-width: 76rem; margin-inline: auto; padding-inline: clamp(1rem, 4vw, 3rem); }
nav { display: flex; flex-wrap: wrap; gap: .8rem 1.4rem; font-size: .94rem; }
h1 { max-width: 24ch; font-size: clamp(2.2rem, 6vw, 4rem); line-height: 1.08; margin: 2rem 0 1rem; }
header p { max-width: 68ch; color: #d1e5ea; }
h2 { font-size: clamp(1.4rem, 3vw, 2rem); margin: 0 0 .8rem; }
h3 { line-height: 1.3; }
section { padding-block: 1.6rem; border-bottom: 1px solid var(--line); }
.coverage, .date-links, .report-list { display: flex; flex-wrap: wrap; gap: .65rem 1.4rem; }
.coverage { margin: 0; }
.coverage div { padding: .45rem 1rem .45rem 0; min-width: 10rem; }
.coverage dt { color: var(--muted); font-size: .92rem; }
.coverage dd { margin: 0; font-weight: 750; font-size: 1.35rem; font-variant-numeric: tabular-nums; }
.date-links a { padding: .3rem .65rem; border: 1px solid var(--line); border-radius: .4rem; background: white; }
details { background: white; border: 1px solid var(--line); border-radius: .5rem; padding: 1rem; margin-top: 1rem; }
details:target { border-color: var(--teal); }
summary { cursor: pointer; font-weight: 700; }
.case-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .2rem 1rem; }
.charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; }
figure { margin: 0; min-width: 0; border: 1px solid var(--line); border-radius: .35rem; overflow: hidden; }
img { display: block; width: 100%; height: auto; }
.report-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); padding: 0; list-style: none; }
.report-list li { background: white; border-top: 2px solid #4e9b7a; padding: .8rem; }
.report-list small { display: block; color: var(--muted); margin-top: .35rem; }
article { max-width: 74ch; background: white; padding: clamp(1rem, 4vw, 2rem); margin: 1.5rem 0; border: 1px solid var(--line); border-radius: .5rem; overflow-wrap: anywhere; }
article h3 { margin-top: 0; }
table { border-collapse: collapse; max-width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: .45rem .55rem; text-align: left; }
pre { overflow-x: auto; }
.note, footer { color: var(--muted); }
footer { padding-block: 1.25rem 2.5rem; }
@media (max-width: 52rem) { .charts { grid-template-columns: 1fr; } }
"""

EXPORT_README = """# Regenerate the static briefing site

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
"""

REPORT_SQL = """
SELECT r.*, t.name AS template_name FROM generated_reports r
JOIN report_templates t USING(template_id)
WHERE length(r.text_output) > 0 AND length(r.markdown_output) > 0
  AND length(r.html_output) > 0
  AND r.text_output NOT LIKE 'No valid data available:%'
  AND r.text_output NOT LIKE 'Template Render Error:%'
ORDER BY r.report_id
"""


def _write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _page(title, body, prefix=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="{prefix}assets/site.css">
</head>
<body>{body}</body>
</html>
"""


def validate_site_links(root):
    """Return broken or out-of-root local references in generated HTML."""
    root = Path(root).resolve()
    errors, pages = [], {}
    for file in sorted(root.rglob("*.html")):
        pages[file] = BeautifulSoup(file.read_text(encoding="utf-8"), "html.parser")
    for file, page in pages.items():
        for tag in page.find_all(["a", "link", "img", "script", "iframe"]):
            ref = tag.get("href") or tag.get("src")
            if not ref:
                continue
            url = urlsplit(ref)
            if url.scheme or url.netloc:
                continue
            target = (file.parent / unquote(url.path)).resolve() if url.path else file
            if not target.is_relative_to(root) or not target.is_file():
                errors.append(f"{file.relative_to(root)} → {ref}")
            elif url.fragment and target in pages and not pages[target].find(id=unquote(url.fragment)):
                errors.append(f"{file.relative_to(root)} → {ref} (fragment missing)")
    return errors


def _demo_reports(db_path, cases, *, custom_cases):
    existing = select(REPORT_SQL, db_path=db_path)
    if existing:
        return existing
    if custom_cases:
        plan = [(name, case) for case in cases for name in TEMPLATE_NAMES]
    else:
        first, last = cases[0], cases[-1]
        plan = [(name, last if index in (4, 6, 7) else first)
                for index, name in enumerate(TEMPLATE_NAMES)]
    failures = []
    with demo_database(db_path) as demo:
        for name, case in plan:
            day = case["obs_date"]
            params = {**case, "station_a": case["station_name"], "start_date": day, "end_date": day}
            # The default Weather and Pollution Summary demonstrates the March method update.
            if not custom_cases and name == TEMPLATE_NAMES[3]:
                params.update(start_date="2025-03-21", end_date="2025-03-23")
            result = make_briefing(name, params, demo, save=True)
            if not result.formal:
                failures.append({"title": result.title, "template_name": "Query data only",
                                 **result.outputs})
        reports = select(REPORT_SQL, db_path=demo)
    return reports + failures


def _publish_reports(root, reports):
    links = []
    for index, row in enumerate(reports, 1):
        stem = f"reports/briefing-{index:02d}"
        title = escape(row["title"])
        report = clean(row["html_output"], tags=(
            "div", "h2", "h3", "h4", "ul", "ol", "li", "p", "strong", "em",
            "code", "pre", "table", "thead", "tbody", "tr", "th", "td", "br", "blockquote",
        ), attributes={"*": ["class"]}, strip=True)
        body = (
            '<header><div class="wrap"><nav><a href="../index.html#reports">All briefings</a>'
            f'</nav><h1>{title}</h1></div></header><main class="wrap"><article>{report}'
            f'<p><a href="briefing-{index:02d}.md">Markdown version</a></p></article></main>'
        )
        _write(root, stem + ".html", _page(row["title"], body, "../"))
        _write(root, stem + ".md", row["markdown_output"] + "\n")
        links.append(f'<li><a href="{stem}.html">{title}</a><small>'
                     f'{escape(row["template_name"])} · <a href="{stem}.md">Markdown</a></small></li>')
    return "".join(links)


def _publish_examples(root, cases, db_path):
    sections, dates = [], []
    for index, case in enumerate(cases, 1):
        station, other, day, month = (case[key] for key in ("station_name", "station_b", "obs_date", "month"))
        key = f"date-{index:02d}"
        charts = []
        for suffix, plot, inputs, description in (
            ("hourly", plot_hourly_aqhi, (station, day), f"Hourly AQHI at {station}"),
            ("categories", plot_category_distribution, (station, day), f"Risk category counts at {station}"),
            ("comparison", plot_station_comparison, (station, other, day), f"{station} and {other} comparison"),
            ("monthly", plot_monthly_trend, (station, month), f"{month} daily maxima and pollutant trend"),
        ):
            path = f"assets/charts/{key}-{suffix}.png"
            plot(*inputs, root / path, db_path=db_path)
            charts.append(f'<figure><a href="{path}"><img loading="lazy" src="{path}" alt="{escape(description)}"></a></figure>')
        map_path = f"maps/{key}.html"
        build_district_map(day, root / map_path, db_path=db_path)
        dates.append(f'<a href="#{key}">{escape(day)}</a>')
        sections.append(
            f'<details id="{key}" open><summary>{escape(day)} · {escape(station)}</summary>'
            f'<div class="case-head"><p>Station setting comparison and {escape(month)} trend</p>'
            f'<a href="{map_path}">Explore the district map →</a></div><div class="charts">'
            + "".join(charts) + "</div></details>"
        )
    return "".join(dates), "".join(sections)


def _home(root, cases, db_path, *, custom_cases):
    dates, examples = _publish_examples(root, cases, db_path)
    report_links = _publish_reports(root, _demo_reports(db_path, cases, custom_cases=custom_cases))
    coverage = select(
        """SELECT MIN(obs_date) AS first_day, MAX(obs_date) AS last_day,
                  COUNT(*) AS aqhi_rows, COUNT(DISTINCT station_id) AS station_count,
                  (SELECT COUNT(*) FROM hourly_pollutants) AS pollutant_rows,
                  (SELECT COUNT(*) FROM daily_weather) AS weather_days
           FROM hourly_aqhi""", db_path=db_path,
    )[0]
    body = f"""
<header><div class="wrap">
<nav aria-label="Main"><a href="#coverage">Coverage</a><a href="#examples">Chart and map examples</a>
<a href="#reports">Briefings</a><a href="#methods">Methods and sources</a></nav>
<h1>Hong Kong Air Quality Briefing System</h1>
<p>Explore how hourly monitoring records become English briefings on station conditions,
risk categories and district coverage. HKBU AIDM7360 Groupby course project.</p>
</div></header>
<main class="wrap">
<section id="coverage"><h2>Monitoring coverage</h2>
<p>{coverage['first_day']} through {coverage['last_day']} · Hong Kong time</p>
<dl class="coverage">
<div><dt>Monitoring stations</dt><dd>{coverage['station_count']:,}</dd></div>
<div><dt>Hourly AQHI records</dt><dd>{coverage['aqhi_rows']:,}</dd></div>
<div><dt>Hourly pollutant records</dt><dd>{coverage['pollutant_rows']:,}</dd></div>
<div><dt>Daily weather records</dt><dd>{coverage['weather_days']:,}</dd></div>
</dl></section>
<section id="examples"><h2>Selected Pre-generated Examples</h2>
<p>These charts and maps show selected dates from the 2025 dataset. The full Python
Notebook (<code>main.ipynb</code>) supports interactive queries, briefings,
charts and district maps for any date in 2025.</p>
<nav class="date-links" aria-label="Observation dates">{dates}</nav>{examples}</section>
<section id="reports"><h2>Exported briefings</h2>
<ul class="report-list">{report_links}</ul></section>
<section id="methods"><h2>Methods and sources</h2>
<p>District colors show the highest valid hourly AQHI among General stations in each district.
Roadside readings appear in their own marker layer. The map distinguishes districts
without General stations from districts where General stations had no valid observations.</p>
<p>Charts keep observation hours 01–24 in the original day. AQHI averages use numeric
values 1–10. Serious readings are reported as 10+. Risk shares use valid hours,
and valid substitute readings are counted separately. {METHOD_NOTE}</p>
<p>AQHI and pollutant observations come from EPD. Weather is from the Hong Kong Observatory
and population is from the Census and Statistics Department. The map uses the supplied
Cydalytics district boundaries and the project's EPD station coordinates.</p>
<p><a href="{EPD}">EPD historical AQHI</a> · <a href="{EPD_FAQ}">EPD calculation update</a>
· <a href="README_EXPORT.md">Export instructions</a></p>
</section></main><footer class="wrap">Hong Kong Baptist University · Groupby</footer>
"""
    _write(root, "index.html", _page("Hong Kong Air Quality Briefing System", body))


# These names are reserved for numbered outputs from this exporter, including v1.
_GENERATED_FILES = {
    "assets/charts": re.compile(r"date-[0-9]{2,}-(hourly|categories|comparison|monthly)\.png"),
    "maps": re.compile(r"date-[0-9]{2,}\.html"),
    "reports": re.compile(r"briefing-[0-9]{2,}\.(html|md)"),
}


def _sync_output(staged, output):
    incoming = {path.relative_to(staged) for path in staged.rglob("*") if path.is_file()}
    targets = [output / name for name in incoming]
    managed_dirs = {output / name: pattern for name, pattern in _GENERATED_FILES.items()}
    # Prevent copies or cleanup through a link that points outside the output tree.
    for path in [*targets, *managed_dirs]:
        if not path.resolve().is_relative_to(output):
            raise ValueError(f"Export target resolves outside its output directory: {path}")
    stale = [
        path for directory, pattern in managed_dirs.items() if directory.is_dir()
        for path in directory.iterdir()
        if pattern.fullmatch(path.name) and path.is_file() and path.relative_to(output) not in incoming
    ]
    copytree(staged, output, dirs_exist_ok=True)
    for path in stale:
        path.unlink(missing_ok=True)


def export_static_site(db_path=DEFAULT_DB_PATH, output_dir=PROJECT_ROOT / "docs", demo_cases=None):
    """Export a verified static site. Return the absolute path to index.html.

    Each optional demo case provides station_name, station_b and obs_date.
    Optional month defaults to the observation date's month. With empty report
    history, custom cases generate a set of example briefings per case.
    Re-export removes obsolete numbered assets owned by this generator.
    The input DB is read-only and unseeded examples use a temporary snapshot.
    """
    output = Path(output_dir).resolve()
    custom_cases = demo_cases is not None
    cases = list(demo_cases if custom_cases else default_cases(db_path))
    if not cases:
        raise ValueError("Provide at least one demo case.")
    cases = [{**case, "month": case.get("month", case["obs_date"][:7])} for case in cases]
    with TemporaryDirectory(prefix="aqhi-site-") as work:
        root = Path(work)
        _write(root, ".nojekyll", "")
        _write(root, "assets/site.css", CSS)
        _write(root, "README_EXPORT.md", EXPORT_README)
        _home(root, cases, db_path, custom_cases=custom_cases)
        if errors := validate_site_links(root):
            raise ValueError("Broken relative links: " + ", ".join(errors))
        _sync_output(root, output)
    return output / "index.html"


if __name__ == "__main__":
    print(export_static_site())
