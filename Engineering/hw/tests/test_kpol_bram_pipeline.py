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


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_cme_cascade_to_cid0_end_to_end_in_sequencer(tmp_path):
    """Issue #167: наскрізна перевірка каскаду CID 1 -> CID 0 через компілятор і автономний секвенсер."""
    from kpol_reference import compile_concept_microcode_bram_image

    source = """
    Problem CascadeZeroHW {
        Invariants {
            InvRoot: RootState >= 0;
            InvNode: TriggerNode >= 0;
        }
    }
    Solution CascadeZeroHW {
        state RootState: Int32 = 10;
        state TriggerNode: Int32 = 20;

        event Pulse(param: Int32);

        rule StepRoot on Pulse when param > 0 {
            set RootState := RootState + 1;
        }
        rule StepTrigger on Pulse when param == 7 {
            set TriggerNode := TriggerNode + 1;
        }
    }
    """
    image = compile_concept_microcode_bram_image(
        parse_module(source), cascade_map={"TriggerNode": "RootState"}
    )
    words = struct.unpack("<256I", image)
    image_hex = tmp_path / "cascade_cid0.hex"
    image_hex.write_text("".join(f"{word:08x}\n" for word in words), encoding="utf-8")

    tb_sv = tmp_path / "cascade_cid0_tb.sv"
    tb_sv.write_text(
        """`timescale 1ns / 1ps
module cascade_cid0_tb;
    logic clk = 0;
    logic rst_n = 0;
    always #5 clk = ~clk;

    logic        bram_a_we = 0;
    logic [7:0]  bram_a_addr = 0;
    logic [31:0] bram_a_wdata = 0;
    wire  [31:0] bram_a_rdata;

    wire         bram_b_we;
    wire  [3:0]  bram_b_wstrb;
    wire  [7:0]  bram_b_addr;
    wire  [31:0] bram_b_wdata;
    wire  [31:0] bram_b_rdata;

    logic        trig_valid = 0;
    logic [5:0]  trig_cid = 0;
    logic [31:0] trig_param = 0;
    wire         trig_ready;
    wire         busy, fifo_full, fifo_overflow;
    wire  [31:0] total_events, total_committed, total_rejected, last_state, dropped_events;
    wire         commit_pulse, reject_pulse;

    reg [31:0] img [0:255];
    integer i;

    km_concept_bram bram_inst (
        .clk(clk), .rst_n(rst_n),
        .a_we_i(bram_a_we), .a_wstrb_i(4'hF), .a_addr_i(bram_a_addr), .a_wdata_i(bram_a_wdata), .a_rdata_o(bram_a_rdata),
        .b_we_i(bram_b_we), .b_wstrb_i(bram_b_wstrb), .b_addr_i(bram_b_addr), .b_wdata_i(bram_b_wdata), .b_rdata_o(bram_b_rdata)
    );

    km_autonomous_sequencer dut (
        .clk(clk), .rst_n(rst_n),
        .hw_trigger_valid_i(trig_valid), .hw_trigger_cid_i(trig_cid), .hw_trigger_param_i(trig_param),
        .hw_trigger_ready_o(trig_ready),
        .bram_b_we_o(bram_b_we), .bram_b_wstrb_o(bram_b_wstrb), .bram_b_addr_o(bram_b_addr), .bram_b_wdata_o(bram_b_wdata), .bram_b_rdata_i(bram_b_rdata),
        .clear_overflow_i(1'b0),
        .busy_o(busy), .fifo_full_o(fifo_full), .fifo_overflow_o(fifo_overflow),
        .events_dropped_count_o(dropped_events),
        .events_processed_count_o(total_events),
        .committed_count_o(total_committed),
        .rejected_count_o(total_rejected),
        .last_committed_state_o(last_state),
        .commit_pulse_o(commit_pulse),
        .reject_pulse_o(reject_pulse)
    );

    initial begin
        $readmemh("IMAGE_HEX_PATH", img);
        #20 rst_n = 1;
        for (i = 0; i < 256; i = i + 1) begin
            @(posedge clk);
            bram_a_we    <= 1'b1;
            bram_a_addr  <= i[7:0];
            bram_a_wdata <= img[i];
        end
        @(posedge clk);
        bram_a_we <= 1'b0;
        @(posedge clk);

        // Подаємо подію на CID=1 (TriggerNode) з param=7:
        // CID=1 переходить 20 -> 21 і каскадно викликає CID=0 (RootState: 10 -> 11)
        trig_cid   <= 6'd1;
        trig_param <= 32'd7;
        trig_valid <= 1'b1;
        @(posedge clk);
        while (!trig_ready) @(posedge clk);
        trig_valid <= 1'b0;

        repeat (4) @(posedge clk);
        while (busy) @(posedge clk);
        repeat (2) @(posedge clk);

        // Зчитуємо фінальний стан CID=0 (Word 0 за адресою 0) через Port A
        bram_a_addr <= 8'd0;
        @(posedge clk);
        @(posedge clk);
        #1;
        if (total_committed !== 32'd2 || bram_a_rdata !== 32'd11 || last_state !== 32'd11) begin
            $fatal(1, "[FAIL] Каскад CID 1 -> CID 0 не виконався: committed=%0d (exp 2), cid0_state=%0d (exp 11), last_state=%0d",
                   total_committed, bram_a_rdata, last_state);
        end
        $display("PASS: cascade CID 1 -> CID 0 committed=2 cid0_state=11");
        $finish;
    end
endmodule
""".replace("IMAGE_HEX_PATH", str(image_hex)),
        encoding="utf-8",
    )

    sim = tmp_path / "cascade_cid0.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012", "-s", "cascade_cid0_tb", "-o", str(sim),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(HW / "rtl/core/km_concept_micro_engine.sv"),
            str(HW / "rtl/core/km_concept_bram.sv"),
            str(HW / "rtl/core/km_autonomous_sequencer.sv"),
            str(tb_sv),
        ],
        check=True, capture_output=True, text=True,
    )
    run = subprocess.run(["vvp", "-n", str(sim)], capture_output=True, text=True, timeout=30)
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "PASS: cascade CID 1 -> CID 0 committed=2 cid0_state=11" in out, out


