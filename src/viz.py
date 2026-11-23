"""Plot station AQHI observations and map district General-station maxima."""

from collections import Counter
from html import escape
from pathlib import Path
from textwrap import fill
import json
import logging

import folium
from matplotlib.figure import Figure
from matplotlib.patches import Patch

from src.queries import QUERY_DEFINITIONS, run_saved_query
from src.schema import DEFAULT_DB_PATH, PROJECT_ROOT, get_connection
from src.task_d_integration import (
    METHOD_DATE, METHOD_NOTE, RISKS, aqhi_label, month_bounds, risk_label,
    select, station_record, validate_date,
)

GEOJSON_PATH = PROJECT_ROOT / "data/raw/geo_population/cydalytics_hkg_adm1.geojson"
RISK_COLORS = dict(zip(RISKS, ("#4E9B7A", "#DDA13C", "#E67E22", "#C0392B", "#6C3483")))
NO_GENERAL = "#D8DEE4"
NO_VALID = "#A9B7C5"
INK = "#172E41"
BLUE = "#205B82"
ROAD = "#93521D"
SOURCE = "Source  Hong Kong Environmental Protection Department (EPD)"
HOURS = tuple(range(1, 25))
LOGGER = logging.getLogger(__name__)


def hourly_data(station_name, obs_date, db_path=DEFAULT_DB_PATH):
    """Return a station, a full 01–24 plotting series and valid-hour statistics."""
    validate_date(obs_date)
    station = station_record(station_name, db_path)
    rows = select(
        """SELECT obs_hour, sort_rank, category, is_missing, is_substitute
           FROM hourly_aqhi WHERE station_id = ? AND obs_date = ? ORDER BY obs_hour""",
        (station["station_id"], obs_date), db_path,
    )
    valid = {row["obs_hour"]: row for row in rows if not row["is_missing"]}
    maximum = max((row["sort_rank"] for row in valid.values()), default=None)
    return {
        "station": station,
        "positions": [valid[h]["sort_rank"] if h in valid else float("nan") for h in HOURS],
        "valid": len(valid), "missing": len(HOURS) - len(valid),
        "substitute": sum(row["is_substitute"] for row in valid.values()),
        "max_rank": maximum,
        "peaks": [h for h, row in valid.items() if row["sort_rank"] == maximum],
        "high_hours": sum(row["sort_rank"] >= 7 for row in valid.values()),
        "counts": Counter(row["category"] for row in valid.values()),
    }


def _coverage(data):
    return f'{data["valid"]} valid  ·  {data["missing"]} missing  ·  {data["substitute"]} valid substitutes'


def _figure(title, subtitle, height=4.8, panels=1):
    fig = Figure(figsize=(10, height), layout="constrained", facecolor="white")
    fig.suptitle(title, x=.07, ha="left", color=INK, weight="bold", fontsize=16)
    axes = fig.subplots(panels, 1, sharex=panels > 1, squeeze=False)[:, 0]
    axes[0].set_title(subtitle, loc="left", color="#40586A", fontsize=9.5, pad=10)
    for ax in axes:
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        for spine in ax.spines.values():
            spine.set_color("#A4B4C1")
        ax.tick_params(colors="#3E5466", labelsize=9)
        ax.grid(axis="y", color="#9DB0C1", alpha=.24, linewidth=.6)
    return fig, axes


