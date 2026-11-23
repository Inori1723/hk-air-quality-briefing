"""Template 3: Comparison of Two Stations (Query Code: Q03_station_comparison)"""

TEMPLATE = {
    "query_code": "Q03_station_comparison",
    "name": "Comparison of Two Stations",
    "scope": "Comparative",
    "required_variables": [
        "obs_date", "station_a_name", "station_a_max", "station_a_avg",
        "station_b_name", "station_b_max", "station_b_avg", "cross_2025_03_22_note"
    ],
    "text_template": (
        "STATION COMPARISON BRIEFING ({obs_date})\n"
        "1. {station_a_name}: Max AQHI = {station_a_max}, Avg AQHI = {station_a_avg}\n"
        "2. {station_b_name}: Max AQHI = {station_b_max}, Avg AQHI = {station_b_avg}\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## Station Comparison Briefing ({obs_date})\n\n"
        "| Station Name | Max AQHI | Average AQHI |\n"
        "|---|---|---|\n"
        "| {station_a_name} | `{station_a_max}` | `{station_a_avg}` |\n"
        "| {station_b_name} | `{station_b_max}` | `{station_b_avg}` |\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"comparison-card\">\n"
        "  <h3>Station Comparison Briefing ({obs_date})</h3>\n"
        "  <table>\n"
        "    <thead><tr><th>Station Name</th><th>Max AQHI</th><th>Average AQHI</th></tr></thead>\n"
        "    <tbody>\n"
        "      <tr><td>{station_a_name}</td><td><code>{station_a_max}</code></td><td><code>{station_a_avg}</code></td></tr>\n"
        "      <tr><td>{station_b_name}</td><td><code>{station_b_max}</code></td><td><code>{station_b_avg}</code></td></tr>\n"
        "    </tbody>\n"
        "  </table>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}