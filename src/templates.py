"""Task C shared template engine, query adapter, and multi-format report renderer."""

from calendar import monthrange
from contextlib import closing, contextmanager
from datetime import date
from html import escape
import json
from pathlib import Path
from string import Formatter

from .queries import QUERY_DEFINITIONS, run_saved_query
from .report_templates.t1_daily_station_briefing import TEMPLATE as T1
from .report_templates.t2_daily_category_breakdown import TEMPLATE as T2
from .report_templates.t3_comparison_of_two_stations import TEMPLATE as T3
from .report_templates.t4_weather_and_pollution_summary import TEMPLATE as T4
from .report_templates.t5_district_map_report import TEMPLATE as T5
from .report_templates.t6_monthly_station_summary import TEMPLATE as T6
from .report_templates.t7_high_risk_episode_bulletin import TEMPLATE as T7
from .report_templates.t8_air_quality_news_flash import TEMPLATE as T8
from .schema import DEFAULT_DB_PATH, get_connection

DEFAULT_TEMPLATES = [T1, T2, T3, T4, T5, T6, T7, T8]
TEMPLATE_NAMES = tuple(tpl["name"] for tpl in DEFAULT_TEMPLATES)

METHOD_DATE = "2025-03-22"
METHOD_NOTE = (
    "EPD updated the AQHI calculation method on 22 March 2025. "
    "AQHI changes across this date do not establish changes in pollutant concentrations."
)
RISKS = ("Low", "Moderate", "High", "Very high", "Serious")
NA_TEXT = "N/A (not available)"
_SERIOUS_RANK_KEYS = frozenset(
    {"max_aqhi", "max_rank", "min_aqhi", "min_rank", "station_a_max", "station_b_max"}
)

_SEED_TEMPLATE_SQL = """
INSERT INTO report_templates (
    query_id, name, scope, required_variables,
    text_template, markdown_template, html_template, version, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
ON CONFLICT(name) DO UPDATE SET
    query_id = excluded.query_id,
    scope = excluded.scope,
    required_variables = excluded.required_variables,
    text_template = excluded.text_template,
    markdown_template = excluded.markdown_template,
    html_template = excluded.html_template,
    version = excluded.version,
    updated_at = datetime('now', 'localtime')
WHERE report_templates.query_id IS NOT excluded.query_id
   OR report_templates.scope IS NOT excluded.scope
   OR report_templates.required_variables IS NOT excluded.required_variables
   OR report_templates.text_template IS NOT excluded.text_template
   OR report_templates.markdown_template IS NOT excluded.markdown_template
   OR report_templates.html_template IS NOT excluded.html_template
   OR report_templates.version IS NOT excluded.version
"""


def validate_date(value: object) -> str:
    """Validate and return a canonical YYYY-MM-DD observation date."""
    try:
        if isinstance(value, str) and date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError(f"Use YYYY-MM-DD for dates, got {value!r}.")


def month_bounds(month: str) -> tuple[str, str]:
    """Return inclusive ISO start and end dates for a canonical YYYY-MM month."""
    start = validate_date(f"{month}-01")
    first = date.fromisoformat(start)
    return start, first.replace(day=monthrange(first.year, first.month)[1]).isoformat()


def aqhi_label(rank: int | None) -> str:
    """Convert an integer sorting rank (1..11) to its public AQHI display label."""
    if rank is None:
        return NA_TEXT
    return "10+" if rank == 11 else str(rank)


def risk_label(rank: int | None) -> str:
    """Return the EPD risk category for a valid sorting rank."""
    if rank is None:
        return "No valid data"
    return RISKS[sum(rank >= threshold for threshold in (4, 7, 8, 11))]


@contextmanager
def _read_only_connection(db_path: Path | str = DEFAULT_DB_PATH):
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(get_connection(path)) as conn:
        conn.execute("PRAGMA query_only = ON")
        yield conn