def _save(fig, out_path, note=""):
    path = Path(out_path)
    if path.suffix.lower() != ".png":
        raise ValueError("Provide a .png chart output path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    footer = SOURCE + (f"\n{fill(note, width=117)}" if note else "")
    fig.supxlabel(footer, x=.07, ha="left", fontsize=8, color="#40586A")
    fig.savefig(path, dpi=300, bbox_inches="tight", pad_inches=.16)
    return path


def _scale(ax, bands=True):
    if bands:
        for category, low, high in zip(RISKS, (.5, 3.5, 6.5, 7.5, 10.5), (3.5, 6.5, 7.5, 10.5, 11.5)):
            ax.axhspan(low, high, color=RISK_COLORS[category], alpha=.15, linewidth=0, zorder=0)
    ax.set(ylim=(.5, 11.5), ylabel="AQHI")
    ax.set_yticks(range(1, 12), [aqhi_label(i) for i in range(1, 12)])


def _hours(ax):
    ax.set(xlim=(.5, 24.5), xlabel="Observation hour (Hong Kong time)")
    ax.set_xticks(HOURS, [f"{hour:02d}" for hour in HOURS])


def plot_hourly_aqhi(station_name, obs_date, out_path, db_path=DEFAULT_DB_PATH):
    """Save a 300 dpi PNG with all 24 hour labels, five risk bands and every peak."""
    data = hourly_data(station_name, obs_date, db_path)
    maximum = aqhi_label(data["max_rank"])
    peak_times = ", ".join(f"{h:02d}:00" for h in data["peaks"])
    peaks = fill(f"Daily maximum {maximum} at {peak_times}", width=107) if peak_times else "No valid AQHI observations"
    fig, (ax,) = _figure(f"Hourly AQHI at {station_name}", f"{obs_date}  ·  {_coverage(data)}\n{peaks}")
    _scale(ax)
    _hours(ax)
    ax.plot(HOURS, data["positions"], color=BLUE, linewidth=1.8, marker="o", markersize=3.5)
    if data["peaks"]:
        ax.scatter(data["peaks"], [data["max_rank"]] * len(data["peaks"]),
                   facecolor="white", edgecolor=BLUE, s=51, linewidth=1.6, zorder=4)
    ax.legend(handles=[Patch(color=color, alpha=.35, label=cat) for cat, color in RISK_COLORS.items()],
              loc="upper left", bbox_to_anchor=(0, -.17), ncol=5, frameon=False, fontsize=9)
    return _save(fig, out_path, "Circled points mark all valid peak hours. Gaps indicate missing observations.")


def plot_category_distribution(station_name, obs_date, out_path, db_path=DEFAULT_DB_PATH):
    """Save the five category counts and shares of valid hours as a 300 dpi PNG."""
    data = hourly_data(station_name, obs_date, db_path)
    fig, (ax,) = _figure(f"AQHI risk categories at {station_name}", f"{obs_date}  ·  {_coverage(data)}", height=4)
    counts = [data["counts"][category] for category in RISKS]
    ax.barh(RISKS, counts, color=[RISK_COLORS[c] for c in RISKS], height=.57)
    ax.invert_yaxis()
    ax.set_xlim(0, 30)
    ax.set_xticks(range(0, 25, 4))
    ax.set_xlabel("Hours")
    for i, count in enumerate(counts):
        label = f"{count} h ({100 * count / data['valid']:.1f}%)" if data["valid"] else "0 h (N/A)"
        ax.text(count + .35, i, label, color=INK, va="center", fontsize=9)
    note = "Percentages use valid AQHI hours." if data["valid"] else "No valid AQHI observations. Percentages are unavailable."
    return _save(fig, out_path, note)


def plot_station_comparison(station_a, station_b, obs_date, out_path, db_path=DEFAULT_DB_PATH):
    """Save a same-day comparison with station type, peak and AQHI ≥ 7 hours."""
    if station_a == station_b:
        raise ValueError("Choose two different stations for comparison.")
    series = [hourly_data(name, obs_date, db_path) for name in (station_a, station_b)]
    detail = [
        f'{name} ({data["station"]["station_type"]})   ·   Maximum {aqhi_label(data["max_rank"])}'
        f'   ·   {str(data["high_hours"]) if data["valid"] else "N/A"} High-or-above hours'
        f'   ·   {data["valid"]} valid hours'
        for name, data in zip((station_a, station_b), series)
    ]
    fig, (ax,) = _figure("Same-day station comparison", f"{obs_date}\n" + "\n".join(detail))
    _scale(ax)
    _hours(ax)
    ax.plot(HOURS, series[0]["positions"], label=station_a, color=BLUE,
            marker="o", markersize=3.5, linewidth=1.8)
    ax.plot(HOURS, series[1]["positions"], label=station_b, color=ROAD,
            marker="s", markerfacecolor="white", markersize=3, linewidth=1.5, linestyle="--")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -.17), ncol=2, frameon=False, fontsize=9)
    return _save(fig, out_path, "High-or-above means AQHI 7 or above. Gaps indicate missing observations.")


