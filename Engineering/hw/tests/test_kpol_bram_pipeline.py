import operator
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HW = ROOT / "hw"
sys.path.insert(0, str(ROOT / "sw" / "kpol-ref"))

from kpol_reference import (  # noqa: E402
    EventInput,
    Interpreter,
    KpolError,
    parse_module,
)


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
@pytest.mark.parametrize("interface", ["direct", "axi"])
def test_kpol_images_change_behavior_in_same_simulated_hardware(tmp_path, interface):
    images = []
    for name, expected in (("increase", 11), ("decrease", 9)):
        source_path = HW / "tests" / f"kpol_bram_pipeline_{name}.kpol"
        source = source_path.read_text(encoding="utf-8")
        module = parse_module(source)
        reference = Interpreter(module).run([
            EventInput("Pulse", {"param": 5}),
            EventInput("Pulse", {"param": 25}),
        ])
        assert reference.state["Counter"] == expected
        assert not reference.diagnostics
        image_path = tmp_path / f"{name}.bin"
        subprocess.run(
            [sys.executable, str(HW / "scripts/compile_kpol_bram_image.py"),
             str(source_path), str(image_path)],
            check=True, capture_output=True, text=True,
        )
        image = image_path.read_bytes()
        duplicate = subprocess.run(
            [sys.executable, str(HW / "scripts/compile_kpol_bram_image.py"),
             str(source_path), str(image_path)],
            capture_output=True, text=True,
        )
        assert duplicate.returncode != 0
        assert image_path.read_bytes() == image
        assert len(image) == 1024
        words = struct.unpack("<256I", image)
        path = tmp_path / f"{name}.hex"
        path.write_text("".join(f"{word:08x}\n" for word in words))
        images.append(path)

    assert images[0].read_bytes() != images[1].read_bytes()
    simulation = tmp_path / "pipeline.vvp"
    top = f"kpol_bram_pipeline_{interface}_tb" if interface == "axi" else "kpol_bram_pipeline_tb"
    bus = [str(HW / "rtl/bus/kpol_bram_pipeline_axi.sv")] if interface == "axi" else []
    subprocess.run(
        [
            "iverilog", "-g2012", "-s", top, "-o", str(simulation),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(HW / "rtl/core/km_concept_micro_engine.sv"),
            str(HW / "rtl/core/km_concept_bram.sv"),
            str(HW / "rtl/core/km_autonomous_sequencer.sv"),
            *bus, str(HW / "tests" / f"{top}.sv"),
        ],
        check=True, capture_output=True, text=True,
    )

    def run(first, second):
        return subprocess.run(
            ["vvp", "-n", str(simulation), f"+image_a={first}", f"+image_b={second}"],
            capture_output=True, text=True, timeout=30,
        )

    result = run(*images)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: both compiled images" in result.stdout

    swapped = run(*reversed(images))
    assert swapped.returncode != 0
    assert "image A: expected state 11" in swapped.stdout + swapped.stderr


INT32_MIN, INT32_MAX = -2147483648, 2147483647
COMPARISONS = {"<": operator.lt, ">": operator.gt, "==": operator.eq, "!=": operator.ne}
PROFILE_CASES = []
for operation in COMPARISONS:
    for limit in (INT32_MIN, -1, 0, 1, INT32_MAX):
        payloads = tuple(sorted(
            value for value in {INT32_MIN, limit-1, limit, limit+1, INT32_MAX}
            if INT32_MIN <= value <= INT32_MAX
        ))
        for delta in (1, -1):
            PROFILE_CASES.append(pytest.param(
                10, operation, limit, delta, payloads, False,
                id=f"{operation}-{limit}-{'inc' if delta == 1 else 'dec'}",
            ))
for delta in (1, -1):
    PROFILE_CASES.append(pytest.param(
        10, "true", 0, delta, (-1, 0, 1), False, id=f"true-{delta}",
    ))
PROFILE_CASES.extend([
    pytest.param(INT32_MAX-1, "true", 0, 1, (0, 0), False, id="overflow"),
    pytest.param(1, "true", 0, -1, (0, 0), False, id="underflow"),
    pytest.param(10, "<", 0, 1, (-1, 0, 1), True, id="renaming"),
])


@pytest.fixture(scope="module", params=["direct", "axi", "axi-hw"])
def profile_simulation(request, tmp_path_factory):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Потрібні iverilog і vvp")
    interface = request.param
    top = "kpol_bram_pipeline_tb" if interface == "direct" else "kpol_bram_pipeline_axi_tb"
    simulation = tmp_path_factory.mktemp(f"profile-{interface}") / "pipeline.vvp"
    sources = [
        HW / "rtl/core" / name for name in (
            "kpol_txn_gate_v2.sv", "km_concept_micro_engine.sv",
            "km_concept_bram.sv", "km_autonomous_sequencer.sv",
        )
    ]
    if interface != "direct":
        sources.append(HW / "rtl/bus/kpol_bram_pipeline_axi.sv")
    subprocess.run(
        ["iverilog", "-g2012", "-s", top, "-o", str(simulation),
         *map(str, sources), str(HW / "tests" / f"{top}.sv")],
        check=True, capture_output=True, text=True,
    )
    return interface, simulation


