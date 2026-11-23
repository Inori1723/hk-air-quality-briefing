"""Template 4: Weather and Pollution Summary (Query Code: Q04_weather_pollution)"""

TEMPLATE = {
    "query_code": "Q04_weather_pollution",
    "name": "Weather and Pollution Summary",
    "scope": "Integrated",
    "required_variables": [
        "station_name", "start_date", "end_date", "avg_pm25", "avg_pm10",
        "avg_no2", "avg_o3", "avg_so2", "avg_co", "weather_note", "cross_2025_03_22_note"
    ],
    "text_template": (
        "WEATHER & POLLUTION INTEGRATED SUMMARY\n"
        "Station: {station_name} | Period: {start_date} to {end_date}\n"
        "Pollutant Means:\n"
        "  - PM2.5: {avg_pm25} ug/m3\n"
        "  - PM10: {avg_pm10} ug/m3\n"
        "  - NO2: {avg_no2} ug/m3\n"
        "  - O3: {avg_o3} ug/m3\n"
        "  - SO2: {avg_so2} ug/m3\n"
        "  - CO: {avg_co} (10 ug/m3)\n"
        "Meteorological Observation: {weather_note}\n"
        "{cross_2025_03_22_note}"
    ),
    "markdown_template": (
        "## Weather & Pollution Integrated Summary\n\n"
        "**Station**: {station_name} | **Period**: {start_date} to {end_date}\n\n"
        "### Key Pollutant Averages\n"
        "- **PM2.5**: `{avg_pm25}` μg/m³\n"
        "- **PM10**: `{avg_pm10}` μg/m³\n"
        "- **NO2**: `{avg_no2}` μg/m³\n"
        "- **O3**: `{avg_o3}` μg/m³\n"
        "- **SO2**: `{avg_so2}` μg/m³\n"
        "- **CO**: `{avg_co}` × 10 μg/m³\n\n"
        "**Meteorological Observation**: {weather_note}\n\n"
        "> {cross_2025_03_22_note}"
    ),
    "html_template": (
        "<div class=\"weather-pollution-card\">\n"
        "  <h3>Weather & Pollution Integrated Summary</h3>\n"
        "  <p><strong>Station:</strong> {station_name} | <strong>Period:</strong> {start_date} to {end_date}</p>\n"
        "  <ul>\n"
        "    <li><strong>PM2.5:</strong> <code>{avg_pm25}</code> &mu;g/m&sup3;</li>\n"
        "    <li><strong>PM10:</strong> <code>{avg_pm10}</code> &mu;g/m&sup3;</li>\n"
        "    <li><strong>NO2:</strong> <code>{avg_no2}</code> &mu;g/m&sup3;</li>\n"
        "    <li><strong>O3:</strong> <code>{avg_o3}</code> &mu;g/m&sup3;</li>\n"
        "    <li><strong>SO2:</strong> <code>{avg_so2}</code> &mu;g/m&sup3;</li>\n"
        "    <li><strong>CO:</strong> <code>{avg_co}</code> &times; 10 &mu;g/m&sup3;</li>\n"
        "  </ul>\n"
        "  <p><strong>Meteorological Observation:</strong> {weather_note}</p>\n"
        "  <p class=\"note\">{cross_2025_03_22_note}</p>\n"
        "</div>"
    ),
    "version": "1.0"
}