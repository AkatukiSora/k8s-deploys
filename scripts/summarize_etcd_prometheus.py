#!/usr/bin/env python3

import argparse
import json
import statistics
from pathlib import Path


def load_series(path: Path) -> dict[str, list[float]]:
    payload = json.loads(path.read_text())
    result = {}
    for series in payload.get("data", {}).get("result", []):
        instance = series.get("metric", {}).get("instance", "unknown")
        values = [
            float(value)
            for _, value in series.get("values", [])
            if value not in ("NaN", "Inf", "+Inf", "-Inf")
        ]
        if values:
            result[instance] = values
    return result


def load_counter_delta(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text())
    result = {}
    for series in payload.get("data", {}).get("result", []):
        instance = series.get("metric", {}).get("instance", "unknown")
        values = [
            float(value)
            for _, value in series.get("values", [])
            if value not in ("NaN", "Inf", "+Inf", "-Inf")
        ]
        if len(values) >= 2:
            result[instance] = values[-1] - values[0]
        elif values:
            result[instance] = 0.0
    return result


def safe_median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def safe_mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def format_seconds(value: float) -> str:
    return f"{value * 1000:.1f} ms"


def format_ratio(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize collected etcd Prometheus query_range data."
    )
    parser.add_argument(
        "dataset_dir", help="Directory created by collect_etcd_prometheus.py"
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    metadata = json.loads((dataset_dir / "metadata.json").read_text())

    wal_rate = load_series(dataset_dir / "wal_rate_5m.json")
    wal_mean = load_series(dataset_dir / "wal_mean_5m.json")
    wal_p50 = load_series(dataset_dir / "wal_p50_5m.json")
    wal_p90 = load_series(dataset_dir / "wal_p90_5m.json")
    wal_p99 = load_series(dataset_dir / "wal_p99_5m.json")
    wal_over_128 = load_series(dataset_dir / "wal_over_128ms_ratio_5m.json")
    wal_over_512 = load_series(dataset_dir / "wal_over_512ms_ratio_5m.json")
    backend_rate = load_series(dataset_dir / "backend_rate_5m.json")
    backend_mean = load_series(dataset_dir / "backend_mean_5m.json")
    backend_p99 = load_series(dataset_dir / "backend_p99_5m.json")
    proposals_pending = load_series(dataset_dir / "proposals_pending.json")
    has_leader = load_series(dataset_dir / "has_leader.json")
    proposals_failed_delta = load_counter_delta(
        dataset_dir / "proposals_failed_total.json"
    )
    leader_changes_delta = load_counter_delta(
        dataset_dir / "leader_changes_seen_total.json"
    )

    instances = sorted(
        set(wal_rate)
        | set(wal_mean)
        | set(backend_rate)
        | set(proposals_pending)
        | set(has_leader)
        | set(proposals_failed_delta)
        | set(leader_changes_delta)
    )

    print(f"dataset: {dataset_dir}")
    print(
        f"window: {metadata['start']} -> {metadata['end']} step={metadata['step']} job={metadata['job']}"
    )
    print("")

    for instance in instances:
        wal_rate_values = wal_rate.get(instance, [])
        backend_rate_values = backend_rate.get(instance, [])
        wal_count_per_4m = safe_mean(wal_rate_values) * 240.0
        backend_count_per_4m = safe_mean(backend_rate_values) * 240.0
        backend_interval_ms = (
            (1000.0 / safe_mean(backend_rate_values))
            if safe_mean(backend_rate_values) > 0
            else 0.0
        )

        print(f"instance: {instance}")
        print(f"  wal count / 4m avg: {wal_count_per_4m:.1f}")
        print(
            f"  wal mean median: {format_seconds(safe_median(wal_mean.get(instance, [])))}"
        )
        print(
            f"  wal p50 median: {format_seconds(safe_median(wal_p50.get(instance, [])))}"
        )
        print(
            f"  wal p90 median: {format_seconds(safe_median(wal_p90.get(instance, [])))}"
        )
        print(
            f"  wal p99 median: {format_seconds(safe_median(wal_p99.get(instance, [])))}"
        )
        print(f"  wal p99 max: {format_seconds(max(wal_p99.get(instance, [0.0])))}")
        print(
            f"  wal >128ms ratio avg: {format_ratio(safe_mean(wal_over_128.get(instance, [])))}"
        )
        print(
            f"  wal >512ms ratio avg: {format_ratio(safe_mean(wal_over_512.get(instance, [])))}"
        )
        print(f"  backend count / 4m avg: {backend_count_per_4m:.1f}")
        print(
            f"  backend mean median: {format_seconds(safe_median(backend_mean.get(instance, [])))}"
        )
        print(
            f"  backend p99 median: {format_seconds(safe_median(backend_p99.get(instance, [])))}"
        )
        print(
            f"  backend p99 max: {format_seconds(max(backend_p99.get(instance, [0.0])))}"
        )
        print(f"  backend mean interval: {backend_interval_ms:.1f} ms")
        print(
            f"  proposals pending max: {max(proposals_pending.get(instance, [0.0])):.0f}"
        )
        print(
            f"  proposals failed delta: {proposals_failed_delta.get(instance, 0.0):.0f}"
        )
        print(f"  leader changes delta: {leader_changes_delta.get(instance, 0.0):.0f}")
        print(f"  has leader min: {min(has_leader.get(instance, [1.0])):.0f}")
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
