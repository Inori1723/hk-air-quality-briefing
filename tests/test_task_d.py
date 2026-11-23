"""Run with python -m pytest -v tests/test_task_d.py from the project root."""

from collections import Counter
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sys

import folium
import nbformat
from bs4 import BeautifulSoup
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient
from PIL import Image, ImageStat
import pytest

from src.queries import run_saved_query
from src.schema import DEFAULT_DB_PATH, PROJECT_ROOT, get_connection
from src.site_export import export_static_site, validate_site_links
from src.task_d_integration import (
    METHOD_NOTE, TEMPLATE_NAMES, default_cases, demo_database, make_briefing, select,
)
from src.viz import (
    HOURS, NO_GENERAL, NO_VALID, RISK_COLORS, build_district_map, hourly_data,
    plot_category_distribution, plot_hourly_aqhi, plot_monthly_trend, plot_station_comparison,
)

STATION = "Central/Western"
DAY = "2025-04-01"
SERIOUS = "2025-04-14"
PARAMS = dict(station_name=STATION, station_a=STATION, station_b="Central",
              obs_date=DAY, month="2025-03", start_date="2025-03-21", end_date="2025-03-23")


def digest(path):
    with Path(path).open("rb") as file:
        digest = hashlib.sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


@pytest.fixture
def demo():
    with demo_database() as db:
        yield db


@pytest.fixture
def empty_db(tmp_path):
    db = tmp_path / "empty-history.db"
    with closing(get_connection(DEFAULT_DB_PATH)) as source, closing(get_connection(db)) as target:
        source.backup(target)
        with target:
            target.execute("DELETE FROM generated_reports")
            target.execute("DELETE FROM report_templates")
            target.execute("DELETE FROM saved_queries")
    return db


def test_database_coverage():
    row = select("""
        SELECT (SELECT COUNT(*) FROM districts) AS districts,
               (SELECT COUNT(*) FROM stations WHERE station_type='General') AS general,
               (SELECT COUNT(*) FROM stations WHERE station_type='Roadside') AS roadside,
               (SELECT COUNT(*) FROM hourly_pollutants) AS pollutants,
               (SELECT COUNT(*) FROM daily_weather) AS weather,
               COUNT(*) AS aqhi, MIN(obs_date) AS first_day, MAX(obs_date) AS last_day,
               MIN(obs_hour) AS first_hour, MAX(obs_hour) AS last_hour,
               SUM(is_missing) AS missing, SUM(is_missing=0 AND is_substitute=1) AS substitutes
        FROM hourly_aqhi
    """)[0]
    assert list(row.values()) == [18, 15, 3, 157680, 365, 157680, "2025-01-01", "2025-12-31", 1, 24, 333, 3731]


def test_april1_sql_and_plot_series(demo):
    row, = run_saved_query("Q01_daily_briefing", PARAMS, demo)
    assert (row["valid_hours"], row["min_aqhi"], row["max_aqhi"]) == (24, "2", "4")
    assert row["peak_hours"] == "17:00, 18:00, 19:00, 20:00, 21:00"
    cats = run_saved_query("Q02_category_breakdown", PARAMS, demo)
    assert [r["hours"] for r in cats] == [19, 5, 0, 0, 0]
    assert [r["percentage"] for r in cats] == [79.2, 20.8, 0, 0, 0]
    day = hourly_data(STATION, DAY)
    assert day["peaks"] == [17, 18, 19, 20, 21]
    assert (min(day["positions"]), day["max_rank"]) == (2, 4)
    assert HOURS == tuple(range(1, 25))


