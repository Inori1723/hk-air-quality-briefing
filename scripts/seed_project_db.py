"""Seed saved_queries, report_templates, and default generated_reports in air_quality.db."""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.queries import seed_saved_queries
from src.schema import DEFAULT_DB_PATH, get_connection
from src.templates import generate_report, seed_report_templates

SHOWCASE_REPORTS: tuple[tuple[str, dict], ...] = (
    (
        "Daily Station Briefing",
        {"station_name": "Central/Western", "obs_date": "2025-04-01"},
    ),
    (
        "Daily Category Breakdown",
        {"station_name": "Central/Western", "obs_date": "2025-04-01"},
    ),
    (
        "Comparison of Two Stations",
        {"station_a": "Central/Western", "station_b": "Central", "obs_date": "2025-04-01"},
    ),
    (
        "Weather and Pollution Summary",
        {"station_name": "Central/Western", "start_date": "2025-03-21", "end_date": "2025-03-23"},
    ),
    (
        "District Map Report",
        {"obs_date": "2025-04-14"},
    ),
    (
        "Monthly Station Summary",
        {"station_name": "Central/Western", "month": "2025-03"},
    ),
    (
        "High Risk Episode Bulletin",
        {"station_name": "Central/Western", "start_date": "2025-04-14", "end_date": "2025-04-14"},
    ),
    (
        "Air Quality News Flash",
        {"obs_date": "2025-04-14"},
    ),
)

_EXPECTED_BASE_COUNTS = {
    "districts": 18,
    "stations": 18,
    "hourly_aqhi": 157680,
    "hourly_pollutants": 157680,
    "daily_weather": 365,
}


def seed_all(db_path: Path | str = DEFAULT_DB_PATH, refresh_reports: bool = False) -> dict[str, int]:
    """Verify base tables and idempotently seed saved_queries, report_templates, and reports."""
    path = Path(db_path)
    with closing(get_connection(path)) as conn:
        for table, expected in _EXPECTED_BASE_COUNTS.items():
            actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if actual != expected:
                raise RuntimeError(
                    f"Unexpected row count in {table}: expected {expected}, got {actual}."
                )

    seed_saved_queries(path)
    seed_report_templates(path)

    showcase_keys = {
        (template_name, json.dumps(params, sort_keys=True))
        for template_name, params in SHOWCASE_REPORTS
    }

    with closing(get_connection(path)) as conn, conn:
        existing_rows = conn.execute(
            """SELECT r.report_id, t.name AS template_name, r.parameter_values
               FROM generated_reports r
               JOIN report_templates t USING(template_id)"""
        ).fetchall()
        if refresh_reports:
            stale_ids = [
                (row["report_id"],)
                for row in existing_rows
                if (row["template_name"], json.dumps(json.loads(row["parameter_values"]), sort_keys=True))
                in showcase_keys
            ]
            if stale_ids:
                conn.executemany("DELETE FROM generated_reports WHERE report_id = ?", stale_ids)
                existing_rows = conn.execute(
                    """SELECT r.report_id, t.name AS template_name, r.parameter_values
                       FROM generated_reports r
                       JOIN report_templates t USING(template_id)"""
                ).fetchall()
        existing_keys = {
            (row["template_name"], json.dumps(json.loads(row["parameter_values"]), sort_keys=True))
            for row in existing_rows
        }

    for template_name, params in SHOWCASE_REPORTS:
        key = (template_name, json.dumps(params, sort_keys=True))
        if key in existing_keys:
            continue
        report_id = generate_report(template_name, params, save=True, db_path=path)
        if not isinstance(report_id, int):
            raise RuntimeError(f"Failed to generate formal showcase report for {template_name}: {report_id}")
        existing_keys.add(key)

    counts: dict[str, int] = {}
    with closing(get_connection(path)) as conn:
        for table in (
            "districts",
            "stations",
            "hourly_aqhi",
            "hourly_pollutants",
            "daily_weather",
            "saved_queries",
            "report_templates",
            "generated_reports",
        ):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv[1:]
    summary = seed_all(refresh_reports=refresh)
    print("Seeded air_quality.db successfully:")
    for table_name, total in summary.items():
        print(f"  {table_name:20s}: {total}")
