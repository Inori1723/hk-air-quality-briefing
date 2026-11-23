"""Unified ETL entry point for rebuilding the full 8-table air_quality.db."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.etl_aqhi import load_aqhi_2025
from src.etl_extra import run_all_extra_etl
from src.queries import seed_saved_queries
from src.schema import DEFAULT_DB_PATH
from src.templates import seed_report_templates


def run_full_etl(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    reset_db: bool = True,
) -> dict[str, Any]:
    """Rebuild base fact/dimension tables from raw files and seed queries/templates."""
    aqhi_summary = load_aqhi_2025(db_path=db_path, reset_db=reset_db)
    extra_summary = run_all_extra_etl(db_path=db_path)
    queries_seeded = seed_saved_queries(db_path=db_path)
    templates_seeded = seed_report_templates(db_path=db_path)
    return {
        "db_path": str(db_path),
        "aqhi": aqhi_summary,
        "extra": extra_summary,
        "saved_queries_seeded": queries_seeded,
        "report_templates_seeded": templates_seeded,
    }


if __name__ == "__main__":
    print(json.dumps(run_full_etl(), indent=2, ensure_ascii=False))
