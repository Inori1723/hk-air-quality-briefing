"""Template 6: Monthly Station Summary (Query Code: Q06_monthly_summary)"""

TEMPLATE = {
    "query_code": "Q06_monthly_summary",
    "name": "Monthly Station Summary",
    "scope": "Monthly Aggregate",
    "required_variables": [
        "station_name", "month", "valid_hours", "avg_aqhi", "max_aqhi", "cross_2025_03_22_note"
    ],
    "text_template": (
        "MONTHLY AIR QUALITY SUMMARY\n"
        "Station: {station_name} | Month: {month}\n"
        "Valid Hours: {valid_hours}\n"
        "Monthly Avg AQHI: {avg_aqhi} | Monthly Max AQHI: {max_aqhi}\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## Monthly Air Quality Summary\n\n"
        "**Station**: {station_name} | **Month**: {month}\n\n"
        "- **Valid Hours**: {valid_hours}\n"
        "- **Monthly Average AQHI**: `{avg_aqhi}`\n"
        "- **Monthly Maximum AQHI**: `{max_aqhi}`\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"monthly-card\">\n"
        "  <h3>Monthly Air Quality Summary</h3>\n"
        "  <p><strong>Station:</strong> {station_name} | <strong>Month:</strong> {month}</p>\n"
        "  <ul>\n"
        "    <li><strong>Valid Hours:</strong> {valid_hours}</li>\n"
        "    <li><strong>Monthly Average AQHI:</strong> <code>{avg_aqhi}</code></li>\n"
        "    <li><strong>Monthly Maximum AQHI:</strong> <code>{max_aqhi}</code></li>\n"
        "  </ul>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}