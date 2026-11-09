#!/usr/bin/env python3
"""AV-08 analysis: medians/spread of f_max across seeds, DUT-only cost (S1_lanes - S1_stub),
least-squares linear fit and log-log exponent of resources vs N, pre-registered limit check."""
import csv
import json
import math
import os
import statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.environ.get("AV08_OUT_DIR", os.path.abspath(os.path.join(HERE, "..", "raw", "av08_scaling")))


def fit(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return a, b, r2


def loglog(xs, ys):
    pts = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if y > 0]
    if len(pts) < 2:
        return None
    return fit([p[0] for p in pts], [p[1] for p in pts])[1]


def main():
    rows = list(csv.DictReader(open(os.path.join(RAW, "av08_results.csv"))))
    by = defaultdict(list)
    for r in rows:
        by[(r["series"], int(r["N"]))].append(r)

    summary = {"per_point": [], "fits": {}, "limit": {}}
    for (s, n), rs in sorted(by.items()):
        f = [float(r["fmax_mhz"]) for r in rs if r["fmax_mhz"]]
        r0 = rs[0]
        summary["per_point"].append({
            "series": s, "N": n, "lut": int(r0["lut"]), "ff": int(r0["ff"]),
            "carry4": int(r0["carry4"]), "bram": int(r0["bram"]), "lutram": int(r0["lutram"]),
            "seeds": len(f), "fmax_median": round(st.median(f), 2) if f else None,
            "fmax_min": round(min(f), 2) if f else None, "fmax_max": round(max(f), 2) if f else None,
            "timing_fail": sum(1 for r in rs if r["status"] == "TIMING_FAIL"),
            "not_routed": sum(1 for r in rs if r["status"] == "NOT_ROUTED"),
        })

    pts = {(p["series"], p["N"]): p for p in summary["per_point"]}
    ns_lane = sorted(n for s, n in pts if s == "S1_lanes" and ("S1_stub", n) in pts)
    for p in [pts[("S1_lanes", n)] for n in ns_lane]:
        q = pts[("S1_stub", p["N"])]
        summary["per_point"].append({"series": "S1_net", "N": p["N"],
                                     "lut": p["lut"] - q["lut"], "ff": p["ff"] - q["ff"],
                                     "carry4": p["carry4"] - q["carry4"], "bram": 0, "lutram": 0})

    for s in sorted({p["series"] for p in summary["per_point"]}):
        pp = sorted((p for p in summary["per_point"] if p["series"] == s), key=lambda p: p["N"])
        xs = [p["N"] for p in pp]
        if len(xs) < 3:
            continue
        summary["fits"][s] = {}
        for k in ("lut", "ff", "carry4"):
            ys = [p[k] for p in pp]
            if max(ys) == min(ys):
                summary["fits"][s][k] = {"const": ys[0]}
                continue
            a, b, r2 = fit(xs, ys)
            summary["fits"][s][k] = {"intercept": round(a, 2), "slope_per_N": round(b, 3),
                                     "r2": round(r2, 5), "loglog_exponent": round(loglog(xs, ys), 3)}
        fm = [p.get("fmax_median") for p in pp]
        if all(v is not None for v in fm):
            below = [p["N"] for p in pp if p["fmax_median"] < 100]
            summary["limit"][s] = {"first_N_fmax_median_below_100": below[0] if below else None,
                                   "fmax_median_by_N": {p["N"]: p["fmax_median"] for p in pp}}

    with open(os.path.join(RAW, "av08_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"{'series':9} {'N':>4} {'LUT':>6} {'FF':>6} {'CARRY4':>6} {'BRAM':>4} {'fmax med [min..max]':>24}")
    for p in summary["per_point"]:
        fm = (f"{p['fmax_median']} [{p['fmax_min']}..{p['fmax_max']}]"
              if p.get("fmax_median") is not None else "-")
        print(f"{p['series']:9} {p['N']:>4} {p['lut']:>6} {p['ff']:>6} {p['carry4']:>6} {p['bram']:>4} {fm:>24}")
    print(json.dumps(summary["fits"], indent=1))
    print(json.dumps(summary["limit"], indent=1))


if __name__ == "__main__":
    main()