CME_MUTANTS = [
    pytest.param(
        "block_cid0_cascade",
        "(guard_flags_w[4] || (subscriber_cid_w != 32'd0))",
        "(subscriber_cid_w != 32'd0)",
        "[FAIL] Сценарій 6A",
        id="block-cid0-cascade",
    ),
    pytest.param(
        "allow_out_of_range_cid64_cascade",
        "wire subscriber_target_valid_w = (subscriber_cid_w < 32'd64);",
        "wire subscriber_target_valid_w = 1'b1;",
        "[FAIL] Сценарій 6C",
        id="allow-cid64-cascade",
    ),
    pytest.param(
        "cross_concept_gate_changed",
        "    logic                  gate_rejected;\n    logic                  gate_hazard_obs;",
        "    logic                  gate_rejected;\n    logic                  gate_changed;\n    logic                  gate_hazard_obs;",
        "[FAIL] Сценарій 7A",
        id="cross-concept-gate-changed",
    ),
    pytest.param(
        "ignore_arith_overflow",
        "assign invariant_true_w   = !arith_overflow_w && ($signed(candidate_state_w) >= 0);",
        "assign invariant_true_w   = ($signed(candidate_state_w) >= 0);",
        "[FAIL] Сценарій 8A",
        id="ignore-arith-overflow",
    ),
    pytest.param(
        "unsigned_range_bounds",
        "8'h05: pred_raw_res = ($signed(event_param_i) >= range_lo_sext_w) &&\n                                  ($signed(event_param_i) <= range_hi_sext_w); // RANGE (signed int16 bounds)",
        "8'h05: pred_raw_res = (event_param_i >= range_lo_w) &&\n                                  (event_param_i <= range_hi_w);",
        "[FAIL] Сценарій 9A",
        id="unsigned-range-bounds",
    ),
    pytest.param(
        "silent_unknown_action_commit",
        ".candidate_known_i(action_valid_w),",
        ".candidate_known_i(1'b1),",
        "[FAIL] Сценарій 10",
        id="silent-unknown-action-commit",
    ),
]


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
@pytest.mark.parametrize("name,target,replacement,expected_marker", CME_MUTANTS)
def test_cme_core_semantics_mutant_controls(
    tmp_path, name, target, replacement, expected_marker,
):
    rtl_text = (HW / "rtl/core/km_concept_micro_engine.sv").read_text(encoding="utf-8")
    assert target in rtl_text, f"Не знайдено фрагмент для мутанта {name}"
    patched = rtl_text.replace(target, replacement)
    if name == "cross_concept_gate_changed":
        patched = patched.replace(".changed_o(),", ".changed_o(gate_changed),")
        patched = patched.replace(
            "assign state_changed_o      = gate_committed && (gate_state_out != sampled_state_q);",
            "assign state_changed_o      = gate_changed;",
        )
    mutated_rtl = tmp_path / f"km_concept_micro_engine_{name}.sv"
    mutated_rtl.write_text(patched, encoding="utf-8")

    simulation = tmp_path / f"cme_mutant_{name}.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012",
            "-s", "km_concept_micro_engine_tb",
            "-o", str(simulation),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(mutated_rtl),
            str(HW / "tb/km_concept_micro_engine_tb.sv"),
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