def _select_rows(sql: str, params=(), db_path: Path | str = DEFAULT_DB_PATH) -> list[dict]:
    with _read_only_connection(db_path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def _station_record(name: object, db_path: Path | str = DEFAULT_DB_PATH) -> dict:
    rows = _select_rows("SELECT * FROM stations WHERE name = ?", (name,), db_path)
    if not rows:
        raise ValueError(f"Unknown station {name!r}. Select a name from the stations table.")
    return rows[0]


def check_cross_2025_03_22(start_date: str = "", end_date: str = "", period_str: str = "") -> str:
    """Return the EPD calculation caveat when a query spans or targets 2025-03-22."""
    if start_date and end_date:
        if start_date < METHOD_DATE <= end_date or start_date == METHOD_DATE:
            return METHOD_NOTE
        return ""
    if METHOD_DATE in period_str or period_str.strip() == "2025-03":
        return METHOD_NOTE
    return ""


def process_value_formatting(data: dict) -> dict:
    """Normalize NULLs, convert rank 11 to '10+ (Serious)', and set safe field fallbacks."""
    processed: dict = {}
    for key, val in data.items():
        if key == "cross_2025_03_22_note":
            processed[key] = "" if val is None or str(val).strip().upper() == "NULL" else str(val)
        elif val is None or val == "" or str(val).strip().upper() == "NULL":
            processed[key] = NA_TEXT
        elif key in _SERIOUS_RANK_KEYS and (val == 11 or str(val).strip() == "11"):
            processed[key] = "10+ (Serious)"
        else:
            processed[key] = val

    if "episode_hours_count" in data:
        if not processed.get("episode_hours_count") or processed.get("episode_hours_count") in (0, NA_TEXT):
            processed["episode_hours_count"] = "0"
            if "high_risk_hours" in data and (
                not processed.get("high_risk_hours") or processed.get("high_risk_hours") == NA_TEXT
            ):
                processed["high_risk_hours"] = "No hours reached AQHI 7 or above during this period."
    elif "high_risk_hours" in data and (
        not processed.get("high_risk_hours") or processed.get("high_risk_hours") == NA_TEXT
    ):
        processed["high_risk_hours"] = "No hours reached AQHI 7 or above during this period."

    if "peak_hours" in data and (not processed.get("peak_hours") or processed.get("peak_hours") == NA_TEXT):
        processed["peak_hours"] = "None recorded"

    if "weather_note" in data and (not processed.get("weather_note") or processed.get("weather_note") == NA_TEXT):
        processed["weather_note"] = "No meteorological summary available."

    return processed


def _collect_required_vars(template_row: dict) -> list[str]:
    req_raw = template_row.get("required_variables", [])
    if isinstance(req_raw, str):
        try:
            required = list(json.loads(req_raw))
        except json.JSONDecodeError:
            required = []
    else:
        required = list(req_raw)
    seen = set(required)
    for key in ("text_template", "markdown_template", "html_template"):
        tpl_str = template_row.get(key) or ""
        for _, field_name, _, _ in Formatter().parse(tpl_str):
            if field_name and field_name not in seen:
                seen.add(field_name)
                required.append(field_name)
    return required


def render_report_templates(
    template_row: dict,
    input_variables: dict,
    *,
    escape_html: bool = True,
) -> dict[str, str]:
    """Validate placeholders and render plain text, Markdown, and HTML outputs."""
    required_vars = _collect_required_vars(template_row)
    processed_vars = process_value_formatting(input_variables)

    if not processed_vars.get("cross_2025_03_22_note"):
        period_val = str(
            input_variables.get("obs_date")
            or input_variables.get("month")
            or ""
        )
        start_val = str(input_variables.get("start_date") or "")
        end_val = str(input_variables.get("end_date") or "")
        processed_vars["cross_2025_03_22_note"] = check_cross_2025_03_22(
            start_date=start_val,
            end_date=end_val,
            period_str=period_val,
        )

    missing_vars = [var for var in required_vars if var not in processed_vars]
    if missing_vars:
        msg = (
            "No valid data available: Missing required field(s) "
            f"[{', '.join(missing_vars)}] for briefing generation."
        )
        return {
            "text_output": msg,
            "markdown_output": f"> **{msg}**",
            "html_output": f'<div class="warning"><p>{escape(msg)}</p></div>',
        }

    html_vars = (
        {k: escape(v) if isinstance(v, str) else v for k, v in processed_vars.items()}
        if escape_html
        else processed_vars
    )
    try:
        text_out = template_row["text_template"].format(**processed_vars)
        md_out = template_row["markdown_template"].format(**processed_vars)
        html_out = template_row["html_template"].format(**html_vars)
    except KeyError as exc:
        err_msg = f"Template Render Error: Missing key {exc} in input data."
        return {
            "text_output": err_msg,
            "markdown_output": f"> **{err_msg}**",
            "html_output": f'<div class="error"><p>{escape(err_msg)}</p></div>',
        }

    return {
        "text_output": text_out,
        "markdown_output": md_out,
        "html_output": html_out,
    }


def _coverage_summary(row: dict) -> str:
    return (
        f'{row["valid_hours"]} valid hours, {row["missing_hours"]} missing hours, '
        f'{row["substitute_hours"]} valid substitute hours.'
    )


def _weather_summary(row: dict) -> str:
    parts = []
    for key, label, unit in (
        ("mean_temp_c", "mean temperature", "°C"),
        ("mean_rh_pct", "mean relative humidity", "%"),
        ("rainfall_mm", "rainfall", "mm"),
        ("mean_wind_kmh", "mean wind speed", "km/h"),
    ):
        if row.get(key) is not None:
            parts.append(f"{label} {row[key]} {unit}")
    if row.get("weather_note"):
        parts.append(str(row["weather_note"]))
    return ", ".join(parts) or NA_TEXT


def _pollutant_summary(row: dict, specs: tuple[tuple[str, str], ...]) -> str:
    parts = []
    for key, label in specs:
        val = row.get(f"avg_{key}")
        count = row.get(f"valid_{key}_hours", 0)
        parts.append(f"{label} {val if val is not None else NA_TEXT} ({count} h)")
    return ", ".join(parts)


def _period_split_note(
    station_name: str,
    start_date: str,
    end_date: str,
    db_path: Path | str,
) -> str:
    """Summarize Pre-22 Mar vs From 22 Mar AQHI metrics when a range spans 2025-03-22."""
    if not (start_date and end_date and start_date < METHOD_DATE <= end_date):
        return ""
    rows = _select_rows(
        """SELECT CASE WHEN h.obs_date < ? THEN 'pre' ELSE 'post' END AS seg,
                  MAX(CASE WHEN h.is_missing = 0 THEN h.sort_rank END) AS max_rank,
                  ROUND(AVG(CASE WHEN h.is_missing = 0 THEN h.numeric_value END), 2) AS avg_aqhi,
                  COUNT(CASE WHEN h.is_missing = 0 THEN h.numeric_value END) AS numeric_n
           FROM hourly_aqhi h
           JOIN stations s USING(station_id)
           WHERE s.name = ? AND h.obs_date BETWEEN ? AND ?
           GROUP BY seg""",
        (METHOD_DATE, station_name, start_date, end_date),
        db_path,
    )
    by_seg = {row["seg"]: row for row in rows}
    parts = []
    for seg, label in (("pre", "Pre-22 Mar"), ("post", "From 22 Mar")):
        row = by_seg.get(seg)
        if row and row["max_rank"] is not None:
            avg_txt = row["avg_aqhi"] if row["avg_aqhi"] is not None else NA_TEXT
            parts.append(
                f'{label}: max AQHI {aqhi_label(row["max_rank"])}, '
                f'mean {avg_txt} ({row["numeric_n"]} h)'
            )
    return f"Period split — {'; '.join(parts)}." if parts else ""


def _adapt_weather_pollution(rows: list[dict], params: dict, db_path: Path | str) -> tuple[dict, str]:
    # Q04 returns rounded daily means; recompute exact period means over all hourly rows.
    bound = {
        "station_name": params["station_name"],
        "start_date": params["start_date"],
        "end_date": params["end_date"],
    }
    stats = _select_rows(
        """SELECT ROUND(AVG(p.pm25), 2) AS avg_pm25, COUNT(p.pm25) AS n_pm25,
                  ROUND(AVG(p.pm10), 2) AS avg_pm10, COUNT(p.pm10) AS n_pm10,
                  ROUND(AVG(p.no2), 2) AS avg_no2, COUNT(p.no2) AS n_no2,
                  ROUND(AVG(p.o3), 2) AS avg_o3, COUNT(p.o3) AS n_o3,
                  ROUND(AVG(p.so2), 2) AS avg_so2, COUNT(p.so2) AS n_so2,
                  ROUND(AVG(p.co), 2) AS avg_co, COUNT(p.co) AS n_co
           FROM hourly_aqhi h
           JOIN stations s USING(station_id)
           LEFT JOIN hourly_pollutants p USING(station_id, obs_date, obs_hour)
           WHERE s.name = :station_name AND h.obs_date BETWEEN :start_date AND :end_date""",
        bound,
        db_path,
    )[0]
    counts = ", ".join(
        f'{label} {stats["n_" + key]}'
        for key, label in (
            ("pm25", "PM2.5"),
            ("pm10", "PM10"),
            ("no2", "NO2"),
            ("o3", "O3"),
            ("so2", "SO2"),
            ("co", "CO"),
        )
    )
    ranks = [row["max_rank"] for row in rows if row.get("max_rank") is not None]
    aqhi_span = (
        f"Daily maximum AQHI ranged from {aqhi_label(min(ranks))} to {aqhi_label(max(ranks))}."
        if ranks
        else "No valid AQHI observations in period."
    )
    split_note = _period_split_note(
        params["station_name"], params["start_date"], params["end_date"], db_path
    )
    weather = " | ".join(f'{row["obs_date"]} {_weather_summary(row)}' for row in rows)
    note_parts = [
        f"Valid concentration measurements (hours) — {counts} (CO in 10 ug/m3).",
        aqhi_span,
    ]
    if split_note:
        note_parts.append(split_note)
    note_parts.append(
        "Daily HKO records provide meteorological context and do not establish "
        "causation of hourly AQHI peaks. Source: EPD & HKO."
    )
    return {**stats, "weather_note": weather}, " ".join(note_parts)


def adapt_query_result(
    query_code: str,
    rows: list[dict],
    params: dict,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> tuple[dict, str]:
    """Convert row-oriented SQL results from Task B queries into Task C template fields and note."""
    first = rows[0] if rows else {}
    if query_code == "Q07_high_risk_bulletin":
        coverage = _select_rows(
            """SELECT COUNT(*) AS n FROM hourly_aqhi h JOIN stations s USING(station_id)
               WHERE s.name = :station_name AND h.obs_date BETWEEN :start_date AND :end_date
               AND h.is_missing = 0""",
            {
                "station_name": params["station_name"],
                "start_date": params["start_date"],
                "end_date": params["end_date"],
            },
            db_path,
        )[0]["n"]
        if not coverage:
            raise ValueError("There are no valid AQHI observations in this date range.")
        h7 = sum(row["high_hours"] for row in rows)
        h8 = sum(row["very_high_hours"] for row in rows)
        h11 = sum(row["serious_hours"] for row in rows)
        tiers = f"Risk tiers — High (7): {h7} h, Very high (8-10): {h8} h, Serious (10+): {h11} h."
        hours = " | ".join(f'{row["obs_date"]} {row["high_risk_hours"]}' for row in rows)
        return (
            {
                "episode_hours_count": sum(row["high_or_above_hours"] for row in rows),
                "high_risk_hours": hours or "No valid observations reached AQHI 7 or above.",
            },
            f"Based on {coverage} valid hourly observations. {tiers} Source: EPD.",
        )

    if not rows:
        raise ValueError("The saved query returned no observations for these inputs.")

    if query_code == "Q01_daily_briefing":
        pollutants = _pollutant_summary(
            first, (("pm25", "PM2.5"), ("pm10", "PM10"), ("no2", "NO2"), ("o3", "O3"))
        )
        co_val = first.get("avg_co")
        co_txt = f"CO {co_val if co_val is not None else NA_TEXT} (10 ug/m3, {first.get('valid_co_hours', 0)} h)"
        note = (
            f"{_coverage_summary(first)} "
            f"Pollutant means (ug/m3) — {pollutants}; {co_txt}. Source: EPD & HKO."
        )
        return {**first, "weather_note": _weather_summary(first)}, note

    if query_code == "Q02_category_breakdown":
        counts = {row["category"].lower().replace(" ", "_") + "_hours": row["hours"] for row in rows}
        percentages = ", ".join(
            f'{row["category"]} {row["percentage"]}%'
            for row in rows
            if row["percentage"] is not None
        )
        note = f"{_coverage_summary(first)} Share of valid hours — {percentages}. Source: EPD."
        return {**first, **counts}, note

    if query_code == "Q03_station_comparison":
        by_name = {row["station_name"]: row for row in rows}
        fields: dict = {}
        detail: list[str] = []
        for side in ("a", "b"):
            row = by_name[params[f"station_{side}"]]
            key = f"station_{side}"
            fields.update(
                {
                    f"{key}_name": f'{row["station_name"]} ({row["station_type"]})',
                    f"{key}_max": row["max_aqhi"],
                    f"{key}_avg": row["avg_aqhi"],
                }
            )
            pols = _pollutant_summary(row, (("pm25", "PM2.5"), ("no2", "NO2")))
            detail.append(
                f'{row["station_name"]} — {row["high_or_above_hours"]} High-or-above hours, '
                f'{row["numeric_aqhi_hours"]} numeric observations in the mean, '
                f'pollutant means (ug/m3): {pols}.'
            )
        return fields, " ".join(detail) + " AQHI averages exclude 10+ and missing hours. Source: EPD."

    if query_code == "Q04_weather_pollution":
        return _adapt_weather_pollution(rows, params, db_path)

    if query_code == "Q05_district_map":
        districts = [row for row in rows if row["row_type"] == "district"]
        roadside = [row for row in rows if row["row_type"] == "roadside"]
        covered = [row for row in districts if row["max_rank"] is not None]
        if not covered:
            raise ValueError("No district has valid General station observations on this date.")
        peak = max(row["max_rank"] for row in covered)
        ties = ", ".join(row["district_name"] for row in covered if row["max_rank"] == peak)
        no_general = ", ".join(
            sorted(row["district_name"] for row in districts if not row["general_station_count"])
        )
        roadside_summary = ", ".join(
            f'{row["station_name"]} ({row["district_name"]}): {aqhi_label(row["max_rank"])}'
            for row in roadside
        )
        note_parts = [
            f"{len(covered)} districts have valid General station observations.",
            "District maxima use General stations only. Roadside stations are shown separately.",
        ]
        if no_general:
            note_parts.append(f"Districts without a General station (unshaded): {no_general}.")
        if roadside_summary:
            note_parts.append(f"Roadside station maxima: {roadside_summary}.")
        note_parts.append("Source: EPD & C&SD.")
        return (
            {"total_districts": len(districts), "highest_district": ties, "max_aqhi": aqhi_label(peak)},
            " ".join(note_parts),
        )

    if query_code == "Q06_monthly_summary":
        risk_counts = (
            f'Risk hours — Low {first["low_hours"]}, Moderate {first["moderate_hours"]}, '
            f'High {first["high_hours"]}, Very high {first["very_high_hours"]}, '
            f'Serious {first["serious_hours"]}.'
        )
        pols = _pollutant_summary(first, (("pm25", "PM2.5"), ("o3", "O3")))
        start, end = month_bounds(params["month"])
        split_note = _period_split_note(params["station_name"], start, end, db_path)
        note_parts = [
            _coverage_summary(first),
            f'The mean uses {first["numeric_aqhi_hours"]} numeric hours and excludes 10+.',
            risk_counts,
            f"Monthly pollutant means (ug/m3) — {pols}.",
        ]
        if split_note:
            note_parts.append(split_note)
        note_parts.append("Source: EPD.")
        return first, " ".join(note_parts)

    if query_code == "Q08_news_flash":
        risk = first["high_risk_hours"] or "none among valid observations"
        station_count = _select_rows(
            "SELECT COUNT(*) AS n FROM stations WHERE station_type = ?",
            ("General",),
            db_path,
        )[0]["n"]
        if first["high_or_above_hours"] == 0:
            lead = (
                f'General stations peaked at AQHI {first["max_aqhi"]} on {first["obs_date"]}, '
                "and no station reached High (7) or above."
            )
        else:
            lead = (
                f'General stations peaked at AQHI {first["max_aqhi"]} on {first["obs_date"]}, '
                f'with {first["high_or_above_hours"]} clock hour(s) reaching High (7) or above.'
            )
        note = (
            f"{lead} Scope is the {station_count} General stations. "
            f'Exact station and hour pairs at the maximum — {first["peak_station_hours"]}. '
            f"Hours with High-or-above AQHI — {risk}. Source: EPD."
        )
        return first, note

    raise ValueError(f"Unsupported query code for template rendering: {query_code!r}.")


def checked_query_params(
    query_code: str,
    params: dict,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict:
    """Validate user inputs for the target saved query against schema conventions."""
    checked = {}
    for key in QUERY_DEFINITIONS[query_code].parameter_names:
        if key not in params:
            raise ValueError(f"Missing input {key}.")
        value = params[key]
        if key.startswith("station_"):
            _station_record(value, db_path)
        elif key.endswith("date"):
            validate_date(value)
        elif key == "month":
            month_bounds(value)
        checked[key] = value
    if query_code == "Q03_station_comparison" and checked["station_a"] == checked["station_b"]:
        raise ValueError("Choose two different stations.")
    if "start_date" in checked and checked["start_date"] > checked["end_date"]:
        raise ValueError("Start date must precede or equal end date.")
    return checked


def seed_report_templates(db_path: Path | str = DEFAULT_DB_PATH) -> int:
    """Upsert the 8 standard templates into report_templates without resetting template_id."""
    with closing(get_connection(db_path)) as conn, conn:
        records = []
        for tpl in DEFAULT_TEMPLATES:
            row = conn.execute(
                "SELECT query_id FROM saved_queries WHERE query_code = ?",
                (tpl["query_code"],),
            ).fetchone()
            if row is None:
                raise KeyError(
                    f"Saved query {tpl['query_code']!r} not found. Run seed_saved_queries() first."
                )
            req_vars_json = (
                tpl["required_variables"]
                if isinstance(tpl["required_variables"], str)
                else json.dumps(tpl["required_variables"])
            )
            records.append(
                (
                    row["query_id"],
                    tpl["name"],
                    tpl["scope"],
                    req_vars_json,
                    tpl["text_template"],
                    tpl["markdown_template"],
                    tpl["html_template"],
                    tpl["version"],
                )
            )
        conn.executemany(_SEED_TEMPLATE_SQL, records)
    return len(records)


def generate_report(
    template_name: str,
    params: dict,
    save: bool = True,
    db_path: Path | str = DEFAULT_DB_PATH,
    station_id: int | None = None,
    title: str | None = None,
    reporting_period: str | None = None,
) -> dict | int:
    """Query SQLite via saved_queries, validate coverage, render 3 formats, and optionally save."""
    template_rows = _select_rows(
        """SELECT t.*, q.query_code
           FROM report_templates t
           JOIN saved_queries q USING(query_id)
           WHERE t.name = ?""",
        (template_name,),
        db_path,
    )
    if not template_rows:
        raise ValueError(f"Template '{template_name}' not found in report_templates table.")

    template = template_rows[0]
    query_code = template["query_code"]
    checked = checked_query_params(query_code, params, db_path)
    rows = run_saved_query(query_code, checked, db_path)

    if "month" in checked:
        start, end = month_bounds(checked["month"])
        period = checked["month"]
    elif "start_date" in checked:
        start, end = checked["start_date"], checked["end_date"]
        period = f"{start} to {end}"
    else:
        start = end = period = checked["obs_date"]

    method_note = check_cross_2025_03_22(start_date=start, end_date=end, period_str=period)

    try:
        if query_code in {"Q01_daily_briefing", "Q02_category_breakdown", "Q06_monthly_summary", "Q08_news_flash"}:
            if rows and not rows[0]["valid_hours"]:
                raise ValueError("There are no valid AQHI observations for these inputs.")
        if query_code == "Q03_station_comparison" and (
            len(rows) != 2 or any(not row["valid_hours"] for row in rows)
        ):
            raise ValueError("Both stations need valid AQHI for a formal comparison.")

        fields, note = adapt_query_result(query_code, rows, checked, db_path)
        combined_note = " ".join(filter(None, (method_note, note)))
        merged_fields = {**checked, **fields, "cross_2025_03_22_note": combined_note}

        required = set(_collect_required_vars(template))
        missing = required - merged_fields.keys()
        if missing:
            raise ValueError(
                f"Required template fields missing from query conversion: {sorted(missing)}."
            )

        rendered = render_report_templates(template, merged_fields, escape_html=True)
        if rendered["text_output"].startswith(("No valid data available:", "Template Render Error:")):
            raise ValueError(rendered["text_output"])
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        msg = f"No valid data available for formal briefing '{template_name}' ({period}): {exc}"
        if method_note:
            msg += f" {method_note}"
        return {
            "formal": False,
            "report_id": None,
            "text_output": msg,
            "markdown_output": f"> **{msg}**",
            "html_output": f'<div class="warning"><p>{escape(msg)}</p></div>',
        }

    if not save:
        return {"formal": True, "report_id": None, **rendered}

    resolved_station_id = station_id
    if resolved_station_id is None and "station_name" in checked:
        resolved_station_id = _station_record(checked["station_name"], db_path)["station_id"]

    resolved_period = reporting_period or period
    resolved_title = title or f"{template_name} · {resolved_period}"

    with closing(get_connection(db_path)) as conn, conn:
        cursor = conn.execute(
            """INSERT INTO generated_reports (
                   template_id, station_id, title, parameter_values,
                   reporting_period, text_output, markdown_output, html_output
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                template["template_id"],
                resolved_station_id,
                resolved_title,
                json.dumps(checked),
                resolved_period,
                rendered["text_output"],
                rendered["markdown_output"],
                rendered["html_output"],
            ),
        )
        return int(cursor.lastrowid)


def export_report_files(
    report_id: int,
    out_dir: Path | str = "exported_reports",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, str]:
    """Extract one stored report from generated_reports and export .txt, .md, and .html files."""
    rows = _select_rows(
        "SELECT title, text_output, markdown_output, html_output FROM generated_reports WHERE report_id = ?",
        (report_id,),
        db_path,
    )
    if not rows:
        raise ValueError(f"Report ID = {report_id} not found.")
    row = rows[0]

    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"report_{report_id}"
    outputs = {
        "txt": row["text_output"] or "",
        "md": row["markdown_output"] or "",
        "html": row["html_output"] or "",
    }
    saved_paths: dict[str, str] = {}
    for ext, content in outputs.items():
        file_path = target_dir / f"{base_name}.{ext}"
        file_path.write_text(content, encoding="utf-8")
        saved_paths[ext] = str(file_path)
    return saved_paths