@pytest.mark.parametrize("initial,operation,limit,delta,payloads,rename", PROFILE_CASES)
def test_profile_per_event_in_simulated_pipeline(
    tmp_path, profile_simulation, initial, operation, limit, delta, payloads, rename,
):
    interface, simulation = profile_simulation
    guard = "true" if operation == "true" else f"P {operation} {limit}"
    source = f"""
    Problem Trace {{ Invariants {{ NonNeg: S >= 0; }} }}
    Solution Trace {{
        state S: Int32 = {initial};
        event E(P: Int32);
        rule Step on E when {guard} {{ set S := S {'+' if delta == 1 else '-'} 1; }}
    }}
    """
    reference = Interpreter(parse_module(source))
    state = initial
    trace = []
    for payload in payloads:
        selected = operation == "true" or COMPARISONS[operation](payload, limit)
        candidate = state + delta
        commit = selected and 0 <= candidate <= INT32_MAX
        state = candidate if commit else state
        if selected and candidate > INT32_MAX:
            with pytest.raises(KpolError, match="Int32"):
                reference.run([EventInput("E", {"P": payload})])
            print(f"REFERENCE: Int32 overflow at payload={payload}, retained={state}")
        else:
            result = reference.run([EventInput("E", {"P": payload})])
            assert result.state["S"] == state
            assert result.diagnostics == (
                ["InvariantViolation:NonNeg"] if selected and candidate < 0 else []
            )
        assert reference.state["S"] == state
        trace.extend((payload & 0xFFFFFFFF, state, int(commit)))

    def compile_source(text, name):
        path = tmp_path / f"{name}.kpol"
        image = tmp_path / f"{name}.bin"
        path.write_text(text, encoding="utf-8")
        subprocess.run(
            [sys.executable, str(HW / "scripts/compile_kpol_bram_image.py"),
             str(path), str(image)],
            check=True, capture_output=True, text=True,
        )
        return image.read_bytes()

    image = compile_source(source, "original")
    trace_file = tmp_path / "trace.hex"
    trace_file.write_text("".join(f"{word:08x}\n" for word in trace))

    def run_image(data, name):
        path = tmp_path / f"{name}.hex"
        path.write_text("".join(f"{word:08x}\n" for word in struct.unpack("<256I", data)))
        result = subprocess.run(
            ["vvp", "-n", str(simulation), f"+image_a={path}", f"+trace={trace_file}",
             f"+events={len(payloads)}", f"+initial={initial:08x}",
             *(["+hw_events"] if interface == "axi-hw" else [])],
            capture_output=True, text=True, timeout=30,
        )
        print(f"{interface} {name}:\n{result.stdout}{result.stderr}")
        return result

    result = run_image(image, "original")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: profile trace" in result.stdout
    if rename:
        renamed = compile_source(source.replace("rule Step", "rule NotifyStep"), "renamed")
        assert renamed == image
        result = run_image(renamed, "renamed")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS: profile trace" in result.stdout

    mutated = bytearray(image)
    mutated[9] ^= 0x08
    result = run_image(mutated, "inverted-guard-control")
    assert result.returncode != 0
    assert "trace event=0 word=0" in result.stdout + result.stderr


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
@pytest.mark.parametrize("queue_depth", [4, 8, 16, 32])
def test_sequencer_queue_retention_parameterized_depths(tmp_path, queue_depth):
    simulation = tmp_path / f"seq_q{queue_depth}.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012",
            f"-Pkm_autonomous_sequencer_tb.QUEUE_DEPTH={queue_depth}",
            "-s", "km_autonomous_sequencer_tb",
            "-o", str(simulation),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(HW / "rtl/core/km_concept_micro_engine.sv"),
            str(HW / "rtl/core/km_concept_bram.sv"),
            str(HW / "rtl/core/km_autonomous_sequencer.sv"),
            str(HW / "tb/km_autonomous_sequencer_tb.sv"),
        ],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["vvp", "-n", str(simulation)],
        capture_output=True, text=True, timeout=60,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for marker in ("[OK] 5A:", "[OK] 5B:", "[OK] 5C:", "[OK] 5D:", "[OK] 5E:", "[OK] 6:"):
        assert marker in out, f"Відсутній маркер {marker}:\n{out}"


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_axi_hw_trigger_managed_burst_and_sw_collision(tmp_path):
    source_path = HW / "tests" / "kpol_bram_pipeline_increase.kpol"
    image_bin = tmp_path / "increase.bin"
    subprocess.run(
        [sys.executable, str(HW / "scripts/compile_kpol_bram_image.py"),
         str(source_path), str(image_bin)],
        check=True, capture_output=True, text=True,
    )
    words = struct.unpack("<256I", image_bin.read_bytes())
    image_hex = tmp_path / "increase.hex"
    image_hex.write_text("".join(f"{word:08x}\n" for word in words))

    simulation = tmp_path / "axi_burst.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012", "-s", "kpol_bram_pipeline_axi_tb",
            "-o", str(simulation),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(HW / "rtl/core/km_concept_micro_engine.sv"),
            str(HW / "rtl/core/km_concept_bram.sv"),
            str(HW / "rtl/core/km_autonomous_sequencer.sv"),
            str(HW / "rtl/bus/kpol_bram_pipeline_axi.sv"),
            str(HW / "tests/kpol_bram_pipeline_axi_tb.sv"),
        ],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["vvp", "-n", str(simulation), "+hw_burst", f"+image_a={image_hex}"],
        capture_output=True, text=True, timeout=60,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "PASS: axi hw_burst lossless" in out, out


