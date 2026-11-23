"""ETL pipeline for loading 2025 Hong Kong AQHI CSVs, 18 districts, and 18 stations into SQLite."""

from __future__ import annotations

from contextlib import closing
import csv
from pathlib import Path
import sys
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.schema import DEFAULT_DB_PATH, PROJECT_ROOT, get_connection, init_db

AQHI_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "aqhi_2025"

# 18 official Hong Kong District Council districts (C&SD population and area populated separately).
DISTRICTS_SEED: list[tuple[str, str, str]] = [
    ("CW", "Central and Western", "Hong Kong Island"),
    ("WC", "Wan Chai", "Hong Kong Island"),
    ("EA", "Eastern", "Hong Kong Island"),
    ("SO", "Southern", "Hong Kong Island"),
    ("YTM", "Yau Tsim Mong", "Kowloon"),
    ("SSP", "Sham Shui Po", "Kowloon"),
    ("KLC", "Kowloon City", "Kowloon"),
    ("WTS", "Wong Tai Sin", "Kowloon"),
    ("KT", "Kwun Tong", "Kowloon"),
    ("KTS", "Kwai Tsing", "New Territories"),
    ("TW", "Tsuen Wan", "New Territories"),
    ("TM", "Tuen Mun", "New Territories"),
    ("YL", "Yuen Long", "New Territories"),
    ("NO", "North", "New Territories"),
    ("TP", "Tai Po", "New Territories"),
    ("ST", "Sha Tin", "New Territories"),
    ("SK", "Sai Kung", "New Territories"),
    ("IS", "Islands", "New Territories"),
]

# 18 EPD monitoring stations matching exact CSV header names (15 General + 3 Roadside).
# Coordinates (latitude, longitude) remain NULL until verified against official EPD/CSDI data.
STATIONS_SEED: list[tuple[str, str, str, str]] = [
    ("CW", "Central/Western", "General", "Central and Western"),
    ("SO", "Southern", "General", "Southern"),
    ("EN", "Eastern", "General", "Eastern"),
    ("KT", "Kwun Tong", "General", "Kwun Tong"),
    ("SSP", "Sham Shui Po", "General", "Sham Shui Po"),
    ("KC", "Kwai Chung", "General", "Kwai Tsing"),
    ("TW", "Tsuen Wan", "General", "Tsuen Wan"),
    ("TKO", "Tseung Kwan O", "General", "Sai Kung"),
    ("YL", "Yuen Long", "General", "Yuen Long"),
    ("TM", "Tuen Mun", "General", "Tuen Mun"),
    ("TC", "Tung Chung", "General", "Islands"),
    ("TP", "Tai Po", "General", "Tai Po"),
    ("ST", "Sha Tin", "General", "Sha Tin"),
    ("NO", "North", "General", "North"),
    ("MB", "Tap Mun", "General", "Tai Po"),
    ("CB", "Causeway Bay", "Roadside", "Wan Chai"),
    ("CL", "Central", "Roadside", "Central and Western"),
    ("MK", "Mong Kok", "Roadside", "Yau Tsim Mong"),
]


def aqhi_category_from_rank(sort_rank: int) -> str:
    """Map an AQHI sort rank (1-11) to its official health risk category."""
    if 1 <= sort_rank <= 3:
        return "Low"
    if 4 <= sort_rank <= 6:
        return "Moderate"
    if sort_rank == 7:
        return "High"
    if 8 <= sort_rank <= 10:
        return "Very high"
    if sort_rank == 11:
        return "Serious"
    raise ValueError(f"Invalid AQHI sort_rank: {sort_rank}")


