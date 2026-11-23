"""Connect Task B's saved queries to Task C's templates without writing to the source DB."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from string import Formatter
from tempfile import TemporaryDirectory

from src.queries import QUERY_DEFINITIONS, run_saved_query, seed_saved_queries
from src.schema import DEFAULT_DB_PATH, get_connection
from src.templates import (
    DEFAULT_TEMPLATES,
    METHOD_DATE,
    METHOD_NOTE,
    NA_TEXT as NA,
    RISKS,
    TEMPLATE_NAMES,
    adapt_query_result,
    aqhi_label,
    checked_query_params,
    month_bounds,
    render_report_templates,
    risk_label,
    seed_report_templates,
    validate_date,
)

_ACTIVE_SNAPSHOTS: set[Path] = set()


@contextmanager
def read_database(db_path=DEFAULT_DB_PATH):
    """Open an existing project database with query-only connections."""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(get_connection(path)) as conn:
        conn.execute("PRAGMA query_only = ON")
        yield conn


def select(sql, params=(), db_path=DEFAULT_DB_PATH):
    """Read internal parameterized SQL and return dictionaries."""
    with read_database(db_path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def station_record(name, db_path=DEFAULT_DB_PATH):
    """Return one station row by exact name or raise ValueError."""
    rows = select("SELECT * FROM stations WHERE name = ?", (name,), db_path)
    if not rows:
        raise ValueError(f"Unknown station {name!r}. Select a name from the stations table.")
    return rows[0]


@contextmanager
def demo_database(db_path=DEFAULT_DB_PATH):
    """Make an SQLite snapshot and seed Task B/C on the snapshot if needed."""
    with TemporaryDirectory(prefix="aqhi-task-d-") as directory:
        path = Path(directory) / "demo.db"
        with read_database(db_path) as source, closing(get_connection(path)) as dest:
            source.backup(dest)
        codes = {row["query_code"] for row in select("SELECT query_code FROM saved_queries", db_path=path)}
        if set(QUERY_DEFINITIONS) - codes:
            seed_saved_queries(path)
        templates = {row["name"] for row in select("SELECT name FROM report_templates", db_path=path)}
        if set(TEMPLATE_NAMES) - templates:
            seed_report_templates(path)
        snapshot = path.resolve()
        _ACTIVE_SNAPSHOTS.add(snapshot)
        try:
            yield snapshot
        finally:
            _ACTIVE_SNAPSHOTS.discard(snapshot)


def query_catalog(db_path=DEFAULT_DB_PATH):
    """Read station, date and month choices from the database."""
    stations = select("SELECT name, station_type FROM stations ORDER BY name", db_path=db_path)
    dates = select("SELECT DISTINCT obs_date FROM hourly_aqhi ORDER BY obs_date", db_path=db_path)
    dates = [row["obs_date"] for row in dates]
    return stations, dates, sorted({day[:7] for day in dates})


def default_cases(db_path=DEFAULT_DB_PATH):
    """Choose the April 1 example and an observed General station Serious case."""
    serious = select(
        """SELECT s.name, h.obs_date
           FROM hourly_aqhi h JOIN stations s USING(station_id)
           WHERE h.is_missing = 0 AND h.raw_value = '10+' AND s.station_type = 'General'
           ORDER BY (h.obs_date = ? AND s.name = ?) DESC, h.obs_date, s.name LIMIT 1""",
        ("2025-04-14", "Central/Western"),
        db_path,
    )
    cases = [
        {
            "station_name": "Central/Western",
            "station_b": "Central",
            "obs_date": "2025-04-01",
            "month": "2025-03",
        }
    ]
    if serious:
        cases.append(
            {
                "station_name": serious[0]["name"],
                "station_b": "Central",
                "obs_date": serious[0]["obs_date"],
                "month": serious[0]["obs_date"][:7],
            }
        )
    return cases


@dataclass
class Briefing:
    """Template result with its query rows and an explicit status."""

    title: str
    query_code: str
    rows: list[dict]
    period: str
    outputs: dict
    formal: bool
    report_id: int | None = None


def make_briefing(template_name, params, db_path, *, save=False):
    """Read the linked B query, validate C inputs and render three output formats.

    Use a DB from demo_database() for save=True. Fallback output is explicitly labeled
    and is never saved to generated_reports as a successful template result.
    """
    if save and Path(db_path).resolve() not in _ACTIVE_SNAPSHOTS:
        raise ValueError("Pass an active temporary database from demo_database() before saving reports.")
    template_rows = select(
        """SELECT t.*, q.query_code FROM report_templates t JOIN saved_queries q USING(query_id)
           WHERE t.name = ?""",
        (template_name,),
        db_path,
    )
    if not template_rows:
        raise ValueError(f"Template {template_name!r} is unavailable. Initialize a demo database.")
    template = template_rows[0]
    code = template["query_code"]
    checked = checked_query_params(code, params, db_path)
    rows = run_saved_query(code, checked, db_path)
    if "month" in checked:
        start, end = month_bounds(checked["month"])
        period = checked["month"]
    elif "start_date" in checked:
        start, end = checked["start_date"], checked["end_date"]
        period = f"{start} to {end}"
    else:
        start = end = period = checked["obs_date"]
    title = f"{template_name} · {period}"
    method_note = METHOD_NOTE if start < METHOD_DATE <= end or start == METHOD_DATE else ""
    try:
        if code in {"Q01_daily_briefing", "Q02_category_breakdown", "Q06_monthly_summary", "Q08_news_flash"}:
            if rows and not rows[0]["valid_hours"]:
                raise ValueError("There are no valid AQHI observations for these inputs.")
        if code == "Q03_station_comparison" and (
            len(rows) != 2 or any(not row["valid_hours"] for row in rows)
        ):
            raise ValueError("Both stations need valid AQHI for a formal comparison.")
        fields, note = adapt_query_result(code, rows, checked, db_path)
        note = " ".join(filter(None, (method_note, note)))
        fields = {**checked, **fields, "cross_2025_03_22_note": note}
        required = set(json.loads(template["required_variables"]))
        for key in ("text_template", "markdown_template", "html_template"):
            required.update(name for _, name, _, _ in Formatter().parse(template[key]) if name)
        if missing := required - fields.keys():
            raise ValueError(f"Required template fields missing from query conversion: {sorted(missing)}.")
        outputs = render_report_templates(template, fields, escape_html=True)
        if outputs["text_output"].startswith(("No valid data available:", "Template Render Error:")):
            raise ValueError(outputs["text_output"])
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        message = f"Query data only. Formal template unavailable. {exc}"
        if method_note:
            message += f" {method_note}"
        data = json.dumps(rows, ensure_ascii=False, indent=2)
        outputs = {
            "text_output": f"{message}\n{data}",
            "markdown_output": f"{message}\n\n```json\n{data}\n```",
            "html_output": f"<p>{escape(message)}</p><pre>{escape(data)}</pre>",
        }
        return Briefing(title, code, rows, period, outputs, False)
    result = Briefing(title, code, rows, period, outputs, True)
    if save:
        station_id = station_record(checked["station_name"], db_path)["station_id"] if "station_name" in checked else None
        with closing(get_connection(db_path)) as conn, conn:
            cursor = conn.execute(
                """INSERT INTO generated_reports (template_id, station_id, title,
                   parameter_values, reporting_period, text_output, markdown_output, html_output)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    template["template_id"],
                    station_id,
                    title,
                    json.dumps(checked),
                    period,
                    outputs["text_output"],
                    outputs["markdown_output"],
                    outputs["html_output"],
                ),
            )
            result.report_id = cursor.lastrowid
    return result