def _compile_increase_hex(tmp_path: Path) -> Path:
    source_path = HW / "tests" / "kpol_bram_pipeline_increase.kpol"
    image_bin = tmp_path / "inc.bin"
    subprocess.run(
        [sys.executable, str(HW / "scripts/compile_kpol_bram_image.py"),
         str(source_path), str(image_bin)],
        check=True, capture_output=True, text=True,
    )
    words = struct.unpack("<256I", image_bin.read_bytes())
    image_hex = tmp_path / "inc.hex"
    image_hex.write_text("".join(f"{word:08x}\n" for word in words), encoding="utf-8")
    return image_hex


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_axi_b4_load_vs_run_write_race(tmp_path):
    """Issue #168: усунення 1-тактової гонитви B4 Load vs Run на межі запису BRAM."""
    image_a_hex = _compile_increase_hex(tmp_path)
    simulation = tmp_path / "axi_b4_race.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012",
            "-s", "kpol_bram_pipeline_axi_tb",
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
        ["vvp", "-n", str(simulation), "+b4_race_audit", f"+image_a={image_a_hex}"],
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "PASS: axi b4_race_audit" in out, out


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_axi_overflow_w1c_clear(tmp_path):
    """Issue #168: W1C очищення sticky fifo_overflow та events_dropped через регістр 0x02C."""
    image_a_hex = _compile_increase_hex(tmp_path)
    simulation = tmp_path / "axi_w1c.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012",
            "-s", "kpol_bram_pipeline_axi_tb",
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
        ["vvp", "-n", str(simulation), "+w1c_clear_audit", f"+image_a={image_a_hex}"],
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "PASS: axi w1c_clear_audit" in out, out


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_pynq_z1_top_cdc_debounce_and_param1(tmp_path):
    """Issue #168: PYNQ-Z1 top має 2-FF CDC для sw[1:0], антибрязкіт btn[0] та param=1."""
    simulation = tmp_path / "pynq_top_sim.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012",
            "-s", "kpol_bram_pipeline_pynq_z1_top_tb",
            "-o", str(simulation),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(HW / "rtl/core/km_concept_micro_engine.sv"),
            str(HW / "rtl/core/km_concept_bram.sv"),
            str(HW / "rtl/core/km_autonomous_sequencer.sv"),
            str(HW / "rtl/bus/kpol_bram_pipeline_axi.sv"),
            str(HW / "boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v"),
            str(HW / "tests/kpol_bram_pipeline_pynq_z1_top_tb.sv"),
        ],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["vvp", "-n", str(simulation)],
        capture_output=True, text=True, timeout=60,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "PASS: pynq_z1_top cdc, debounce and param=1 verified" in out, out


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_axi_hw_commit_cid_diagnostic_output(tmp_path):
    """Issue #247: ізольована перевірка hw_commit_cid_o на каскаді CID 3 -> 19 -> 42 та reject CID 57."""
    simulation = tmp_path / "axi_commit_cid.vvp"
    subprocess.run(
        [
            "iverilog", "-g2012",
            "-s", "kpol_bram_pipeline_axi_tb",
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
        ["vvp", "-n", str(simulation), "+commit_cid_audit"],
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "PASS: axi commit_cid_audit (cids=3,19,42,42,19 reject_cid=57)" in out, out


AXI_PYNQ_MUTANTS = [
    pytest.param(
        "axi_commit_cid_shifted_slice",
        "rtl/bus/kpol_bram_pipeline_axi.sv",
        "assign hw_commit_cid_o = b_addr[7:2];",
        "assign hw_commit_cid_o = b_addr[5:0];",
        "axi_commit_cid",
        "[FAIL] commit_cid_audit:",
        id="axi-commit-cid-shifted-slice",
    ),
    pytest.param(
        "axi_commit_cid_stuck_zero",
        "rtl/bus/kpol_bram_pipeline_axi.sv",
        "assign hw_commit_cid_o = b_addr[7:2];",
        "assign hw_commit_cid_o = 6'd0;",
        "axi_commit_cid",
        "[FAIL] commit_cid_audit:",
        id="axi-commit-cid-stuck-zero",
    ),
    pytest.param(
        "axi_allow_b4_write_race",
        "rtl/bus/kpol_bram_pipeline_axi.sv",
        "wire ext_trigger_blocked = sw_trigger || bram_we || cfg_write_fire;",
        "wire ext_trigger_blocked = sw_trigger;",
        "axi_b4",
        "[FAIL] B4 race: hw_trigger_ready_o remained 1",
        id="axi-allow-b4-write-race",
    ),
    pytest.param(
        "axi_unstoppable_leaks_into_seq",
        "rtl/bus/kpol_bram_pipeline_axi.sv",
        "wire seq_trigger_valid = sw_trigger || (!ext_trigger_blocked && ext_hw_trigger_valid_i);",
        "wire seq_trigger_valid = sw_trigger || ext_hw_trigger_valid_i;",
        "axi_b4",
        "[FAIL] B4 race: Port A bram_we=1 overlapped with PHASE_RUN busy=1",
        id="axi-unstoppable-leaks-into-seq",
    ),
    pytest.param(
        "axi_w1c_ignore_bit16",
        "rtl/bus/kpol_bram_pipeline_axi.sv",
        "(write_addr == 13'h02c) && write_data[16];",
        "(write_addr == 13'h02c) && 1'b0;",
        "axi_w1c",
        "[FAIL] W1C write 0x0001_0000 did not clear outputs",
        id="axi-w1c-ignore-bit16",
    ),
    pytest.param(
        "pynq_top_param0",
        "boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v",
        ".ext_hw_trigger_param_i(32'd1)",
        ".ext_hw_trigger_param_i(32'd0)",
        "pynq_top",
        "[FAIL] PYNQ top param=1 check failed",
        id="pynq-top-param0",
    ),
    pytest.param(
        "pynq_top_bypass_sw_cdc",
        "boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v",
        "wire [5:0] target_cid  = {4'd0, sw_cdc_1_q};",
        "wire [5:0] target_cid  = {4'd0, sw[1:0]};",
        "pynq_top",
        "[FAIL] PYNQ top CDC violation",
        id="pynq-top-bypass-sw-cdc",
    ),
    pytest.param(
        "pynq_top_bypass_btn_debounce",
        "boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v",
        "wire btn0_trig_pulse = btn0_stable_q & ~btn0_stable_d_q;",
        "wire btn0_trig_pulse = btn0_cdc_q[1] & ~btn0_stable_d_q;",
        "pynq_top",
        "[FAIL] PYNQ top button bounce leaked spurious triggers",
        id="pynq-top-bypass-btn-debounce",
    ),
]


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
@pytest.mark.parametrize(
    "name,rel_file,target,replacement,runner,expected_marker", AXI_PYNQ_MUTANTS
)
def test_axi_b4_and_pynq_top_mutant_controls(
    tmp_path, name, rel_file, target, replacement, runner, expected_marker
):
    orig_path = HW / rel_file
    rtl_text = orig_path.read_text(encoding="utf-8")
    assert target in rtl_text, f"Не знайдено цільовий рядок для мутанта {name}"
    mutated_path = tmp_path / f"mut_{name}_{orig_path.name}"
    mutated_path.write_text(rtl_text.replace(target, replacement), encoding="utf-8")

    axi_src = str(mutated_path) if rel_file.endswith(".sv") else str(HW / "rtl/bus/kpol_bram_pipeline_axi.sv")
    top_src = str(mutated_path) if rel_file.endswith(".v") else str(HW / "boards/pynq-z1/kpol_bram_pipeline_pynq_z1_top.v")

    sim = tmp_path / f"mut_{name}.vvp"
    if runner == "axi_commit_cid":
        subprocess.run(
            [
                "iverilog", "-g2012",
                "-s", "kpol_bram_pipeline_axi_tb",
                "-o", str(sim),
                str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
                str(HW / "rtl/core/km_concept_micro_engine.sv"),
                str(HW / "rtl/core/km_concept_bram.sv"),
                str(HW / "rtl/core/km_autonomous_sequencer.sv"),
                axi_src,
                str(HW / "tests/kpol_bram_pipeline_axi_tb.sv"),
            ],
            check=True, capture_output=True, text=True,
        )
        res = subprocess.run(
            ["vvp", "-n", str(sim), "+commit_cid_audit"],
            capture_output=True, text=True, timeout=30,
        )
    elif runner in ("axi_b4", "axi_w1c"):
        image_a_hex = _compile_increase_hex(tmp_path)
        subprocess.run(
            [
                "iverilog", "-g2012",
                "-s", "kpol_bram_pipeline_axi_tb",
                "-o", str(sim),
                str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
                str(HW / "rtl/core/km_concept_micro_engine.sv"),
                str(HW / "rtl/core/km_concept_bram.sv"),
                str(HW / "rtl/core/km_autonomous_sequencer.sv"),
                axi_src,
                str(HW / "tests/kpol_bram_pipeline_axi_tb.sv"),
            ],
            check=True, capture_output=True, text=True,
        )
        plusarg = "+b4_race_audit" if runner == "axi_b4" else "+w1c_clear_audit"
        res = subprocess.run(
            ["vvp", "-n", str(sim), plusarg, f"+image_a={image_a_hex}"],
            capture_output=True, text=True, timeout=30,
        )
    else:
        subprocess.run(
            [
                "iverilog", "-g2012",
                "-s", "kpol_bram_pipeline_pynq_z1_top_tb",
                "-o", str(sim),
                str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
                str(HW / "rtl/core/km_concept_micro_engine.sv"),
                str(HW / "rtl/core/km_concept_bram.sv"),
                str(HW / "rtl/core/km_autonomous_sequencer.sv"),
                axi_src,
                top_src,
                str(HW / "tests/kpol_bram_pipeline_pynq_z1_top_tb.sv"),
            ],
            check=True, capture_output=True, text=True,
        )
        res = subprocess.run(["vvp", "-n", str(sim)], capture_output=True, text=True, timeout=60)

    out = res.stdout + res.stderr
    assert res.returncode != 0, f"Мутант {name} не впав:\n{out}"
    assert expected_marker in out, f"Мутант {name} впав не на {expected_marker}:\n{out}"