def parse_aqhi_cell(raw_cell: str) -> tuple[str | None, int | None, int | None, str | None, int, int]:
    """Parse one raw EPD AQHI cell into normalized database fields.

    Returns:
        (raw_value, numeric_value, sort_rank, category, is_substitute, is_missing)
    """
    text = raw_cell.strip()
    is_substitute = 1 if "*" in text else 0
    core = text.replace("*", "").strip()

    # Empty cell, '-', and '-*' all denote missing AQHI observations (not zero).
    if core == "" or core == "-":
        return (text if text else None, None, None, None, is_substitute, 1)

    # '10+' stays a distinct Serious category; sort_rank=11 is for sorting/max only, never averaged.
    if core == "10+":
        return (text, None, 11, "Serious", is_substitute, 0)

    if core.isdigit():
        val = int(core)
        if not 1 <= val <= 10:
            raise ValueError(f"AQHI integer out of range 1..10: {raw_cell!r}")
        return (text, val, val, aqhi_category_from_rank(val), is_substitute, 0)

    raise ValueError(f"Unrecognized AQHI cell value: {raw_cell!r}")


def parse_aqhi_csv(csv_path: Path) -> tuple[list[str], list[dict[str, Any]], dict[tuple[str, str], tuple[int | None, int]]]:
    """Read one monthly EPD AQHI CSV file into hourly rows and Daily Max check targets."""
    lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
    rows = list(csv.reader(lines))
    header_idx = next(i for i, row in enumerate(rows) if len(row) >= 2 and row[:2] == ["Date", "Hour"])
    station_names = [name.strip() for name in rows[header_idx][2:] if name.strip()]

    hourly_records: list[dict[str, Any]] = []
    daily_max_targets: dict[tuple[str, str], tuple[int | None, int]] = {}
    current_date: str | None = None

    for row in rows[header_idx + 1 :]:
        if not row or all(not cell.strip() for cell in row):
            continue
        if row[0].strip():
            current_date = row[0].strip()
        if current_date is None:
            raise ValueError(f"Missing Date before row in {csv_path.name}: {row}")

        hour_str = row[1].strip() if len(row) > 1 else ""
        if hour_str.lower() == "daily max":
            for idx, station in enumerate(station_names):
                cell = row[idx + 2] if idx + 2 < len(row) else ""
                _, _, sort_rank, _, _, is_missing = parse_aqhi_cell(cell)
                daily_max_targets[(station, current_date)] = (sort_rank, is_missing)
            continue

        if not hour_str.isdigit():
            raise ValueError(f"Unexpected Hour token in {csv_path.name}: {row}")

        obs_hour = int(hour_str)
        if not 1 <= obs_hour <= 24:
            raise ValueError(f"Hour out of 1..24 in {csv_path.name}: {obs_hour}")

        for idx, station in enumerate(station_names):
            cell = row[idx + 2] if idx + 2 < len(row) else ""
            raw_val, num_val, sort_rank, category, is_sub, is_miss = parse_aqhi_cell(cell)
            hourly_records.append(
                {
                    "station_name": station,
                    "obs_date": current_date,
                    "obs_hour": obs_hour,
                    "raw_value": raw_val,
                    "numeric_value": num_val,
                    "sort_rank": sort_rank,
                    "category": category,
                    "is_substitute": is_sub,
                    "is_missing": is_miss,
                }
            )

    return station_names, hourly_records, daily_max_targets


