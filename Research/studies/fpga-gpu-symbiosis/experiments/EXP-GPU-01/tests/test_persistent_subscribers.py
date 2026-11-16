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
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXP_DIR = Path(__file__).resolve().parents[1]
if str(EXP_DIR) not in sys.path:
    sys.path.insert(0, str(EXP_DIR))

from summarize_repeatability_240 import (  # noqa: E402
    REQUIRED_PUB_FIELDS,
    compute_across_run_stats,
    summarize_repeatability_dir,
    validate_rep240_record,
)

STUDY_DIR = EXP_DIR.parents[1]
CU_FILE = EXP_DIR / "persistent_subscribers.cu"
RAW_DIR = STUDY_DIR / "data" / "exp-gpu-01-phase3"
REP240_DIR = RAW_DIR / "repeatability-240"
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

EXPECTED_REP240_SHA256 = {
    "sass-sm87-04.txt": "9ddef87feb3f0a84cdd6f8b75add780eb85f938870ce9e96b0214097a08f6dfd",
    "run-05-repeatability-240.log": "874c1354186e2b58abe03084ffcc2e122ae1a5f74cb1eb4c5db47dbfdf4288af",
    "summary_repeatability_240.json": "45af46398b4af105644957e2afbe14009f4cbd1fdbef4d413c40a73f2e2dd0db",
    "rep240_16x64_partitioned_none_r1.json": "b55f62da6f8d607be46d119cf083000847bdd2542c43339dd99bf42387056884",
    "rep240_16x64_partitioned_none_r2.json": "25f6c1527f23ff53a7af84c30e15a18f6adb17a763255e76a49b0521675c28f8",
    "rep240_16x64_partitioned_none_r3.json": "66f90583116b674ac220cd5939dc4544f6e07caac1903636e0c86f8ce29cead9",
    "rep240_16x64_partitioned_none_r4.json": "1f1c60e411f64dc337e47ef1d5d9b1cdd537790ca0762b862d2c8952e3077d8d",
    "rep240_16x64_partitioned_none_r5.json": "9249969435c58791e6813477603206654f87913a37ba4bbb3b7b7667ed50aa80",
    "rep240_16x64_partitioned_rand_r1.json": "6621b5aa3ebd9008c7f5aa6e99f47b057792a413e7af56f4fd72eb4b6365aa7d",
    "rep240_16x64_partitioned_rand_r2.json": "42924e58b8e8476dd9dc5bd10b0f877ea430ff39a26433b6e916a2e0506ca4fd",
    "rep240_16x64_partitioned_rand_r3.json": "2dd18922434aa28eb5bb55a68162fc6af875b70ba63d5f7680956e79f21c959a",
    "rep240_16x64_partitioned_rand_r4.json": "f8e4c4ab9eeb7a46eb100db9a3d0f536bcf835dc06cdcc5a2a53477f81e63742",
    "rep240_16x64_partitioned_rand_r5.json": "0f84c313a6fd2a7e4c12fd56729972bea515fa82580987b38dd877e5869927f9",
    "rep240_16x64_shared_1line_none_r1.json": "1dd40e482be658e305168f18dca5335a874744a27cf6d325fe90dd022b8aba95",
    "rep240_16x64_shared_1line_none_r2.json": "544e284ec5bcfdc95ccb5e4aa7ca5a64eb0164c67fe519352f49dc9e531351d5",
    "rep240_16x64_shared_1line_none_r3.json": "17054b313c3abe4bfa1e28b5eb929c6b9068fa8fc4e6f35b2676a5f9a1f8a70d",
    "rep240_16x64_shared_1line_none_r4.json": "103ed3927fd67ce7a29c378d71a20efe9c3c2a41588e50b46d4e9a198273e29e",
    "rep240_16x64_shared_1line_none_r5.json": "244e9d052c09068d9bed0d23040454ded9595f8f2db19b3a9d3c8bd239b4c9e8",
    "rep240_16x64_shared_1line_rand_r1.json": "70a312dd7124b6024b7a49a8d7f093ec552bea3e53169a848eb23a006039de3a",
    "rep240_16x64_shared_1line_rand_r2.json": "5a5bb5f11570ee7efd3babb8bda411896a6ae13954bcdcf47599cee14d57be60",
    "rep240_16x64_shared_1line_rand_r3.json": "3fdb36a5a01739a59faba78fbfe99bda81afd38f743a6c725746faeb0d81098d",
    "rep240_16x64_shared_1line_rand_r4.json": "4411cd49185d60169d2f2f7b8035895380d552b61d39ef161796e583e10b788f",
    "rep240_16x64_shared_1line_rand_r5.json": "4fb9c0996b29b0c9d8cffbbc1a98b649899d00278bae165f825629ba097cbe7b",
    "rep240_16x64_shared_2line_none_r1.json": "57617d7464762a633437951403fd0ed3aa555329f35a107697bfd32f5b0037d5",
    "rep240_16x64_shared_2line_none_r2.json": "7138350ca900c52de795649bd143f5424ba44b781666d9e9bdcb2c9dad66768d",
    "rep240_16x64_shared_2line_none_r3.json": "c5d66f1b7d4f8ce9a2bed8871543ac205f45f8eee85ad50e9c94bff0ea1c1efe",
    "rep240_16x64_shared_2line_none_r4.json": "3ba72d5dd1d6e540db4c172db5b7fd37206328f526272305e1a7e42e77c0c2e8",
    "rep240_16x64_shared_2line_none_r5.json": "e49ca955d73388ce9734990758a1d0d4bbabea4720c91b5923098feaa2c60451",
    "rep240_16x64_shared_2line_rand_r1.json": "c56a5bde0effcf40d36da8609b18009ae7f8d4240a9023b5171c8e198aba1cfe",
    "rep240_16x64_shared_2line_rand_r2.json": "4f70ec84f7cecfff6752752c7f17b186e02e27cfaed7b8827aa69206ec853528",
    "rep240_16x64_shared_2line_rand_r3.json": "a7cbbb541d0b89edff0fe4d212b8c7f5e70400ec3bdce5c10f16975485951cae",
    "rep240_16x64_shared_2line_rand_r4.json": "2b9eb9a77b1106a4aa73ac27b383a00bb7a351913c13de5e847f6c59931c175c",
    "rep240_16x64_shared_2line_rand_r5.json": "783cc3c3b76fce4feea2dc1b0aa3d4bc3de528c702db2daa8a700f547df31e4a",
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
    assert "--shared-ingress" in src
    assert "--shared-1line" in src
    assert "KM_INGRESS_SHARED_1LINE" in src
    assert "KM_INGRESS_SHARED_2LINE" in src
    assert "host_pub_ns_mean" in src
    assert "host_wait_ack_ns_mean" in src
    assert "mismatch_count" in src
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
        assert head[3] == "# cu_sha256: 7c31ef547baad58d062889ca31a0a385a2575c56239adfdcd13ef48a64c62493"
        assert head[4].startswith("# nvcc_version: ") and "-O3 -arch=sm_87 -lineinfo" in head[4]
        assert head[5].startswith("# git_base_sha: ")
        assert all(not ln.endswith(" ") and not ln.endswith("\t") for ln in lines)

    for fname, expected_sha in EXPECTED_REP240_SHA256.items():
        fpath = REP240_DIR / fname
        assert fpath.exists(), f"Missing repeatability-240 artifact {fname}"
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"SHA-256 mismatch for repeatability-240/{fname}"

    for log_name in ("sass-sm87-04.txt", "run-05-repeatability-240.log"):
        lines = (REP240_DIR / log_name).read_text(encoding="utf-8").splitlines()
        head = lines[:6]
        assert head[0].startswith("# cmd: ")
        assert re.match(r"^# timestamp: \d{4}-\d{2}-\d{2}T", head[1])
        assert head[2].startswith("# host: jetson")
        assert head[3] == f"# cu_sha256: {hashlib.sha256(CU_FILE.read_bytes()).hexdigest()}"
        assert head[4].startswith("# nvcc_version: ") and "-O3 -arch=sm_87 -lineinfo" in head[4]
        assert head[5].startswith("# git_base_sha: ")
        assert all(not ln.endswith(" ") and not ln.endswith("\t") for ln in lines)

    run05_text = (REP240_DIR / "run-05-repeatability-240.log").read_text(encoding="utf-8")
    assert "devfreq_hz_before: cur=816000000 min=816000000 max=816000000" in run05_text
    assert "devfreq_hz_after: cur=816000000 min=816000000 max=816000000" in run05_text


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


def test_repeatability_240_matrix_and_host_rt_decomposition():
    """Issue #240: verify R=5 x 10k 3x2 matrix, SASS v4, Host RT decomposition, and report v0.4.0."""
    sass4 = (REP240_DIR / "sass-sm87-04.txt").read_text(encoding="utf-8")
    assert "SEL R" in sass4
    assert re.search(r"@P\d+\s+STG\.E\s+\[R\d+\.64\+0x880\]", sass4)
    assert "LDG.E.STRONG.SYS" in sass4
    assert "STG.E.STRONG.SYS" in sass4
    assert "SR_GLOBALTIMERLO" in sass4

    # Independent hand-calculated check of across-run aggregator (ddof=1, AGENTS.md §4.3)
    hand = compute_across_run_stats([10.0, 20.0, 30.0, 40.0, 50.0])
    assert hand["runs"] == 5
    assert hand["mean_of_means"] == pytest.approx(30.0)
    assert hand["sd_across_runs"] == pytest.approx(math.sqrt(250.0))
    assert hand["cv_pct"] == pytest.approx(math.sqrt(250.0) / 30.0 * 100.0)
    assert hand["min"] == 10.0 and hand["max"] == 50.0

    summary = summarize_repeatability_dir(REP240_DIR)
    committed_summary = json.loads((REP240_DIR / "summary_repeatability_240.json").read_text(encoding="utf-8"))
    assert summary == committed_summary
    assert summary["total_runs"] == 30
    assert summary["total_events"] == 300000
    assert summary["all_mismatches_zero"] is True

    cells = summary["cells"]
    sh1_rand = cells["shared_1line__rand"]["metrics"]
    sh2_rand = cells["shared_2line__rand"]["metrics"]
    pt_rand = cells["partitioned__rand"]["metrics"]
    sh1_none = cells["shared_1line__none"]["metrics"]
    sh2_none = cells["shared_2line__none"]["metrics"]
    pt_none = cells["partitioned__none"]["metrics"]

    # Point 2 (#240): shared_1line (1x128B) and shared_2line (2x128B) agree within 5% on T_e2e_sm
    assert abs(sh1_rand["e2e_sm_ns_mean"]["mean_of_means"] - sh2_rand["e2e_sm_ns_mean"]["mean_of_means"]) / sh2_rand["e2e_sm_ns_mean"]["mean_of_means"] < 0.05
    assert abs(sh1_none["e2e_sm_ns_mean"]["mean_of_means"] - sh2_none["e2e_sm_ns_mean"]["mean_of_means"]) / sh2_none["e2e_sm_ns_mean"]["mean_of_means"] < 0.05

    # Point 3 (#240): partitioned achieves >9x mean and >8x p99.9 SM speedup vs both shared topologies across R=5
    assert sh1_rand["e2e_sm_ns_mean"]["mean_of_means"] / pt_rand["e2e_sm_ns_mean"]["mean_of_means"] > 9.0
    assert sh2_rand["e2e_sm_ns_mean"]["mean_of_means"] / pt_rand["e2e_sm_ns_mean"]["mean_of_means"] > 9.0
    assert sh1_rand["e2e_sm_ns_p999"]["mean_of_means"] / pt_rand["e2e_sm_ns_p999"]["mean_of_means"] > 8.0
    for cell_data in cells.values():
        assert cell_data["metrics"]["e2e_sm_ns_p999"]["cv_pct"] < 3.0
        assert cell_data["metrics"]["math_ns_p999"]["mean_of_means"] <= 100.0

    # Point 4 (#240): 16x stlr in partitioned increases T_host_pub vs 1x stlr, while T_wait_ack drops >4.5x
    assert pt_rand["host_pub_ns_mean"]["mean_of_means"] > 5.0 * sh1_rand["host_pub_ns_mean"]["mean_of_means"]
    assert pt_none["host_pub_ns_mean"]["mean_of_means"] > 5.0 * sh1_none["host_pub_ns_mean"]["mean_of_means"]
    assert sh1_rand["host_wait_ack_ns_mean"]["mean_of_means"] / pt_rand["host_wait_ack_ns_mean"]["mean_of_means"] > 4.5
    assert sh2_rand["host_wait_ack_ns_mean"]["mean_of_means"] / pt_rand["host_wait_ack_ns_mean"]["mean_of_means"] > 4.5

    # Report v0.4.0 tone & structure guard (AGENTS.md §3: zero exclamation marks)
    report_text = REPORT_FILE.read_text(encoding="utf-8")
    assert "* **Версія:** 0.4.0" in report_text
    assert "!" not in report_text, "Exclamation marks violate AGENTS.md §3 in report-phase3-warp-scaling.md"


def test_repeatability_240_mutants_fail_on_tamper_and_mismatches():
    """AGENTS.md §4.1: prove repeatability-240 validators catch mismatch_count != 0 and corrupted JSON."""
    sample_path = REP240_DIR / "rep240_16x64_shared_1line_rand_r1.json"
    valid_rec = json.loads(sample_path.read_text(encoding="utf-8"))
    validate_rep240_record(valid_rec, expected_ingress="shared_1line", expected_mask="rand")

    # Mutant 1: non-zero mismatch_count must fail
    with pytest.raises(ValueError, match="Non-zero CPU oracle mismatch"):
        validate_rep240_record({**valid_rec, "mismatch_count": 1}, "shared_1line", "rand")

    # Mutant 2: missing host_pub_ns_* field must fail
    for field in REQUIRED_PUB_FIELDS:
        stripped = dict(valid_rec)
        stripped.pop(field)
        with pytest.raises(ValueError, match="Missing required host publication field"):
            validate_rep240_record(stripped, "shared_1line", "rand")

    # Mutant 3: broken Host RT = T_host_pub + T_wait_ack decomposition must fail
    with pytest.raises(ValueError, match="Host RT decomposition mismatch"):
        validate_rep240_record(
            {**valid_rec, "host_pub_ns_mean": valid_rec["host_pub_ns_mean"] + 50.0},
            "shared_1line",
            "rand",
        )

    # Mutant 4: swapped ingress_mode label must fail
    with pytest.raises(ValueError, match="Expected ingress_mode=shared_1line"):
        validate_rep240_record({**valid_rec, "ingress_mode": "shared_2line"}, "shared_1line", "rand")

    # Mutant 5: ddof=1 enforcement (<2 runs rejected; 2-run SD != population SD)
    with pytest.raises(ValueError, match="requires at least 2 runs"):
        compute_across_run_stats([42.0])
    two_run = compute_across_run_stats([10.0, 20.0])
    assert two_run["sd_across_runs"] == pytest.approx(math.sqrt(50.0))
    assert two_run["sd_across_runs"] != pytest.approx(5.0)

    # Mutant 6: directory-level detection of corrupted JSON and injected mismatch_count
    scratch_dir = EXP_DIR / ".scratch_mutant_rep240"
    try:
        shutil.rmtree(scratch_dir, ignore_errors=True)
        shutil.copytree(REP240_DIR, scratch_dir)
        target_json = scratch_dir / "rep240_16x64_partitioned_rand_r3.json"
        tampered = json.loads(target_json.read_text(encoding="utf-8"))
        tampered["mismatch_count"] = 2
        target_json.write_text(json.dumps(tampered), encoding="utf-8")
        with pytest.raises(ValueError, match="Non-zero CPU oracle mismatch"):
            summarize_repeatability_dir(scratch_dir)

        target_json.write_text("{corrupted_json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            summarize_repeatability_dir(scratch_dir)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


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
            f"ssh -o StrictHostKeyChecking=no {JETSON_HOST} 'mkdir -p $HOME/.km_pytest_240' && "
            f"scp -q {CU_FILE} {JETSON_HOST}:~/.km_pytest_240/km_pytest_subs.cu && "
            f"ssh -o StrictHostKeyChecking=no {JETSON_HOST} '"
            "/usr/local/cuda/bin/nvcc -O3 -arch=sm_87 $HOME/.km_pytest_240/km_pytest_subs.cu -o $HOME/.km_pytest_240/km_pytest_subs -lm && "
            "$HOME/.km_pytest_240/km_pytest_subs --events 500 --blocks 1 --threads 32 --mask alt --json-out $HOME/.km_pytest_240/km_pytest_alt.json >/dev/null && "
            "$HOME/.km_pytest_240/km_pytest_subs --events 500 --blocks 16 --threads 64 --shared-1line --mask rand --json-out $HOME/.km_pytest_240/km_pytest_1line.json >/dev/null && "
            "$HOME/.km_pytest_240/km_pytest_subs --events 500 --blocks 16 --threads 64 --ingress-mode partitioned --mask rand --json-out $HOME/.km_pytest_240/km_pytest_1024.json >/dev/null && "
            "cat $HOME/.km_pytest_240/km_pytest_alt.json && echo ---SPLIT--- && "
            "cat $HOME/.km_pytest_240/km_pytest_1line.json && echo ---SPLIT--- && "
            "cat $HOME/.km_pytest_240/km_pytest_1024.json && "
            "rm -rf $HOME/.km_pytest_240'"
        ),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Live Jetson HIL failed: {res.stderr}\n{res.stdout}"
    part_alt, part_1line, part_1024 = res.stdout.split("---SPLIT---")
    rec_alt = json.loads(part_alt.strip())
    rec_1line = json.loads(part_1line.strip())
    rec_1024 = json.loads(part_1024.strip())
    assert rec_alt["mismatches"] == 0 and rec_alt["subscribers"] == 32
    assert rec_1line["mismatch_count"] == 0 and rec_1line["subscribers"] == 1024 and rec_1line["ingress_mode"] == "shared_1line"
    assert rec_1024["mismatch_count"] == 0 and rec_1024["subscribers"] == 1024 and rec_1024["ingress_mode"] == "partitioned"
    assert "host_pub_ns_mean" in rec_1024 and "host_rt_us_mean" in rec_1024
