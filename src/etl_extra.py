"""ETL pipeline for loading 2025 pollutants, HKO daily weather, station coordinates, and C&SD district metrics."""

from __future__ import annotations

from contextlib import closing
import csv
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.schema import DEFAULT_DB_PATH, PROJECT_ROOT, get_connection

RAW_DIR = PROJECT_ROOT / "data" / "raw"
POLLUTANTS_CSV = RAW_DIR / "air_hourly.csv"
WEATHER_DIR = RAW_DIR / "weather_2025"
GEO_DIR = RAW_DIR / "geo_population"
CSD_JSON = GEO_DIR / "csd_table_110_02001_en.json"
EPD_GEOJSON = GEO_DIR / "epd_monitoring_stations.geojson"

# Exact mapping from EPIC Simplified Chinese station labels to canonical stations.name
EPIC_ZH_TO_STATION: dict[str, str] = {
    "中西区": "Central/Western",
    "南区": "Southern",
    "东区": "Eastern",
    "观塘": "Kwun Tong",
    "深水埗": "Sham Shui Po",
    "葵涌": "Kwai Chung",
    "荃湾": "Tsuen Wan",
    "将军澳": "Tseung Kwan O",
    "元朗": "Yuen Long",
    "屯门": "Tuen Mun",
    "东涌": "Tung Chung",
    "大埔": "Tai Po",
    "沙田": "Sha Tin",
    "北区": "North",
    "塔门": "Tap Mun",
    "铜锣湾": "Causeway Bay",
    "中环": "Central",
    "旺角": "Mong Kok",
}


def load_district_demographics(conn: Any, csd_path: Path = CSD_JSON) -> int:
    """Update districts table with C&SD Table 110-02001 2025 land population and land area."""
    payload = json.loads(csd_path.read_text(encoding="utf-8"))
    by_district: dict[str, dict[str, float]] = {}
    for row in payload.get("dataSet", []):
        if row.get("period") != "2025":
            continue
        dc = (row.get("DC") or "").strip()
        if len(dc) != 1:  # Individual districts have 1-letter DC codes A..T (excluding Total/HK/KLN/NT)
            continue
        name = row["DCDesc"].strip()
        sv = row.get("sv")
        if sv in ("MYPOPN_LAND", "LA") and row.get("figure") not in (None, ""):
            by_district.setdefault(name, {})[sv] = float(row["figure"])

    updated = 0
    for name, metrics in by_district.items():
        pop = int(round(metrics["MYPOPN_LAND"] * 1000)) if "MYPOPN_LAND" in metrics else None
        area = round(metrics["LA"], 2) if "LA" in metrics else None
        cur = conn.execute(
            """
            UPDATE districts
            SET population_2025 = ?, area_sqkm = ?, population_ref_year = ?
            WHERE english_name = ?
            """,
            (pop, area, "2025 Mid-year (C&SD Table 110-02001)", name),
        )
        if cur.rowcount != 1:
            raise ValueError(f"District not matched in DB for C&SD row: {name!r}")
        updated += 1
    return updated


def load_station_coordinates(conn: Any, epd_path: Path = EPD_GEOJSON) -> int:
    """Update stations table with official EPD latitude/longitude from CSDI GeoJSON."""
    payload = json.loads(epd_path.read_text(encoding="utf-8"))
    suffix = " Air Quality Monitoring Station"
    updated = 0
    for feat in payload.get("features", []):
        props = feat["properties"]
        full_name = props["NameEN"].strip()
        if not full_name.endswith(suffix):
            raise ValueError(f"Unexpected EPD station name format: {full_name!r}")
        short_name = full_name[: -len(suffix)]
        lat = float(props["Latitude"])
        lon = float(props["Longitude"])
        aqms_type = props.get("AqmsTypeEN", "").upper()
        expected_type = "Roadside" if "ROADSIDE" in aqms_type else "General"

        row = conn.execute(
            "SELECT station_id, station_type FROM stations WHERE name = ?",
            (short_name,),
        ).fetchone()
        if row is None:
            raise ValueError(f"EPD GeoJSON station not found in DB: {short_name!r}")
        if row["station_type"] != expected_type:
            raise ValueError(
                f"Station type mismatch for {short_name}: DB={row['station_type']} vs CSDI={expected_type}"
            )
        conn.execute(
            "UPDATE stations SET latitude = ?, longitude = ? WHERE station_id = ?",
            (lat, lon, row["station_id"]),
        )
        updated += 1
    return updated


