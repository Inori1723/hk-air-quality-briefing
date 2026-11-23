"""Template 1: Daily Station Briefing (Query Code: Q01_daily_briefing)"""

TEMPLATE = {
    "query_code": "Q01_daily_briefing",
    "name": "Daily Station Briefing",
    "scope": "Station Daily",
    "required_variables": [
        "station_name", "obs_date", "valid_hours", "min_aqhi", "max_aqhi",
        "peak_hours", "weather_note", "cross_2025_03_22_note"
    ],
    "text_template": (
        "AIR QUALITY BRIEFING: {station_name} ({obs_date})\n"
        "Valid Hours Reported: {valid_hours}/24\n"
        "AQHI Range: Min {min_aqhi} | Max {max_aqhi}\n"
        "Peak Risk Hours: {peak_hours}\n"
        "Weather Summary: {weather_note}\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## Air Quality Briefing: {station_name} ({obs_date})\n\n"
        "- **Valid Hours Reported**: {valid_hours}/24\n"
        "- **AQHI Range**: Min `{min_aqhi}` | Max `{max_aqhi}`\n"
        "- **Peak Risk Hours**: {peak_hours}\n"
        "- **Weather Summary**: {weather_note}\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"briefing-card\">\n"
        "  <h3>Air Quality Briefing: {station_name} ({obs_date})</h3>\n"
        "  <ul>\n"
        "    <li><strong>Valid Hours Reported:</strong> {valid_hours}/24</li>\n"
        "    <li><strong>AQHI Range:</strong> Min <code>{min_aqhi}</code> | Max <code>{max_aqhi}</code></li>\n"
        "    <li><strong>Peak Risk Hours:</strong> {peak_hours}</li>\n"
        "    <li><strong>Weather Summary:</strong> {weather_note}</li>\n"
        "  </ul>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}