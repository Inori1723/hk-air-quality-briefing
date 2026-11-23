"""Saved SQLite queries for the Hong Kong Air Quality Briefing System."""

from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from textwrap import dedent

from .schema import DEFAULT_DB_PATH, get_connection


@dataclass(frozen=True)
class QueryDefinition:
    name: str
    parameter_names: tuple[str, ...]
    description: str
    sql: str


_CATEGORIES = (
    ("Low", "low_hours"),
    ("Moderate", "moderate_hours"),
    ("High", "high_hours"),
    ("Very high", "very_high_hours"),
    ("Serious", "serious_hours"),
)
_POLLUTANTS = ("pm25", "pm10", "o3", "no2", "so2", "co")

_COVERAGE = """
    COUNT(CASE WHEN h.is_missing = 0 THEN 1 END) AS valid_hours,
    SUM(h.is_missing) AS missing_hours,
    COUNT(CASE WHEN h.is_missing = 0 AND h.is_substitute = 1 THEN 1 END)
        AS substitute_hours
""".strip()
_AQHI_STATS = """
    MIN(CASE WHEN h.is_missing = 0 THEN h.sort_rank END) AS min_rank,
    MAX(CASE WHEN h.is_missing = 0 THEN h.sort_rank END) AS max_rank,
    ROUND(AVG(CASE WHEN h.is_missing = 0 THEN h.numeric_value END), 2) AS avg_aqhi,
    COUNT(CASE WHEN h.is_missing = 0 THEN h.numeric_value END) AS numeric_aqhi_hours,
    COUNT(CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN 1 END) AS high_or_above_hours
""".strip()
_CATEGORY_COUNTS = ",\n    ".join(
    f"COUNT(CASE WHEN h.is_missing = 0 AND h.category = '{category}' THEN 1 END) AS {column}"
    for category, column in _CATEGORIES
)
# The source database stores a common unit per pollutant. Preserve that unit
# and count only non-NULL measurements in each average's denominator.
_POLLUTANT_STATS = ",\n    ".join(
    expression
    for pollutant in _POLLUTANTS
    for expression in (
        f"ROUND(AVG(p.{pollutant}), 2) AS avg_{pollutant}",
        f"COUNT(p.{pollutant}) AS valid_{pollutant}_hours",
        f"MAX(CASE WHEN p.{pollutant} IS NOT NULL THEN p.{pollutant}_unit END) AS {pollutant}_unit",
    )
)
_POLLUTANT_JOIN = """
LEFT JOIN hourly_pollutants AS p
       ON p.station_id = h.station_id AND p.obs_date = h.obs_date AND p.obs_hour = h.obs_hour
""".strip()
_DISPLAY_MAX = "CASE WHEN max_rank = 11 THEN '10+' ELSE CAST(max_rank AS TEXT) END AS max_aqhi"
_DISPLAY_MIN = "CASE WHEN min_rank = 11 THEN '10+' ELSE CAST(min_rank AS TEXT) END AS min_aqhi"


def _daily_summary(criteria: str, order_by: str) -> str:
    """Build a station-day result with fixed, internal SQL filters."""
    return f"""
WITH daily AS (
    SELECT h.station_id, s.name AS station_name, s.station_type,
           d.english_name AS district_name, h.obs_date,
           {_COVERAGE},
           {_AQHI_STATS},
           {_CATEGORY_COUNTS},
           {_POLLUTANT_STATS},
           w.mean_temp_c, w.max_temp_c, w.min_temp_c, w.mean_rh_pct,
           w.rainfall_mm, w.mean_wind_kmh, w.sunshine_hours,
           w.source_note AS weather_note
    FROM hourly_aqhi AS h
    JOIN stations AS s ON s.station_id = h.station_id
    JOIN districts AS d ON d.district_id = s.district_id
    {_POLLUTANT_JOIN}
    LEFT JOIN daily_weather AS w ON w.obs_date = h.obs_date
    WHERE {criteria}
    GROUP BY h.station_id, h.obs_date
)
SELECT daily.*, {_DISPLAY_MIN}, {_DISPLAY_MAX},
       (
           SELECT GROUP_CONCAT(peak_time, ', ')
           FROM (
               SELECT printf('%02d:00', peak.obs_hour) AS peak_time
               FROM hourly_aqhi AS peak
               WHERE peak.station_id = daily.station_id
                 AND peak.obs_date = daily.obs_date
                 AND peak.is_missing = 0 AND peak.sort_rank = daily.max_rank
               ORDER BY peak.obs_hour
           )
       ) AS peak_hours
FROM daily
ORDER BY {order_by}
"""


