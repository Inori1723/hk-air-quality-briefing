"""Download remaining raw datasets for the Hong Kong Air Quality Briefing System.

Datasets fetched:
1. HKO 2025 daily weather observations (CIS dailyExtract pages + Open Data CSV/API checks)
2. District boundaries (Cydalytics GitHub GeoJSON + official HAD CSDI District Boundary GeoJSON)
3. EPD Air Quality Monitoring Network coordinates (CSDI GeoJSON / ArcGIS REST GeoJSON)
4. C&SD Table 110-02001 (18-district land area and land population JSON API)
"""

from __future__ import annotations

import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEATHER_DIR = PROJECT_ROOT / "data" / "raw" / "weather_2025"
GEO_DIR = PROJECT_ROOT / "data" / "raw" / "geo_population"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AIDM7360-Groupby/1.0",
    "Accept": "*/*",
}


def download_url(url: str, dest: Path, timeout: int = 45, overwrite: bool = False) -> dict:
    """Fetch URL bytes to disk and return status metadata."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and dest.exists() and dest.stat().st_size > 0:
        return {
            "url": url,
            "dest": str(dest.relative_to(PROJECT_ROOT)),
            "status": "cached",
            "bytes": dest.stat().st_size,
            "ok": True,
        }
    req = urllib.request.Request(url, headers=HEADERS)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = resp.read()
            dest.write_bytes(data)
            return {
                "url": url,
                "dest": str(dest.relative_to(PROJECT_ROOT)),
                "status": resp.status,
                "bytes": len(data),
                "ok": True,
            }
    except Exception as exc:
        return {
            "url": url,
            "dest": str(dest.relative_to(PROJECT_ROOT)),
            "ok": False,
            "error": repr(exc),
        }


def main() -> None:
    results: list[dict] = []

    # 1. C&SD Table 110-02001 (Land area, land population and population density by District Council district)
    results.append(
        download_url(
            "https://www.censtatd.gov.hk/api/get.php?id=110-02001&lang=en&full_series=1",
            GEO_DIR / "csd_table_110_02001_en.json",
        )
    )

    # 2. EPD Air Quality Monitoring Network GeoJSON (CSDI static + ArcGIS REST fallback)
    epd_static = download_url(
        "https://static.csdi.gov.hk/csdi-webpage/download/common/42b54d18c4445208b66cca67f6295904fb614bba7a5cf93e822161e999469410",
        GEO_DIR / "epd_monitoring_stations_csdi.zip",
    )
    results.append(epd_static)
    results.append(
        download_url(
            "https://portal.csdi.gov.hk/server/rest/services/common/epd_rcd_1629267205214_40635/FeatureServer/0/query?where=1=1&outFields=*&f=geojson",
            GEO_DIR / "epd_monitoring_stations.geojson",
        )
    )

    # 3. District Boundary GeoJSON: official HAD CSDI + Cydalytics GitHub repo listing
    results.append(
        download_url(
            "https://static.csdi.gov.hk/csdi-webpage/download/common/3d8545d17c23ca553c32842d7801c99f0a73727237b681c039054cae5011054b",
            GEO_DIR / "had_district_boundary_csdi.zip",
        )
    )
    results.append(
        download_url(
            "https://portal.csdi.gov.hk/server/rest/services/common/had_rcd_1634523272907_75218/FeatureServer/0/query?where=1=1&outFields=*&f=geojson",
            GEO_DIR / "had_district_boundary.geojson",
        )
    )
    cyd_tree = download_url(
        "https://api.github.com/repos/cydalytics/HK_Voters_Distribution/git/trees/master?recursive=1",
        GEO_DIR / "cydalytics_tree.json",
    )
    results.append(cyd_tree)
    if not cyd_tree["ok"]:
        results.append(
            download_url(
                "https://api.github.com/repos/cydalytics/HK_Voters_Distribution/git/trees/main?recursive=1",
                GEO_DIR / "cydalytics_tree.json",
            )
        )

    for fname in ["hkg_adm1.geojson", "hkg_mod.geojson", "README.md"]:
        local_name = "cydalytics_README.md" if fname == "README.md" else f"cydalytics_{fname}"
        results.append(
            download_url(
                f"https://raw.githubusercontent.com/cydalytics/HK_Voters_Distribution/master/{fname}",
                GEO_DIR / local_name,
            )
        )

    # 4. HKO 2025 Daily Weather: CIS dailyExtract XML (12 months) + Open Data daily CSVs
    for m in range(1, 13):
        results.append(
            download_url(
                f"https://www.hko.gov.hk/cis/dailyExtract/dailyExtract_2025{m:02d}.xml",
                WEATHER_DIR / f"dailyExtract_2025{m:02d}.xml",
            )
        )
    hko_csv_types = {
        "CLMTEMP": "hko_daily_mean_temp.csv",
        "CLMMAXT": "hko_daily_max_temp.csv",
        "CLMMINT": "hko_daily_min_temp.csv",
    }
    for dtype, fname in hko_csv_types.items():
        results.append(
            download_url(
                f"https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType={dtype}&rformat=csv&station=HKO",
                WEATHER_DIR / fname,
            )
        )
    for stn, cis_name in [
        ("HKO", "daily_HKO_RF_ALL.csv"),
        ("HKO", "daily_HKO_RH_ALL.csv"),
        ("KP", "daily_KP_WSPD_ALL.csv"),
        ("KP", "daily_KP_SUN_ALL.csv"),
    ]:
        results.append(
            download_url(
                f"https://data.weather.gov.hk/weatherAPI/cis/csvfile/{stn}/ALL/{cis_name}",
                WEATHER_DIR / cis_name,
            )
        )

    manifest_path = PROJECT_ROOT / "data" / "raw" / "fetch_manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"Completed: {ok_count}/{len(results)} succeeded. Manifest: {manifest_path}")
    for r in results:
        tag = "OK" if r.get("ok") else "FAIL"
        detail = f"{r.get('bytes')} bytes" if r.get("ok") else r.get("error")
        print(f"[{tag}] {r['dest']} <- {detail}")


if __name__ == "__main__":
    main()
