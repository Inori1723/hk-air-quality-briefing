"""End-to-end integration tests for consolidated database, CRUD, templates, main.ipynb, and docs."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import folium
import nbformat
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient
import pytest

from src import crud
from src.etl import run_full_etl
from src.queries import seed_saved_queries
from src.schema import DEFAULT_DB_PATH, PROJECT_ROOT, get_connection, init_db
from src.site_export import validate_site_links
from src.templates import (
    DEFAULT_TEMPLATES,
    METHOD_NOTE,
    TEMPLATE_NAMES,
    export_report_files,
    generate_report,
    render_report_templates,
    seed_report_templates,
)
from src.viz import build_district_map


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "integration_copy.db"
    with closing(get_connection(DEFAULT_DB_PATH)) as src, closing(get_connection(db)) as dst:
        src.backup(dst)
    return db


def test_seeded_database_table_counts():
    expected = {
        "districts": 18,
        "stations": 18,
        "hourly_aqhi": 157680,
        "hourly_pollutants": 157680,
        "daily_weather": 365,
        "saved_queries": 9,
        "report_templates": 8,
        "generated_reports": 8,
    }
    with closing(get_connection(DEFAULT_DB_PATH)) as conn:
        actual = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in expected
        }
    assert actual == expected


def test_full_eight_table_crud_and_fk_protection(temp_db: Path):
    def roundtrip(create_fn, get_fn, update_fn, delete_fn, fields, changes):
        row_id = create_fn(db_path=temp_db, **fields)
        created = get_fn(row_id, db_path=temp_db)
        assert created is not None
        assert update_fn(row_id, db_path=temp_db, **changes)
        updated = get_fn(row_id, db_path=temp_db)
        assert all(updated[k] == v for k, v in changes.items())
        assert delete_fn(row_id, db_path=temp_db)
        assert get_fn(row_id, db_path=temp_db) is None

    with closing(get_connection(temp_db)) as conn:
        station_id = conn.execute("SELECT station_id FROM stations LIMIT 1").fetchone()[0]
        district_id = conn.execute("SELECT district_id FROM districts LIMIT 1").fetchone()[0]
        query_id = conn.execute("SELECT query_id FROM saved_queries LIMIT 1").fetchone()[0]

    roundtrip(
        crud.create_district, crud.get_district, crud.update_district, crud.delete_district,
        {"district_code": "INT_D", "english_name": "Integration District", "region": "Kowloon"},
        {"area_sqkm": 4.2},
    )
    roundtrip(
        crud.create_station, crud.get_station, crud.update_station, crud.delete_station,
        {"code": "INT_S", "name": "Integration Station", "station_type": "General", "district_id": district_id},
        {"latitude": 22.31},
    )
    roundtrip(
        crud.create_hourly_aqhi, crud.get_hourly_aqhi, crud.update_hourly_aqhi, crud.delete_hourly_aqhi,
        {"station_id": station_id, "obs_date": "2099-02-01", "obs_hour": 12, "raw_value": "5*"},
        {"raw_value": "10+", "numeric_value": None, "sort_rank": 11, "category": "Serious", "is_substitute": 0},
    )
    roundtrip(
        crud.create_hourly_pollutant, crud.get_hourly_pollutant, crud.update_hourly_pollutant, crud.delete_hourly_pollutant,
        {"station_id": station_id, "obs_date": "2099-02-01", "obs_hour": 12, "pm25": 10.0, "pm25_unit": "ug/m3"},
        {"pm25": 15.5},
    )
    roundtrip(
        crud.create_daily_weather, crud.get_daily_weather, crud.update_daily_weather, crud.delete_daily_weather,
        {"obs_date": "2099-02-01", "mean_temp_c": 20.0},
        {"rainfall_mm": 0.5},
    )
    roundtrip(
        crud.create_saved_query, crud.get_saved_query, crud.update_saved_query, crud.delete_saved_query,
        {"query_code": "INT_Q", "name": "Integration Query", "sql_text": "SELECT 1", "parameter_names": "[]"},
        {"description": "Integration test"},
    )
    tpl_fields = {
        "query_id": query_id,
        "name": "Integration Template",
        "scope": "territory",
        "required_variables": json.dumps(["max_aqhi"]),
        "text_template": "AQHI {max_aqhi}",
        "markdown_template": "**AQHI {max_aqhi}**",
        "html_template": "<p>AQHI {max_aqhi}</p>",
    }
    roundtrip(
        crud.create_report_template, crud.get_report_template, crud.update_report_template, crud.delete_report_template,
        tpl_fields,
        {"version": "2.0"},
    )

    tpl_id = crud.create_report_template(db_path=temp_db, **tpl_fields)
    rep_id = crud.create_generated_report(
        db_path=temp_db,
        template_id=tpl_id,
        station_id=None,
        title="FK Test Report",
        parameter_values=json.dumps({"obs_date": "2025-04-14"}),
        reporting_period="2025-04-14",
        text_output="AQHI 10+",
        markdown_output="**AQHI 10+**",
        html_output="<p>AQHI 10+</p>",
    )
    assert crud.get_generated_report(rep_id, db_path=temp_db)["station_id"] is None
    assert crud.update_generated_report(rep_id, db_path=temp_db, title="FK Test Report Updated")

    with pytest.raises(crud.ReferencedRowError):
        crud.delete_report_template(tpl_id, db_path=temp_db)

    assert crud.delete_generated_report(rep_id, db_path=temp_db)
    assert crud.delete_report_template(tpl_id, db_path=temp_db)


def test_seed_report_templates_requires_queries_and_preserves_ids(tmp_path: Path, temp_db: Path):
    blank = tmp_path / "blank.db"
    init_db(blank)
    with pytest.raises(KeyError, match="seed_saved_queries"):
        seed_report_templates(blank)

    seed_saved_queries(blank)
    assert seed_report_templates(blank) == 8

    with closing(get_connection(temp_db)) as conn:
        before_ids = [
            (r["template_id"], r["name"])
            for r in conn.execute("SELECT template_id, name FROM report_templates ORDER BY template_id")
        ]
    seed_report_templates(temp_db)
    with closing(get_connection(temp_db)) as conn:
        after_ids = [
            (r["template_id"], r["name"])
            for r in conn.execute("SELECT template_id, name FROM report_templates ORDER BY template_id")
        ]
    assert before_ids == after_ids


def test_generate_report_all_templates_escaping_and_edge_cases(temp_db: Path, tmp_path: Path):
    cases = [
        ("Daily Station Briefing", {"station_name": "Central/Western", "obs_date": "2025-04-01"}),
        ("Daily Category Breakdown", {"station_name": "Central/Western", "obs_date": "2025-04-01"}),
        ("Comparison of Two Stations", {"station_a": "Central/Western", "station_b": "Central", "obs_date": "2025-04-01"}),
        ("Weather and Pollution Summary", {"station_name": "Central/Western", "start_date": "2025-03-21", "end_date": "2025-03-23"}),
        ("District Map Report", {"obs_date": "2025-04-14"}),
        ("Monthly Station Summary", {"station_name": "Central/Western", "month": "2025-03"}),
        ("High Risk Episode Bulletin", {"station_name": "Central/Western", "start_date": "2025-04-14", "end_date": "2025-04-14"}),
        ("Air Quality News Flash", {"obs_date": "2025-04-14"}),
    ]
    assert [name for name, _ in cases] == list(TEMPLATE_NAMES)

    for name, params in cases:
        preview = generate_report(name, params, save=False, db_path=temp_db)
        assert preview["formal"] is True and preview["report_id"] is None
        assert preview["text_output"].strip()
        assert preview["markdown_output"].strip()
        assert preview["html_output"].strip()

        saved_id = generate_report(name, params, save=True, db_path=temp_db)
        assert isinstance(saved_id, int)
        row = crud.get_generated_report(saved_id, db_path=temp_db)
        assert row is not None and row["text_output"] == preview["text_output"]

        if name in ("Weather and Pollution Summary", "Monthly Station Summary"):
            assert METHOD_NOTE in row["text_output"]
            assert "Pre-22 Mar" in row["text_output"]
            assert "From 22 Mar" in row["text_output"]
        if name == "District Map Report":
            assert row["station_id"] is None
            assert "Wan Chai" in row["text_output"]
            assert "Yau Tsim Mong" in row["text_output"]
        if name == "Weather and Pollution Summary":
            assert "CO:" in row["text_output"]
            assert "10 ug/m3" in row["text_output"]
            assert "do not establish causation" in row["text_output"]
        if name == "High Risk Episode Bulletin":
            assert "High (7):" in row["text_output"]
            assert "Very high (8-10):" in row["text_output"]
            assert "Serious (10+):" in row["text_output"]

    exported = export_report_files(saved_id, out_dir=tmp_path / "exp", db_path=temp_db)
    assert all(Path(p).is_file() for p in exported.values())

    # Zero high-risk hours vs out-of-coverage date
    low_day = generate_report(
        "High Risk Episode Bulletin",
        {"station_name": "Central/Western", "start_date": "2025-04-01", "end_date": "2025-04-01"},
        save=False,
        db_path=temp_db,
    )
    assert low_day["formal"] is True
    assert "No valid observations reached AQHI 7 or above" in low_day["text_output"]

    with closing(get_connection(temp_db)) as conn:
        count_before = conn.execute("SELECT COUNT(*) FROM generated_reports").fetchone()[0]
    missing_day = generate_report(
        "Daily Station Briefing",
        {"station_name": "Central/Western", "obs_date": "2026-01-01"},
        save=True,
        db_path=temp_db,
    )
    with closing(get_connection(temp_db)) as conn:
        count_after = conn.execute("SELECT COUNT(*) FROM generated_reports").fetchone()[0]
    assert missing_day["formal"] is False and missing_day["report_id"] is None
    assert count_before == count_after

    # HTML escaping check on direct rendering
    rendered = render_report_templates(
        DEFAULT_TEMPLATES[0],
        {
            "station_name": "Central & Western <Test>",
            "obs_date": "2025-04-01",
            "valid_hours": 24,
            "min_aqhi": 2,
            "max_aqhi": 11,
            "peak_hours": None,
            "weather_note": "<script>alert(1)</script>",
            "cross_2025_03_22_note": "",
        },
        escape_html=True,
    )
    assert "10+ (Serious)" in rendered["text_output"]
    assert "None recorded" in rendered["text_output"]
    assert "<script>" not in rendered["html_output"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered["html_output"]
    assert "Central &amp; Western &lt;Test&gt;" in rendered["html_output"]


def test_full_etl_rebuild_closes_connections():
    with TemporaryDirectory(prefix="aqhi-etl-test-") as td:
        rebuilt = Path(td) / "rebuilt.db"
        summary = run_full_etl(db_path=rebuilt, reset_db=True)
        assert summary["aqhi"]["total_inserted"] == 157680
        assert summary["aqhi"]["daily_max_mismatches"] == []
        assert summary["extra"]["districts_updated"] == 18
        assert summary["extra"]["stations_updated"] == 18
        assert summary["extra"]["weather_days_inserted"] == 365
        assert summary["extra"]["pollutants_rows_inserted"] == 157680
        assert summary["saved_queries_seeded"] == 9
        assert summary["report_templates_seeded"] == 8


def test_district_map_tooltip_includes_population_for_unmonitored_districts():
    fmap = build_district_map("2025-04-14")
    geo = next(layer for layer in fmap._children.values() if isinstance(layer, folium.GeoJson))
    by_name = {f["properties"]["name_1"]: f["properties"] for f in geo.data["features"]}
    for district in ("Kowloon City", "Wong Tai Sin"):
        props = by_name[district]
        assert props["population"] not in ("", "N/A")
        assert "km²" in props["area_sqkm"]
        assert "2025" in props["population_ref"]


def test_published_docs_directory():
    docs = PROJECT_ROOT / "docs"
    index = docs / "index.html"
    assert (docs / ".nojekyll").is_file()
    assert index.is_file()
    assert "main.ipynb" in index.read_text(encoding="utf-8")
    assert len(list((docs / "reports").glob("*.html"))) == 8
    assert len(list((docs / "reports").glob("*.md"))) == 8
    assert len(list((docs / "assets" / "charts").glob("*.png"))) == 8
    assert len(list((docs / "maps").glob("*.html"))) == 2
    assert validate_site_links(docs) == []


@pytest.mark.parametrize("disable_widgets", [False, True], ids=["widgets", "parameter-fallback"])
def test_main_notebook_executes_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disable_widgets: bool):
    if disable_widgets:
        monkeypatch.setenv("AQHI_DISABLE_WIDGETS", "1")
    else:
        monkeypatch.delenv("AQHI_DISABLE_WIDGETS", raising=False)

    spec = tmp_path / "kernels" / "main-nb"
    spec.mkdir(parents=True)
    (spec / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                "display_name": "Groupby Main",
                "language": "python",
            }
        ),
        encoding="utf-8",
    )
    manager = KernelManager(
        kernel_name="main-nb",
        kernel_spec_manager=KernelSpecManager(
            kernel_dirs=[str(spec.parent)],
            ensure_native_kernel=False,
        ),
    )

    nb = nbformat.read(PROJECT_ROOT / "main.ipynb", as_version=4)
    nbformat.validate(nb)

    before_hash = _sha256(DEFAULT_DB_PATH)
    executed = NotebookClient(
        nb,
        km=manager,
        timeout=180,
        resources={"metadata": {"path": str(PROJECT_ROOT)}},
    ).execute()

    code_cells = [c for c in executed.cells if c.cell_type == "code"]
    assert all(c.execution_count for c in code_cells)
    outputs = [item for c in code_cells for item in c.outputs]
    assert not any(item.output_type == "error" for item in outputs)

    stream = "".join(item.get("text", "") for item in outputs)
    assert "[CRUD PASS]" in stream
    assert "[FK PROTECTION PASS]" in stream
    assert "Verified static site index" in stream
    assert sum("image/png" in item.get("data", {}) for item in outputs) == 4
    assert sum("<iframe" in item.get("data", {}).get("text/html", "") for item in outputs) == 1
    assert _sha256(DEFAULT_DB_PATH) == before_hash
