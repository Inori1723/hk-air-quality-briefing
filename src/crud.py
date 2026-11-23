"""Parameterized CRUD for the eight tables defined in src.schema.

create_* returns a new primary key. get_* returns a dictionary or None.
update_* and delete_* return whether a row matched the given primary key.
Use JSON strings for required_variables and parameter_values.
"""

from contextlib import closing
from datetime import date
import sqlite3

from .etl_aqhi import parse_aqhi_cell
from .schema import DEFAULT_DB_PATH, get_connection


_PRIMARY_KEYS = {
    "districts": "district_id",
    "stations": "station_id",
    "hourly_aqhi": "aqhi_id",
    "hourly_pollutants": "pollutant_id",
    "daily_weather": "weather_id",
    "saved_queries": "query_id",
    "report_templates": "template_id",
    "generated_reports": "report_id",
}
_DEPENDENCIES = {
    "districts": (("stations", "district_id"),),
    "stations": (
        ("hourly_aqhi", "station_id"),
        ("hourly_pollutants", "station_id"),
        ("generated_reports", "station_id"),
    ),
    "saved_queries": (("report_templates", "query_id"),),
    "report_templates": (("generated_reports", "template_id"),),
}
_UPDATE_TIMESTAMPS = {"saved_queries", "report_templates", "generated_reports"}
_AQHI_FIELDS = ("raw_value", "numeric_value", "sort_rank", "category", "is_substitute", "is_missing")


class ReferencedRowError(sqlite3.IntegrityError):
    """A child table still refers to the parent row being deleted."""

    def __init__(self, table, row_id, references):
        self.table = table
        self.row_id = row_id
        self.references = references
        details = ", ".join(f"{column} ({count} row(s))" for column, count in references.items())
        super().__init__(f"Cannot delete {table} row {row_id!r}. Referenced by {details}.")


def _write_columns(conn, table, fields):
    """Only interpolate existing non-primary-key identifiers. Bind all values."""
    if not fields:
        raise ValueError(f"Supply at least one field for {table}.")
    allowed = {
        row["name"] for row in conn.execute("SELECT name FROM pragma_table_info(?) WHERE pk = 0", (table,))
    }
    invalid = fields.keys() - allowed
    if invalid:
        raise ValueError(f"Unknown or read-only fields for {table}: {', '.join(sorted(invalid))}")
    if "obs_date" in fields:
        value = fields["obs_date"]
        try:
            canonical = date.fromisoformat(value).isoformat()
        except (TypeError, ValueError) as exc:
            raise ValueError("obs_date must use YYYY-MM-DD.") from exc
        if value != canonical:
            raise ValueError("obs_date must use YYYY-MM-DD.")
    return ['"' + name.replace('"', '""') + '"' for name in fields]


def _create(table, fields, db_path):
    with closing(get_connection(db_path)) as conn, conn:
        columns = _write_columns(conn, table, fields)
        placeholders = ", ".join("?" for _ in columns)
        cursor = conn.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
        return cursor.lastrowid


def _get(table, row_id, db_path):
    key = _PRIMARY_KEYS[table]
    with closing(get_connection(db_path)) as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE {key} = ?", (row_id,)).fetchone()
        return dict(row) if row is not None else None


def _update(table, row_id, fields, db_path):
    key = _PRIMARY_KEYS[table]
    with closing(get_connection(db_path)) as conn, conn:
        columns = _write_columns(conn, table, fields)
        assignments = [f"{column} = ?" for column in columns]
        if table in _UPDATE_TIMESTAMPS and "updated_at" not in fields:
            assignments.append("updated_at = datetime('now', 'localtime')")
        cursor = conn.execute(
            f"UPDATE {table} SET {', '.join(assignments)} WHERE {key} = ?",
            (*fields.values(), row_id),
        )
        return cursor.rowcount > 0


def _delete(table, row_id, db_path):
    key = _PRIMARY_KEYS[table]
    with closing(get_connection(db_path)) as conn, conn:
        children = _DEPENDENCIES.get(table, ())
        if children:
            # Keep the reference checks and DELETE in a single write transaction.
            conn.execute("BEGIN IMMEDIATE")
            references = {}
            for child, column in children:
                count = conn.execute(f"SELECT COUNT(*) FROM {child} WHERE {column} = ?", (row_id,)).fetchone()[0]
                if count:
                    references[f"{child}.{column}"] = count
            if references:
                raise ReferencedRowError(table, row_id, references)
        cursor = conn.execute(f"DELETE FROM {table} WHERE {key} = ?", (row_id,))
        return cursor.rowcount > 0