def plot_monthly_trend(station_name, month, out_path, db_path=DEFAULT_DB_PATH, *, pollutant="pm25"):
    """Plot calendar-day AQHI maxima with an independent PM2.5 or O3 mean panel.

    Use pollutant=None for AQHI only. Missing calendar days remain as gaps.
    """
    start, end = month_bounds(month)
    station = station_record(station_name, db_path)
    if pollutant not in (None, "pm25", "o3"):
        raise ValueError("Pollutant must be 'pm25', 'o3' or None.")
    params = (station["station_id"], start, end)
    maxima = select(
        """SELECT obs_date, MAX(sort_rank) AS maximum FROM hourly_aqhi
           WHERE station_id = ? AND obs_date BETWEEN ? AND ? AND is_missing = 0
           GROUP BY obs_date""", params, db_path,
    )
    values = {int(row["obs_date"][-2:]): row["maximum"] for row in maxima}
    means = {}
    if pollutant:
        rows = select(
            """SELECT obs_date, AVG(pm25) AS pm25, AVG(o3) AS o3 FROM hourly_pollutants
               WHERE station_id = ? AND obs_date BETWEEN ? AND ?
               GROUP BY obs_date""", params, db_path,
        )
        means = {int(row["obs_date"][-2:]): row[pollutant]
                 for row in rows if row[pollutant] is not None}
    days = list(range(1, int(end[-2:]) + 1))
    subtitle = f"{month}  ·  {len(values)} of {len(days)} days with valid AQHI"
    if pollutant and not means:
        subtitle += "  ·  No valid pollutant measurements"
    fig, axes = _figure(f"Monthly AQHI trend at {station_name}", subtitle,
                        height=6.4 if means else 4.6, panels=2 if means else 1)
    ax = axes[0]
    _scale(ax)
    ax.set_ylabel("Daily maximum AQHI")
    ax.plot(days, [values.get(day, float("nan")) for day in days], marker="o", color=BLUE, markersize=3.5)
    note = ""
    if means:
        label = {"pm25": "PM2.5", "o3": "Ozone (O₃)"}[pollutant]
        axes[1].plot(days, [means.get(day, float("nan")) for day in days],
                     marker="o", color=ROAD, markersize=3.5)
        axes[1].set_ylabel(f"Daily mean {label}\n(µg/m³)")
        note = "Concentration means use valid measurements in each day. "
    if start < METHOD_DATE <= end:
        for panel in axes:
            panel.axvline(22, linestyle="--", color="#394757", linewidth=1.3)
        ax.text(22.3, .94, "22 Mar · method update", transform=ax.get_xaxis_transform(),
                va="top", fontsize=8.5, bbox={"facecolor": "white", "edgecolor": "none", "alpha": .88})
        note += METHOD_NOTE
    axes[-1].set(xlim=(.5, len(days) + .5), xlabel="Day of month")
    axes[-1].set_xticks(days)
    return _save(fig, out_path, note)


def _map_style(feature):
    return {"fillColor": feature["properties"]["fill"], "fillOpacity": .67,
            "color": "#32485A", "weight": 1.1}


def _station_popup(row):
    lines = [
        ("Station", row["name"]), ("Type", row["station_type"]), ("District", row["district_name"]),
        ("Valid hours", f'{row["valid_hours"]}/24'), ("Maximum AQHI", aqhi_label(row["max_rank"])),
        ("Risk", risk_label(row["max_rank"])),
    ]
    if row["population_2025"] is not None:
        lines.append(("District population", f'{row["population_2025"]:,}'))
    if row["population_ref_year"]:
        lines.append(("Population reference", row["population_ref_year"]))
    def safe(value):
        return escape(str(value)).replace("`", "&#96;").replace("$", "&#36;")
    return "<br>".join(f"<strong>{key}</strong> {safe(value)}" for key, value in lines)


