"""Module entrypoint: `python -m backend`."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from backend.orchestrator import Orchestrator
from shared.models.config import FrameworkConfig


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backend", description="Run the QA pipeline.")
    p.add_argument("--config", type=str, default="", help="Path to JSON config file")
    p.add_argument("--target-url", type=str, default="", help="Target URL (overrides config)")
    p.add_argument(
        "--mode",
        type=str,
        default="full",
        choices=["full", "crawl", "plan"],
        help="Which pipeline stages to run",
    )
    p.add_argument("--log-level", type=str, default="INFO", help="Logging level")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    if args.config:
        cfg = FrameworkConfig.load(Path(args.config))
    else:
        if not args.target_url:
            raise SystemExit("Provide --target-url or --config")
        cfg = FrameworkConfig(target_url=args.target_url)

    if args.target_url:
        cfg.target_url = args.target_url
        cfg.crawl.target_url = args.target_url

    orch = Orchestrator(cfg)

    if args.mode == "crawl":
        model = orch.run_crawl_only()
        print(json.dumps(model.model_dump(), indent=2, default=str))
        return 0
    if args.mode == "plan":
        plan = orch.run_plan_only()
        print(json.dumps(plan.model_dump(), indent=2, default=str))
        return 0

    result = orch.run_full_pipeline()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