_CATEGORY_BREAKDOWN = f"""
WITH risk_categories(category, category_order) AS (
    VALUES ('Low', 1), ('Moderate', 2), ('High', 3), ('Very high', 4), ('Serious', 5)
),
station_day AS (
    SELECT s.station_id, s.name AS station_name, h.obs_date, h.category,
           h.is_missing, h.is_substitute
    FROM hourly_aqhi AS h
    JOIN stations AS s ON s.station_id = h.station_id
    WHERE s.name = :station_name AND h.obs_date = :obs_date
),
coverage AS (
    SELECT h.station_id, h.station_name, h.obs_date, {_COVERAGE}
    FROM station_day AS h
    GROUP BY h.station_id, h.obs_date
),
counts AS (
    SELECT category, COUNT(*) AS hours
    FROM station_day
    WHERE is_missing = 0
    GROUP BY category
)
SELECT coverage.*, r.category, r.category_order, COALESCE(counts.hours, 0) AS hours,
       ROUND(100.0 * COALESCE(counts.hours, 0) / NULLIF(coverage.valid_hours, 0), 1)
           AS percentage
FROM coverage
CROSS JOIN risk_categories AS r
LEFT JOIN counts ON counts.category = r.category
ORDER BY r.category_order
"""

_DISTRICT_MAP = f"""
WITH station_day AS (
    SELECT h.station_id,
           COUNT(CASE WHEN h.is_missing = 0 THEN 1 END) AS valid_hours,
           MAX(CASE WHEN h.is_missing = 0 THEN h.sort_rank END) AS max_rank
    FROM hourly_aqhi AS h
    WHERE h.obs_date = :obs_date
    GROUP BY h.station_id
),
map_rows AS (
    SELECT 'district' AS row_type, d.district_id, d.english_name AS district_name,
           d.population_2025, d.area_sqkm, d.population_ref_year,
           :obs_date AS obs_date, NULL AS station_id, NULL AS station_name,
           'General' AS station_type, NULL AS latitude, NULL AS longitude,
           COUNT(s.station_id) AS general_station_count,
           COALESCE(SUM(a.valid_hours), 0) AS valid_hours, MAX(a.max_rank) AS max_rank
    FROM districts AS d
    LEFT JOIN stations AS s ON s.district_id = d.district_id AND s.station_type = 'General'
    LEFT JOIN station_day AS a ON a.station_id = s.station_id
    GROUP BY d.district_id

    UNION ALL

    SELECT 'roadside', d.district_id, d.english_name,
           d.population_2025, d.area_sqkm, d.population_ref_year,
           :obs_date, s.station_id, s.name,
           s.station_type, s.latitude, s.longitude, NULL,
           COALESCE(a.valid_hours, 0), a.max_rank
    FROM stations AS s
    JOIN districts AS d ON d.district_id = s.district_id
    LEFT JOIN station_day AS a ON a.station_id = s.station_id
    WHERE s.station_type = 'Roadside'
)
SELECT map_rows.*, {_DISPLAY_MAX}
FROM map_rows
ORDER BY row_type, district_name, station_name
"""

_MONTHLY_SUMMARY = f"""
WITH monthly AS (
    SELECT h.station_id, s.name AS station_name, s.station_type,
           d.english_name AS district_name, substr(h.obs_date, 1, 7) AS month,
           {_COVERAGE},
           {_AQHI_STATS},
           {_CATEGORY_COUNTS},
           {_POLLUTANT_STATS}
    FROM hourly_aqhi AS h
    JOIN stations AS s ON s.station_id = h.station_id
    JOIN districts AS d ON d.district_id = s.district_id
    {_POLLUTANT_JOIN}
    WHERE s.name = :station_name
      AND h.obs_date >= :month || '-01'
      AND h.obs_date < date(:month || '-01', '+1 month')
    GROUP BY h.station_id, substr(h.obs_date, 1, 7)
)
SELECT monthly.*, {_DISPLAY_MIN}, {_DISPLAY_MAX}
FROM monthly
"""