def load_aqhi_2025(db_path: Path | str = DEFAULT_DB_PATH, raw_dir: Path = AQHI_RAW_DIR, reset_db: bool = True) -> dict[str, Any]:
    """Initialize schema, seed districts/stations, and import all 2025 monthly AQHI CSV files."""
    if reset_db:
        init_db(db_path, drop_existing=True)
    else:
        init_db(db_path, drop_existing=False)

    csv_files = sorted(raw_dir.glob("2025*_Eng.csv"))
    if len(csv_files) != 12:
        raise FileNotFoundError(f"Expected 12 monthly CSV files in {raw_dir}, found {len(csv_files)}")

    with closing(get_connection(db_path)) as conn, conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO districts (district_code, english_name, region)
            VALUES (?, ?, ?)
            """,
            DISTRICTS_SEED,
        )
        district_rows = conn.execute("SELECT district_id, english_name FROM districts").fetchall()
        district_id_by_name = {r["english_name"]: r["district_id"] for r in district_rows}

        station_params = [
            (code, name, stype, district_id_by_name[district_name])
            for code, name, stype, district_name in STATIONS_SEED
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO stations (code, name, station_type, district_id)
            VALUES (?, ?, ?, ?)
            """,
            station_params,
        )
        station_rows = conn.execute("SELECT station_id, name FROM stations").fetchall()
        station_id_by_name = {r["name"]: r["station_id"] for r in station_rows}

        all_daily_max: dict[tuple[str, str], tuple[int | None, int]] = {}
        computed_daily_max: dict[tuple[str, str], int | None] = {}
        total_inserted = 0

        for csv_file in csv_files:
            headers, records, daily_max = parse_aqhi_csv(csv_file)
            unknown = [h for h in headers if h not in station_id_by_name]
            if unknown:
                raise ValueError(f"Unknown stations in {csv_file.name}: {unknown}")

            all_daily_max.update(daily_max)
            insert_rows = []
            for rec in records:
                key = (rec["station_name"], rec["obs_date"])
                rank = rec["sort_rank"]
                if rank is not None:
                    prev = computed_daily_max.get(key)
                    computed_daily_max[key] = rank if prev is None or rank > prev else prev
                elif key not in computed_daily_max:
                    computed_daily_max[key] = None

                insert_rows.append(
                    (
                        station_id_by_name[rec["station_name"]],
                        rec["obs_date"],
                        rec["obs_hour"],
                        rec["raw_value"],
                        rec["numeric_value"],
                        rec["sort_rank"],
                        rec["category"],
                        rec["is_substitute"],
                        rec["is_missing"],
                    )
                )

            conn.executemany(
                """
                INSERT INTO hourly_aqhi (
                    station_id, obs_date, obs_hour, raw_value, numeric_value,
                    sort_rank, category, is_substitute, is_missing
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                insert_rows,
            )
            total_inserted += len(insert_rows)

        conn.commit()

        # Verify Daily Max rows match computed hourly maxima
        mismatches = []
        for key, (expected_rank, expected_missing) in all_daily_max.items():
            actual_rank = computed_daily_max.get(key)
            if expected_missing == 1 and actual_rank is None:
                continue
            if expected_rank != actual_rank:
                mismatches.append((key, expected_rank, actual_rank))

        stats = conn.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                SUM(CASE WHEN is_missing = 0 THEN 1 ELSE 0 END) AS valid_rows,
                SUM(is_missing) AS missing_rows,
                SUM(is_substitute) AS substitute_rows,
                SUM(CASE WHEN is_missing = 1 AND is_substitute = 1 THEN 1 ELSE 0 END) AS missing_with_asterisk,
                SUM(CASE WHEN raw_value = '10+' THEN 1 ELSE 0 END) AS serious_rows
            FROM hourly_aqhi
            """
        ).fetchone()

        example_apr1 = conn.execute(
            """
            SELECT
                COUNT(*) AS total_hours,
                SUM(CASE WHEN h.is_missing = 0 THEN 1 ELSE 0 END) AS valid_hours,
                MIN(h.numeric_value) AS min_aqhi,
                MAX(h.sort_rank) AS max_rank,
                SUM(CASE WHEN h.category = 'Low' THEN 1 ELSE 0 END) AS low_hours,
                SUM(CASE WHEN h.category = 'Moderate' THEN 1 ELSE 0 END) AS moderate_hours,
                SUM(h.is_missing) AS missing_hours,
                SUM(h.is_substitute) AS substitute_hours
            FROM hourly_aqhi h
            JOIN stations s ON s.station_id = h.station_id
            WHERE s.name = 'Central/Western' AND h.obs_date = '2025-04-01'
            """
        ).fetchone()

    return {
        "db_path": str(db_path),
        "csv_files_loaded": len(csv_files),
        "total_inserted": total_inserted,
        "daily_max_checked": len(all_daily_max),
        "daily_max_mismatches": mismatches,
        "summary": dict(stats),
        "example_2025_04_01_central_western": dict(example_apr1),
    }


if __name__ == "__main__":
    import json

    report = load_aqhi_2025()
    print(json.dumps(report, indent=2, ensure_ascii=False))
