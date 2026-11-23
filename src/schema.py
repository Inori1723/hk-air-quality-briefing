"""SQLite database schema definition and connection helpers for the Hong Kong Air Quality Briefing System."""

from contextlib import closing
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "air_quality.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS districts (
    district_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    district_code        TEXT    NOT NULL UNIQUE,
    english_name         TEXT    NOT NULL UNIQUE,
    region               TEXT    NOT NULL CHECK (region IN ('Hong Kong Island', 'Kowloon', 'New Territories')),
    population_2025      INTEGER,
    area_sqkm            REAL,
    population_ref_year  TEXT
);

CREATE TABLE IF NOT EXISTS stations (
    station_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL UNIQUE,
    station_type  TEXT    NOT NULL CHECK (station_type IN ('General', 'Roadside')),
    district_id   INTEGER NOT NULL,
    latitude      REAL,
    longitude     REAL,
    FOREIGN KEY (district_id) REFERENCES districts(district_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hourly_aqhi (
    aqhi_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id     INTEGER NOT NULL,
    obs_date       TEXT    NOT NULL,  -- YYYY-MM-DD (Hong Kong Time)
    obs_hour       INTEGER NOT NULL CHECK (obs_hour BETWEEN 1 AND 24),
    raw_value      TEXT,              -- Original cell text (e.g. '4', '4*', '10+', '-', '-*', or NULL)
    numeric_value  INTEGER CHECK (numeric_value BETWEEN 1 AND 10),  -- NULL for '10+' and missing
    sort_rank      INTEGER CHECK (sort_rank BETWEEN 1 AND 11),      -- 11 reserved exclusively for '10+' sorting/max
    category       TEXT    CHECK (category IN ('Low', 'Moderate', 'High', 'Very high', 'Serious')),
    is_substitute  INTEGER NOT NULL DEFAULT 0 CHECK (is_substitute IN (0, 1)),
    is_missing     INTEGER NOT NULL DEFAULT 0 CHECK (is_missing IN (0, 1)),
    UNIQUE (station_id, obs_date, obs_hour),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hourly_pollutants (
    pollutant_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id     INTEGER NOT NULL,
    obs_date       TEXT    NOT NULL,  -- YYYY-MM-DD (Hong Kong Time)
    obs_hour       INTEGER NOT NULL CHECK (obs_hour BETWEEN 1 AND 24),
    pm25           REAL,
    pm25_unit      TEXT,
    pm10           REAL,
    pm10_unit      TEXT,
    o3             REAL,
    o3_unit        TEXT,
    no2            REAL,
    no2_unit       TEXT,
    so2            REAL,
    so2_unit       TEXT,
    co             REAL,
    co_unit        TEXT,
    UNIQUE (station_id, obs_date, obs_hour),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS daily_weather (
    weather_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    obs_date       TEXT    NOT NULL UNIQUE,  -- YYYY-MM-DD
    mean_temp_c    REAL,
    max_temp_c     REAL,
    min_temp_c     REAL,
    mean_rh_pct    REAL,
    rainfall_mm    REAL,
    mean_wind_kmh  REAL,
    sunshine_hours REAL,
    source_note    TEXT
);

CREATE TABLE IF NOT EXISTS saved_queries (
    query_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query_code       TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL,
    sql_text         TEXT    NOT NULL,
    parameter_names  TEXT    NOT NULL,  -- JSON list or comma-separated parameter names
    description      TEXT,
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS report_templates (
    template_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id            INTEGER NOT NULL,
    name                TEXT    NOT NULL UNIQUE,
    scope               TEXT    NOT NULL,
    required_variables  TEXT    NOT NULL,  -- JSON list of placeholder names
    text_template       TEXT    NOT NULL,
    markdown_template   TEXT    NOT NULL,
    html_template       TEXT    NOT NULL,
    version             TEXT    NOT NULL DEFAULT '1.0',
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (query_id) REFERENCES saved_queries(query_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS generated_reports (
    report_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id       INTEGER NOT NULL,
    station_id        INTEGER,  -- Nullable for territory-wide / multi-station / district reports
    title             TEXT    NOT NULL,
    parameter_values  TEXT    NOT NULL,  -- JSON object of inputs used
    reporting_period  TEXT    NOT NULL,
    text_output       TEXT    NOT NULL,
    markdown_output   TEXT    NOT NULL,
    html_output       TEXT    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (template_id) REFERENCES report_templates(template_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_stations_district ON stations(district_id);
CREATE INDEX IF NOT EXISTS idx_aqhi_date_station ON hourly_aqhi(obs_date, station_id);
CREATE INDEX IF NOT EXISTS idx_aqhi_station_rank ON hourly_aqhi(station_id, sort_rank);
CREATE INDEX IF NOT EXISTS idx_pollutants_date_station ON hourly_pollutants(obs_date, station_id);
CREATE INDEX IF NOT EXISTS idx_reports_template ON generated_reports(template_id);
CREATE INDEX IF NOT EXISTS idx_reports_station ON generated_reports(station_id);
"""


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled and Row factory configured."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH, drop_existing: bool = False) -> Path:
    """Create all 8 tables and indexes in SQLite."""
    path = Path(db_path)
    if drop_existing and path.exists():
        path.unlink()
    with closing(get_connection(path)) as conn, conn:
        conn.executescript(SCHEMA_SQL)
    return path


if __name__ == "__main__":
    created = init_db()
    print(f"Initialized SQLite schema at: {created}")
