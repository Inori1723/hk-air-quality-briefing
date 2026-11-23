"""Template 2: Daily Category Breakdown (Query Code: Q02_category_breakdown)"""

TEMPLATE = {
    "query_code": "Q02_category_breakdown",
    "name": "Daily Category Breakdown",
    "scope": "Station Daily",
    "required_variables": [
        "station_name", "obs_date", "valid_hours", "low_hours", "moderate_hours",
        "high_hours", "very_high_hours", "serious_hours", "cross_2025_03_22_note"
    ],
    "text_template": (
        "RISK CATEGORY BREAKDOWN: {station_name} ({obs_date})\n"
        "Valid Hours Evaluated: {valid_hours}\n"
        "Distribution:\n"
        "  - Low (1-3): {low_hours} hrs\n"
        "  - Moderate (4-6): {moderate_hours} hrs\n"
        "  - High (7): {high_hours} hrs\n"
        "  - Very High (8-10): {very_high_hours} hrs\n"
        "  - Serious (10+): {serious_hours} hrs\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## Risk Category Breakdown: {station_name} ({obs_date})\n\n"
        "**Valid Hours Evaluated**: {valid_hours}\n\n"
        "| Risk Level | Range | Duration (Hours) |\n"
        "|---|---|---|\n"
        "| Low | 1–3 | {low_hours} |\n"
        "| Moderate | 4–6 | {moderate_hours} |\n"
        "| High | 7 | {high_hours} |\n"
        "| Very High | 8–10 | {very_high_hours} |\n"
        "| Serious | 10+ | {serious_hours} |\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"category-card\">\n"
        "  <h3>Risk Category Breakdown: {station_name} ({obs_date})</h3>\n"
        "  <p><strong>Valid Hours Evaluated:</strong> {valid_hours}</p>\n"
        "  <table>\n"
        "    <thead><tr><th>Risk Level</th><th>Range</th><th>Duration (Hours)</th></tr></thead>\n"
        "    <tbody>\n"
        "      <tr><td>Low</td><td>1–3</td><td>{low_hours}</td></tr>\n"
        "      <tr><td>Moderate</td><td>4–6</td><td>{moderate_hours}</td></tr>\n"
        "      <tr><td>High</td><td>7</td><td>{high_hours}</td></tr>\n"
        "      <tr><td>Very High</td><td>8–10</td><td>{very_high_hours}</td></tr>\n"
        "      <tr><td>Serious</td><td>10+</td><td>{serious_hours}</td></tr>\n"
        "    </tbody>\n"
        "  </table>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}