def test_serious_and_missing(demo):
    row, = run_saved_query("Q01_daily_briefing", {**PARAMS, "obs_date": SERIOUS}, demo)
    assert (row["max_aqhi"], row["valid_hours"], row["numeric_aqhi_hours"], row["valid_pm25_hours"]) == ("10+", 24, 21, 7)
    data = hourly_data(STATION, SERIOUS, demo)
    assert data["counts"]["Serious"] == 3
    assert max(data["positions"]) == 11
    assert select("""
        SELECT COUNT(*) AS n FROM hourly_aqhi h JOIN stations s USING(station_id)
        WHERE s.name = ? AND h.obs_date = ? AND raw_value = '10+' AND sort_rank = 11
        AND numeric_value IS NULL AND is_missing = 0
    """, (STATION, SERIOUS), demo)[0]["n"] == 3
    tap = hourly_data("Tap Mun", "2025-08-05", demo)
    assert (tap["valid"], tap["missing"], sum(math.isnan(x) for x in tap["positions"])) == (10, 14, 14)
    assert all(math.isnan(x) or x >= 1 for x in tap["positions"])
    assert tap["substitute"] == select("""
        SELECT SUM(is_missing=0 AND is_substitute=1) AS n FROM hourly_aqhi h
        JOIN stations s USING(station_id) WHERE s.name=? AND h.obs_date=?
    """, ("Tap Mun", "2025-08-05"), demo)[0]["n"]


def check_png(path):
    with Image.open(path) as img:
        img.load()
        assert img.format == "PNG"
        assert img.width >= 2400 and img.height >= 800
        assert img.info["dpi"][0] == pytest.approx(300, abs=0.1)
        assert max(ImageStat.Stat(img.convert("RGB")).stddev) > 8


@pytest.mark.parametrize(("plot", "args"), [
    (plot_hourly_aqhi, (STATION, DAY)),
    (plot_hourly_aqhi, (STATION, SERIOUS)),
    (plot_hourly_aqhi, ("Tap Mun", "2025-08-05")),
    (plot_category_distribution, (STATION, DAY)),
    (plot_category_distribution, (STATION, "2026-01-01")),
    (plot_station_comparison, (STATION, "Central", SERIOUS)),
    (plot_monthly_trend, (STATION, "2025-03")),
])
def test_pngs(plot, args, tmp_path):
    check_png(plot(*args, tmp_path / "out.png"))


