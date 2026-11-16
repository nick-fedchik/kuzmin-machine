"""CI & local pytest bridge for EXP-GPU-01 L2 snoop decoupling and 1024-subscriber scaling (#235)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
TARGET = (
    REPO_ROOT
    / "Research"
    / "studies"
    / "fpga-gpu-symbiosis"
    / "experiments"
    / "EXP-GPU-01"
    / "tests"
    / "test_persistent_subscribers.py"
)

_spec = importlib.util.spec_from_file_location("exp_gpu_01_persistent_subscribers_tests", TARGET)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

test_cu_source_contracts_and_no_hardcoded_clock = _mod.test_cu_source_contracts_and_no_hardcoded_clock
test_raw_artifacts_sha256_and_provenance_headers = _mod.test_raw_artifacts_sha256_and_provenance_headers
test_sass_predicated_execution_and_locked_metrology = _mod.test_sass_predicated_execution_and_locked_metrology
test_ab_ack_isolation_10k_and_bootstrap_ci = _mod.test_ab_ack_isolation_10k_and_bootstrap_ci
test_per_sm_ingress_decoupling_factorial_and_1024_scaling = _mod.test_per_sm_ingress_decoupling_factorial_and_1024_scaling
test_negative_controls_catch_fake_clock_dvfs_and_divergence = _mod.test_negative_controls_catch_fake_clock_dvfs_and_divergence
test_live_jetson_hil_sparse_and_single_sm_256 = _mod.test_live_jetson_hil_sparse_and_single_sm_256
