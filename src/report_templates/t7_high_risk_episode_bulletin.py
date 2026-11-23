"""Template 7: High Risk Episode Bulletin (Query Code: Q07_high_risk_bulletin)"""

TEMPLATE = {
    "query_code": "Q07_high_risk_bulletin",
    "name": "High Risk Episode Bulletin",
    "scope": "Alert Bulletin",
    "required_variables": [
        "station_name", "start_date", "end_date", "episode_hours_count", "high_risk_hours", "cross_2025_03_22_note"
    ],
    "text_template": (
        "HIGH RISK EPISODE BULLETIN\n"
        "Station: {station_name} | Period: {start_date} to {end_date}\n"
        "Total High Risk Hours (AQHI >= 7): {episode_hours_count}\n"
        "Recorded High Risk Hours: {high_risk_hours}\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## High Risk Episode Bulletin\n\n"
        "**Station**: {station_name} | **Period**: {start_date} to {end_date}\n\n"
        "- **Total High Risk Hours (AQHI ≥ 7)**: `{episode_hours_count}`\n"
        "- **Recorded High Risk Hours**: {high_risk_hours}\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"alert-card\">\n"
        "  <h3>High Risk Episode Bulletin</h3>\n"
        "  <p><strong>Station:</strong> {station_name} | <strong>Period:</strong> {start_date} to {end_date}</p>\n"
        "  <ul>\n"
        "    <li><strong>Total High Risk Hours (AQHI &ge; 7):</strong> <code>{episode_hours_count}</code></li>\n"
        "    <li><strong>Recorded High Risk Hours:</strong> {high_risk_hours}</li>\n"
        "  </ul>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}