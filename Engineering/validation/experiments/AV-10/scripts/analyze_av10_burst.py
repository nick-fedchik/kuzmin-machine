#!/usr/bin/env python3
"""
Statistical analysis script for AV-10 experiment (Hardware Transaction Gate Latency).
Processes Logic Analyzer raw captures (.lac or .csv) and computes:
- Per-event latency (rising edge STIM -> rising edge REACT)
- Minimum, Maximum, Mean, Standard Deviation (jitter)
- Percentiles: p50, p90, p95, p99
- Inter-pulse period and stability
"""

import json
import base64
import csv
import sys
from pathlib import Path
import statistics

def analyze_capture(lac_path: Path, events_csv_out: Path = None):
    with open(lac_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    settings = data["Settings"]
    freq = settings["Frequency"]
    dt_ns = 1e9 / freq
    pre_samples = settings["PreTriggerSamples"]

    ch0_bytes = base64.b64decode(settings["CaptureChannels"][0]["Samples"])
    ch1_bytes = base64.b64decode(settings["CaptureChannels"][1]["Samples"])

    ch0 = list(ch0_bytes)
    ch1 = list(ch1_bytes)

    # Detect rising edges (0 -> 1)
    rises_ch0 = [i for i in range(1, len(ch0)) if ch0[i-1] == 0 and ch0[i] == 1]
    rises_ch1 = [i for i in range(1, len(ch1)) if ch1[i-1] == 0 and ch1[i] == 1]

    n_events = min(len(rises_ch0), len(rises_ch1))
    events = []
    deltas_ns = []

    for idx in range(n_events):
        t0 = rises_ch0[idx]
        t1 = rises_ch1[idx]
        ds = t1 - t0
        dns = ds * dt_ns
        deltas_ns.append(dns)
        events.append({
            "event_id": idx + 1,
            "stim_sample": t0,
            "stim_time_ns": (t0 - pre_samples) * dt_ns,
            "react_sample": t1,
            "react_time_ns": (t1 - pre_samples) * dt_ns,
            "delta_samples": ds,
            "delta_ns": dns
        })

    if events_csv_out and events:
        events_csv_out.parent.mkdir(parents=True, exist_ok=True)
        with open(events_csv_out, "x", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(events[0].keys()))
            writer.writeheader()
            writer.writerows(events)

    sorted_d = sorted(deltas_ns)
    stats = {
        "n": n_events,
        "freq_hz": freq,
        "dt_ns": dt_ns,
        "min_ns": min(deltas_ns) if deltas_ns else 0.0,
        "max_ns": max(deltas_ns) if deltas_ns else 0.0,
        "mean_ns": statistics.mean(deltas_ns) if deltas_ns else 0.0,
        "stdev_ns": statistics.stdev(deltas_ns) if len(deltas_ns) > 1 else 0.0,
        "p50_ns": sorted_d[int(0.50 * n_events)] if n_events else 0.0,
        "p90_ns": sorted_d[int(0.90 * n_events)] if n_events else 0.0,
        "p95_ns": sorted_d[int(0.95 * n_events)] if n_events else 0.0,
        "p99_ns": sorted_d[min(int(0.99 * n_events), n_events - 1)] if n_events else 0.0,
    }
    return stats, events

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze retained CFG-R data without overwriting raw.")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for derived CSV")
    args = parser.parse_args()
    base_dir = Path(__file__).resolve().parent.parent
    lac_file = base_dir / "raw" / "av10_pynq_100burst_run03.lac"
    events_csv = args.output_dir / "av10_pynq_100burst_run03_events.csv"
    
    if not lac_file.exists():
        print(f"File not found: {lac_file}", file=sys.stderr)
        sys.exit(1)
        
    args.output_dir.mkdir(parents=True, exist_ok=False)
    stats, events = analyze_capture(lac_file, events_csv)
    print("AV-10 recorded CFG-R analysis; not a new HIL or CFG-P result:")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"  {k:12s}: {v:.4f}")
        else:
            print(f"  {k:12s}: {v}")
    print(f"Exported per-event table to {events_csv}")
