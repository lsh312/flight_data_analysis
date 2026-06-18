from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from analysis import build_prepared_datasets, summarize_key_findings, write_prepared_datasets
from db import DbConfig, make_engine, read_project_summary_tables, read_project_tables, test_connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read ATTPLANE DB2 tables, prepare Polars datasets, and save Parquet files."
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory where prepared Parquet files are written.",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Optional DB2 schema override such as ATTGRP7.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100_000,
        help=(
            "Rows to fetch per DB batch. Larger values can be faster but use more memory. "
            "Use 0 to disable batched reads."
        ),
    )
    parser.add_argument(
        "--raw-tickets",
        action="store_true",
        help=(
            "Read every TICKETS row into Parquet. This is usually too slow for the "
            "full ATTPLANE dataset; the default uses DB-side summaries instead."
        ),
    )
    return parser.parse_args()


def log_step(message: str) -> None:
    print(message, flush=True)


def main() -> None:
    started_at = perf_counter()
    args = parse_args()
    config = DbConfig.from_env()
    if args.schema:
        config = DbConfig(
            host=config.host,
            port=config.port,
            database=config.database,
            username=config.username,
            password=config.password,
            schema=args.schema.upper(),
        )

    print("Connection settings:")
    for key, value in config.safe_summary.items():
        print(f"  {key}: {value}")

    try:
        engine = make_engine(config)
    except ImportError as exc:
        raise RuntimeError(
            "The IBM DB2 Python driver is installed but could not be loaded. "
            "On macOS this can happen with some Python/ibm_db combinations. "
            "Use the course-provided Python environment, Python 3.10-3.12, "
            "or another machine where `python -c \"import ibm_db\"` succeeds."
        ) from exc

    if not test_connection(engine):
        raise RuntimeError("DB2 connection test failed")

    if args.raw_tickets:
        print("Reading source tables, including all ticket rows...")
        raw_tables = read_project_tables(
            engine,
            config.schema,
            batch_size=args.batch_size,
            progress=lambda message: log_step(f"  {message}"),
        )
    else:
        print("Reading source tables with DB-side ticket summaries...")
        raw_tables = read_project_summary_tables(
            engine,
            config.schema,
            batch_size=args.batch_size,
            progress=lambda message: log_step(f"  {message}"),
        )
    for table_name, df in raw_tables.items():
        print(f"  {table_name}: {df.height:,} rows, {df.width:,} columns")

    prepare_started_at = perf_counter()
    print("Preparing analytical datasets with Polars...")
    datasets = build_prepared_datasets(raw_tables)
    print(f"Prepared analytical datasets in {perf_counter() - prepare_started_at:,.1f}s.")

    output_dir = Path(args.output_dir)
    write_started_at = perf_counter()
    write_prepared_datasets(datasets, output_dir)
    print(f"Wrote Parquet datasets in {perf_counter() - write_started_at:,.1f}s.")

    print("Saved prepared datasets:")
    for name, df in datasets.items():
        print(f"  {output_dir / f'{name}.parquet'}: {df.height:,} rows")

    findings = summarize_key_findings(
        datasets["tickets_enriched"],
        datasets["flights_enriched"],
    )
    findings_path = output_dir / "generated_findings.md"
    findings_path.write_text(
        "# Generated Findings\n\n"
        + "\n".join(f"- {finding}" for finding in findings)
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {findings_path}")
    print(f"Done in {perf_counter() - started_at:,.1f}s.")


if __name__ == "__main__":
    main()