def _read_hko_daily_series_2025(csv_path: Path) -> dict[str, tuple[float | None, str]]:
    """Read a 2025 daily HKO/KP CSV into {obs_date: (float_or_none, raw_token)}."""
    series: dict[str, tuple[float | None, str]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 4 or row[0].strip() != "2025":
                continue
            y, m, d = int(row[0]), int(row[1]), int(row[2])
            obs_date = f"{y:04d}-{m:02d}-{d:02d}"
            raw = row[3].strip()
            if raw == "Trace":
                series[obs_date] = (0.0, "Trace")
            elif raw in ("", "***", "N.A."):
                series[obs_date] = (None, raw or "MISSING")
            else:
                series[obs_date] = (float(raw), raw)
    return series


def load_daily_weather_2025(conn: Any, weather_dir: Path = WEATHER_DIR) -> int:
    """Merge 7 HKO/King's Park 2025 daily CSV series and upsert into daily_weather."""
    mean_t = _read_hko_daily_series_2025(weather_dir / "hko_daily_mean_temp.csv")
    max_t = _read_hko_daily_series_2025(weather_dir / "hko_daily_max_temp.csv")
    min_t = _read_hko_daily_series_2025(weather_dir / "hko_daily_min_temp.csv")
    rh = _read_hko_daily_series_2025(weather_dir / "daily_HKO_RH_ALL.csv")
    rf = _read_hko_daily_series_2025(weather_dir / "daily_HKO_RF_ALL.csv")
    wspd = _read_hko_daily_series_2025(weather_dir / "daily_KP_WSPD_ALL.csv")
    sun = _read_hko_daily_series_2025(weather_dir / "daily_KP_SUN_ALL.csv")

    all_dates = sorted(mean_t.keys())
    if len(all_dates) != 365:
        raise ValueError(f"Expected 365 dates for 2025 weather, got {len(all_dates)}")

    conn.execute("DELETE FROM daily_weather WHERE obs_date LIKE '2025-%'")
    rows_to_insert = []
    for dt in all_dates:
        notes = ["Temp/RH/Rain: HKO HQ; Wind/Sunshine: King's Park (KP)"]
        if rf[dt][1] == "Trace":
            notes.append("Rainfall=Trace (<0.05 mm stored as 0.0)")
        if wspd[dt][0] is None:
            notes.append(f"Wind unavailable ({wspd[dt][1]})")
        rows_to_insert.append(
            (
                dt,
                mean_t[dt][0],
                max_t[dt][0],
                min_t[dt][0],
                rh[dt][0],
                rf[dt][0],
                wspd[dt][0],
                sun[dt][0],
                "; ".join(notes),
            )
        )

    conn.executemany(
        """
        INSERT INTO daily_weather (
            obs_date, mean_temp_c, max_temp_c, min_temp_c,
            mean_rh_pct, rainfall_mm, mean_wind_kmh, sunshine_hours, source_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_to_insert,
    )
    return len(rows_to_insert)


def _parse_pollutant_val(token: str) -> float | None:
    text = token.strip()
    if text in ("", "N.A.", "-", "***"):
        return None
    return float(text)


def load_hourly_pollutants_2025(conn: Any, csv_path: Path = POLLUTANTS_CSV) -> int:
    """Import 2025 EPIC hourly pollutant concentrations into hourly_pollutants."""
    station_rows = conn.execute("SELECT station_id, name FROM stations").fetchall()
    station_id_by_name = {r["name"]: r["station_id"] for r in station_rows}

    conn.execute("DELETE FROM hourly_pollutants WHERE obs_date LIKE '2025-%'")

    batch: list[tuple[Any, ...]] = []
    total = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = None
        for row in reader:
            if row and row[0].strip() == "日期":
                header = [c.strip() for c in row]
                break
        if header != ["日期", "小时", "监测站", "SO2", "NO2", "CO", "RSP", "O3", "FSP"]:
            raise ValueError(f"Unexpected EPIC CSV header: {header}")

        for row in reader:
            if not row or not row[0].strip():
                continue
            obs_date = datetime.strptime(row[0].strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
            obs_hour = int(row[1].strip())
            zh_station = row[2].strip()
            en_station = EPIC_ZH_TO_STATION.get(zh_station)
            if en_station is None:
                raise ValueError(f"Unmapped EPIC station name: {zh_station!r}")
            station_id = station_id_by_name[en_station]

            so2 = _parse_pollutant_val(row[3])
            no2 = _parse_pollutant_val(row[4])
            co = _parse_pollutant_val(row[5])
            pm10 = _parse_pollutant_val(row[6])   # RSP
            o3 = _parse_pollutant_val(row[7])
            pm25 = _parse_pollutant_val(row[8])   # FSP

            batch.append(
                (
                    station_id,
                    obs_date,
                    obs_hour,
                    pm25,
                    "ug/m3",
                    pm10,
                    "ug/m3",
                    o3,
                    "ug/m3",
                    no2,
                    "ug/m3",
                    so2,
                    "ug/m3",
                    co,
                    "10 ug/m3",
                )
            )
            if len(batch) >= 10000:
                conn.executemany(
                    """
                    INSERT INTO hourly_pollutants (
                        station_id, obs_date, obs_hour,
                        pm25, pm25_unit, pm10, pm10_unit, o3, o3_unit,
                        no2, no2_unit, so2, so2_unit, co, co_unit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                total += len(batch)
                batch.clear()

        if batch:
            conn.executemany(
                """
                INSERT INTO hourly_pollutants (
                    station_id, obs_date, obs_hour,
                    pm25, pm25_unit, pm10, pm10_unit, o3, o3_unit,
                    no2, no2_unit, so2, so2_unit, co, co_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            total += len(batch)
    return total


def run_all_extra_etl(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Run all supplemental 2025 ETL loaders and verify joined records."""
    with closing(get_connection(db_path)) as conn, conn:
        districts_updated = load_district_demographics(conn)
        stations_updated = load_station_coordinates(conn)
        weather_inserted = load_daily_weather_2025(conn)
        pollutants_inserted = load_hourly_pollutants_2025(conn)
        conn.commit()

        apr1_check = conn.execute(
            """
            SELECT
                w.obs_date, w.mean_temp_c, w.max_temp_c, w.min_temp_c,
                w.mean_rh_pct, w.rainfall_mm, w.mean_wind_kmh, w.sunshine_hours,
                ROUND(AVG(p.pm25), 2) AS avg_pm25,
                ROUND(AVG(p.no2), 2) AS avg_no2,
                ROUND(AVG(p.o3), 2) AS avg_o3,
                COUNT(p.pm25) AS valid_pm25_hours
            FROM daily_weather w
            JOIN hourly_pollutants p ON p.obs_date = w.obs_date
            JOIN stations s ON s.station_id = p.station_id
            WHERE w.obs_date = '2025-04-01' AND s.name = 'Central/Western'
            GROUP BY w.obs_date
            """
        ).fetchone()

        missing_coords = conn.execute(
            "SELECT COUNT(*) FROM stations WHERE latitude IS NULL OR longitude IS NULL"
        ).fetchone()[0]
        missing_pop = conn.execute(
            "SELECT COUNT(*) FROM districts WHERE population_2025 IS NULL OR area_sqkm IS NULL"
        ).fetchone()[0]

    return {
        "db_path": str(db_path),
        "districts_updated": districts_updated,
        "stations_updated": stations_updated,
        "weather_days_inserted": weather_inserted,
        "pollutants_rows_inserted": pollutants_inserted,
        "stations_missing_coords": missing_coords,
        "districts_missing_demographics": missing_pop,
        "example_2025_04_01_central_western_weather_pollutants": dict(apr1_check),
    }


if __name__ == "__main__":
    print(json.dumps(run_all_extra_etl(), indent=2, ensure_ascii=False))
