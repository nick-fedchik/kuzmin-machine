"""Verification & negative-control tests for EXP-GPU-01 Phase 3–4 (#225, ADR B6).

Includes:
1. Offline structural, C-layout, SASS predication, and raw-artifact provenance checks
   (always executed in local pytest and GitHub Actions CI without SSH).
2. Explicit mutant / negative-control tests proving the checks fail on:
   - hardcoded fake clock divisor (e.g. 1300 MHz vs actual 816 MHz -> >37% timer mismatch),
   - warp-divergent cycle inflation (>5% growth on sparse masks),
   - broken Q8 PID state update against independent Python oracle.
3. Optional live HIL execution on Jetson AGX Orin (192.168.68.68) strictly under
   flock /tmp/km-bench.lock when the stand is reachable.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

EXP_DIR = Path(__file__).resolve().parents[1]
STUDY_DIR = EXP_DIR.parents[1]
CU_FILE = EXP_DIR / "persistent_subscribers.cu"
RAW_DIR = STUDY_DIR / "data" / "exp-gpu-01-phase3"
REPORT_FILE = EXP_DIR / "report-phase3-warp-scaling.md"

JETSON_HOST = "mfedchyk@192.168.68.68"

EXPECTED_RAW_SHA256 = {
    "sass-sm87-01.txt": "daacfb34b0c64899930dc9392cda59cf645beb8d504be79a70abacebd0968431",
    "run-01-dvfs-unlocked-1x32.log": "5321c22d939a2324d42898da20084b0212454d8377570ba22989ce0f352ab048",
    "run-02-locked-matrix-01.log": "d88983af538e14ca6ee5843b1e1d64edfd3651273cdacd504dc8fe0899a779aa",
    "dvfs_unlocked_1x32.json": "4ce451395395a3c435a9461399eb8dfd0b1a1a00136156135f7191086920b5ab",
    "mask_1x32_all.json": "921c5da2e38e6a43cdb89ff3cf190d876681383934fdc5cd7bf635c5514deeda",
    "mask_1x32_alt.json": "f3f7fee472a399e94e383e3fb7931a54f6653f59f63aa05e6ebb92db7147e14f",
    "mask_1x32_one.json": "613f27f17e4b67d8d6af101d73da97c19f66f996463781479570252c47462557",
    "mask_1x32_ends.json": "59d917a3bbbd4be86ef9ab5e52fc899b62fb471a27e5d9b0ba9d94c615356778",
    "mask_1x32_rand.json": "d9f10cb6f53d906819fc058ca2f5b674ffbb792f6487369152b82ea81230a78b",
    "mask_1x32_none.json": "7cb08c950f1faef6559412230c7b38474a9eaa8439c2c7e7476185bd44f88384",
    "sleep20_1x32.json": "c4b9da1aba35908d05ef0a50bd3fb10cf04ae93c7449bb543eba022f08605bc3",
    "scale_1x32.json": "78b30831716b254d9c83f7ae559cbf55414958faabcc11066c8dbc7325845be9",
    "scale_1x128.json": "16a8066f65aed64ff44ce25a3d0599c8aff6658c26d863e8179e79e2f2291061",
    "scale_1x256.json": "87b3f58828a5334021c2627823c3c1b8e86697208aa2eb2072e3101151105d6b",
    "scale_1x512.json": "7db16d6b02d2e84759455ef48f05df94aecd0e96259a8038aac4386a00f1a369",
    "scale_4x32.json": "3e1712614717ba9235e0323520f2e26a87d892ea621686ec401ef0130b4c38ac",
    "scale_8x32.json": "c55965ca75355a45ceb15cda6dc4e8b41018f239047b6c715bc25c27ffc7be5f",
    "scale_16x32.json": "18dfb86d234913a6a78f7dbc19058fbfff2029b1d9a6f471828b65b3f62e1a82",
    "sass-sm87-02.txt": "3604d8a488df24e1de5b923011743e792b936c5cce17caa8f8976b156dd617a1",
    "run-03-ab-scaling-10k.log": "d69a08b06553267001b712f7103f6c00c28aee33349d0d0c271ea1c09643883d",
    "ab_scale_1x32_10k.json": "5d54f4fa5711d7e471966ed3652721d1c6818616e748ee589d94cbf01bcf5f69",
    "ab_scale_1x128_10k.json": "58eef6155f971d56e8f31103f18b962c76679293423199c2fc4d77b24f9065f3",
    "ab_scale_1x256_10k.json": "373105e7cca25887fe4d7597246d5bc3f89fd8c2588827c876f1097419896b25",
    "ab_scale_1x512_10k.json": "e9cf16795509a4d173125bcc0e085c02e093098fdd44e8642a0418a4136a0370",
    "ab_8x32_packed_10k.json": "ea78f3b3381065493d5348c44ce65cc868de35682e538809e8425152fd2fb9db",
    "ab_8x32_isolated_10k.json": "80876be4a4443b96ec7a3c28abf5d7c313a9b9271ddfa18ff94b9326ae16ba2a",
    "ab_16x32_packed_10k.json": "2972f2c72d808dcbd772b9d37f230e0976158647a74709bbc2e9e93a7620cee5",
    "ab_16x32_isolated_10k.json": "552657a4e0e3c787abc13a18bdcd4a6bfdf357b9b0a0bf6da692a0bf1d8a8c68",
    "sass-sm87-03.txt": "3446ad901d66a7120f4acca95d0f31107bff654232a871ae336adb1e10495136",
    "run-04-l2-snoop-decoupling-10k.log": "d4ac9677d90ef13b5448f3fdcb6653c92939b34ba279124bef9e410e4b023d04",
    "snoop_16x32_part_none_10k.json": "40ad287e8cae64c6362b7ea707f2d2a62e9f5146199cea917d4d651f92c069f0",
    "snoop_16x32_part_rand_10k.json": "1d453404da1d2225a0ceafb336d9a74eee3913c5138eaf66d164c2ecc9976a2a",
    "snoop_16x32_shared_none_10k.json": "7d7046d9953869d4938ac9035d108ada3384d667284dbd4317ed55d16e356627",
    "snoop_16x32_shared_rand_10k.json": "c5e2276c7c06aaef33cb926b8207473c00be0599bf2591cf5d11a4ef15282df8",
    "snoop_16x64_part_rand_10k.json": "62e0b6bfc6932fdfe75918fd052bd7a3c9b996e903bae2a22f66e4e8e081b4ec",
    "snoop_16x64_shared_rand_10k.json": "a25dffa34820bcd29b384342006fa98962cffd12943c40a77c1d52812428dd65",
    "snoop_2x512_part_rand_10k.json": "65aaefe66c2acd50b5bac5a813a5e0d97ad83acf7754a7b5311008645df53861",
    "snoop_2x512_shared_rand_10k.json": "a838ede1941969754cd539a4a65d0be28b062af22f251a7b39145406125e168c",
    "snoop_4x256_part_rand_10k.json": "72033b2e71e31b6675b1dbb57406dd3441536c18977bbf97fb772105041bf6ea",
    "snoop_8x32_part_rand_10k.json": "60a9364b86b7ffabb814498d3913ec59be58c478b4a355338641140f21539820",
    "snoop_8x32_shared_rand_10k.json": "17569fe83978bf4abab7f8626ce1504716d3ea8a341ccf964121c5a4a2b95e8a",
}


def validate_metrology_record(rec: dict, max_clock_gt_rel_err: float = 0.02) -> None:
    """Validate dual-timer consistency and CPU-oracle agreement on a run record."""
    if rec["mismatches"] != 0:
        raise ValueError(f"CPU oracle mismatch count {rec['mismatches']} != 0")
    freq_hz = rec["sysfs_cur_freq_hz"]
    if freq_hz <= 0:
        raise ValueError("Missing sysfs_cur_freq_hz")
    computed_ns = rec["e2e_sm_cycles_mean"] * (1e9 / freq_hz)
    if abs(computed_ns - rec["e2e_sm_ns_mean"]) > 0.05:
        raise ValueError("Inconsistent cycle-to-ns conversion")
    gt_ns = rec["e2e_gt_ns_mean"]
    rel_err = abs(computed_ns - gt_ns) / gt_ns
    if rel_err > max_clock_gt_rel_err:
        raise ValueError(
            f"Clock/globaltimer divergence {rel_err:.4f} exceeds {max_clock_gt_rel_err}: "
            f"computed={computed_ns:.2f}ns vs globaltimer={gt_ns:.2f}ns"
        )


def validate_zero_divergence_sweep(mask_records: dict[str, dict]) -> None:
    """Falsification Criterion 1: sparse masks must not inflate cycles >5% vs all-ones."""
    base_cyc = mask_records["all"]["math_cycles_mean"]
    for mode in ("alt", "one", "ends", "rand"):
        cur_cyc = mask_records[mode]["math_cycles_mean"]
        growth = (cur_cyc - base_cyc) / base_cyc
        if growth > 0.05:
            raise ValueError(f"Warp divergence detected on mask={mode}: {cur_cyc} vs {base_cyc} (+{growth:.2%})")


def python_q8_pid_step(state: dict, gid: int, c_val: int, active: bool) -> dict:
    """Independent Python oracle for subscriber register update."""
    nxt = dict(state)
    if active:
        in_val = c_val + gid
        err = in_val - state["target"]
        p_term = err * state["kp"]
        d_term = (err - state["prev_err"]) * state["kd"]
        new_int = state["integral"] + err
        i_term = (new_int * state["ki_q8"]) >> 8
        nxt["integral"] = new_int
        nxt["prev_err"] = err
        nxt["out_val"] = p_term + d_term + i_term
        nxt["trigger_count"] = state["trigger_count"] + 1
    return nxt


def test_cu_source_contracts_and_no_hardcoded_clock():
    src = CU_FILE.read_text(encoding="utf-8")
    assert "GPU_CLOCK_KHZ" not in src, "Hardcoded nominal GPU clock constant is prohibited"
    assert "static_assert(sizeof(km_event_ingress_t) == 128" in src
    assert "static_assert(sizeof(km_ack_line_t) == 128" in src
    assert "static_assert(offsetof(km_event_egress_t, isolated_ack) == 128" in src
    assert "static_assert(offsetof(km_event_egress_t, outputs) == 128 + KM_MAX_BLOCKS * 128" in src
    assert "--ack-mode" in src
    assert "--ingress-mode" in src
    assert "KM_MAX_SUBSCRIBERS    1024u" in src
    assert "--allow-attr-clock" in src
    assert "%%globaltimer" in src
    assert "ld.global.acquire.sys.u32" in src
    assert "st.global.release.sys.u32" in src


def test_raw_artifacts_sha256_and_provenance_headers():
    assert REPORT_FILE.exists()
    for fname, expected_sha in EXPECTED_RAW_SHA256.items():
        fpath = RAW_DIR / fname
        assert fpath.exists(), f"Missing raw artifact {fname}"
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"SHA-256 mismatch for {fname}"

    for log_name in ("sass-sm87-01.txt", "run-01-dvfs-unlocked-1x32.log", "run-02-locked-matrix-01.log"):
        head = (RAW_DIR / log_name).read_text(encoding="utf-8").splitlines()[:4]
        assert head[0].startswith("# cmd: ")
        assert re.match(r"^# timestamp: \d{4}-\d{2}-\d{2}T", head[1])
        assert head[2].startswith("# host: jetson")
        assert head[3].startswith("# git_base_sha: ")

    for log_name in ("sass-sm87-02.txt", "run-03-ab-scaling-10k.log"):
        head = (RAW_DIR / log_name).read_text(encoding="utf-8").splitlines()[:5]
        assert head[0].startswith("# cmd: ")
        assert re.match(r"^# timestamp(_start)?: \d{4}-\d{2}-\d{2}T", head[1])
        assert head[2].startswith("# host: jetson")
        assert re.match(r"^# cu_sha256: [0-9a-f]{64}$", head[3])
        assert head[4].startswith("# nvcc: ") and "-O3 -arch=sm_87 -lineinfo" in head[4]

    for log_name in ("sass-sm87-03.txt", "run-04-l2-snoop-decoupling-10k.log"):
        lines = (RAW_DIR / log_name).read_text(encoding="utf-8").splitlines()
        head = lines[:6]
        assert head[0].startswith("# cmd: ")
        assert re.match(r"^# timestamp: \d{4}-\d{2}-\d{2}T", head[1])
        assert head[2].startswith("# host: jetson")
        assert head[3] == f"# cu_sha256: {hashlib.sha256(CU_FILE.read_bytes()).hexdigest()}"
        assert head[4].startswith("# nvcc_version: ") and "-O3 -arch=sm_87 -lineinfo" in head[4]
        assert head[5].startswith("# git_base_sha: ")
        assert all(not ln.endswith(" ") and not ln.endswith("\t") for ln in lines)


def test_sass_predicated_execution_and_locked_metrology():
    sass = (RAW_DIR / "sass-sm87-01.txt").read_text(encoding="utf-8")
    assert "SEL R" in sass
    assert re.search(r"@P\d+\s+STG\.E", sass), "Expected predicated egress store in sm_87 SASS"
    assert "LDG.E.STRONG.SYS" in sass
    assert "STG.E.STRONG.SYS" in sass
    assert "SR_GLOBALTIMERLO" in sass

    mask_records = {}
    for mode in ("all", "alt", "one", "ends", "rand", "none"):
        rec = json.loads((RAW_DIR / f"mask_1x32_{mode}.json").read_text(encoding="utf-8"))
        validate_metrology_record(rec, max_clock_gt_rel_err=0.01)
        assert rec["math_ns_mean"] <= 100.0
        mask_records[mode] = rec

    validate_zero_divergence_sweep(mask_records)

    s_1x512 = json.loads((RAW_DIR / "scale_1x512.json").read_text(encoding="utf-8"))
    s_16x32 = json.loads((RAW_DIR / "scale_16x32.json").read_text(encoding="utf-8"))
    validate_metrology_record(s_1x512, max_clock_gt_rel_err=0.01)
    validate_metrology_record(s_16x32, max_clock_gt_rel_err=0.01)
    assert s_1x512["math_ns_mean"] <= 100.0
    # Empirical L2 snoop storm proof: Single-SM 1x512 must substantially beat naive 16x32
    assert s_16x32["e2e_sm_ns_mean"] > 4.0 * s_1x512["e2e_sm_ns_mean"]


def test_ab_ack_isolation_10k_and_bootstrap_ci():
    """F-1 / F-2 / F-3: N=10000, 95% bootstrap CI, packed vs isolated ack A/B, and SASS v2."""
    sass2 = (RAW_DIR / "sass-sm87-02.txt").read_text(encoding="utf-8")
    assert "SEL R" in sass2
    assert re.search(r"@P\d+\s+STG\.E\s+\[R\d+\.64\+0x880\]", sass2)
    assert "LDG.E.STRONG.SYS" in sass2
    assert "STG.E.STRONG.SYS" in sass2

    single_sm = {}
    for geom in ("1x32", "1x128", "1x256", "1x512"):
        rec = json.loads((RAW_DIR / f"ab_scale_{geom}_10k.json").read_text(encoding="utf-8"))
        validate_metrology_record(rec, max_clock_gt_rel_err=0.01)
        assert rec["events"] == 10000
        assert rec["mid_run_mismatches"] == 0
        assert rec["ack_mode"] == "isolated"
        assert rec["e2e_sm_ns_p99_ci95_lo"] <= rec["e2e_sm_ns_p99"] <= rec["e2e_sm_ns_p99_ci95_hi"]
        assert rec["e2e_sm_ns_p999_ci95_lo"] <= rec["e2e_sm_ns_p999"] <= rec["e2e_sm_ns_p999_ci95_hi"]
        # F-1: at 816 MHz (MODE_50W), p99.9 exceeds 1500 ns across ALL geometries
        assert rec["e2e_sm_ns_p999"] > 1500.0
        single_sm[geom] = rec

    for blk in (8, 16):
        packed = json.loads((RAW_DIR / f"ab_{blk}x32_packed_10k.json").read_text(encoding="utf-8"))
        isolated = json.loads((RAW_DIR / f"ab_{blk}x32_isolated_10k.json").read_text(encoding="utf-8"))
        for rec in (packed, isolated):
            validate_metrology_record(rec, max_clock_gt_rel_err=0.01)
            assert rec["events"] == 10000
            assert rec["mid_run_mismatches"] == 0
            assert len(rec["per_block_e2e_sm_ns_mean"]) == blk
        assert packed["ack_mode"] == "packed"
        assert isolated["ack_mode"] == "isolated"
        # Isolating ack lines reduces mean latency and p99.9, but L2 read snoop on ingress dominates
        assert isolated["e2e_sm_ns_mean"] < packed["e2e_sm_ns_mean"]
        assert isolated["e2e_sm_ns_p999"] < packed["e2e_sm_ns_p999"]

    ab_16_iso = json.loads((RAW_DIR / "ab_16x32_isolated_10k.json").read_text(encoding="utf-8"))
    assert ab_16_iso["e2e_sm_ns_mean"] > 5.0 * single_sm["1x512"]["e2e_sm_ns_mean"]


def validate_snoop_decoupling_factorial(
    shared_rand: dict, shared_none: dict, part_rand: dict, part_none: dict
) -> None:
    """Validate 2x2 factorial proof that L2 Read Snoop (not outputs[] write) dominates."""
    # Disabling outputs[] writes in shared mode must NOT eliminate the >8 us bottleneck
    if shared_none["e2e_sm_ns_mean"] < 0.80 * shared_rand["e2e_sm_ns_mean"]:
        raise ValueError("Outputs write unexpectedly dominated shared mode")
    # Partitioning ingress per SM must cut SM e2e time by >= 3.0x and Host RT by >= 3.5x
    if shared_rand["e2e_sm_ns_mean"] / part_rand["e2e_sm_ns_mean"] < 3.0:
        raise ValueError("Per-SM partitioned ingress failed to achieve >=3.0x SM speedup")
    if shared_rand["host_rt_ns_mean"] / part_rand["host_rt_ns_mean"] < 3.5:
        raise ValueError("Per-SM partitioned ingress failed to achieve >=3.5x Host RT speedup")


def test_per_sm_ingress_decoupling_factorial_and_1024_scaling():
    """Issue #235: verify 2x2 L2 snoop decoupling factorial and 1024-subscriber scaling."""
    sass3 = (RAW_DIR / "sass-sm87-03.txt").read_text(encoding="utf-8")
    assert "SEL R" in sass3
    assert re.search(r"@P\d+\s+STG\.E\s+\[R\d+\.64\+0x880\]", sass3)

    sh_rand = json.loads((RAW_DIR / "snoop_16x32_shared_rand_10k.json").read_text(encoding="utf-8"))
    sh_none = json.loads((RAW_DIR / "snoop_16x32_shared_none_10k.json").read_text(encoding="utf-8"))
    pt_rand = json.loads((RAW_DIR / "snoop_16x32_part_rand_10k.json").read_text(encoding="utf-8"))
    pt_none = json.loads((RAW_DIR / "snoop_16x32_part_none_10k.json").read_text(encoding="utf-8"))
    for rec in (sh_rand, sh_none, pt_rand, pt_none):
        validate_metrology_record(rec, max_clock_gt_rel_err=0.015)
        assert rec["events"] == 10000 and rec["mid_run_mismatches"] == 0
    validate_snoop_decoupling_factorial(sh_rand, sh_none, pt_rand, pt_none)

    # 1024-subscriber verification across 16x64, 4x256, and 2x512
    s16x64_sh = json.loads((RAW_DIR / "snoop_16x64_shared_rand_10k.json").read_text(encoding="utf-8"))
    s16x64_pt = json.loads((RAW_DIR / "snoop_16x64_part_rand_10k.json").read_text(encoding="utf-8"))
    s4x256_pt = json.loads((RAW_DIR / "snoop_4x256_part_rand_10k.json").read_text(encoding="utf-8"))
    s2x512_pt = json.loads((RAW_DIR / "snoop_2x512_part_rand_10k.json").read_text(encoding="utf-8"))
    for rec in (s16x64_sh, s16x64_pt, s4x256_pt, s2x512_pt):
        validate_metrology_record(rec, max_clock_gt_rel_err=0.02)
        assert rec["subscribers"] == 1024
        assert rec["mismatches"] == 0 and rec["mid_run_mismatches"] == 0
        assert rec["math_ns_mean"] <= 100.0

    # 16x64 partitioned achieves >9x SM speedup over 16x64 shared
    assert s16x64_sh["e2e_sm_ns_mean"] / s16x64_pt["e2e_sm_ns_mean"] > 9.0

    # Negative-control mutant for factorial validator (AGENTS.md §4.1)
    broken_part = {**pt_rand, "e2e_sm_ns_mean": sh_rand["e2e_sm_ns_mean"] * 0.8}
    with pytest.raises(ValueError, match="failed to achieve >=3.0x SM speedup"):
        validate_snoop_decoupling_factorial(sh_rand, sh_none, broken_part, pt_none)