def _normalize_aqhi(fields, *, creating=False):
    explicit_derived = fields.keys() & set(_AQHI_FIELDS[1:])
    if "raw_value" not in fields and not creating:
        if explicit_derived:
            raise ValueError("Set raw_value to update the derived AQHI fields.")
        return

    raw = fields.get("raw_value")
    parsed = dict(zip(_AQHI_FIELDS, parse_aqhi_cell("" if raw is None else str(raw))))
    invalid = [name for name in explicit_derived if parsed[name] != fields[name]]
    if invalid:
        raise ValueError(f"raw_value disagrees with: {', '.join(sorted(invalid))}")
    fields.update(parsed)


def create_district(*, db_path=DEFAULT_DB_PATH, **fields):
    return _create("districts", fields, db_path)


def get_district(district_id, *, db_path=DEFAULT_DB_PATH):
    return _get("districts", district_id, db_path)


def update_district(district_id, *, db_path=DEFAULT_DB_PATH, **fields):
    return _update("districts", district_id, fields, db_path)


def delete_district(district_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("districts", district_id, db_path)


def create_station(*, db_path=DEFAULT_DB_PATH, **fields):
    return _create("stations", fields, db_path)


def get_station(station_id, *, db_path=DEFAULT_DB_PATH):
    return _get("stations", station_id, db_path)


def update_station(station_id, *, db_path=DEFAULT_DB_PATH, **fields):
    return _update("stations", station_id, fields, db_path)


def delete_station(station_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("stations", station_id, db_path)


def create_hourly_aqhi(*, db_path=DEFAULT_DB_PATH, **fields):
    """Insert an AQHI reading, deriving its rank and flags from raw_value."""
    _normalize_aqhi(fields, creating=True)
    return _create("hourly_aqhi", fields, db_path)


def get_hourly_aqhi(aqhi_id, *, db_path=DEFAULT_DB_PATH):
    return _get("hourly_aqhi", aqhi_id, db_path)


def update_hourly_aqhi(aqhi_id, *, db_path=DEFAULT_DB_PATH, **fields):
    """Update raw_value together with its derived rank, category and flags."""
    _normalize_aqhi(fields)
    return _update("hourly_aqhi", aqhi_id, fields, db_path)


def delete_hourly_aqhi(aqhi_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("hourly_aqhi", aqhi_id, db_path)


def create_hourly_pollutant(*, db_path=DEFAULT_DB_PATH, **fields):
    return _create("hourly_pollutants", fields, db_path)


def get_hourly_pollutant(pollutant_id, *, db_path=DEFAULT_DB_PATH):
    return _get("hourly_pollutants", pollutant_id, db_path)


def update_hourly_pollutant(pollutant_id, *, db_path=DEFAULT_DB_PATH, **fields):
    return _update("hourly_pollutants", pollutant_id, fields, db_path)


def delete_hourly_pollutant(pollutant_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("hourly_pollutants", pollutant_id, db_path)


def create_daily_weather(*, db_path=DEFAULT_DB_PATH, **fields):
    return _create("daily_weather", fields, db_path)


def get_daily_weather(weather_id, *, db_path=DEFAULT_DB_PATH):
    return _get("daily_weather", weather_id, db_path)


def update_daily_weather(weather_id, *, db_path=DEFAULT_DB_PATH, **fields):
    return _update("daily_weather", weather_id, fields, db_path)


def delete_daily_weather(weather_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("daily_weather", weather_id, db_path)


def create_saved_query(*, db_path=DEFAULT_DB_PATH, **fields):
    return _create("saved_queries", fields, db_path)


def get_saved_query(query_id, *, db_path=DEFAULT_DB_PATH):
    return _get("saved_queries", query_id, db_path)


def update_saved_query(query_id, *, db_path=DEFAULT_DB_PATH, **fields):
    return _update("saved_queries", query_id, fields, db_path)


def delete_saved_query(query_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("saved_queries", query_id, db_path)


def create_report_template(*, db_path=DEFAULT_DB_PATH, **fields):
    return _create("report_templates", fields, db_path)


def get_report_template(template_id, *, db_path=DEFAULT_DB_PATH):
    return _get("report_templates", template_id, db_path)


def update_report_template(template_id, *, db_path=DEFAULT_DB_PATH, **fields):
    return _update("report_templates", template_id, fields, db_path)


def delete_report_template(template_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("report_templates", template_id, db_path)


def create_generated_report(*, db_path=DEFAULT_DB_PATH, **fields):
    return _create("generated_reports", fields, db_path)


def get_generated_report(report_id, *, db_path=DEFAULT_DB_PATH):
    return _get("generated_reports", report_id, db_path)


def update_generated_report(report_id, *, db_path=DEFAULT_DB_PATH, **fields):
    return _update("generated_reports", report_id, fields, db_path)


def delete_generated_report(report_id, *, db_path=DEFAULT_DB_PATH):
    return _delete("generated_reports", report_id, db_path)
