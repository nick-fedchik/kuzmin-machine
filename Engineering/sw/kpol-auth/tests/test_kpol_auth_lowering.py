"""Tests and mutant controls for derived KPOL-AUTH Do/Go + CME-RAW-1 lowering."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
from unittest import mock
import uuid

PACKAGE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_DIR.parents[2]


@contextmanager
def _workspace_scratch_dir():
    base = REPO_ROOT / ".pytest_cache" / f"kpol_auth_cli_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _load_kpol_auth():
    if "kpol_auth" in sys.modules:
        return sys.modules["kpol_auth"]
    spec = importlib.util.spec_from_file_location(
        "kpol_auth",
        PACKAGE_DIR / "__init__.py",
        submodule_search_locations=[str(PACKAGE_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


ka = _load_kpol_auth()
lowering_mod = sys.modules["kpol_auth.lowering"]


class ReferenceDoGoVM:
    """Independent reference stack-VM matching km_mcu_fpga_bridge.c semantics."""

    def __init__(self, artifact: ka.LoweredArtifact) -> None:
        self.artifact = artifact
        self.val_cur = [c.init_val for c in artifact.concepts]
        self.val_prev = [c.init_val for c in artifact.concepts]
        self.big_dot_ok = [0 for _ in artifact.concepts]
        self.queue: list[int] = []

    def _eval_event_vector(self, cid: int) -> int:
        v = self.val_cur[cid]
        vec = 1 << 7  # KM_EV_ALWAYS
        if v == 0:
            vec |= 1 << 1  # KM_EV_NULL
        elif v > 0:
            vec |= 1 << 2  # KM_EV_POSITIVE
        else:
            vec |= 1 << 3  # KM_EV_NEGATIVE
        if (v & 1) == 0:
            vec |= 1 << 4  # KM_EV_EVEN
        else:
            vec |= 1 << 5  # KM_EV_UNEVEN
        if v != self.val_prev[cid]:
            vec |= 1 << 6  # KM_EV_CHANGED
        return vec

    def write_concept(self, cid: int, new_val: int) -> None:
        c = self.artifact.concepts[cid]
        if c.flags & lowering_mod.KM_FLAG_HW_PROTECTED:
            ok = True
            if c.lower_bound is not None and new_val < c.lower_bound:
                ok = False
            if c.upper_bound is not None and new_val > c.upper_bound:
                ok = False
            if not ok:
                self.big_dot_ok[cid] = 1
                for i in range(c.sub_count):
                    s_idx = c.first_sub_idx + i
                    if self.artifact.subscriptions[s_idx].phase == lowering_mod.KM_PHASE_ON_ABORT:
                        self.queue.append(s_idx)
                return
        self.val_prev[cid] = self.val_cur[cid]
        self.val_cur[cid] = new_val
        self.big_dot_ok[cid] = 0

        ev_vec = self._eval_event_vector(cid)
        for i in range(c.sub_count):
            s_idx = c.first_sub_idx + i
            sub = self.artifact.subscriptions[s_idx]
            if (
                sub.phase == lowering_mod.KM_PHASE_POST_CHANGE
                and (sub.trigger_mask & ev_vec) != 0
            ):
                self.queue.append(s_idx)

    def _exec_sub(self, sub_idx: int) -> None:
        sub = self.artifact.subscriptions[sub_idx]
        stack: list[int] = []
        exited = False
        for pc in range(sub.line_start_pc, sub.line_start_pc + sub.line_len):
            word = self.artifact.code_o[pc]
            opc = (word >> 28) & 0x0F
            sub_op = (word >> 24) & 0x0F
            operand = word & 0xFFFF

            if opc == lowering_mod.KM_OPC_IMM:
                signed_imm = operand - 0x10000 if (operand & 0x8000) else operand
                stack.append(signed_imm)
            elif opc == lowering_mod.KM_OPC_GO:
                if sub_op == lowering_mod.KM_GO_READ:
                    stack.append(self.val_cur[operand])
                elif sub_op == lowering_mod.KM_GO_WRITE:
                    val = stack.pop()
                    self.write_concept(operand, val)
                else:
                    raise AssertionError(f"Unexpected GO sub_op {sub_op}")
            elif opc == lowering_mod.KM_OPC_DO:
                rhs = stack.pop()
                lhs = stack.pop()
                if sub_op == lowering_mod.KM_DO_ADD:
                    stack.append(lhs + rhs)
                elif sub_op == lowering_mod.KM_DO_SUB:
                    stack.append(lhs - rhs)
                elif sub_op == lowering_mod.KM_DO_MUL:
                    stack.append(lhs * rhs)
                else:
                    raise AssertionError(f"Unexpected DO sub_op {sub_op}")
            elif opc == lowering_mod.KM_OPC_EXIT:
                exited = True
                break
            else:
                raise AssertionError(f"Unexpected opcode 0x{opc:x}")
        if not exited:
            raise AssertionError(f"Subscription S{sub_idx} missing KM_OPC_EXIT")

    def trigger_external(self, cid: int, val: int) -> None:
        self.write_concept(cid, val)
        while self.queue:
            s_idx = self.queue.pop(0)
            self._exec_sub(s_idx)


THERMAL_GRAPH_SOURCE = """
Concept(Temp, 20)
Concept(Heater, 10, Lower=10, Upper=80)
Concept(Fan, 0)
Concept(Alarm, 0)
Temp • Assign(Heater, 25 + ((Temp - 20) * 5))
OnPositive(Heater) • Assign(Fan, Heater)
OnAbort(Heater) • Assign(Alarm, 1)
OnAbort(Heater) • Assign(Fan, 100)
"""


class KpolAuthLoweringTests(unittest.TestCase):
    def _run_thermal_verification(self, artifact: ka.LoweredArtifact) -> None:
        vm = ReferenceDoGoVM(artifact)

        # Scenario 1: Normal operation (25°C -> 25 + (25 - 20) * 5 = 50W)
        vm.trigger_external(0, 25)
        self.assertEqual(vm.val_cur, [25, 50, 50, 0])
        self.assertEqual(vm.big_dot_ok[1], 0)

        # Scenario 2: Invariant abort (45°C -> 150W > 80W REJECT -> C1=50, C2=100, C3=1)
        vm.trigger_external(0, 45)
        self.assertEqual(vm.val_cur, [45, 50, 100, 1])
        self.assertEqual(vm.big_dot_ok[1], 1)

    def test_thermal_graph_lowering_executes_identically_on_reference_vm(self) -> None:
        prog = ka.parse_kpol_auth(THERMAL_GRAPH_SOURCE)
        artifact = ka.lower_kpol_auth(prog)

        self.assertEqual(len(artifact.concepts), 4)
        self.assertEqual(len(artifact.subscriptions), 4)
        self.assertTrue(len(artifact.code_o) > 0)

        # Every subscription line must terminate with KM_OPC_EXIT (0x5)
        for sub in artifact.subscriptions:
            last_word = artifact.code_o[sub.line_start_pc + sub.line_len - 1]
            self.assertEqual((last_word >> 28) & 0x0F, lowering_mod.KM_OPC_EXIT)

        self._run_thermal_verification(artifact)

    def test_bram_image_unpacking_matches_cme_raw_1_layout(self) -> None:
        prog = ka.parse_kpol_auth(THERMAL_GRAPH_SOURCE)
        artifact = ka.lower_kpol_auth(prog)

        self.assertEqual(len(artifact.bram_image), 1024)
        slots = [
            struct.unpack("<4I", artifact.bram_image[i * 16 : (i + 1) * 16])
            for i in range(64)
        ]

        # C0 (Temp): init=20, SUBSCRIBER_EN (0x10), W3=1
        self.assertEqual(slots[0][0], 20)
        self.assertEqual((slots[0][2] >> 8) & 0xFF, lowering_mod.CME_GUARD_SUBSCRIBER_EN)
        self.assertEqual(slots[0][3], 1)

        # C1 (Heater): init=10, INVARIANT_EN (0x02) | SUBSCRIBER_EN (0x10), W3=2
        self.assertEqual(slots[1][0], 10)
        self.assertEqual(
            (slots[1][2] >> 8) & 0xFF,
            lowering_mod.CME_GUARD_INVARIANT_EN | lowering_mod.CME_GUARD_SUBSCRIBER_EN,
        )
        self.assertEqual(slots[1][3], 2)

        # C2 (Fan), C3 (Alarm): leaf nodes, W3=0
        self.assertEqual(slots[2], (0, 0, 0, 0))
        self.assertEqual(slots[3], (0, 0, 0, 0))

        # Unused slots 4..63 must be zeroed
        for cid in range(4, 64):
            self.assertEqual(slots[cid], (0, 0, 0, 0))

    def test_fail_closed_negative_controls(self) -> None:
        # 1. Unresolved uncertainty in CST (record-diagnostic mode)
        cfg = ka.AuthFrontendConfig(policies={"KPOL-AUTH-U05": "record-diagnostic"})
        prog_u = ka.parse_kpol_auth("#legacy", config=cfg)
        with self.assertRaises(ka.KpolAuthLoweringError) as ctx_u:
            ka.lower_kpol_auth(prog_u)
        self.assertEqual(ctx_u.exception.code, "KPOL-LOWER-UNCERTAINTY")

        # 2. Out-of-subset construct (DefLayoutCST)
        prog_def = ka.parse_kpol_auth("Def(1, 0, 1, 0, 0, 0, 0)")
        with self.assertRaises(ka.KpolAuthLoweringError) as ctx_def:
            ka.lower_kpol_auth(prog_def)
        self.assertEqual(ctx_def.exception.code, "KPOL-LOWER-UNSUPPORTED-CST")

        # 3. BRAM acyclicity violation: dst_cid <= src_cid
        cycle_src = """
        Concept(A, 0)
        Concept(B, 0)
        B • Assign(A, B)
        """
        with self.assertRaises(ka.KpolAuthLoweringError) as ctx_cycle:
            ka.lower_kpol_auth(ka.parse_kpol_auth(cycle_src))
        self.assertEqual(ctx_cycle.exception.code, "KPOL-LOWER-CYCLE")

        # 4. BRAM fan-out > 1 on POST_CHANGE
        fanout_src = """
        Concept(A, 0)
        Concept(B, 0)
        Concept(C, 0)
        A • Assign(B, A)
        A • Assign(C, A)
        """
        with self.assertRaises(ka.KpolAuthLoweringError) as ctx_fanout:
            ka.lower_kpol_auth(ka.parse_kpol_auth(fanout_src))
        self.assertEqual(ctx_fanout.exception.code, "KPOL-LOWER-FANOUT")

    def test_self_loop_positive_and_negative_controls_direct_and_ast(self) -> None:
        # Positive direct control: acyclic edge C0 -> C1 in build_bram_routing_image
        c0 = ka.LoweredConcept(
            cid=0,
            name="C0",
            init_val=7,
            flags=0,
            lower_bound=None,
            upper_bound=None,
            first_sub_idx=0,
            sub_count=1,
        )
        c1 = ka.LoweredConcept(
            cid=1,
            name="C1",
            init_val=0,
            flags=0,
            lower_bound=None,
            upper_bound=None,
            first_sub_idx=0,
            sub_count=0,
        )
        acyclic_sub = ka.LoweredSubscription(
            sub_idx=0,
            owner_cid=0,
            target_cid=1,
            phase=lowering_mod.KM_PHASE_POST_CHANGE,
            trigger_mask=lowering_mod.KM_EV_CHANGED,
            line_start_pc=0,
            line_len=3,
        )
        abort_self_sub = ka.LoweredSubscription(
            sub_idx=1,
            owner_cid=0,
            target_cid=0,
            phase=lowering_mod.KM_PHASE_ON_ABORT,
            trigger_mask=lowering_mod.KM_EV_ALWAYS,
            line_start_pc=3,
            line_len=3,
        )
        ok_bram = ka.build_bram_routing_image((c0, c1), (acyclic_sub, abort_self_sub))
        self.assertEqual(len(ok_bram), 1024)
        slot0 = struct.unpack("<4I", ok_bram[0:16])
        slot1 = struct.unpack("<4I", ok_bram[16:32])
        self.assertEqual(slot0[0], 7)
        self.assertEqual((slot0[2] >> 8) & 0xFF, lowering_mod.CME_GUARD_SUBSCRIBER_EN)
        self.assertEqual(slot0[3], 1)
        self.assertEqual(slot1, (0, 0, 0, 0))

        # Positive AST control via lower_document: C0 -> C1
        acyclic_ast = ka.parse_kpol_auth(
            "Concept(C0, 1)\nConcept(C1, 0)\nC0 • Assign(C1, C0 + 1)"
        )
        acyclic_art = ka.lower_document(acyclic_ast)
        self.assertEqual(
            struct.unpack("<4I", acyclic_art.bram_image[0:16])[3],
            1,
        )

        # Negative direct control: self-loop dst_cid == src_cid in build_bram_routing_image
        for self_cid in (0, 1):
            self_sub = ka.LoweredSubscription(
                sub_idx=0,
                owner_cid=self_cid,
                target_cid=self_cid,
                phase=lowering_mod.KM_PHASE_POST_CHANGE,
                trigger_mask=lowering_mod.KM_EV_CHANGED,
                line_start_pc=0,
                line_len=3,
            )
            with self.subTest(direct_self_cid=self_cid):
                with self.assertRaises(ka.LoweringError) as ctx_direct:
                    ka.build_bram_routing_image((c0, c1), (self_sub,))
                self.assertEqual(ctx_direct.exception.code, "KPOL-LOWER-CYCLE")

        # Negative AST control via lower_document: concept subscribed to itself (C0 -> C0)
        self_loop_ast = ka.parse_kpol_auth(
            "Concept(C0, 1)\nC0 • Assign(C0, C0 + 1)"
        )
        with self.assertRaises(ka.LoweringError) as ctx_ast:
            ka.lower_document(self_loop_ast)
        self.assertEqual(ctx_ast.exception.code, "KPOL-LOWER-CYCLE")

    def test_mutant_controls_catch_opcode_exit_and_bram_cycle_defects(self) -> None:
        prog = ka.parse_kpol_auth(THERMAL_GRAPH_SOURCE)
        artifact = ka.lower_kpol_auth(prog)

        # Mutant 1: Corrupt Do/Go opcode (swap KM_DO_ADD -> KM_DO_SUB)
        corrupted_code = list(artifact.code_o)
        add_word = lowering_mod.km_pack_instr(lowering_mod.KM_OPC_DO, lowering_mod.KM_DO_ADD, 0, 0)
        sub_word = lowering_mod.km_pack_instr(lowering_mod.KM_OPC_DO, lowering_mod.KM_DO_SUB, 0, 0)
        idx = corrupted_code.index(add_word)
        corrupted_code[idx] = sub_word
        mutated_opcode_artifact = replace(artifact, code_o=tuple(corrupted_code))
        with self.assertRaises(AssertionError):
            self._run_thermal_verification(mutated_opcode_artifact)

        # Mutant 2: Omit KM_OPC_EXIT from first subscription line
        exit_word = lowering_mod.km_pack_instr(lowering_mod.KM_OPC_EXIT, 0, 0, 0)
        exit_idx = list(artifact.code_o).index(exit_word)
        no_exit_code = list(artifact.code_o)
        no_exit_code[exit_idx] = lowering_mod.km_pack_instr(lowering_mod.KM_OPC_NOP, 0, 0, 0)
        mutated_exit_artifact = replace(artifact, code_o=tuple(no_exit_code))
        with self.assertRaises(AssertionError):
            self._run_thermal_verification(mutated_exit_artifact)

        # Mutant M3a: Replace _validate_bram_acyclic with no-op; verify mutant lets 2-node
        # cycle A -> B -> A slip through while unmutated code raises KPOL-LOWER-CYCLE.
        two_node_cycle_ast = ka.parse_kpol_auth(
            """
            Concept(A, 0)
            Concept(B, 0)
            A • Assign(B, A)
            B • Assign(A, B)
            """
        )
        with mock.patch.object(
            lowering_mod, "_validate_bram_acyclic", lambda *a, **k: None
        ):
            mutant_m3a_artifact = ka.lower_document(two_node_cycle_ast)
            m3a_slot0 = struct.unpack("<4I", mutant_m3a_artifact.bram_image[0:16])
            m3a_slot1 = struct.unpack("<4I", mutant_m3a_artifact.bram_image[16:32])
            self.assertEqual(m3a_slot0[3], 1)
            self.assertEqual(m3a_slot1[3], 0)
            self.assertEqual(
                (m3a_slot1[2] >> 8) & 0xFF, lowering_mod.CME_GUARD_SUBSCRIBER_EN
            )

        with self.assertRaises(ka.LoweringError) as ctx_m3a_real:
            ka.lower_document(two_node_cycle_ast)
        self.assertEqual(ctx_m3a_real.exception.code, "KPOL-LOWER-CYCLE")

        # Mutant M3b: Defective validator checks only distinct 2-node cycles (u != v)
        # and ignores self-loop dst_cid == src_cid; verify mutant lets C0 -> C0 slip
        # through while unmutated code rejects it with KPOL-LOWER-CYCLE.
        def defective_two_node_only(edges):
            edge_set = set(edges)
            for u, v in edges:
                if u != v and (v, u) in edge_set:
                    raise ka.LoweringError("KPOL-LOWER-CYCLE", "2-node cycle only")

        self_loop_ast = ka.parse_kpol_auth(
            "Concept(C0, 1)\nC0 • Assign(C0, C0 + 1)"
        )
        with mock.patch.object(
            lowering_mod, "_validate_bram_acyclic", defective_two_node_only
        ):
            # Confirm defective mutant still catches A -> B -> A, proving only C0 -> C0 kills M3b
            with self.assertRaises(ka.LoweringError) as ctx_m3b_2node:
                ka.lower_document(two_node_cycle_ast)
            self.assertEqual(ctx_m3b_2node.exception.code, "KPOL-LOWER-CYCLE")

            mutant_m3b_artifact = ka.lower_document(self_loop_ast)
            m3b_slot0 = struct.unpack("<4I", mutant_m3b_artifact.bram_image[0:16])
            self.assertEqual(
                (m3b_slot0[2] >> 8) & 0xFF, lowering_mod.CME_GUARD_SUBSCRIBER_EN
            )
            self.assertEqual(m3b_slot0[3], 0)

        with self.assertRaises(ka.LoweringError) as ctx_m3b_real:
            ka.lower_document(self_loop_ast)
        self.assertEqual(ctx_m3b_real.exception.code, "KPOL-LOWER-CYCLE")

    def test_cli_check_emit_and_fail_closed_negative_controls(self) -> None:
        expected_artifact = ka.lower_document(THERMAL_GRAPH_SOURCE)
        env = os.environ.copy()
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{PACKAGE_DIR}{os.pathsep}{existing_pp}" if existing_pp else str(PACKAGE_DIR)
        )

        with _workspace_scratch_dir() as scratch:
            valid_src = scratch / "thermal.kpol"
            valid_src.write_text(THERMAL_GRAPH_SOURCE, encoding="utf-8")
            bram_out = scratch / "thermal.bram.bin"
            dogo_json = scratch / "thermal.dogo.json"
            dogo_bin = scratch / "thermal.dogo.bin"

            # 1. `PYTHONPATH=Engineering/sw/kpol-auth python3 -m kpol_auth`
            res_mod = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "kpol_auth",
                    str(valid_src),
                    "--check",
                    "--emit-bram",
                    str(bram_out),
                    "--emit-dogo",
                    str(dogo_json),
                ],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_mod.returncode, 0, msg=res_mod.stderr)
            self.assertIn("OK:", res_mod.stdout)
            self.assertEqual(bram_out.read_bytes(), expected_artifact.bram_image)
            parsed_json = json.loads(dogo_json.read_text(encoding="utf-8"))
            self.assertEqual(parsed_json["code_o"], list(expected_artifact.code_o))
            self.assertEqual(len(parsed_json["concepts"]), 4)
            self.assertEqual(len(parsed_json["subscriptions"]), 4)

            # 2. Direct execution `python3 Engineering/sw/kpol-auth` with binary Do/Go emission
            res_dir = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_DIR),
                    str(valid_src),
                    "--emit-dogo",
                    str(dogo_bin),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_dir.returncode, 0, msg=res_dir.stderr)
            expected_dogo_bytes = b"".join(
                struct.pack("<I", w) for w in expected_artifact.code_o
            )
            self.assertEqual(dogo_bin.read_bytes(), expected_dogo_bytes)

            # 3. Negative CLI controls: cyclic graph, self-loop, U04, and U12
            negative_cases = [
                (
                    "cycle_2node.kpol",
                    "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, A)\nB • Assign(A, B)\n",
                    "KPOL-LOWER-CYCLE",
                ),
                (
                    "cycle_self.kpol",
                    "Concept(C0, 1)\nC0 • Assign(C0, C0 + 1)\n",
                    "KPOL-LOWER-CYCLE",
                ),
                (
                    "uncertain_u04.kpol",
                    "Static(@runtime, OpenBracket, A, CloseBracket)\n",
                    "KPOL-AUTH-U04",
                ),
                (
                    "uncertain_u12.kpol",
                    "Property(DefBit=1, Value=_)\n",
                    "KPOL-AUTH-U12",
                ),
            ]
            for fname, bad_text, expected_code in negative_cases:
                with self.subTest(cli_negative=fname):
                    bad_file = scratch / fname
                    bad_file.write_text(bad_text, encoding="utf-8")
                    bad_bram = scratch / f"{fname}.bram.bin"
                    bad_dogo = scratch / f"{fname}.dogo.json"
                    res_bad = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "kpol_auth",
                            str(bad_file),
                            "--check",
                            "--emit-bram",
                            str(bad_bram),
                            "--emit-dogo",
                            str(bad_dogo),
                        ],
                        cwd=str(REPO_ROOT),
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertNotEqual(res_bad.returncode, 0)
                    self.assertIn(expected_code, res_bad.stderr)
                    self.assertFalse(bad_bram.exists())
                    self.assertFalse(bad_dogo.exists())


if __name__ == "__main__":
    unittest.main()
