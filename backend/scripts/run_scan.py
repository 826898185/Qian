from __future__ import annotations

import argparse

from dotenv import load_dotenv

from backend.app.data_service import create_data_service
from backend.app.factor_engine import FactorConfig
from backend.app.scanner import execute_scan_job
from backend.app.storage import K13Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily K13 scan job and persist snapshots.")
    parser.add_argument("--lookback", type=int, default=260, help="Lookback trading days")
    args = parser.parse_args()

    load_dotenv()
    service = create_data_service()
    cfg = FactorConfig()
    store = K13Storage()

    result = execute_scan_job(
        data_service=service,
        cfg=cfg,
        storage=store,
        lookback=args.lookback,
    )
    print(
        f"[k13-scan] run_id={result['run_id']} saved_signals={result['saved_signals']} "
        f"signal_count={result['signal_count']} source={result['meta'].get('source')}"
    )


if __name__ == "__main__":
    main()