SEQUENCER_MUTANTS = [
    pytest.param(
        "ready_occupancy_only",
        "!cascade_pending_valid_q &&\n                                      (({1'b0, fifo_count_q} + ext_slots_needed) <= {1'b0, DEPTH_CNT})",
        "(fifo_count_q < DEPTH_CNT)",
        "[FAIL] 5C:",
        id="ready-occupancy-only",
    ),
    pytest.param(
        "drop_full_cascade",
        "cascade_pending_valid_q <= 1'b1;",
        "cascade_pending_valid_q <= 1'b0;",
        "[FAIL] 5D:",
        id="drop-full-cascade",
    ),
    pytest.param(
        "double_commit_on_full_cascade",
        "                        state_q <= ST_IDLE;\n                    end else begin",
        "                        state_q <= (cascade_req && fifo_full_o && !cascade_pending_valid_q) ? ST_EVAL_GATE : ST_IDLE;\n                    end else begin",
        "[FAIL] 5D:",
        id="double-eval-full-cascade",
    ),
    pytest.param(
        "duplicate_bram_write_on_pending",
        "            end else if (cascade_enq) begin",
        "            end else if (cascade_enq) begin\n                if (cascade_pending_valid_q) bram_b_we_o <= 1'b1;",
        "[FAIL] 5D:",
        id="duplicate-bram-write-pending",
    ),
    pytest.param(
        "stall_counts_as_drop",
        "                if (hw_trigger_valid_i && !hw_trigger_ready_o) begin\n                    stalled_ext_q   <= 1'b1;",
        "                if (hw_trigger_valid_i && !hw_trigger_ready_o) begin\n                    overflow_latched_q <= 1'b1;\n                    dropped_count_q <= dropped_count_q + 32'd1;\n                    stalled_ext_q   <= 1'b1;",
        "[FAIL] 5A:",
        id="stall-counts-as-drop",
    ),
    pytest.param(
        "silent_violation_drop",
        "dropped_count_q    <= dropped_count_q + 32'd1;",
        "dropped_count_q    <= dropped_count_q;",
        "[FAIL] 6:",
        id="silent-violation-drop",
    ),
]


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
@pytest.mark.parametrize("name,target,replacement,expected_marker", SEQUENCER_MUTANTS)
def test_sequencer_queue_retention_mutant_controls(
    tmp_path, name, target, replacement, expected_marker,
):
    rtl_text = (HW / "rtl/core/km_autonomous_sequencer.sv").read_text(encoding="utf-8")
    assert target in rtl_text, f"Не знайдено фрагмент для мутанта {name}"
    mutated_rtl = tmp_path / f"km_autonomous_sequencer_{name}.sv"
    mutated_rtl.write_text(rtl_text.replace(target, replacement), encoding="utf-8")

    simulation = tmp_path / f"mutant_{name}.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012",
            "-Pkm_autonomous_sequencer_tb.QUEUE_DEPTH=8",
            "-s", "km_autonomous_sequencer_tb",
            "-o", str(simulation),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(HW / "rtl/core/km_concept_micro_engine.sv"),
            str(HW / "rtl/core/km_concept_bram.sv"),
            str(mutated_rtl),
            str(HW / "tb/km_autonomous_sequencer_tb.sv"),
        ],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["vvp", "-n", str(simulation)],
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr
    assert result.returncode != 0, f"Мутант {name} не впав:\n{out}"
    assert expected_marker in out, f"Мутант {name} впав не на {expected_marker}:\n{out}"


