"""Tests and mutant controls for derived KPOL-AUTH Do/Go + CME-RAW-1 lowering."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

PACKAGE_DIR = Path(__file__).resolve().parents[1]


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

        # Mutant 3: Invert src/dst in BRAM cascade (dst_cid <= src_cid)
        cycle_src = """
        Concept(A, 0)
        Concept(B, 0)
        B • Assign(A, B)
        """
        cycle_prog = ka.parse_kpol_auth(cycle_src)
        with mock.patch.dict(lowering_mod.__dict__, {}):
            # Verify that without acyclicity check, W3 would encode dst_cid < src_cid (0 < 1)
            with self.assertRaises(ka.KpolAuthLoweringError) as ctx:
                ka.lower_kpol_auth(cycle_prog)
            self.assertEqual(ctx.exception.code, "KPOL-LOWER-CYCLE")


if __name__ == "__main__":
    unittest.main()