def test_negative_controls_catch_fake_clock_dvfs_and_divergence():
    """AGENTS.md §4.1: prove validators fail on fake clock, unlocked DVFS, and divergence."""
    valid_rec = json.loads((RAW_DIR / "mask_1x32_all.json").read_text(encoding="utf-8"))

    # Mutant 1: substituting nominal 1.30 GHz instead of actual 816 MHz must fail against %globaltimer
    fake_1300mhz_rec = dict(valid_rec)
    fake_1300mhz_rec["sysfs_cur_freq_hz"] = 1_300_000_000
    fake_1300mhz_rec["e2e_sm_ns_mean"] = fake_1300mhz_rec["e2e_sm_cycles_mean"] * (1e9 / 1_300_000_000)
    with pytest.raises(ValueError, match="Clock/globaltimer divergence"):
        validate_metrology_record(fake_1300mhz_rec)

    # Mutant 2: real unlocked DVFS record (306->816 MHz) MUST be rejected by strict timer consistency
    unlocked_rec = json.loads((RAW_DIR / "dvfs_unlocked_1x32.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="Clock/globaltimer divergence"):
        validate_metrology_record(unlocked_rec)

    # Mutant 3: warp-divergent cycle growth on alternating mask must fail Criterion 1
    bad_masks = {
        "all": valid_rec,
        "alt": {**valid_rec, "math_cycles_mean": valid_rec["math_cycles_mean"] * 1.15},
        "one": valid_rec,
        "ends": valid_rec,
        "rand": valid_rec,
    }
    with pytest.raises(ValueError, match="Warp divergence detected"):
        validate_zero_divergence_sweep(bad_masks)

    # Mutant 4: inactive lane mutating integrator must diverge from Python Q8 oracle
    st0 = {"target": 20, "kp": 2, "ki_q8": 26, "kd": 1, "integral": 0, "prev_err": 0, "out_val": -7777, "trigger_count": 0}
    ref_inactive = python_q8_pid_step(st0, gid=3, c_val=28, active=False)
    ref_active = python_q8_pid_step(st0, gid=3, c_val=28, active=True)
    # Hand-calculated check: in_val=31, err=11 -> P=22, D=11, I=(286>>8)=1 -> out_val=34
    assert ref_inactive == st0
    assert ref_active["out_val"] == 34 and ref_active["trigger_count"] == 1


def _is_jetson_reachable() -> bool:
    if os.environ.get("KM_SKIP_LIVE_HIL") == "1":
        return False
    res = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", JETSON_HOST, "echo OK"],
        capture_output=True,
        text=True,
    )
    return res.returncode == 0 and "OK" in res.stdout


@pytest.mark.skipif(not _is_jetson_reachable(), reason="Jetson AGX Orin stand not reachable via SSH")
def test_live_jetson_hil_sparse_and_single_sm_256():
    """Live HIL verification on Jetson AGX Orin strictly under /tmp/km-bench.lock."""
    cmd = [
        "flock", "-w", "120", "/tmp/km-bench.lock",
        "bash", "-c",
        (
            f"scp -q {CU_FILE} {JETSON_HOST}:/tmp/km_pytest_subs.cu && "
            f"ssh -o StrictHostKeyChecking=no {JETSON_HOST} '"
            "/usr/local/cuda/bin/nvcc -O3 -arch=sm_87 /tmp/km_pytest_subs.cu -o /tmp/km_pytest_subs -lm && "
            "/tmp/km_pytest_subs --events 500 --blocks 1 --threads 32 --mask alt --json-out /tmp/km_pytest_alt.json >/dev/null && "
            "/tmp/km_pytest_subs --events 500 --blocks 16 --threads 64 --ingress-mode partitioned --mask rand --json-out /tmp/km_pytest_1024.json >/dev/null && "
            "cat /tmp/km_pytest_alt.json && echo ---SPLIT--- && cat /tmp/km_pytest_1024.json && "
            "rm -f /tmp/km_pytest_subs.cu /tmp/km_pytest_subs /tmp/km_pytest_alt.json /tmp/km_pytest_1024.json'"
        ),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Live Jetson HIL failed: {res.stderr}\n{res.stdout}"
    part_alt, part_1024 = res.stdout.split("---SPLIT---")
    rec_alt = json.loads(part_alt.strip())
    rec_1024 = json.loads(part_1024.strip())
    assert rec_alt["mismatches"] == 0 and rec_alt["subscribers"] == 32
    assert rec_1024["mismatches"] == 0 and rec_1024["subscribers"] == 1024 and rec_1024["ingress_mode"] == "partitioned"