def test_chart_artists_preserve_gaps_serious_ticks_and_method_date(tmp_path, monkeypatch):
    from matplotlib.figure import Figure
    charts = []
    real_save = Figure.savefig

    def capture(fig, *args, **kwargs):
        charts.append(fig)
        return real_save(fig, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", capture)
    plot_hourly_aqhi("Tap Mun", "2025-08-05", tmp_path / "gaps.png")
    ax = charts[-1].axes[0]
    assert sum(math.isnan(x) for x in ax.lines[0].get_ydata()) == 14
    assert len(ax.patches) == 5
    assert [t.get_text() for t in ax.get_xticklabels()] == [f"{h:02d}" for h in HOURS]
    assert [t.get_text() for t in ax.get_yticklabels()][-1] == "10+"
    plot_monthly_trend(STATION, "2025-03", tmp_path / "ozone.png", pollutant="o3")
    assert len(charts[-1].axes) == 2
    for panel in charts[-1].axes:
        assert any(list(line.get_xdata()) == [22, 22] and line.get_linestyle() == "--" for line in panel.lines)
    assert any("method update" in label.get_text() for label in charts[-1].axes[0].texts)
    assert "pollutant concentrations" in " ".join(t.get_text() for t in charts[-1].texts)
    check_png(tmp_path / "ozone.png")


def test_map_saved_query_layers_and_tai_po(demo, tmp_path):
    rows = run_saved_query("Q05_district_map", {"obs_date": SERIOUS}, demo)
    assert Counter(r["row_type"] for r in rows) == {"district": 18, "roadside": 3}
    target = tmp_path / "map.html"
    fmap = build_district_map(SERIOUS, target, db_path=demo)
    assert fmap.task_d_query_source.startswith("saved_queries")
    geo, = [layer for layer in fmap._children.values() if isinstance(layer, folium.GeoJson)]
    districts = {f["properties"]["name_1"]: f for f in geo.data["features"]}
    assert len(districts) == 18
    assert all(f["geometry"]["type"] in {"Polygon", "MultiPolygon"} and f["geometry"]["coordinates"]
               for f in districts.values())
    no_general = {name for name, f in districts.items() if f["properties"]["status"] == "No general station"}
    assert no_general == {"Wan Chai", "Yau Tsim Mong", "Kowloon City", "Wong Tai Sin"}
    assert all(geo.style_function(districts[name])["fillColor"] == NO_GENERAL for name in no_general)
    maxima = select("""
        SELECT MAX(h.sort_rank) AS peak FROM hourly_aqhi h JOIN stations s USING(station_id)
        JOIN districts d USING(district_id) WHERE h.obs_date = ? AND d.english_name = ?
        AND s.station_type = 'General' AND h.is_missing = 0 GROUP BY s.station_id
    """, (SERIOUS, "Tai Po"), demo)
    assert len(maxima) == 2 and max(r["peak"] for r in maxima) == 11
    assert districts["Tai Po"]["properties"]["maximum"] == "10+"
    assert geo.style_function(districts["Tai Po"])["fillColor"] == RISK_COLORS["Serious"]
    groups = {child.layer_name: child for child in fmap._children.values()
              if isinstance(child, folium.FeatureGroup)}
    for group, count in (("General stations", 15), ("Roadside stations", 3)):
        markers = [marker for marker in groups[group]._children.values()
                   if isinstance(marker, folium.CircleMarker)]
        assert len(markers) == count
        expected = select("SELECT latitude, longitude FROM stations WHERE station_type = ?",
                          (group.split()[0],), demo)
        assert Counter(tuple(marker.location) for marker in markers) == Counter(
            (row["latitude"], row["longitude"]) for row in expected)
    html = target.read_text(encoding="utf-8")
    assert all(s in html for s in ("Causeway Bay", "Central", "Mong Kok", "Population reference",
                                  "L.control.layers", NO_GENERAL, NO_VALID, "Serious"))


def test_map_empty_valid_data_and_unseeded_fallback(empty_db):
    fmap = build_district_map("2026-01-01", db_path=empty_db)
    assert fmap.task_d_query_source.startswith("direct parameterized")
    geo = next(layer for layer in fmap._children.values() if isinstance(layer, folium.GeoJson))
    counts = Counter((f["properties"]["status"], f["properties"]["fill"]) for f in geo.data["features"])
    assert counts == {("No general station", NO_GENERAL): 4, ("No valid data", NO_VALID): 14}


@pytest.mark.parametrize("template", TEMPLATE_NAMES)
def test_templates_use_real_results_and_persist(template, demo):
    params = PARAMS.copy()
    if template == TEMPLATE_NAMES[6]:
        params.update(start_date=SERIOUS, end_date=SERIOUS)
    if template in (TEMPLATE_NAMES[4], TEMPLATE_NAMES[7]):
        params["obs_date"] = SERIOUS
    result = make_briefing(template, params, demo, save=True)
    assert result.formal and result.report_id and result.rows
    row, = select("SELECT * FROM generated_reports WHERE report_id = ?", (result.report_id,), demo)
    for fmt, output in result.outputs.items():
        assert output == row[fmt] and output.strip()
        assert "Template Render Error" not in output
    text = row["text_output"]
    expected = {
        TEMPLATE_NAMES[0]: ("24/24", "Min 2 | Max 4", "17:00, 18:00, 19:00, 20:00, 21:00"),
        TEMPLATE_NAMES[1]: ("19 hrs", "5 hrs", "79.2%", "20.8%"),
        TEMPLATE_NAMES[2]: ("Central/Western (General)", "Central (Roadside)", "High-or-above"),
        TEMPLATE_NAMES[3]: (METHOD_NOTE, "PM2.5", "Valid concentration measurements"),
        TEMPLATE_NAMES[4]: ("Tai Po", "10+", "14 districts"),
        TEMPLATE_NAMES[5]: ("744", METHOD_NOTE, "numeric hours"),
        TEMPLATE_NAMES[6]: ("2025-04-14", "Total High Risk Hours (AQHI >= 7):"),
        TEMPLATE_NAMES[7]: ("Territory Max AQHI Reached: 10+", "15 General stations"),
    }
    assert all(fragment in text for fragment in expected[template])
    if template == TEMPLATE_NAMES[6]:
        assert f': {result.rows[0]["high_or_above_hours"]}' in text
    if template == TEMPLATE_NAMES[3]:
        expected_mean, = select("""
            SELECT ROUND(AVG(p.pm25),2) AS mean FROM hourly_pollutants p JOIN stations s USING(station_id)
            WHERE s.name=? AND p.obs_date BETWEEN ? AND ?
        """, (STATION, PARAMS["start_date"], PARAMS["end_date"]), demo)
        assert f'PM2.5: {expected_mean["mean"]} ug/m3' in text


def test_no_high_vs_no_observations_and_bad_inputs(demo, tmp_path):
    name = TEMPLATE_NAMES[6]
    low = make_briefing(name, {**PARAMS, "start_date": DAY, "end_date": DAY}, demo)
    assert low.formal and "No valid observations reached" in low.outputs["text_output"]
    none = make_briefing(name, {**PARAMS, "start_date": "2026-01-01", "end_date": "2026-01-01"}, demo, save=True)
    assert not none.formal and none.report_id is None
    assert "Query data only" in none.outputs["text_output"]
    with pytest.raises(ValueError, match="Unknown station"):
        hourly_data("station' OR 1=1 --", DAY)
    with pytest.raises(ValueError, match="YYYY"):
        hourly_data(STATION, "2025-02-30")
    with pytest.raises(ValueError, match="different"):
        plot_station_comparison(STATION, STATION, DAY, tmp_path / "out.png")
    with pytest.raises(ValueError, match="temporary"):
        make_briefing(name, PARAMS, DEFAULT_DB_PATH, save=True)


def test_template_defect_is_not_saved(demo):
    before_count = select("SELECT COUNT(*) AS n FROM generated_reports", db_path=demo)[0]["n"]
    with closing(get_connection(demo)) as conn, conn:
        conn.execute("UPDATE report_templates SET text_template = ? WHERE name = ?",
                     ("{unavailable_metric}", TEMPLATE_NAMES[0]))
    result = make_briefing(TEMPLATE_NAMES[0], PARAMS, demo, save=True)
    assert not result.formal and len(result.rows) == 1 and result.report_id is None
    assert "unavailable_metric" in result.outputs["text_output"]
    assert select("SELECT COUNT(*) AS n FROM generated_reports", db_path=demo)[0]["n"] == before_count


def test_site_from_empty_history_and_relative_links(empty_db, tmp_path):
    before = digest(DEFAULT_DB_PATH), digest(empty_db)
    index = export_static_site(empty_db, tmp_path / "site")
    root = index.parent
    assert index.is_file() and not validate_site_links(root)
    assert (root / ".nojekyll").is_file()
    assert (root / "assets/site.css").is_file() and (root / "README_EXPORT.md").is_file()
    assert len(list((root / "reports").glob("*.html"))) == 8
    assert len(list((root / "reports").glob("*.md"))) == 8
    assert len(list((root / "maps").glob("*.html"))) == 2
    charts = list((root / "assets/charts").glob("*.png"))
    assert len(charts) == 8
    for chart in charts:
        check_png(chart)
    html = BeautifulSoup(index.read_text(encoding="utf-8"), "html.parser")
    assert all(f"{s:,}" in html.get_text() for s in (157680, 365, 18))
    assert html.find("meta", attrs={"name": "viewport"})
    assert html.select_one("#date-01") and html.select_one("#date-02")
    assert not list(root.rglob("*.db"))
    assert before == (digest(DEFAULT_DB_PATH), digest(empty_db))


def test_site_uses_existing_history(demo, tmp_path):
    with closing(get_connection(demo)) as conn, conn:
        conn.execute("DELETE FROM generated_reports")
    result = make_briefing(TEMPLATE_NAMES[0], PARAMS, demo, save=True)
    assert result.formal
    before = digest(demo)
    index = export_static_site(demo, tmp_path / "existing", default_cases(demo)[:1])
    reports = list((index.parent / "reports").glob("*.md"))
    assert len(reports) == 1 and reports[0].read_text(encoding="utf-8").strip() == result.outputs["markdown_output"].strip()
    assert before == digest(demo)
    assert not validate_site_links(index.parent)


def execute_task_d_notebook(tmp_path, monkeypatch, disable_widgets, extend):
    if disable_widgets:
        monkeypatch.setenv("AQHI_DISABLE_WIDGETS", "1")
    else:
        monkeypatch.delenv("AQHI_DISABLE_WIDGETS", raising=False)
    spec = tmp_path / "kernels" / "task-d"
    spec.mkdir(parents=True)
    (spec / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Task D", "language": "python",
    }), encoding="utf-8")
    manager = KernelManager(kernel_name="task-d", kernel_spec_manager=KernelSpecManager(
        kernel_dirs=[str(spec.parent)], ensure_native_kernel=False,
    ))
    path = PROJECT_ROOT / "task_d_demo.ipynb"
    nb = nbformat.read(path, as_version=4)
    nbformat.validate(nb)
    extend(nb)
    nbformat.validate(nb)
    before = digest(DEFAULT_DB_PATH)
    executed = NotebookClient(nb, km=manager, timeout=180,
                              resources={"metadata": {"path": str(PROJECT_ROOT)}}).execute()
    cells = [cell for cell in executed.cells if cell.cell_type == "code"]
    assert all(cell.execution_count for cell in cells)
    outputs = [item for cell in cells for item in cell.outputs]
    assert not any(item.output_type == "error" for item in outputs)
    assert before == digest(DEFAULT_DB_PATH)
    return outputs


