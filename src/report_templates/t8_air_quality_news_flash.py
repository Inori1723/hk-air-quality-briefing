"""Template 8: Air Quality News Flash (Query Code: Q08_news_flash)"""

TEMPLATE = {
    "query_code": "Q08_news_flash",
    "name": "Air Quality News Flash",
    "scope": "Public Flash News",
    "required_variables": [
        "obs_date", "max_aqhi", "peak_stations", "peak_hours", "cross_2025_03_22_note"
    ],
    "text_template": (
        "AIR QUALITY NEWS FLASH ({obs_date})\n"
        "Territory Max AQHI Reached: {max_aqhi}\n"
        "Affected Peak Stations: {peak_stations}\n"
        "Peak Occurrence Hours: {peak_hours}\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## Air Quality News Flash ({obs_date})\n\n"
        "- **Territory Max AQHI Reached**: `{max_aqhi}`\n"
        "- **Affected Peak Stations**: {peak_stations}\n"
        "- **Peak Occurrence Hours**: {peak_hours}\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"newsflash-card\">\n"
        "  <h3>Air Quality News Flash ({obs_date})</h3>\n"
        "  <ul>\n"
        "    <li><strong>Territory Max AQHI Reached:</strong> <code>{max_aqhi}</code></li>\n"
        "    <li><strong>Affected Peak Stations:</strong> {peak_stations}</li>\n"
        "    <li><strong>Peak Occurrence Hours:</strong> {peak_hours}</li>\n"
        "  </ul>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}