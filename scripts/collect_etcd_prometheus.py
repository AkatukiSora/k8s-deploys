#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def build_queries(job: str) -> dict[str, str]:
    return {
        "up": f'up{{job="{job}"}}',
        "has_leader": f'etcd_server_has_leader{{job="{job}"}}',
        "leader_changes_seen_total": f'etcd_server_leader_changes_seen_total{{job="{job}"}}',
        "proposals_pending": f'etcd_server_proposals_pending{{job="{job}"}}',
        "proposals_failed_total": f'etcd_server_proposals_failed_total{{job="{job}"}}',
        "wal_count_raw": f'etcd_disk_wal_fsync_duration_seconds_count{{job="{job}"}}',
        "wal_sum_raw": f'etcd_disk_wal_fsync_duration_seconds_sum{{job="{job}"}}',
        "wal_bucket_raw": f'etcd_disk_wal_fsync_duration_seconds_bucket{{job="{job}"}}',
        "backend_count_raw": f'etcd_disk_backend_commit_duration_seconds_count{{job="{job}"}}',
        "backend_sum_raw": f'etcd_disk_backend_commit_duration_seconds_sum{{job="{job}"}}',
        "backend_bucket_raw": f'etcd_disk_backend_commit_duration_seconds_bucket{{job="{job}"}}',
        "wal_rate_5m": (
            f'sum by (instance)(rate(etcd_disk_wal_fsync_duration_seconds_count{{job="{job}"}}[5m]))'
        ),
        "wal_mean_5m": (
            f'sum by (instance)(rate(etcd_disk_wal_fsync_duration_seconds_sum{{job="{job}"}}[5m])) '
            f'/ sum by (instance)(rate(etcd_disk_wal_fsync_duration_seconds_count{{job="{job}"}}[5m]))'
        ),
        "wal_p50_5m": (
            f"histogram_quantile(0.50, sum by (le, instance) "
            f'(rate(etcd_disk_wal_fsync_duration_seconds_bucket{{job="{job}"}}[5m])))'
        ),
        "wal_p90_5m": (
            f"histogram_quantile(0.90, sum by (le, instance) "
            f'(rate(etcd_disk_wal_fsync_duration_seconds_bucket{{job="{job}"}}[5m])))'
        ),
        "wal_p99_5m": (
            f"histogram_quantile(0.99, sum by (le, instance) "
            f'(rate(etcd_disk_wal_fsync_duration_seconds_bucket{{job="{job}"}}[5m])))'
        ),
        "wal_over_128ms_ratio_5m": (
            f'1 - (sum by (instance)(rate(etcd_disk_wal_fsync_duration_seconds_bucket{{job="{job}",le="0.128"}}[5m])) '
            f'/ sum by (instance)(rate(etcd_disk_wal_fsync_duration_seconds_count{{job="{job}"}}[5m])))'
        ),
        "wal_over_512ms_ratio_5m": (
            f'1 - (sum by (instance)(rate(etcd_disk_wal_fsync_duration_seconds_bucket{{job="{job}",le="0.512"}}[5m])) '
            f'/ sum by (instance)(rate(etcd_disk_wal_fsync_duration_seconds_count{{job="{job}"}}[5m])))'
        ),
        "backend_rate_5m": (
            f'sum by (instance)(rate(etcd_disk_backend_commit_duration_seconds_count{{job="{job}"}}[5m]))'
        ),
        "backend_mean_5m": (
            f'sum by (instance)(rate(etcd_disk_backend_commit_duration_seconds_sum{{job="{job}"}}[5m])) '
            f'/ sum by (instance)(rate(etcd_disk_backend_commit_duration_seconds_count{{job="{job}"}}[5m]))'
        ),
        "backend_p99_5m": (
            f"histogram_quantile(0.99, sum by (le, instance) "
            f'(rate(etcd_disk_backend_commit_duration_seconds_bucket{{job="{job}"}}[5m])))'
        ),
        "proposals_failed_increase_5m": (
            f'increase(etcd_server_proposals_failed_total{{job="{job}"}}[5m])'
        ),
        "leader_changes_increase_5m": (
            f'increase(etcd_server_leader_changes_seen_total{{job="{job}"}}[5m])'
        ),
    }


def fetch_via_http(base_url: str, path: str, params: dict[str, str]) -> bytes:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{base_url}{path}?{query}") as response:
        return response.read()


def fetch_via_kubectl(
    namespace: str, pod: str, path: str, params: dict[str, str]
) -> bytes:
    url = f"http://127.0.0.1:9090{path}?{urllib.parse.urlencode(params)}"
    result = subprocess.run(
        ["kubectl", "exec", "-n", namespace, pod, "--", "wget", "-qO-", url],
        check=True,
        capture_output=True,
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect reproducible etcd Prometheus query_range datasets."
    )
    parser.add_argument(
        "--start",
        required=True,
        help="RFC3339 or unix timestamp accepted by Prometheus",
    )
    parser.add_argument(
        "--end", required=True, help="RFC3339 or unix timestamp accepted by Prometheus"
    )
    parser.add_argument("--step", default="60s", help="Prometheus query_range step")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where raw JSON responses are written",
    )
    parser.add_argument(
        "--job", default="kube-etcd", help="Prometheus job label for etcd targets"
    )
    parser.add_argument(
        "--prometheus-url",
        help="Direct Prometheus base URL, for example http://127.0.0.1:9090",
    )
    parser.add_argument(
        "--prometheus-namespace",
        default="monitoring",
        help="Namespace of the Prometheus pod",
    )
    parser.add_argument(
        "--prometheus-pod",
        default="prometheus-kube-prometheus-stack-prometheus-0",
        help="Prometheus pod name when using kubectl exec",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    queries = build_queries(args.job)
    metadata = {
        "start": args.start,
        "end": args.end,
        "step": args.step,
        "job": args.job,
        "prometheus_url": args.prometheus_url,
        "prometheus_namespace": args.prometheus_namespace,
        "prometheus_pod": args.prometheus_pod,
        "queries": queries,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )

    for name, query in queries.items():
        params = {
            "query": query,
            "start": args.start,
            "end": args.end,
            "step": args.step,
        }
        if args.prometheus_url:
            payload = fetch_via_http(args.prometheus_url, "/api/v1/query_range", params)
        else:
            payload = fetch_via_kubectl(
                args.prometheus_namespace,
                args.prometheus_pod,
                "/api/v1/query_range",
                params,
            )

        parsed = json.loads(payload)
        (output_dir / f"{name}.json").write_text(
            json.dumps(parsed, indent=2, sort_keys=True) + "\n"
        )
        print(f"saved {name}.json", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