_HIGH_RISK_BULLETIN = f"""
WITH station_range AS (
    SELECT h.*, s.name AS station_name, s.station_type, d.english_name AS district_name
    FROM hourly_aqhi AS h
    JOIN stations AS s ON s.station_id = h.station_id
    JOIN districts AS d ON d.district_id = s.district_id
    WHERE s.name = :station_name AND h.obs_date BETWEEN :start_date AND :end_date
),
episodes AS (
    SELECT h.station_id, h.station_name, h.station_type, h.district_name, h.obs_date,
           {_COVERAGE},
           MIN(CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN h.sort_rank END) AS min_rank,
           MAX(CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN h.sort_rank END) AS max_rank,
           COUNT(CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN 1 END)
               AS high_or_above_hours,
           MIN(CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN h.obs_hour END)
               AS first_high_hour,
           MAX(CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN h.obs_hour END)
               AS last_high_hour,
           {_CATEGORY_COUNTS}
    FROM station_range AS h
    WHERE h.obs_date IN (
        SELECT obs_date FROM station_range WHERE is_missing = 0 AND sort_rank >= 7
    )
    GROUP BY h.station_id, h.obs_date
)
SELECT episodes.*, {_DISPLAY_MIN}, {_DISPLAY_MAX},
       (
           SELECT GROUP_CONCAT(hour_label, ', ')
           FROM (
               SELECT printf('%02d:00', obs_hour) AS hour_label
               FROM station_range
               WHERE obs_date = episodes.obs_date AND is_missing = 0 AND sort_rank >= 7
               ORDER BY obs_hour
           )
       ) AS high_risk_hours
FROM episodes
ORDER BY obs_date
"""

_NEWS_FLASH = f"""
WITH general_hours AS (
    SELECT h.obs_hour, h.sort_rank, h.is_missing, h.is_substitute, s.name AS station_name
    FROM hourly_aqhi AS h
    JOIN stations AS s ON s.station_id = h.station_id
    WHERE h.obs_date = :obs_date AND s.station_type = 'General'
),
summary AS (
    SELECT {_COVERAGE},
           MAX(CASE WHEN h.is_missing = 0 THEN h.sort_rank END) AS max_rank,
           COUNT(CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN 1 END)
               AS high_station_hours,
           COUNT(DISTINCT CASE WHEN h.is_missing = 0 AND h.sort_rank >= 7 THEN h.obs_hour END)
               AS high_or_above_hours
    FROM general_hours AS h
    HAVING COUNT(*) > 0
),
peaks AS (
    SELECT station_name, obs_hour FROM general_hours
    WHERE is_missing = 0 AND sort_rank = (SELECT max_rank FROM summary)
)
SELECT :obs_date AS obs_date, summary.*, {_DISPLAY_MAX},
       (
           SELECT GROUP_CONCAT(station_name, ', ')
           FROM (SELECT DISTINCT station_name FROM peaks ORDER BY station_name)
       ) AS peak_stations,
       (
           SELECT GROUP_CONCAT(printf('%02d:00', obs_hour), ', ')
           FROM (SELECT DISTINCT obs_hour FROM peaks ORDER BY obs_hour)
       ) AS peak_hours,
       (
           SELECT GROUP_CONCAT(station_name || ' ' || printf('%02d:00', obs_hour), ', ')
           FROM (SELECT station_name, obs_hour FROM peaks ORDER BY station_name, obs_hour)
       ) AS peak_station_hours,
       (
           SELECT GROUP_CONCAT(printf('%02d:00', obs_hour), ', ')
           FROM (
               SELECT DISTINCT obs_hour FROM general_hours
               WHERE is_missing = 0 AND sort_rank >= 7 ORDER BY obs_hour
           )
       ) AS high_risk_hours
FROM summary
"""

_REPORT_HISTORY = """
SELECT t.template_id, t.name AS template_name, strftime('%Y-%m', r.created_at) AS month,
       COUNT(*) AS report_count, COUNT(DISTINCT s.station_id) AS station_count,
       COUNT(CASE WHEN r.station_id IS NULL THEN 1 END) AS reports_without_station,
       MIN(r.created_at) AS first_created_at, MAX(r.created_at) AS last_created_at
FROM generated_reports AS r
JOIN report_templates AS t ON t.template_id = r.template_id
LEFT JOIN stations AS s ON s.station_id = r.station_id
GROUP BY t.template_id, strftime('%Y-%m', r.created_at)
ORDER BY month DESC, template_name
"""