def build_district_map(obs_date, out_path=None, geojson_path=GEOJSON_PATH, db_path=DEFAULT_DB_PATH):
    """Build the Folium map and optionally save its complete HTML document.

    The map's task_d_query_source records whether Q05 came from saved_queries
    or the project's registered SQL definition was executed directly.
    """
    validate_date(obs_date)
    code, params = "Q05_district_map", {"obs_date": obs_date}
    if select("SELECT 1 FROM saved_queries WHERE query_code = ?", (code,), db_path):
        rows = run_saved_query(code, params, db_path)
        source = "saved_queries / Q05_district_map"
    else:
        rows = select(QUERY_DEFINITIONS[code].sql, params, db_path)
        source = "direct parameterized Q05_district_map (unseeded database)"
    LOGGER.info("District map data from %s", source)
    districts = {row["district_name"]: row for row in rows if row["row_type"] == "district"}
    geo = json.loads(Path(geojson_path).read_text(encoding="utf-8-sig"))
    features = geo["features"]
    names = [feature["properties"]["name_1"] for feature in features]
    if len(names) != len(set(names)) or set(names) != set(districts) or len(names) != 18:
        raise ValueError("GeoJSON must cover exactly the 18 unique database districts.")
    for feature in features:
        geometry = feature["geometry"]
        if geometry["type"] not in {"Polygon", "MultiPolygon"} or not geometry["coordinates"]:
            raise ValueError("Each district must have polygon geometry.")
        row = districts[feature["properties"]["name_1"]]
        rank = row["max_rank"]
        status = risk_label(rank) if row["general_station_count"] else "No general station"
        color = RISK_COLORS.get(status, NO_GENERAL if status == "No general station" else NO_VALID)
        feature["properties"].update(
            status=status, fill=color, maximum=aqhi_label(rank), valid_hours=row["valid_hours"],
            station_count=row["general_station_count"],
            population=f'{row["population_2025"]:,}' if row.get("population_2025") is not None else "N/A",
            area_sqkm=f'{row["area_sqkm"]:.2f} km²' if row.get("area_sqkm") is not None else "N/A",
            population_ref=row.get("population_ref_year") or "N/A",
        )
    fmap = folium.Map(location=[22.34, 114.13], zoom_start=10, tiles="OpenStreetMap", control_scale=True)
    fmap.task_d_query_source = source
    layer = folium.GeoJson(
        geo, name="District maxima · General stations", style_function=_map_style,
        highlight_function=lambda _: {"weight": 2.4},
        tooltip=folium.GeoJsonTooltip(
            fields=["name_1", "status", "maximum", "station_count", "valid_hours", "population", "area_sqkm", "population_ref"],
            aliases=[
                "District", "Risk or coverage", "Maximum AQHI", "General stations",
                "Valid station-hours", "Population (2025)", "Land area", "Population reference",
            ],
        ),
    ).add_to(fmap)
    fmap.fit_bounds(layer.get_bounds(), padding=(12, 12))
    layers = {kind: folium.FeatureGroup(name=f"{kind} stations").add_to(fmap)
              for kind in ("General", "Roadside")}
    stations = select(
        """SELECT s.*, d.english_name AS district_name, d.population_2025, d.population_ref_year,
                  COUNT(h.sort_rank) AS valid_hours, MAX(h.sort_rank) AS max_rank
           FROM stations s JOIN districts d USING(district_id)
           LEFT JOIN hourly_aqhi h ON h.station_id = s.station_id AND h.obs_date = ?
                AND h.is_missing = 0
           GROUP BY s.station_id ORDER BY s.station_type, s.name""", (obs_date,), db_path,
    )
    for row in stations:
        roadside = row["station_type"] == "Roadside"
        if row["latitude"] is None or row["longitude"] is None:
            raise ValueError(f'Station {row["name"]} is missing coordinates.')
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]], radius=7 if roadside else 5,
            color=ROAD if roadside else BLUE, weight=2, fill=True,
            fill_opacity=1, fill_color="white" if roadside else BLUE,
            tooltip=escape(row["name"]), popup=folium.Popup(_station_popup(row), max_width=320),
        ).add_to(layers[row["station_type"]])
    folium.LayerControl(collapsed=False).add_to(fmap)
    colors = {**RISK_COLORS, "No general station": NO_GENERAL, "No valid data": NO_VALID}
    legend = "".join(
        f'<div><span style="display:inline-block;width:12px;height:12px;margin-right:6px;'
        f'background:{color};opacity:.67;border:1px solid #32485A;vertical-align:middle"></span>{label}</div>'
        for label, color in colors.items()
    )
    fmap.get_root().html.add_child(folium.Element(
        '<aside style="position:fixed;bottom:26px;left:12px;z-index:999;'
        'padding:10px 12px;background:#fff;border:1px solid #b7c8d6;border-radius:6px;'
        'font:12px/1.45 system-ui;color:#172e41;box-shadow:0 2px 10px #172e4129">'
        f'<strong>District maximum AQHI</strong><div>{obs_date}</div>{legend}'
        '<div style="margin-top:5px">● General &nbsp; ◯ Roadside</div>'
        '<div>Source EPD · project colors</div>'
        f'<div title="{escape(source)}">Q05 data</div></aside>'
    ))
    if out_path is not None:
        path = Path(out_path)
        if path.suffix.lower() != ".html":
            raise ValueError("Provide an .html map output path.")
        path.parent.mkdir(parents=True, exist_ok=True)
        fmap.save(str(path))
    return fmap