@pytest.mark.parametrize("disable_widgets", [False, True], ids=["widgets", "parameter-fallback"])
def test_notebook_executes(tmp_path, monkeypatch, disable_widgets):
    def run_optional_examples(nb):
        nb.cells.append(nbformat.v4.new_code_cell("show_example_maps()"))

    outputs = execute_task_d_notebook(tmp_path, monkeypatch, disable_widgets, run_optional_examples)
    stream = "".join(item.get("text", "") for item in outputs)
    assert "formal template" in stream and "Verified static index" in stream
    assert "2025-04-01" in stream and "2025-04-14" in stream
    assert sum("image/png" in item.get("data", {}) for item in outputs) == 4
    # One selected map from the parameter cell and two explicitly run examples.
    assert sum("<iframe" in item.get("data", {}).get("text/html", "") for item in outputs) == 3
    widget_view = [item for item in outputs if "application/vnd.jupyter.widget-view+json" in item.get("data", {})]
    assert bool(widget_view) != disable_widgets



def test_custom_site_dates_and_reexport_cleanup(empty_db, tmp_path):
    output = tmp_path / "custom-site"
    january_case = {"station_name": STATION, "station_b": "Central", "obs_date": "2025-01-02"}
    july_case = {**january_case, "obs_date": "2025-07-16"}
    before = digest(empty_db)
    index = export_static_site(empty_db, output, [january_case, july_case])
    page = BeautifulSoup(index.read_text(encoding="utf-8"), "html.parser")
    examples = page.select_one("#examples")
    assert examples.h2.get_text() == "Selected Pre-generated Examples"
    assert "any date in 2025" in examples.p.get_text(" ", strip=True)
    assert [link.get_text() for link in examples.select("nav a")] == ["2025-01-02", "2025-07-16"]
    assert len(list((output / "maps").glob("*.html"))) == 2
    assert len(list((output / "assets/charts").glob("*.png"))) == 8
    assert len(list((output / "reports").glob("*.md"))) == 16
    for idx, day in enumerate(("2025-01-02", "2025-07-16"), 1):
        raw_map = (output / f"maps/date-{idx:02d}.html").read_text(encoding="utf-8")
        assert f"<div>{day}</div>" in raw_map
        assert day[:7] in examples.select("details")[idx - 1].get_text()
        assert any(f"Air Quality Briefing: {STATION} ({day})" in path.read_text(encoding="utf-8")
                   for path in (output / "reports").glob("*.md"))
    assert not validate_site_links(output)

    legacy_guide = output / "maps" / "field-notes.md"
    legacy_guide.write_text("Keep this file.", encoding="utf-8")
    export_static_site(empty_db, output, [july_case])
    assert [p.name for p in (output / "maps").glob("*.html")] == ["date-01.html"]
    assert len(list((output / "assets/charts").glob("*.png"))) == 4
    assert len(list((output / "reports").glob("*.md"))) == 8
    assert len(list((output / "reports").glob("*.html"))) == 8
    assert "<div>2025-07-16</div>" in (output / "maps/date-01.html").read_text(encoding="utf-8")
    assert "2025-01-02" not in index.read_text(encoding="utf-8")
    assert legacy_guide.read_text(encoding="utf-8") == "Keep this file."
    assert not validate_site_links(output)
    assert digest(empty_db) == before


