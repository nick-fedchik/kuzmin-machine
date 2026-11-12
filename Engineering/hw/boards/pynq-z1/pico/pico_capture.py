#!/usr/bin/env python3
"""
Host Capture and VCD Exporter for Raspberry Pi Pico Logic Analyzer
Part of Kuzmin Machine PYNQ-Z1 HIL Bench.

Reads digital sample streams from RP2040, generates VCD (Value Change Dump),
and measures latency between External Stimulus (CH0/1) and Commit/Reject (CH2/3).
"""

import sys
import argparse
from typing import List, Tuple, Dict, Optional

CHANNEL_NAMES = {
    0: "EXT_STIMULUS",      # Physical sensor / button
    1: "FPGA_JA1_TRIGGER",  # Stimulus on PYNQ-Z1 PMOD JA1
    2: "FPGA_JA2_COMMIT",   # Commit pulse (valid transaction)
    3: "FPGA_JA3_REJECT",   # Reject pulse (invariant violation)
    4: "MOSFET_GATE",       # Power switch gate
    5: "PIPELINE_BUSY",     # Pipeline processing busy monitor
    6: "CH6_SPARE",
    7: "CH7_SPARE"
}

def generate_mock_capture_samples(
    sample_rate_hz: int = 125_000_000,
    total_samples: int = 200,
    trigger_sample: int = 20,
    pipeline_cycles: int = 8,
    fpga_freq_hz: int = 100_000_000,
    pulse_stretch_ns: int = 100
) -> List[int]:
    """
    Generates a deterministic sequence of 8-bit samples simulating
    a physical Kuzmin Machine BRAM pipeline execution cycle.
    
    1 sample @ 125 MHz = 8.0 ns.
    8 FPGA cycles @ 100 MHz = 80.0 ns = 10 samples @ 125 MHz.
    Pulse stretcher = 100.0 ns = 12.5 samples @ 125 MHz.
    """
    samples = [0] * total_samples
    ns_per_sample = 1e9 / sample_rate_hz
    
    # Calculate sample indices
    stimulus_start = trigger_sample
    stimulus_duration_samples = int(50 / ns_per_sample) # 50 ns pulse
    
    # 8 FPGA cycles = 80 ns latency from trigger detection (allow 2-FF CDC = +20 ns)
    commit_start = stimulus_start + int((80 + 20) / ns_per_sample)
    commit_duration_samples = int(pulse_stretch_ns / ns_per_sample)
    
    for i in range(total_samples):
        val = 0
        # CH0 & CH1: Stimulus pulse
        if stimulus_start <= i < stimulus_start + stimulus_duration_samples:
            val |= (1 << 0) | (1 << 1)
            
        # CH5: Pipeline busy during execution
        if stimulus_start + int(20 / ns_per_sample) <= i < commit_start:
            val |= (1 << 5)
            
        # CH2: Commit pulse
        if commit_start <= i < commit_start + commit_duration_samples:
            val |= (1 << 2)
            val |= (1 << 4) # MOSFET gate driven high with Commit
            
        samples[i] = val
        
    return samples

def export_samples_to_vcd(
    samples: List[int],
    sample_rate_hz: int = 125_000_000,
    output_path: Optional[str] = None
) -> str:
    """
    Exports a list of 8-bit samples to standard VCD (Value Change Dump) format.
    """
    time_step_ns = int(round(1e9 / sample_rate_hz))
    
    header = [
        "$date",
        "   2026-11-12",
        "$end",
        "$version",
        "   Kuzmin Machine RP2040 VCD Exporter 1.0.0",
        "$end",
        f"$timescale 1ns $end",
        "$scope module km_bench $end"
    ]
    
    var_symbols = {}
    for ch, name in CHANNEL_NAMES.items():
        sym = chr(ord('!') + ch)
        var_symbols[ch] = sym
        header.append(f"$var wire 1 {sym} {name} $end")
        
    header.append("$upscope $end")
    header.append("$enddefinitions $end")
    header.append("$dumpvars")
    
    for ch, sym in var_symbols.items():
        header.append(f"0{sym}")
    header.append("$end")
    
    body = []
    prev_val = 0
    
    for idx, sample in enumerate(samples):
        timestamp = idx * time_step_ns
        changes = []
        for ch in range(8):
            curr_bit = (sample >> ch) & 1
            prev_bit = (prev_val >> ch) & 1
            if idx == 0 or curr_bit != prev_bit:
                sym = var_symbols[ch]
                changes.append(f"{curr_bit}{sym}")
                
        if changes:
            body.append(f"#{timestamp}")
            body.extend(changes)
            
        prev_val = sample
        
    vcd_content = "\n".join(header + body) + "\n"
    
    if output_path:
        with open(output_path, "w") as f:
            f.write(vcd_content)
            
    return vcd_content

def analyze_capture_latency(
    samples: List[int],
    sample_rate_hz: int = 125_000_000,
    trigger_ch: int = 1,
    response_ch: int = 2
) -> Dict[str, float]:
    """
    Measures latency between rising edge of trigger_ch and response_ch.
    """
    ns_per_sample = 1e9 / sample_rate_hz
    
    trigger_idx = None
    response_idx = None
    
    for idx in range(1, len(samples)):
        prev = samples[idx - 1]
        curr = samples[idx]
        
        # Detect rising edge on trigger
        if trigger_idx is None:
            if ((prev >> trigger_ch) & 1 == 0) and ((curr >> trigger_ch) & 1 == 1):
                trigger_idx = idx
                
        # Detect rising edge on response
        if trigger_idx is not None and response_idx is None:
            if ((prev >> response_ch) & 1 == 0) and ((curr >> response_ch) & 1 == 1):
                response_idx = idx
                break
                
    if trigger_idx is None or response_idx is None:
        return {
            "measured_latency_ns": -1.0,
            "success": False,
            "trigger_timestamp_ns": -1.0,
            "response_timestamp_ns": -1.0
        }
        
    trig_time = trigger_idx * ns_per_sample
    resp_time = response_idx * ns_per_sample
    latency = resp_time - trig_time
    
    return {
        "measured_latency_ns": latency,
        "success": True,
        "trigger_timestamp_ns": trig_time,
        "response_timestamp_ns": resp_time,
        "sample_step_ns": ns_per_sample
    }

def main():
    parser = argparse.ArgumentParser(description="Kuzmin Machine RP2040 Logic Analyzer Host")
    parser.add_argument("--mock", action="store_true", help="Run simulated capture")
    parser.add_argument("--output", "-o", default="capture.vcd", help="Output VCD file path")
    parser.add_argument("--rate", type=int, default=125_000_000, help="Sample rate in Hz (125000000)")
    
    args = parser.parse_args()
    
    if args.mock:
        print(f"Generating mock capture @ {args.rate / 1e6:.1f} MS/s...")
        samples = generate_mock_capture_samples(sample_rate_hz=args.rate)
        export_samples_to_vcd(samples, sample_rate_hz=args.rate, output_path=args.output)
        analysis = analyze_capture_latency(samples, sample_rate_hz=args.rate)
        print(f"VCD exported to: {args.output}")
        print(f"Latency Analysis:")
        print(f"  Trigger edge:  {analysis['trigger_timestamp_ns']:.1f} ns")
        print(f"  Response edge: {analysis['response_timestamp_ns']:.1f} ns")
        print(f"  Delta latency: {analysis['measured_latency_ns']:.1f} ns")
        print(f"  Status: {'PASS' if analysis['success'] else 'FAIL'}")
    else:
        print("Serial capture from /dev/ttyACM0 requested. Use --mock for unit testing.")

if __name__ == "__main__":
    main()