QUERY_DEFINITIONS = {
    "Q01_daily_briefing": QueryDefinition(
        "Daily station briefing",
        ("station_name", "obs_date"),
        "Station-day coverage, AQHI range, all peak hours, pollutant means and daily weather.",
        _daily_summary("s.name = :station_name AND h.obs_date = :obs_date", "obs_date"),
    ),
    "Q02_category_breakdown": QueryDefinition(
        "Daily category breakdown",
        ("station_name", "obs_date"),
        "Five risk categories with hours and percentages using valid AQHI hours.",
        _CATEGORY_BREAKDOWN,
    ),
    "Q03_station_comparison": QueryDefinition(
        "Comparison of two stations",
        ("station_a", "station_b", "obs_date"),
        "One row per available station with comparable AQHI and pollutant statistics.",
        _daily_summary(
            "s.name IN (:station_a, :station_b) AND h.obs_date = :obs_date",
            "CASE WHEN station_name = :station_a THEN 0 ELSE 1 END, station_name",
        ),
    ),
    "Q04_weather_pollution": QueryDefinition(
        "Weather and pollution summary",
        ("station_name", "start_date", "end_date"),
        "Daily AQHI, pollutant and weather measurements over an inclusive date range.",
        _daily_summary("s.name = :station_name AND h.obs_date BETWEEN :start_date AND :end_date", "obs_date"),
    ),
    "Q05_district_map": QueryDefinition(
        "District map report",
        ("obs_date",),
        "All districts with General station maxima, plus individually identified Roadside stations.",
        _DISTRICT_MAP,
    ),
    "Q06_monthly_summary": QueryDefinition(
        "Monthly station summary",
        ("station_name", "month"),
        "AQHI coverage and risk categories with pollutant statistics for one YYYY-MM month.",
        _MONTHLY_SUMMARY,
    ),
    "Q07_high_risk_bulletin": QueryDefinition(
        "High risk episode bulletin",
        ("station_name", "start_date", "end_date"),
        "One row per date with AQHI 7 or above, including every high-risk hour on that date.",
        _HIGH_RISK_BULLETIN,
    ),
    "Q08_news_flash": QueryDefinition(
        "Air quality news flash",
        ("obs_date",),
        "Territory-wide General station maximum, all peak stations and hours, and High-or-above hours.",
        _NEWS_FLASH,
    ),
    "Q09_report_history": QueryDefinition(
        "Report history by template and month",
        (),
        "Generated report counts grouped by template and calendar month of creation.",
        _REPORT_HISTORY,
    ),
}

_SEED_SQL = """
INSERT INTO saved_queries (query_code, name, sql_text, parameter_names, description)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(query_code) DO UPDATE SET
    name = excluded.name,
    sql_text = excluded.sql_text,
    parameter_names = excluded.parameter_names,
    description = excluded.description,
    updated_at = datetime('now', 'localtime')
WHERE saved_queries.name IS NOT excluded.name
   OR saved_queries.sql_text IS NOT excluded.sql_text
   OR saved_queries.parameter_names IS NOT excluded.parameter_names
   OR saved_queries.description IS NOT excluded.description
"""


def seed_saved_queries(db_path: Path | str = DEFAULT_DB_PATH) -> int:
    """Register the nine queries after schema initialization, preserving their IDs."""
    records = [
        (code, definition.name, dedent(definition.sql).strip(),
         json.dumps(definition.parameter_names), definition.description)
        for code, definition in QUERY_DEFINITIONS.items()
    ]
    with closing(get_connection(db_path)) as conn, conn:
        conn.executemany(_SEED_SQL, records)
    return len(records)


def _parameter_names(text: str) -> tuple[str, ...]:
    try:
        names = json.loads(text)
    except json.JSONDecodeError:
        names = [name.strip() for name in text.split(",") if name.strip()]
    if not isinstance(names, list) or any(
        not isinstance(name, str) or re.fullmatch("[A-Za-z_][A-Za-z_0-9]*", name) is None
        for name in names
    ):
        raise ValueError("parameter_names must be a list of named SQL parameters.")
    return tuple(names)


_READ_OPERATIONS = {
    sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE,
}


def _authorize_read(action, *_details):
    return sqlite3.SQLITE_OK if action in _READ_OPERATIONS else sqlite3.SQLITE_DENY


def run_saved_query(
    query_code: str,
    params: Mapping[str, object] | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Execute one saved read query with named parameters, returning dictionaries."""
    parameters = dict(params) if params is not None else {}
    with closing(get_connection(db_path)) as conn:
        record = conn.execute(
            "SELECT sql_text, parameter_names FROM saved_queries WHERE query_code = ?", (query_code,)
        ).fetchone()
        if record is None:
            raise KeyError(f"Unknown saved query {query_code!r}. Run seed_saved_queries() first.")
        required = _parameter_names(record["parameter_names"])
        missing = [name for name in required if name not in parameters]
        if missing:
            raise ValueError(f"{query_code} requires parameter(s): {', '.join(missing)}")
        conn.set_authorizer(_authorize_read)
        rows = conn.execute(record["sql_text"], parameters).fetchall()
        return [dict(row) for row in rows]