@pytest.mark.parametrize("disable_widgets", [False, True], ids=["widgets", "parameter-fallback"])
def test_notebook_uses_selected_dates(tmp_path, monkeypatch, disable_widgets):
    dates = ("2025-01-02", "2025-07-16", "2025-12-31")

    def add_selection_checks(nb):
        parameters = next(cell.source for cell in nb.cells if cell.cell_type == "code"
                          and "# Edit these values" in cell.source)
        nb.cells.append(nbformat.v4.new_code_cell(
            f"selected_dates = {dates!r}\nparameter_source = {parameters!r}\n" + """
from datetime import date, timedelta
from unittest.mock import patch

import folium
from matplotlib.figure import Figure
from src.queries import run_saved_query

year_days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(365)]
assert dates == year_days
if widgets is not None:
    assert tuple(controls["day"].options) == tuple(year_days)
    assert map_button.description == "Show District Map"

images = []
shown = []
real_savefig = Figure.savefig

def trace_savefig(fig, path, **kwargs):
    images.append((fig.axes[0].get_title(loc="left"), Path(path)))
    return real_savefig(fig, path, **kwargs)

def capture_display(*items, **kwargs):
    shown.extend(items)

for selected_day in selected_dates:
    shown.clear()
    images.clear()
    with patch.dict(globals(), {"display": capture_display}), patch.object(Figure, "savefig", trace_savefig):
        if widgets is None:
            # Rerun the original parameter cell with the editable dates changed.
            selection_code = parameter_source.replace(
                'day=first["obs_date"], month=first["month"]',
                f'day={selected_day!r}, month={selected_day[:7]!r}',
            )
            exec(selection_code)
        else:
            controls["day"].value = selected_day
            controls["month"].value = selected_day[:7]
            briefing_button.click()
            chart_button.click()
            map_button.click()
    html, = [item.data for item in shown if isinstance(item, HTML)]
    row, = run_saved_query("Q01_daily_briefing", {
        "station_name": first["station_name"], "obs_date": selected_day,
    }, demo_db)
    assert selected_day in html and row["peak_hours"] in html
    assert f'{row["valid_hours"]}/24' in html
    assert len(images) == 4 and len([item for item in shown if isinstance(item, Image)]) == 4
    assert all(selected_day in title and path.is_file() for title, path in images[:3])
    assert selected_day[:7] in images[3][0] and images[3][1].is_file()

    fmap, = [item for item in shown if isinstance(item, folium.Map)]
    saved_map = work / f"districts-{selected_day}.html"
    assert f"<div>{selected_day}</div>" in saved_map.read_text(encoding="utf-8")
    layer, = [item for item in fmap._children.values() if isinstance(item, folium.GeoJson)]
    district_maxima = {f["properties"]["name_1"]: f["properties"]["maximum"]
                       for f in layer.data["features"]}
    expected = run_saved_query("Q05_district_map", {"obs_date": selected_day}, demo_db)
    assert len(district_maxima) == 18
    assert district_maxima == {row["district_name"]: row["max_aqhi"] or "N/A (not available)"
                              for row in expected if row["row_type"] == "district"}
    print(f"Verified selected date {selected_day}")
"""
        ))

    outputs = execute_task_d_notebook(tmp_path, monkeypatch, disable_widgets, add_selection_checks)
    stream = "".join(item.get("text", "") for item in outputs)
    assert all(f"Verified selected date {day}" in stream for day in dates)
