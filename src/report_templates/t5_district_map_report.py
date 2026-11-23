"""Template 5: District Map Report (Query Code: Q05_district_map)"""

TEMPLATE = {
    "query_code": "Q05_district_map",
    "name": "District Map Report",
    "scope": "Territory-wide",
    "required_variables": [
        "obs_date", "total_districts", "highest_district", "max_aqhi", "cross_2025_03_22_note"
    ],
    "text_template": (
        "DISTRICT MAP OVERVIEW ({obs_date})\n"
        "Total Districts Analyzed: {total_districts}\n"
        "Highest Risk District: {highest_district} (Max AQHI: {max_aqhi})\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## District Map Overview ({obs_date})\n\n"
        "- **Total Districts Analyzed**: {total_districts}\n"
        "- **Highest Risk District**: `{highest_district}` (Max AQHI: `{max_aqhi}`)\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"map-card\">\n"
        "  <h3>District Map Overview ({obs_date})</h3>\n"
        "  <ul>\n"
        "    <li><strong>Total Districts Analyzed:</strong> {total_districts}</li>\n"
        "    <li><strong>Highest Risk District:</strong> <code>{highest_district}</code> (Max AQHI: <code>{max_aqhi}</code>)</li>\n"
        "  </ul>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}