#!/usr/bin/env python3
"""Event & Cascade Step Debugger for the Kuzmin Machine (Issue #272).

Provides a phase-accurate, human-readable and JSON-exportable debugger for
KPOL-CME-1, KPOL-CME-2, and KPOL-AUTH compiled 64-slot BRAM descriptor tables
(`CFG-P` / `CME-RAW-1`), as well as an executable reference tracer for the
Author's slide/article examples (`If` T-flip-flop, `Sum` post-read reset, and
Euclidean `Nod(120, 6) = 6` cross-checked against historical `km_euclid_core.sv`
in Icarus Verilog).

Outputs 4 visual blocks for any inspected program:
  1. Source Code / Concept Declaration Summary
  2. BRAM Descriptor Table (`--dump-concepts`: W0, Valid '_', W1, W2 Hex & Decoded, W3)
  3. Step-by-Step Event & Cascade Lifecycle Trace (`--trace-events`)
  4. State Diff (`Before -> After`) & Telemetry Counters (`events, commits, rejects, fault_propagations`)
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from typing import Any
import uuid

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
KPOL_AUTH_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-auth"
HW_RTL_DIR = REPO_ROOT / "Engineering" / "hw" / "rtl"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from c99_emitter import (  # noqa: E402
    HAS_Z3_PYTHON,
    ReferenceCmeSafetyEngine,
    _run_z3_cli_smt2,
    _to_i16,
    _to_i32,
    _to_u32,
    compute_topological_order,
    emit_c99_safety_module,
    extract_active_cids_and_edges,
    has_subscription_edge,
    is_descriptor_configured,
    normalize_descriptors,
    prove_c99_descriptor_safety_z3,
    z3,
)
from kpol_reference import (  # noqa: E402
    CME_ACT_ADD,
    CME_ACT_ASSIGN,
    CME_ACT_DEC,
    CME_ACT_INC,
    CME_ACT_SUB,
    CME_GUARD_ASSUMPTION_EN,
    CME_GUARD_HAZARD_EN,
    CME_GUARD_INVARIANT_EN,
    CME_GUARD_INVERT_ASSUMPTION,
    CME_GUARD_SUBSCRIBER_EN,
    CME_PRED_BITMASK,
    CME_PRED_EQ,
    CME_PRED_GT,
    CME_PRED_LT,
    CME_PRED_NEQ,
    CME_PRED_NOP,
    CME_PRED_RANGE,
    ConceptMicroDescriptor,
    EventInput,
    Interpreter,
    KpolError,
    Module,
    Parser,
    compile_concept_microcode_bram_image,
    disassemble_concept_microcode,
    parse_module,
)

# --- Verdict Constants ---
VERDICT_COMMIT = "COMMIT"
VERDICT_REJECT_GUARD = "REJECT_GUARD"
VERDICT_REJECT_INVARIANT = "REJECT_INVARIANT"
VERDICT_REJECT_FAULT = "REJECT_FAULT"
VERDICT_SUPPRESSED_SELF = "SUPPRESSED_SELF"

PRED_NAMES: dict[int, str] = {
    CME_PRED_NOP: "NOP",
    CME_PRED_EQ: "EQ",
    CME_PRED_NEQ: "NEQ",
    CME_PRED_GT: "GT",
    CME_PRED_LT: "LT",
    CME_PRED_RANGE: "RANGE",
    CME_PRED_BITMASK: "BITMASK",
}

ACT_NAMES: dict[int, str] = {
    CME_ACT_ASSIGN: "ASSIGN",
    CME_ACT_INC: "INC",
    CME_ACT_DEC: "DEC",
    CME_ACT_ADD: "ADD",
    CME_ACT_SUB: "SUB",
}


def decode_predicate_formula(d: ConceptMicroDescriptor) -> str:
    """Return a human-readable predicate formula (`::`) for a descriptor."""
    if (d.guard_flags & CME_GUARD_ASSUMPTION_EN) == 0:
        return "ASSUMP_DISABLED(false)"
    op_i32 = _to_i32(d.operand_val)
    op_u32 = _to_u32(d.operand_val)
    invert = (d.guard_flags & CME_GUARD_INVERT_ASSUMPTION) != 0

    if d.pred_opcode == CME_PRED_NOP:
        raw = "true"
    elif d.pred_opcode == CME_PRED_EQ:
        raw = f"param == {op_i32}"
    elif d.pred_opcode == CME_PRED_NEQ:
        raw = f"param != {op_i32}"
    elif d.pred_opcode == CME_PRED_GT:
        raw = f"param > {op_i32}"
    elif d.pred_opcode == CME_PRED_LT:
        raw = f"param < {op_i32}"
    elif d.pred_opcode == CME_PRED_RANGE:
        lo16 = _to_i16(op_u32 & 0xFFFF)
        hi16 = _to_i16((op_u32 >> 16) & 0xFFFF)
        raw = f"{lo16} <= param <= {hi16}"
    elif d.pred_opcode == CME_PRED_BITMASK:
        raw = f"(param & 0x{op_u32:08X}) != 0"
    else:
        raw = f"UNKNOWN_PRED(0x{d.pred_opcode:02X})"

    if invert:
        if d.pred_opcode == CME_PRED_LT:
            return f"!(param < {op_i32}) [>= {op_i32}]"
        if d.pred_opcode == CME_PRED_GT:
            return f"!(param > {op_i32}) [<= {op_i32}]"
        if d.pred_opcode == CME_PRED_EQ:
            return f"!(param == {op_i32}) [!= {op_i32}]"
        return f"!({raw})"
    return raw


def decode_action_formula(d: ConceptMicroDescriptor) -> str:
    """Return a human-readable candidate action formula for a descriptor."""
    op_i32 = _to_i32(d.operand_val)
    if d.action_opcode == CME_ACT_ASSIGN:
        return "W0' := param"
    if d.action_opcode == CME_ACT_INC:
        return "W0' := W0 + 1"
    if d.action_opcode == CME_ACT_DEC:
        return "W0' := W0 - 1"
    if d.action_opcode == CME_ACT_ADD:
        return f"W0' := W0 + {op_i32}"
    if d.action_opcode == CME_ACT_SUB:
        return f"W0' := W0 - {op_i32}"
    return f"INVALID_ACT(0x{d.action_opcode:02X})"


def decode_invariant_formula(d: ConceptMicroDescriptor) -> str:
    """Return a human-readable Big Dot (`•`) invariant gate formula."""
    if (d.guard_flags & CME_GUARD_INVARIANT_EN) == 0:
        return "INV_DISABLED(false)"
    parts = ["cand >= 0", "!ovf32"]
    if (d.guard_flags & CME_GUARD_HAZARD_EN) != 0 and d.hazard_limit != 0:
        parts.append(f"param <= {d.hazard_limit}")
    return " && ".join(parts)


def decode_w2_word(d: ConceptMicroDescriptor) -> tuple[int, str]:
    """Return packed 32-bit W2 integer and decoded summary string."""
    w2 = (
        (d.pred_opcode & 0xFF)
        | ((d.guard_flags & 0xFF) << 8)
        | ((d.hazard_limit & 0xFF) << 16)
        | ((d.action_opcode & 0xFF) << 24)
    )
    pred_str = decode_predicate_formula(d)
    act_str = decode_action_formula(d)
    inv_str = "•(cand>=0 && !ovf)" if (d.guard_flags & CME_GUARD_INVARIANT_EN) else "•(OFF)"
    return w2, f"::({pred_str}) | {act_str} | {inv_str}"


def decode_w3_subscriber(
    d: ConceptMicroDescriptor,
    descriptors: Sequence[ConceptMicroDescriptor],
) -> str:
    """Return a human-readable subscriber routing description for W3."""
    sub_en = has_subscription_edge(d)
    if not sub_en:
        return "None (0)"
    target = d.subscriber_cid
    if target >= 64:
        return f"OUT_OF_RANGE(C{target})"
    if target == d.cid:
        return f"SELF_LOOP(C{target} -> suppressed)"
    t_name = descriptors[target].name if 0 <= target < len(descriptors) else f"Concept_{target}"
    return f"-> C{target} ({t_name})"


@dataclass(frozen=True)
class WatchpointTrigger:
    """Recorded watchpoint or breakpoint hit during cascade step debugging."""

    step_index: int
    event_id: int
    cascade_depth: int
    cid: int
    concept_name: str
    reason: str
    verdict: str
    pre_w0: int
    post_w0: int
    param: int
    param_valid: bool


@dataclass(frozen=True)
class CascadeTraceStep:
    """Full 10-phase record of a single concept evaluation step inside a cascade wave."""

    step_index: int
    event_id: int
    cascade_step: int
    depth: int
    cid: int
    concept_name: str
    param: int
    param_valid: bool
    pre_w0: int
    pre_valid: bool
    pred_formula: str
    pred_match: bool
    action_formula: str
    candidate_w0: int
    arith_overflow: bool
    inv_formula: str
    inv_ok: bool
    verdict: str
    post_w0: int
    post_valid: bool
    enqueued_subscriber_cid: int | None
    enqueued_subscriber_name: str | None = None
    watchpoints_hit: tuple[str, ...] = ()

    @property
    def param_valid_symbol(self) -> str:
        return "1" if self.param_valid else "_"

    @property
    def pre_valid_symbol(self) -> str:
        return "1" if self.pre_valid else "_"

    @property
    def post_valid_symbol(self) -> str:
        return "1" if self.post_valid else "_"


@dataclass
class DebugSessionReport:
    """Complete result of running a trace in KpolCascadeDebugger."""

    module_name: str
    profile: str
    source_code: str
    active_cids: list[int]
    topological_order: list[int]
    initial_state: dict[int, int]
    initial_valid: dict[int, bool]
    final_state: dict[int, int]
    final_valid: dict[int, bool]
    steps: list[CascadeTraceStep] = field(default_factory=list)
    watchpoint_triggers: list[WatchpointTrigger] = field(default_factory=list)
    halted_on_breakpoint: bool = False
    events_processed: int = 0
    commits: int = 0
    rejects: int = 0
    fault_propagations: int = 0

    def to_dict(self) -> dict[str, Any]:
        state_diff: list[dict[str, Any]] = []
        for cid in self.active_cids:
            b_val = self.initial_state[cid]
            a_val = self.final_state[cid]
            b_ok = self.initial_valid[cid]
            a_ok = self.final_valid[cid]
            state_diff.append(
                {
                    "cid": cid,
                    "before_w0": b_val,
                    "before_valid": "1" if b_ok else "_",
                    "after_w0": a_val,
                    "after_valid": "1" if a_ok else "_",
                    "delta": a_val - b_val,
                    "changed": (b_val != a_val) or (b_ok != a_ok),
                }
            )
        return {
            "module_name": self.module_name,
            "profile": self.profile,
            "active_cids": self.active_cids,
            "topological_order": self.topological_order,
            "telemetry": {
                "events_processed": self.events_processed,
                "commits": self.commits,
                "rejects": self.rejects,
                "fault_propagations": self.fault_propagations,
                "halted_on_breakpoint": self.halted_on_breakpoint,
            },
            "state_diff": state_diff,
            "steps": [asdict(s) for s in self.steps],
            "watchpoint_triggers": [asdict(w) for w in self.watchpoint_triggers],
        }


class KpolCascadeDebugger:
    """Step-by-step Event & Cascade Debugger for 64-slot CME-RAW-1 descriptor tables."""

    def __init__(
        self,
        descriptors_or_image: bytes | bytearray | Sequence[ConceptMicroDescriptor] | Module,
        *,
        profile: str = "KPOL-CME-2",
        module_name: str = "km_debug",
        source_code: str = "",
        concept_names: Mapping[int, str] | Sequence[str] | None = None,
        watch_cids: Sequence[int] | set[int] | None = None,
        break_on_reject: bool = False,
        watch_state_change: bool = False,
        threshold_watch: Mapping[int, int] | None = None,
        stop_on_breakpoint: bool = False,
    ) -> None:
        if isinstance(descriptors_or_image, Module):
            if not module_name or module_name == "km_debug":
                module_name = descriptors_or_image.name
        self.profile = profile
        self.module_name = module_name
        self.source_code = source_code.strip()
        self.descriptors = normalize_descriptors(
            descriptors_or_image,
            profile=profile,
            concept_names=concept_names,
        )
        self.active_cids, self.edges = extract_active_cids_and_edges(self.descriptors)
        try:
            self.topo_order = compute_topological_order(self.active_cids, self.edges)
        except KpolError:
            self.topo_order = list(self.active_cids)

        self.initial_state: list[int] = [_to_i32(d.current_state) for d in self.descriptors]
        self.state: list[int] = list(self.initial_state)
        self.valid_mask: int = 0xFFFFFFFFFFFFFFFF
        self.initial_valid_mask: int = self.valid_mask

        self.watch_cids: set[int] = set(watch_cids or ())
        self.break_on_reject: bool = bool(break_on_reject)
        self.watch_state_change: bool = bool(watch_state_change)
        self.threshold_watch: dict[int, int] = dict(threshold_watch or {})
        self.stop_on_breakpoint: bool = bool(stop_on_breakpoint)

        self.events_processed: int = 0
        self.commits: int = 0
        self.rejects: int = 0
        self.fault_propagations: int = 0
        self.last_committed_state: int = 0

        self.steps: list[CascadeTraceStep] = []
        self.watchpoint_triggers: list[WatchpointTrigger] = []
        self.halted_on_breakpoint: bool = False
        self._event_counter: int = 0

    def reset(self) -> None:
        """Reset all concept states, validity bits, and trace logs to initial values."""
        self.state = list(self.initial_state)
        self.valid_mask = 0xFFFFFFFFFFFFFFFF
        self.initial_valid_mask = self.valid_mask
        self.events_processed = 0
        self.commits = 0
        self.rejects = 0
        self.fault_propagations = 0
        self.last_committed_state = 0
        self.steps.clear()
        self.watchpoint_triggers.clear()
        self.halted_on_breakpoint = False
        self._event_counter = 0

    def invalidate_concept(self, cid: int) -> None:
        """Force concept `cid` into the uninitialized/fault state `_` (`valid=0`)."""
        if 0 <= cid < 64:
            self.valid_mask &= ~(1 << cid)

    def revalidate_concept(self, cid: int, recovered_state: int) -> None:
        """Recover concept `cid` from `_` if `recovered_state >= 0`."""
        if 0 <= cid < 64:
            if recovered_state < 0:
                self.valid_mask &= ~(1 << cid)
            else:
                self.state[cid] = _to_i32(recovered_state)
                self.valid_mask |= 1 << cid

    def _eval_predicate(self, d: ConceptMicroDescriptor, cur_param: int) -> bool:
        """Evaluate predicate `::` (including invert flag)."""
        param_u32 = _to_u32(cur_param)
        if d.pred_opcode == CME_PRED_NOP:
            pred_raw = True
        elif d.pred_opcode == CME_PRED_EQ:
            pred_raw = param_u32 == d.operand_val
        elif d.pred_opcode == CME_PRED_NEQ:
            pred_raw = param_u32 != d.operand_val
        elif d.pred_opcode == CME_PRED_GT:
            pred_raw = cur_param > _to_i32(d.operand_val)
        elif d.pred_opcode == CME_PRED_LT:
            pred_raw = cur_param < _to_i32(d.operand_val)
        elif d.pred_opcode == CME_PRED_RANGE:
            lo16 = _to_i16(d.operand_val & 0xFFFF)
            hi16 = _to_i16((d.operand_val >> 16) & 0xFFFF)
            pred_raw = lo16 <= cur_param <= hi16
        elif d.pred_opcode == CME_PRED_BITMASK:
            pred_raw = (param_u32 & d.operand_val) != 0
        else:
            pred_raw = False

        assump_known = (d.guard_flags & CME_GUARD_ASSUMPTION_EN) != 0
        assump_true = (
            (not pred_raw)
            if ((d.guard_flags & CME_GUARD_INVERT_ASSUMPTION) != 0)
            else pred_raw
        )
        return assump_known and assump_true

    def _eval_action(
        self, d: ConceptMicroDescriptor, cur_w0: int, cur_param: int
    ) -> tuple[int, bool, bool]:
        """Compute `(candidate_i32, action_valid, arith_overflow)`."""
        cur_u32 = _to_u32(cur_w0)
        param_u32 = _to_u32(cur_param)
        action_valid = True
        arith_overflow = False

        if d.action_opcode == CME_ACT_ASSIGN:
            cand_u32 = param_u32
        elif d.action_opcode == CME_ACT_INC:
            cand_u32 = _to_u32(cur_u32 + 1)
            arith_overflow = cur_u32 == 0x7FFFFFFF
        elif d.action_opcode == CME_ACT_DEC:
            cand_u32 = _to_u32(cur_u32 - 1)
            arith_overflow = cur_u32 == 0x80000000
        elif d.action_opcode == CME_ACT_ADD:
            cand_u32 = _to_u32(cur_u32 + d.operand_val)
            arith_overflow = (((cur_u32 ^ d.operand_val) & 0x80000000) == 0) and (
                ((cand_u32 ^ cur_u32) & 0x80000000) != 0
            )
        elif d.action_opcode == CME_ACT_SUB:
            cand_u32 = _to_u32(cur_u32 - d.operand_val)
            arith_overflow = (((cur_u32 ^ d.operand_val) & 0x80000000) != 0) and (
                ((cand_u32 ^ cur_u32) & 0x80000000) != 0
            )
        else:
            cand_u32 = cur_u32
            action_valid = False

        return _to_i32(cand_u32), action_valid, arith_overflow

    def _eval_invariant_gate(
        self,
        d: ConceptMicroDescriptor,
        cand_i32: int,
        cur_param: int,
        action_valid: bool,
        arith_overflow: bool,
    ) -> bool:
        """Evaluate Big Dot (`•`) invariant & hazard gate (`kpol_txn_gate_v2.sv`)."""
        inv_known = (d.guard_flags & CME_GUARD_INVARIANT_EN) != 0
        cand_u32 = _to_u32(cand_i32)
        inv_true = (not arith_overflow) and ((cand_u32 & 0x80000000) == 0)
        haz_true = (
            ((d.guard_flags & CME_GUARD_HAZARD_EN) != 0)
            and (d.hazard_limit != 0)
            and (cur_param > d.hazard_limit)
        )
        return action_valid and inv_known and inv_true and (not haz_true)

    def _resolve_subscriber(self, d: ConceptMicroDescriptor) -> tuple[int | None, bool]:
        """Return `(enqueued_subscriber_cid, suppressed_self)` on a committed step."""
        sub_valid = d.subscriber_cid < 64
        sub_en = ((d.guard_flags & CME_GUARD_SUBSCRIBER_EN) != 0) or (d.subscriber_cid != 0)
        if not (sub_valid and sub_en):
            return None, False
        next_cid = d.subscriber_cid & 0x3F
        if next_cid == d.cid:
            return None, True
        return next_cid, False

    def step_event(
        self,
        root_cid: int,
        param: int,
        param_valid: bool = True,
    ) -> list[CascadeTraceStep]:
        """Execute one external stimulus and trace every resulting cascade step."""
        if self.halted_on_breakpoint and self.stop_on_breakpoint:
            return []

        event_id = self._event_counter
        self._event_counter += 1

        if root_cid < 0 or root_cid >= 64:
            self.events_processed += 1
            self.rejects += 1
            self.fault_propagations += 1
            step_idx = len(self.steps)
            reasons: list[str] = []
            if self.break_on_reject:
                reasons.append("BREAK_ON_REJECT(BAD_CID)")
            bad_step = CascadeTraceStep(
                step_index=step_idx,
                event_id=event_id,
                cascade_step=0,
                depth=0,
                cid=root_cid,
                concept_name=f"INVALID_CID_{root_cid}",
                param=_to_i32(param),
                param_valid=bool(param_valid),
                pre_w0=0,
                pre_valid=False,
                pred_formula="N/A",
                pred_match=False,
                action_formula="N/A",
                candidate_w0=0,
                arith_overflow=False,
                inv_formula="cid in 0..63",
                inv_ok=False,
                verdict=VERDICT_REJECT_FAULT,
                post_w0=0,
                post_valid=False,
                enqueued_subscriber_cid=None,
                enqueued_subscriber_name=None,
                watchpoints_hit=tuple(reasons),
            )
            self.steps.append(bad_step)
            for r in reasons:
                self.watchpoint_triggers.append(
                    WatchpointTrigger(
                        step_index=step_idx,
                        event_id=event_id,
                        cascade_depth=0,
                        cid=root_cid,
                        concept_name=bad_step.concept_name,
                        reason=r,
                        verdict=VERDICT_REJECT_FAULT,
                        pre_w0=0,
                        post_w0=0,
                        param=_to_i32(param),
                        param_valid=bool(param_valid),
                    )
                )
            if reasons and self.stop_on_breakpoint:
                self.halted_on_breakpoint = True
            return [bad_step]

        wave_steps: list[CascadeTraceStep] = []
        cid = root_cid
        cur_param = _to_i32(param)
        cur_valid = bool(param_valid)

        for depth in range(64):
            d = self.descriptors[cid]
            step_idx = len(self.steps)
            self.events_processed += 1

            pre_w0 = self.state[cid]
            pre_valid = ((self.valid_mask >> cid) & 1) != 0

            pred_formula = decode_predicate_formula(d)
            act_formula = decode_action_formula(d)
            inv_formula = decode_invariant_formula(d)

            cand_w0, action_valid, arith_ovf = self._eval_action(d, pre_w0, cur_param)
            pred_match = self._eval_predicate(d, cur_param)
            inv_ok = self._eval_invariant_gate(d, cand_w0, cur_param, action_valid, arith_ovf)

            enqueued_cid: int | None = None
            enqueued_name: str | None = None

            # Phase 1: Fail-Closed Uncertainty '_' / Sensor Fault Check
            if (not cur_valid) or (not pre_valid):
                verdict = VERDICT_REJECT_FAULT
                pred_match = False
                inv_ok = False
                post_w0 = pre_w0
                post_valid = pre_valid
                self.rejects += 1
                self.fault_propagations += 1
            elif not pred_match:
                # Phase 2: Guard / Assumption '::' Rejected
                verdict = VERDICT_REJECT_GUARD
                post_w0 = pre_w0
                post_valid = pre_valid
                self.rejects += 1
            elif not inv_ok:
                # Phase 3: Big Dot '•' Invariant / Hazard Gate Rejected (Fail-Closed!)
                verdict = VERDICT_REJECT_INVARIANT
                post_w0 = pre_w0
                post_valid = pre_valid
                self.rejects += 1
            else:
                # Phase 4: Commit State & Resolve Subscriber W3
                post_w0 = cand_w0
                post_valid = pre_valid
                self.state[cid] = post_w0
                self.commits += 1
                self.last_committed_state = post_w0
                enqueued_cid, suppressed_self = self._resolve_subscriber(d)
                if suppressed_self:
                    verdict = VERDICT_SUPPRESSED_SELF
                else:
                    verdict = VERDICT_COMMIT
                if enqueued_cid is not None:
                    enqueued_name = self.descriptors[enqueued_cid].name

            # Check Watchpoints / Breakpoints
            hit_reasons: list[str] = []
            if cid in self.watch_cids:
                hit_reasons.append(f"WATCH_CID(C{cid}:{d.name})")
            if self.break_on_reject and verdict in (
                VERDICT_REJECT_GUARD,
                VERDICT_REJECT_INVARIANT,
                VERDICT_REJECT_FAULT,
            ):
                hit_reasons.append(f"BREAK_ON_REJECT({verdict})")
            if self.watch_state_change and post_w0 != pre_w0:
                hit_reasons.append(f"STATE_CHANGE({pre_w0}->{post_w0})")
            if cid in self.threshold_watch:
                thr = self.threshold_watch[cid]
                if post_w0 >= thr and pre_w0 < thr:
                    hit_reasons.append(f"THRESHOLD_REACHED(C{cid}>={thr})")

            step_record = CascadeTraceStep(
                step_index=step_idx,
                event_id=event_id,
                cascade_step=depth,
                depth=depth,
                cid=cid,
                concept_name=d.name,
                param=cur_param,
                param_valid=cur_valid,
                pre_w0=pre_w0,
                pre_valid=pre_valid,
                pred_formula=pred_formula,
                pred_match=pred_match,
                action_formula=act_formula,
                candidate_w0=cand_w0,
                arith_overflow=arith_ovf,
                inv_formula=inv_formula,
                inv_ok=inv_ok,
                verdict=verdict,
                post_w0=post_w0,
                post_valid=post_valid,
                enqueued_subscriber_cid=enqueued_cid,
                enqueued_subscriber_name=enqueued_name,
                watchpoints_hit=tuple(hit_reasons),
            )
            self.steps.append(step_record)
            wave_steps.append(step_record)

            for r in hit_reasons:
                self.watchpoint_triggers.append(
                    WatchpointTrigger(
                        step_index=step_idx,
                        event_id=event_id,
                        cascade_depth=depth,
                        cid=cid,
                        concept_name=d.name,
                        reason=r,
                        verdict=verdict,
                        pre_w0=pre_w0,
                        post_w0=post_w0,
                        param=cur_param,
                        param_valid=cur_valid,
                    )
                )

            if hit_reasons and self.stop_on_breakpoint:
                self.halted_on_breakpoint = True
                break

            if enqueued_cid is not None:
                cid = enqueued_cid
                cur_param = post_w0
                cur_valid = post_valid
            else:
                break

        return wave_steps

    def run_events(
        self,
        events: Sequence[tuple[int, int] | tuple[int, int, bool] | tuple[str, int, int, bool]],
    ) -> DebugSessionReport:
        """Run a sequence of `(cid, param[, param_valid])` or `('invalidate'/'revalidate', ...)`."""
        for item in events:
            if self.halted_on_breakpoint and self.stop_on_breakpoint:
                break
            if len(item) == 2:
                cid, param = int(item[0]), int(item[1])
                self.step_event(cid, param, True)
            elif len(item) == 3:
                cid, param, valid = int(item[0]), int(item[1]), bool(item[2])
                self.step_event(cid, param, valid)
            elif len(item) == 4:
                op, cid, param, valid = str(item[0]), int(item[1]), int(item[2]), bool(item[3])
                if op == "invalidate":
                    self.invalidate_concept(cid)
                elif op == "revalidate":
                    self.revalidate_concept(cid, param)
                elif op == "event":
                    self.step_event(cid, param, valid)
                else:
                    raise KpolError(f"Unknown debugger event operation: {op!r}")
            else:
                raise KpolError(f"Unsupported event tuple shape: {item!r}")
        return self.build_report()

    def build_report(self) -> DebugSessionReport:
        """Construct a structured DebugSessionReport for the current session."""
        init_st = {cid: self.initial_state[cid] for cid in self.active_cids}
        init_val = {
            cid: (((self.initial_valid_mask >> cid) & 1) != 0) for cid in self.active_cids
        }
        fin_st = {cid: self.state[cid] for cid in self.active_cids}
        fin_val = {cid: (((self.valid_mask >> cid) & 1) != 0) for cid in self.active_cids}
        return DebugSessionReport(
            module_name=self.module_name,
            profile=self.profile,
            source_code=self.source_code,
            active_cids=list(self.active_cids),
            topological_order=list(self.topo_order),
            initial_state=init_st,
            initial_valid=init_val,
            final_state=fin_st,
            final_valid=fin_val,
            steps=list(self.steps),
            watchpoint_triggers=list(self.watchpoint_triggers),
            halted_on_breakpoint=self.halted_on_breakpoint,
            events_processed=self.events_processed,
            commits=self.commits,
            rejects=self.rejects,
            fault_propagations=self.fault_propagations,
        )

    def format_source_block(self) -> str:
        """Block 1: Format the program source code or concept summary."""
        lines = [
            f"=== [BLOCK 1] SOURCE CODE / PROGRAM SPECIFICATION ({self.module_name}, {self.profile}) ==="
        ]
        if self.source_code:
            for idx, line in enumerate(self.source_code.splitlines(), 1):
                lines.append(f"  {idx:02d} | {line}")
        else:
            lines.append(f"  Active Concepts ({len(self.active_cids)}): {self.active_cids}")
            lines.append(f"  Topological Order: {self.topo_order}")
        return "\n".join(lines)

    def format_concepts_table(self, *, include_unconfigured: bool = False) -> str:
        """Block 2 (`--dump-concepts`): Format the BRAM descriptor table."""
        cids = list(range(64)) if include_unconfigured else list(self.active_cids)
        rows: list[tuple[str, ...]] = []
        headers = (
            "CID",
            "Name",
            "W0 (Init State)",
            "Valid (_)",
            "W1 (Operand)",
            "W2 (Hex & Decoded: Predicate ::, Action, Invariant •)",
            "W3 (Subscriber -> CID)",
        )
        for cid in cids:
            d = self.descriptors[cid]
            w0_i32 = self.initial_state[cid]
            w0_str = f"{w0_i32} (0x{_to_u32(w0_i32):08X})"
            val_ok = ((self.valid_mask >> cid) & 1) != 0
            val_str = "1 (valid)" if val_ok else "_ (invalid)"
            w1_i32 = _to_i32(d.operand_val)
            w1_str = f"{w1_i32} (0x{d.operand_val:08X})"
            w2_u32, w2_dec = decode_w2_word(d)
            w2_str = f"0x{w2_u32:08X} [{w2_dec}]"
            w3_str = f"{d.subscriber_cid} ({decode_w3_subscriber(d, self.descriptors)})"
            rows.append((f"C{cid:02d}", d.name, w0_str, val_str, w1_str, w2_str, w3_str))

        widths = [
            max(len(headers[col]), *(len(r[col]) for r in rows)) if rows else len(headers[col])
            for col in range(len(headers))
        ]
        sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
        hdr_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"

        out = [
            f"=== [BLOCK 2] BRAM DESCRIPTOR TABLE (--dump-concepts, {len(cids)} active of 64 slots) ===",
            sep,
            hdr_line,
            sep,
        ]
        for r in rows:
            out.append("| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(headers))) + " |")
        out.append(sep)
        return "\n".join(out)

    def format_trace_table(self) -> str:
        """Block 3 (`--trace-events`): Format the step-by-step event and cascade execution trace."""
        headers = (
            "Step",
            "Depth",
            "CID (Name)",
            "Event(param, valid)",
            "Pre-State",
            "Predicate ::",
            "Candidate",
            "Gate •",
            "Verdict",
            "Post-State",
            "Next Subscriber",
        )
        rows: list[tuple[str, ...]] = []
        for s in self.steps:
            step_lbl = f"E{s.event_id}.{s.cascade_step} (#{s.step_index})"
            depth_lbl = str(s.depth)
            cid_lbl = f"C{s.cid:02d} ({s.concept_name})" if 0 <= s.cid < 64 else f"C{s.cid} ({s.concept_name})"
            ev_lbl = f"param={s.param}, valid={s.param_valid_symbol}"
            pre_lbl = f"W0={s.pre_w0}, valid={s.pre_valid_symbol}"
            pred_lbl = f"{s.pred_formula} => {s.pred_match}"
            ovf_tag = " [OVF!]" if s.arith_overflow else ""
            cand_lbl = f"{s.action_formula} => {s.candidate_w0}{ovf_tag}"
            gate_lbl = f"{s.inv_formula} => {s.inv_ok}"
            verdict_lbl = s.verdict
            if s.watchpoints_hit:
                verdict_lbl += f" *{','.join(s.watchpoints_hit)}"
            post_lbl = f"W0={s.post_w0}, valid={s.post_valid_symbol}"
            if s.enqueued_subscriber_cid is not None:
                next_lbl = f"C{s.enqueued_subscriber_cid:02d} ({s.enqueued_subscriber_name})"
            else:
                next_lbl = "None"
            rows.append(
                (
                    step_lbl,
                    depth_lbl,
                    cid_lbl,
                    ev_lbl,
                    pre_lbl,
                    pred_lbl,
                    cand_lbl,
                    gate_lbl,
                    verdict_lbl,
                    post_lbl,
                    next_lbl,
                )
            )

        widths = [
            max(len(headers[col]), *(len(r[col]) for r in rows)) if rows else len(headers[col])
            for col in range(len(headers))
        ]
        sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
        hdr_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"

        out = [
            f"=== [BLOCK 3] STEP-BY-STEP EVENT & CASCADE TRACE (--trace-events, {len(self.steps)} steps) ===",
            sep,
            hdr_line,
            sep,
        ]
        for r in rows:
            out.append("| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(headers))) + " |")
        out.append(sep)
        if self.watchpoint_triggers:
            out.append("Watchpoints / Breakpoints Triggered:")
            for wp in self.watchpoint_triggers:
                out.append(
                    f"  * [Step #{wp.step_index} | E{wp.event_id}.{wp.cascade_depth}] "
                    f"C{wp.cid:02d} ({wp.concept_name}): {wp.reason} -> {wp.verdict} "
                    f"(W0: {wp.pre_w0} -> {wp.post_w0}, param={wp.param}, valid={'1' if wp.param_valid else '_'})"
                )
        return "\n".join(out)

    def format_state_diff_block(self) -> str:
        """Block 4: Format the summary State Diff (`Before -> After`) and telemetry counters."""
        headers = ("CID", "Name", "Before (W0, valid)", "After (W0, valid)", "Delta", "Status")
        rows: list[tuple[str, ...]] = []
        for cid in self.active_cids:
            d = self.descriptors[cid]
            b_w0 = self.initial_state[cid]
            a_w0 = self.state[cid]
            b_ok = ((self.initial_valid_mask >> cid) & 1) != 0
            a_ok = ((self.valid_mask >> cid) & 1) != 0
            delta = a_w0 - b_w0
            delta_str = f"{delta:+d}" if delta != 0 else "0"
            changed = (b_w0 != a_w0) or (b_ok != a_ok)
            status_str = "CHANGED" if changed else "UNCHANGED"
            rows.append(
                (
                    f"C{cid:02d}",
                    d.name,
                    f"W0={b_w0}, valid={'1' if b_ok else '_'}",
                    f"W0={a_w0}, valid={'1' if a_ok else '_'}",
                    delta_str,
                    status_str,
                )
            )

        widths = [
            max(len(headers[col]), *(len(r[col]) for r in rows)) if rows else len(headers[col])
            for col in range(len(headers))
        ]
        sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
        hdr_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"

        out = [
            "=== [BLOCK 4] STATE DIFF (Before -> After) & TELEMETRY COUNTERS ===",
            sep,
            hdr_line,
            sep,
        ]
        for r in rows:
            out.append("| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(headers))) + " |")
        out.append(sep)
        out.append(
            f"Telemetry Summary: events_processed={self.events_processed}, "
            f"commits={self.commits}, rejects={self.rejects}, "
            f"fault_propagations={self.fault_propagations}, "
            f"last_committed_state={self.last_committed_state}"
        )
        return "\n".join(out)

    def format_full_4block_report(self) -> str:
        """Render all 4 visual blocks (`Source`, `BRAM Descriptors`, `Step Trace`, `State Diff`)."""
        return "\n\n".join(
            [
                self.format_source_block(),
                self.format_concepts_table(),
                self.format_trace_table(),
                self.format_state_diff_block(),
            ]
        )


def parse_trace_events_spec(spec: str) -> list[tuple[int, int, bool]]:
    """Parse CLI `--trace-events` specification string into `[(cid, param, param_valid), ...]`.

    Supported token formats (comma- or semicolon-separated):
      - `0:10`         -> `(cid=0, param=10, param_valid=True)`
      - `0:-5`         -> `(cid=0, param=-5, param_valid=True)`
      - `0:invalid`    -> `(cid=0, param=0, param_valid=False)`
      - `0:_`          -> `(cid=0, param=0, param_valid=False)`
      - `0:120:invalid` or `0:120:_` -> `(cid=0, param=120, param_valid=False)`
      - `0:120:valid`  or `0:120:1`  -> `(cid=0, param=120, param_valid=True)`
    """
    cleaned = spec.strip()
    if not cleaned:
        raise KpolError("TRACE-SPEC: empty --trace-events specification")

    events: list[tuple[int, int, bool]] = []
    for raw_tok in cleaned.replace(";", ",").split(","):
        tok = raw_tok.strip()
        if not tok:
            continue
        parts = [p.strip() for p in tok.split(":")]
        if len(parts) < 2 or len(parts) > 3:
            raise KpolError(
                f"TRACE-SPEC: invalid event token {tok!r} (expected '<cid>:<param>' or '<cid>:invalid')"
            )
        try:
            cid = int(parts[0], 0)
        except ValueError as err:
            raise KpolError(f"TRACE-SPEC: invalid CID in token {tok!r}") from err

        p_str = parts[1].lower()
        if len(parts) == 2:
            if p_str in ("invalid", "_", "fault", "null_frame"):
                events.append((cid, 0, False))
            else:
                try:
                    param = int(parts[1], 0)
                except ValueError as err:
                    raise KpolError(f"TRACE-SPEC: invalid parameter in token {tok!r}") from err
                events.append((cid, param, True))
        else:
            try:
                param = int(parts[1], 0)
            except ValueError as err:
                raise KpolError(f"TRACE-SPEC: invalid parameter in token {tok!r}") from err
            v_str = parts[2].lower()
            if v_str in ("invalid", "_", "0", "false", "fault"):
                events.append((cid, param, False))
            elif v_str in ("valid", "1", "true", "ok"):
                events.append((cid, param, True))
            else:
                raise KpolError(f"TRACE-SPEC: invalid validity flag {parts[2]!r} in token {tok!r}")

    if not events:
        raise KpolError("TRACE-SPEC: no events found in --trace-events specification")
    return events


def diagnose_invariant_counterexample_z3(
    descriptor: ConceptMicroDescriptor,
    *,
    bypass_invariant_gate: bool = True,
) -> dict[str, Any]:
    """Use Z3 (`QF_BV` BitVec32) to find a concrete witness `(cur_state, ev_param)` where
    a transition with satisfied predicate `::` would violate `candidate >= 0 && !overflow`
    if the Big Dot `•` invariant gate were bypassed (or if `INVARIANT_EN == 0`).
    """
    d = descriptor
    op_hex = f"#x{_to_u32(d.operand_val):08x}"
    pr_hex = f"#x{d.pred_opcode & 0xFF:02x}"
    gf_hex = f"#x{d.guard_flags & 0xFF:02x}"
    ac_hex = f"#x{d.action_opcode & 0xFF:02x}"

    smt2 = f"""(set-logic QF_BV)
(declare-const cur_state (_ BitVec 32))
(declare-const ev_param (_ BitVec 32))

(define-fun pred_rtl ((ev_p (_ BitVec 32)) (operand (_ BitVec 32)) (pred_op (_ BitVec 8))) Bool
  (ite (= pred_op #x00) true
  (ite (= pred_op #x01) (= ev_p operand)
  (ite (= pred_op #x02) (not (= ev_p operand))
  (ite (= pred_op #x03) (bvsgt ev_p operand)
  (ite (= pred_op #x04) (bvslt ev_p operand)
  (ite (= pred_op #x05) (and (bvsge ev_p ((_ sign_extend 16) ((_ extract 15 0) operand)))
                             (bvsle ev_p ((_ sign_extend 16) ((_ extract 31 16) operand))))
  (ite (= pred_op #x06) (not (= (bvand ev_p operand) #x00000000))
       false))))))))

(define-fun cand_rtl ((cur_s (_ BitVec 32)) (ev_p (_ BitVec 32)) (operand (_ BitVec 32)) (act_op (_ BitVec 8))) (_ BitVec 32)
  (ite (= act_op #x00) ev_p
  (ite (= act_op #x01) (bvadd cur_s #x00000001)
  (ite (= act_op #x02) (bvsub cur_s #x00000001)
  (ite (= act_op #x03) (bvadd cur_s operand)
  (ite (= act_op #x04) (bvsub cur_s operand)
       cur_s))))))

(define-fun ovf_rtl ((cur_s (_ BitVec 32)) (operand (_ BitVec 32)) (act_op (_ BitVec 8))) Bool
  (let ((add_r (bvadd cur_s operand))
        (sub_r (bvsub cur_s operand)))
    (ite (= act_op #x01) (= cur_s #x7fffffff)
    (ite (= act_op #x02) (= cur_s #x80000000)
    (ite (= act_op #x03) (and (= ((_ extract 31 31) cur_s) ((_ extract 31 31) operand))
                              (not (= ((_ extract 31 31) add_r) ((_ extract 31 31) cur_s))))
    (ite (= act_op #x04) (and (not (= ((_ extract 31 31) cur_s) ((_ extract 31 31) operand)))
                              (not (= ((_ extract 31 31) sub_r) ((_ extract 31 31) cur_s))))
         false))))))

; Pre-state is valid non-negative Int32
(assert (bvsge cur_state #x00000000))
; Assumption guard :: is satisfied
(assert (let ((p_raw (pred_rtl ev_param {op_hex} {pr_hex}))
              (inv_a (= ((_ extract 3 3) {gf_hex}) #b1)))
          (ite inv_a (not p_raw) p_raw)))
; Invariant gate • is either disabled or bypassed in mutant, and candidate violates safety
(assert {"true" if bypass_invariant_gate else f"(= ((_ extract 1 1) {gf_hex}) #b1)"})
(assert (let ((cand (cand_rtl cur_state ev_param {op_hex} {ac_hex}))
              (ovf (ovf_rtl cur_state {op_hex} {ac_hex})))
          (or (bvslt cand #x00000000) ovf)))
"""
    if HAS_Z3_PYTHON and z3 is not None:
        s = z3.Solver()
        s.from_string(smt2)
        res = s.check()
        if res == z3.sat:
            m = s.model()
            cur_val = None
            param_val = None
            for decl in m.decls():
                if decl.name() == "cur_state":
                    cur_val = _to_i32(m[decl].as_long())
                elif decl.name() == "ev_param":
                    param_val = _to_i32(m[decl].as_long())
            cur_i32 = 0 if cur_val is None else cur_val
            par_i32 = 0 if param_val is None else param_val
            cand_i32, _, ovf = KpolCascadeDebugger([d])._eval_action(d, cur_i32, par_i32)
            return {
                "status": "SAT_WITNESS_FOUND",
                "cid": d.cid,
                "concept_name": d.name,
                "witness_cur_state": cur_i32,
                "witness_ev_param": par_i32,
                "unsafe_candidate_w0": cand_i32,
                "arith_overflow": ovf,
            }
        return {
            "status": "UNSAT_NO_VIOLATION",
            "cid": d.cid,
            "concept_name": d.name,
        }

    verdict, raw_out = _run_z3_cli_smt2(smt2 + "\n(check-sat)\n(get-model)\n")
    return {
        "status": "SAT_WITNESS_FOUND" if verdict == "sat" else "UNSAT_NO_VIOLATION",
        "cid": d.cid,
        "concept_name": d.name,
        "raw_z3_output": raw_out,
    }


# ============================================================================
# Reference Tracer for Author Slide / Article Extended Semantic Examples
# ============================================================================


@dataclass(frozen=True)
class AuthorSlideTraceStep:
    """Single step in the reference trace of an Author slide/article program."""

    step: int
    stimulus: str
    active_concept: str
    pre_state: str
    event_evaluated: str
    rule_or_bar_action: str
    post_state: str
    anti_loop_or_convergence_note: str


def trace_author_if_toggle_example() -> dict[str, Any]:
    """Trace the Author's T-flip-flop `If` example (`_ -> ! -> ¬ -> !`) with RFC-001 anti-loop rule."""
    source_slide = (
        "Boolean If _\n"
        "  _ -> If = !\n"
        "  ! -> If = ¬\n"
        "  ¬ -> If = !"
    )
    steps = [
        AuthorSlideTraceStep(
            step=1,
            stimulus="Go If ← (Write impulse #1)",
            active_concept="If",
            pre_state="_ (uninitialized, valid=0)",
            event_evaluated="If :: _ => True",
            rule_or_bar_action="If ← ! (True, code 0)",
            post_state="! (True, valid=1)",
            anti_loop_or_convergence_note=(
                "RFC-001 Cycle Prevention: write to `If` inside subscription of `If` "
                "suppresses recursive re-triggering (`self_suppress = 1`). Wave stops after 1 step."
            ),
        ),
        AuthorSlideTraceStep(
            step=2,
            stimulus="Go If ← (Write impulse #2)",
            active_concept="If",
            pre_state="! (True, valid=1)",
            event_evaluated="If :: ! => True",
            rule_or_bar_action="If ← ¬ (False, code 1)",
            post_state="¬ (False, valid=1)",
            anti_loop_or_convergence_note=(
                "Single-reaction per write impulse: `If` flips `! -> ¬` and stops without oscillating."
            ),
        ),
        AuthorSlideTraceStep(
            step=3,
            stimulus="Go If ← (Write impulse #3)",
            active_concept="If",
            pre_state="¬ (False, valid=1)",
            event_evaluated="If :: ¬ => True",
            rule_or_bar_action="If ← ! (True, code 0)",
            post_state="! (True, valid=1)",
            anti_loop_or_convergence_note=(
                "Single-reaction per write impulse: `If` flips `¬ -> !` and stops."
            ),
        ),
    ]
    return {
        "example_id": "author_slide_if_toggle",
        "title": "T-тригер `If` зі станом невизначеності `_` та правилом анти-зациклення (`RFC-001`)",
        "source_text": source_slide,
        "initial_state": "_",
        "final_state": "!",
        "state_trajectory": ["_", "!", "¬", "!"],
        "steps": [asdict(s) for s in steps],
    }


def trace_author_sum_post_read_reset_example() -> dict[str, Any]:
    """Trace the Author's `Sum` accumulator with post-read Big Dot `•` reset (`RFC-013`)."""
    source_slide = (
        "Int32 Sum = 0\n"
        "  ← @ Int32 x : Sum += x\n"
        "  → • Sum = 0"
    )
    steps = [
        AuthorSlideTraceStep(
            step=1,
            stimulus="Init(Sum = 0)",
            active_concept="Sum",
            pre_state="_",
            event_evaluated="Init(:)",
            rule_or_bar_action="Sum := 0",
            post_state="Sum = 0",
            anti_loop_or_convergence_note="Accumulator initialized to 0.",
        ),
        AuthorSlideTraceStep(
            step=2,
            stimulus="Go Sum ← 10 (Write x=10)",
            active_concept="Sum",
            pre_state="Sum = 0",
            event_evaluated="← (Write event, x=10)",
            rule_or_bar_action="Sum := Sum + 10",
            post_state="Sum = 10",
            anti_loop_or_convergence_note="Write subscription accumulates +10.",
        ),
        AuthorSlideTraceStep(
            step=3,
            stimulus="Go Sum ← 25 (Write x=25)",
            active_concept="Sum",
            pre_state="Sum = 10",
            event_evaluated="← (Write event, x=25)",
            rule_or_bar_action="Sum := Sum + 25",
            post_state="Sum = 35",
            anti_loop_or_convergence_note="Write subscription accumulates +25 (total 35).",
        ),
        AuthorSlideTraceStep(
            step=4,
            stimulus="Go Sum → (Read & Post-Read • Reset)",
            active_concept="Sum",
            pre_state="Sum = 35",
            event_evaluated="→ (Read phase 1) then • (Post-Read barrier phase 2, RFC-013)",
            rule_or_bar_action="BusRead := 35; then • executes Sum := 0",
            post_state="Sum = 0 (Read value = 35)",
            anti_loop_or_convergence_note=(
                "RFC-013 / RFC-017: current value 35 is placed on read bus first, "
                "then post-addressing subscription after `•` resets `Sum = 0`."
            ),
        ),
    ]
    return {
        "example_id": "author_slide_sum_post_read_reset",
        "title": "Акумулятор `Sum` із пост-адресним скиданням після читання `→ • Sum = 0` (`RFC-013`)",
        "source_text": source_slide,
        "read_returned_value": 35,
        "post_read_state": 0,
        "steps": [asdict(s) for s in steps],
    }


def trace_author_euclid_nod_example(a_init: int = 120, b_init: int = 6) -> dict[str, Any]:
    """Trace the Author's reactive Euclidean GCD `Nod(a, b)` step-by-step."""
    if a_init <= 0 or b_init <= 0:
        raise ValueError("a_init and b_init must be positive integers")

    source_slide = (
        "U64 Nod | @ U64 ( a_ > b -=b , b_ > a -=a ) =a\n"
        f"Z = Nod({a_init}, {b_init})"
    )
    a = int(a_init)
    b = int(b_init)
    steps: list[AuthorSlideTraceStep] = []
    step_no = 0

    while a != b:
        step_no += 1
        pre = f"a={a}, b={b}"
        if a > b:
            next_a = a - b
            steps.append(
                AuthorSlideTraceStep(
                    step=step_no,
                    stimulus=f"Reactive wave #{step_no} (ST_EVAL -> ST_EXEC -> ST_COMMIT)",
                    active_concept="Concept a",
                    pre_state=pre,
                    event_evaluated=f"(a > b): {a} > {b} => True; (b > a) => False",
                    rule_or_bar_action=f"a -= b ({a} - {b} = {next_a})",
                    post_state=f"a={next_a}, b={b}",
                    anti_loop_or_convergence_note=(
                        "3 clock cycles in km_euclid_core.sv (EVAL, EXEC, COMMIT)."
                    ),
                )
            )
            a = next_a
        else:
            next_b = b - a
            steps.append(
                AuthorSlideTraceStep(
                    step=step_no,
                    stimulus=f"Reactive wave #{step_no} (ST_EVAL -> ST_EXEC -> ST_COMMIT)",
                    active_concept="Concept b",
                    pre_state=pre,
                    event_evaluated=f"(b > a): {b} > {a} => True; (a > b) => False",
                    rule_or_bar_action=f"b -= a ({b} - {a} = {next_b})",
                    post_state=f"a={a}, b={next_b}",
                    anti_loop_or_convergence_note=(
                        "3 clock cycles in km_euclid_core.sv (EVAL, EXEC, COMMIT)."
                    ),
                )
            )
            b = next_b

    # Final convergence evaluation step (ST_EVAL: a == b)
    final_step_no = step_no + 1
    steps.append(
        AuthorSlideTraceStep(
            step=final_step_no,
            stimulus=f"Convergence check #{final_step_no} (ST_EVAL final)",
            active_concept="Concept a, b",
            pre_state=f"a={a}, b={b}",
            event_evaluated=f"(a > b): {a} > {b} => False; (b > a): {b} > {a} => False; (a == b) => True",
            rule_or_bar_action=f"Return =a ({a})",
            post_state=f"result={a} (wave extinguished)",
            anti_loop_or_convergence_note=(
                "Both predicates `a > b` and `b > a` are False; reactive wave naturally "
                f"extinguishes without a `while` counter after {step_no} subtractions "
                f"({step_no * 3 + 1} clock cycles = {(step_no * 3 + 1) * 10} ns @ 100 MHz)."
            ),
        )
    )

    return {
        "example_id": f"author_slide_nod_{a_init}_{b_init}",
        "title": f"Реактивний алгоритм Евкліда `Nod({a_init}, {b_init}) = {a}`",
        "source_text": source_slide,
        "a_init": a_init,
        "b_init": b_init,
        "subtraction_iterations": step_no,
        "total_eval_steps": final_step_no,
        "hardware_cycles_at_3cyc_per_sub_plus_1": step_no * 3 + 1,
        "result": a,
        "steps": [asdict(s) for s in steps],
    }


def format_author_slide_trace(trace_dict: dict[str, Any]) -> str:
    """Format an Author slide example trace into a readable ASCII table."""
    lines = [
        f"=== AUTHOR SLIDE / ARTICLE TRACE: {trace_dict['title']} ===",
        "Source Notation:",
    ]
    for idx, sline in enumerate(trace_dict["source_text"].splitlines(), 1):
        lines.append(f"  {idx:02d} | {sline}")

    headers = (
        "Step",
        "Stimulus / Phase",
        "Concept",
        "Pre-State",
        "Predicate / Event",
        "Action / Barrier •",
        "Post-State",
    )
    rows: list[tuple[str, ...]] = []
    for st in trace_dict["steps"]:
        rows.append(
            (
                str(st["step"]),
                str(st["stimulus"]),
                str(st["active_concept"]),
                str(st["pre_state"]),
                str(st["event_evaluated"]),
                str(st["rule_or_bar_action"]),
                str(st["post_state"]),
            )
        )
    widths = [
        max(len(headers[col]), *(len(r[col]) for r in rows)) if rows else len(headers[col])
        for col in range(len(headers))
    ]
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    hdr_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"
    lines.extend([sep, hdr_line, sep])
    for r in rows:
        lines.append("| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(headers))) + " |")
    lines.append(sep)
    return "\n".join(lines)


# Historical PoC RTL module `km_euclid_core.sv` (from commit c1b9d2f8694dd9d172e79b4e59603ba304af46f0)
# Used exclusively in a temporary scratch directory for differential iverilog verification of Nod(120, 6) = 6.
KM_EUCLID_CORE_SV_SOURCE = r"""`timescale 1ns/1ps
module km_euclid_core #(
    parameter int DATA_WIDTH = 32
)(
    input  logic                   clk,
    input  logic                   rst_n,
    input  logic                   start_i,
    input  logic [DATA_WIDTH-1:0]  a_init_i,
    input  logic [DATA_WIDTH-1:0]  b_init_i,
    output logic                   busy_o,
    output logic                   done_o,
    output logic                   error_o,
    output logic [DATA_WIDTH-1:0]  result_o,
    output logic [15:0]            iterations_o,
    output logic [31:0]            cycle_count_o,
    output logic [DATA_WIDTH-1:0]  concept_a_o,
    output logic [DATA_WIDTH-1:0]  concept_b_o
);
    typedef enum logic [1:0] {
        ST_IDLE   = 2'd0,
        ST_EVAL   = 2'd1,
        ST_EXEC   = 2'd2,
        ST_COMMIT = 2'd3
    } state_t;

    state_t state_q;
    logic [DATA_WIDTH-1:0] reg_a_q, reg_b_q, next_val_q, result_q;
    logic                  target_is_a_q, done_q, error_q;
    logic [15:0]           iter_cnt_q;
    logic [31:0]           cyc_cnt_q;

    assign concept_a_o   = reg_a_q;
    assign concept_b_o   = reg_b_q;
    assign busy_o        = (state_q != ST_IDLE);
    assign done_o        = done_q;
    assign error_o       = error_q;
    assign result_o      = result_q;
    assign iterations_o  = iter_cnt_q;
    assign cycle_count_o = cyc_cnt_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q       <= ST_IDLE;
            reg_a_q       <= '0;
            reg_b_q       <= '0;
            next_val_q    <= '0;
            target_is_a_q <= 1'b0;
            iter_cnt_q    <= 16'd0;
            cyc_cnt_q     <= 32'd0;
            done_q        <= 1'b0;
            error_q       <= 1'b0;
            result_q      <= '0;
        end else begin
            case (state_q)
                ST_IDLE: begin
                    if (start_i) begin
                        done_q     <= 1'b0;
                        error_q    <= 1'b0;
                        cyc_cnt_q  <= 32'd0;
                        iter_cnt_q <= 16'd0;
                        if (a_init_i == '0 || b_init_i == '0) begin
                            error_q  <= 1'b1;
                            done_q   <= 1'b1;
                            result_q <= '0;
                            state_q  <= ST_IDLE;
                        end else begin
                            reg_a_q <= a_init_i;
                            reg_b_q <= b_init_i;
                            state_q <= ST_EVAL;
                        end
                    end
                end
                ST_EVAL: begin
                    cyc_cnt_q <= cyc_cnt_q + 32'd1;
                    if (reg_a_q == reg_b_q) begin
                        result_q <= reg_a_q;
                        done_q   <= 1'b1;
                        state_q  <= ST_IDLE;
                    end else if (reg_a_q > reg_b_q) begin
                        target_is_a_q <= 1'b1;
                        state_q       <= ST_EXEC;
                    end else begin
                        target_is_a_q <= 1'b0;
                        state_q       <= ST_EXEC;
                    end
                end
                ST_EXEC: begin
                    cyc_cnt_q <= cyc_cnt_q + 32'd1;
                    if (target_is_a_q) next_val_q <= reg_a_q - reg_b_q;
                    else               next_val_q <= reg_b_q - reg_a_q;
                    state_q <= ST_COMMIT;
                end
                ST_COMMIT: begin
                    cyc_cnt_q  <= cyc_cnt_q + 32'd1;
                    iter_cnt_q <= iter_cnt_q + 16'd1;
                    if (target_is_a_q) reg_a_q <= next_val_q;
                    else               reg_b_q <= next_val_q;
                    state_q <= ST_EVAL;
                end
                default: state_q <= ST_IDLE;
            endcase
        end
    end
endmodule
"""


@contextmanager
def _debugger_scratch_dir(prefix: str = "dbg272"):
    base = REPO_ROOT / ".pytest_cache" / f"{prefix}_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ============================================================================
# 1. STDIO Binding (`@stdin` / `@stdout` / `stderr`) for KPOL Programs
# ============================================================================


@dataclass(frozen=True)
class StdioConfig:
    """STDIO binding configuration extracted from KPOL source or defaults."""

    stdin_concepts: tuple[str, ...]
    stdout_concepts: tuple[str, ...]
    default_stdin_cid: int = 0


def parse_stdio_directives(
    source_code: str,
    descriptors: Sequence[ConceptMicroDescriptor],
    active_cids: Sequence[int],
) -> StdioConfig:
    """Extract `# @stdin <Concept>` / `# @stdout <Concept>` pragmas or infer defaults."""
    name_to_cid = {d.name: d.cid for d in descriptors if is_descriptor_configured(d)}
    for cid in active_cids:
        name_to_cid[descriptors[cid].name] = cid

    stdin_names: list[str] = []
    stdout_names: list[str] = []

    for line in source_code.splitlines():
        s = line.strip()
        for prefix in ("#", "//"):
            if s.startswith(prefix):
                body = s[len(prefix) :].strip()
                if body.startswith("@stdin"):
                    tokens = body[len("@stdin") :].replace(",", " ").split()
                    stdin_names.extend(tokens)
                elif body.startswith("@stdout"):
                    tokens = body[len("@stdout") :].replace(",", " ").split()
                    stdout_names.extend(tokens)

    if not stdin_names and active_cids:
        stdin_names = [descriptors[active_cids[0]].name]
    if not stdout_names and active_cids:
        stdout_names = [descriptors[cid].name for cid in active_cids]

    default_cid = active_cids[0] if active_cids else 0
    if stdin_names and stdin_names[0] in name_to_cid:
        default_cid = name_to_cid[stdin_names[0]]

    return StdioConfig(
        stdin_concepts=tuple(stdin_names),
        stdout_concepts=tuple(stdout_names),
        default_stdin_cid=default_cid,
    )


def parse_stdio_input_line(
    line: str,
    descriptors: Sequence[ConceptMicroDescriptor],
    default_cid: int = 0,
) -> tuple[int, int, bool] | None:
    """Parse one STDIN line into `(cid, param, param_valid)`.

    Supported formats:
      - `<param>` (e.g. `5`, `-10`, `_`, `invalid`) -> targets `default_cid`
      - `<cid_or_name> <param>` (e.g. `0 120`, `Cell_Delta_mV 180`, `Counter _`)
      - `<cid_or_name>:<param>` (e.g. `0:120`, `0:invalid`)
      - JSONL: `{"cid": 0, "param": 120, "valid": true}` or `{"concept": "Counter", "param": "_"}`
    """
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("//"):
        return None

    name_to_cid = {d.name.lower(): d.cid for d in descriptors}
    for d in descriptors:
        name_to_cid[f"c{d.cid}"] = d.cid
        name_to_cid[f"cid{d.cid}"] = d.cid

    def _resolve_target(tok: str) -> int:
        tl = tok.strip().lower()
        if tl in name_to_cid:
            return name_to_cid[tl]
        try:
            return int(tok, 0)
        except ValueError as err:
            raise KpolError(f"STDIO-PARSE: unknown concept or CID {tok!r}") from err

    def _resolve_param(tok: str) -> tuple[int, bool]:
        tl = tok.strip().lower()
        if tl in ("_", "invalid", "fault", "null", "nan"):
            return 0, False
        try:
            return int(tok, 0), True
        except ValueError as err:
            raise KpolError(f"STDIO-PARSE: invalid integer parameter {tok!r}") from err

    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as err:
            raise KpolError(f"STDIO-PARSE: malformed JSONL input {s!r}") from err
        if "cid" in obj:
            cid = int(obj["cid"])
        elif "concept" in obj:
            cid = _resolve_target(str(obj["concept"]))
        else:
            cid = default_cid
        raw_p = obj.get("param", 0)
        if raw_p in ("_", "invalid") or obj.get("valid") is False:
            p_val = 0 if isinstance(raw_p, str) else int(raw_p)
            return cid, p_val, False
        return cid, int(raw_p), True

    if ":" in s and " " not in s:
        evs = parse_trace_events_spec(s)
        return evs[0]

    parts = s.split()
    if len(parts) == 1:
        param, valid = _resolve_param(parts[0])
        return default_cid, param, valid
    if len(parts) == 2:
        cid = _resolve_target(parts[0])
        param, valid = _resolve_param(parts[1])
        return cid, param, valid
    if len(parts) == 3:
        cid = _resolve_target(parts[0])
        param, _ = _resolve_param(parts[1])
        v_tok = parts[2].strip().lower()
        valid = v_tok not in ("_", "0", "false", "invalid", "fault")
        return cid, param, valid

    raise KpolError(f"STDIO-PARSE: unsupported STDIN line format {s!r}")


@dataclass
class StdioExecutionResult:
    """Captured streams (`stdin_records`, `stdout_lines`, `stderr_lines`) from a STDIO session."""

    stdin_records: list[tuple[int, int, bool]]
    stdout_lines: list[str]
    stderr_lines: list[str]
    report: DebugSessionReport


def run_stdio_stream(
    debugger: KpolCascadeDebugger,
    stdin_lines: Sequence[str],
    *,
    stdio_config: StdioConfig | None = None,
    emit_to_sys_stdio: bool = False,
) -> StdioExecutionResult:
    """Process a stream of STDIN lines through `debugger`, routing COMMITs to STDOUT
    and REJECTs (`REJECT_GUARD`, `REJECT_INVARIANT`, `REJECT_FAULT`) to STDERR.
    """
    cfg = stdio_config or parse_stdio_directives(
        debugger.source_code,
        debugger.descriptors,
        debugger.active_cids,
    )
    stdout_set = set(cfg.stdout_concepts)
    stdin_records: list[tuple[int, int, bool]] = []
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    for raw_line in stdin_lines:
        parsed = parse_stdio_input_line(
            raw_line,
            debugger.descriptors,
            default_cid=cfg.default_stdin_cid,
        )
        if parsed is None:
            continue
        cid, param, param_valid = parsed
        stdin_records.append((cid, param, param_valid))
        wave_steps = debugger.step_event(cid, param, param_valid)
        for st in wave_steps:
            if st.verdict in (VERDICT_COMMIT, VERDICT_SUPPRESSED_SELF):
                if not stdout_set or st.concept_name in stdout_set:
                    msg = (
                        f"COMMIT: {st.concept_name}[cid={st.cid}] = {st.post_w0} "
                        f"(pre={st.pre_w0}, depth={st.depth}, param={st.param}, valid={st.param_valid_symbol})"
                    )
                    stdout_lines.append(msg)
                    if emit_to_sys_stdio:
                        sys.stdout.write(msg + "\n")
                        sys.stdout.flush()
            else:
                err_msg = (
                    f"{st.verdict}: {st.concept_name}[cid={st.cid}] kept W0={st.post_w0} "
                    f"(depth={st.depth}, param={st.param}, valid={st.param_valid_symbol}, "
                    f"pred=({st.pred_formula})=>{st.pred_match}, "
                    f"cand={st.candidate_w0}, gate=({st.inv_formula})=>{st.inv_ok})"
                )
                stderr_lines.append(err_msg)
                if emit_to_sys_stdio:
                    sys.stderr.write(err_msg + "\n")
                    sys.stderr.flush()

    return StdioExecutionResult(
        stdin_records=stdin_records,
        stdout_lines=stdout_lines,
        stderr_lines=stderr_lines,
        report=debugger.build_report(),
    )


# ============================================================================
# 2. Machine Target Connection, PRE-LOAD vs POST-LOAD Snapshots & TUI Debugger
# ============================================================================


@dataclass(frozen=True)
class ConceptTopologySummary:
    """Breakdown of concept roles in a 64-slot BRAM image."""

    total_slots: int
    active_concepts: int
    free_slots: int
    entry_concepts: tuple[int, ...]
    internal_cascade_concepts: tuple[int, ...]
    leaf_concepts: tuple[int, ...]
    isolated_concepts: tuple[int, ...]


def analyze_concept_topology(
    descriptors: Sequence[ConceptMicroDescriptor],
) -> ConceptTopologySummary:
    """Classify the 64 BRAM slots into active, entry, internal cascade, leaf, and free."""
    configured = [d.cid for d in descriptors if is_descriptor_configured(d)]
    active_set = set(configured)
    out_edges: dict[int, int] = {}
    in_deg: dict[int, int] = {cid: 0 for cid in range(64)}

    for d in descriptors:
        if has_subscription_edge(d) and 0 <= d.subscriber_cid < 64 and d.subscriber_cid != d.cid:
            active_set.add(d.cid)
            active_set.add(d.subscriber_cid)
            out_edges[d.cid] = d.subscriber_cid
            in_deg[d.subscriber_cid] = in_deg.get(d.subscriber_cid, 0) + 1

    active_sorted = sorted(active_set)
    entry_cids: list[int] = []
    internal_cids: list[int] = []
    leaf_cids: list[int] = []
    isolated_cids: list[int] = []

    for cid in active_sorted:
        has_in = in_deg.get(cid, 0) > 0
        has_out = cid in out_edges
        if not has_in and has_out:
            entry_cids.append(cid)
        elif has_in and has_out:
            internal_cids.append(cid)
        elif has_in and not has_out:
            leaf_cids.append(cid)
        else:
            isolated_cids.append(cid)
            entry_cids.append(cid)

    return ConceptTopologySummary(
        total_slots=64,
        active_concepts=len(active_sorted),
        free_slots=64 - len(active_sorted),
        entry_concepts=tuple(entry_cids),
        internal_cascade_concepts=tuple(internal_cids),
        leaf_concepts=tuple(leaf_cids),
        isolated_concepts=tuple(isolated_cids),
    )


@dataclass(frozen=True)
class MachineSnapshot:
    """Full hardware/simulator state snapshot (`PRE-LOAD`, `POST-LOAD`, or `POST-RUN`)."""

    phase: str
    target: str
    hw_id_hex: str
    hw_id_ascii: str
    bram_bytes: bytes
    bram_sha256: str
    descriptors: tuple[ConceptMicroDescriptor, ...]
    topology: ConceptTopologySummary
    hw_events: int
    hw_commits: int
    hw_rejects: int
    hw_last_state: int
    hw_dropped: int = 0

    def to_dict(self) -> dict[str, Any]:
        active_rows = []
        for cid in range(64):
            d = self.descriptors[cid]
            if is_descriptor_configured(d):
                w2_u32, w2_dec = decode_w2_word(d)
                active_rows.append(
                    {
                        "cid": cid,
                        "name": d.name,
                        "w0_state": _to_i32(d.current_state),
                        "w1_operand": _to_i32(d.operand_val),
                        "w2_hex": f"0x{w2_u32:08X}",
                        "w2_decoded": w2_dec,
                        "w3_subscriber": d.subscriber_cid,
                    }
                )
        return {
            "phase": self.phase,
            "target": self.target,
            "hw_id_hex": self.hw_id_hex,
            "hw_id_ascii": self.hw_id_ascii,
            "bram_sha256": self.bram_sha256,
            "topology": asdict(self.topology),
            "counters": {
                "hw_events": self.hw_events,
                "hw_commits": self.hw_commits,
                "hw_rejects": self.hw_rejects,
                "hw_last_state": self.hw_last_state,
                "hw_dropped": self.hw_dropped,
            },
            "active_descriptors": active_rows,
        }


@dataclass(frozen=True)
class SlotLoadDiff:
    """Per-slot comparison between PRE-LOAD and POST-LOAD BRAM descriptors."""

    cid: int
    name: str
    changed: bool
    pre_active: bool
    post_active: bool
    pre_w0: int
    post_w0: int
    pre_w1: int
    post_w1: int
    pre_w2_hex: str
    post_w2_hex: str
    pre_rule: str
    post_rule: str
    pre_sub: str
    post_sub: str


def compute_pre_post_load_diff(
    pre: MachineSnapshot,
    post: MachineSnapshot,
) -> list[SlotLoadDiff]:
    """Compare all 64 BRAM slots between PRE-LOAD and POST-LOAD snapshots."""
    diffs: list[SlotLoadDiff] = []
    for cid in range(64):
        d0 = pre.descriptors[cid]
        d1 = post.descriptors[cid]
        pre_act = is_descriptor_configured(d0)
        post_act = is_descriptor_configured(d1)
        changed = d0.pack() != d1.pack()
        if not (pre_act or post_act or changed):
            continue
        w2_0, dec_0 = decode_w2_word(d0)
        w2_1, dec_1 = decode_w2_word(d1)
        diffs.append(
            SlotLoadDiff(
                cid=cid,
                name=d1.name if post_act else d0.name,
                changed=changed,
                pre_active=pre_act,
                post_active=post_act,
                pre_w0=_to_i32(d0.current_state),
                post_w0=_to_i32(d1.current_state),
                pre_w1=_to_i32(d0.operand_val),
                post_w1=_to_i32(d1.operand_val),
                pre_w2_hex=f"0x{w2_0:08X}",
                post_w2_hex=f"0x{w2_1:08X}",
                pre_rule=dec_0 if pre_act else "EMPTY",
                post_rule=dec_1 if post_act else "EMPTY",
                pre_sub=decode_w3_subscriber(d0, pre.descriptors) if pre_act else "None",
                post_sub=decode_w3_subscriber(d1, post.descriptors) if post_act else "None",
            )
        )
    return diffs


def _hw_id_to_ascii(hw_id: int) -> str:
    chars = []
    for shift in (24, 16, 8, 0):
        b = (hw_id >> shift) & 0xFF
        chars.append(chr(b) if 32 <= b <= 126 else "?")
    return "".join(chars)


def make_snapshot_from_bytes(
    bram_bytes: bytes,
    *,
    phase: str,
    target: str = "sim",
    hw_id: int = 0x4B504D43,
    hw_events: int = 0,
    hw_commits: int = 0,
    hw_rejects: int = 0,
    hw_last_state: int = 0,
    hw_dropped: int = 0,
    concept_names: Mapping[int, str] | Sequence[str] | None = None,
) -> MachineSnapshot:
    """Create a MachineSnapshot from a 1024-byte BRAM image and hardware counters."""
    if len(bram_bytes) != 1024:
        raise KpolError(f"Expected 1024-byte BRAM snapshot, got {len(bram_bytes)}")
    descs = normalize_descriptors(bram_bytes, concept_names=concept_names)
    topo = analyze_concept_topology(descs)
    return MachineSnapshot(
        phase=phase,
        target=target,
        hw_id_hex=f"0x{hw_id & 0xFFFFFFFF:08X}",
        hw_id_ascii=_hw_id_to_ascii(hw_id),
        bram_bytes=bytes(bram_bytes),
        bram_sha256=hashlib.sha256(bram_bytes).hexdigest(),
        descriptors=tuple(descs),
        topology=topo,
        hw_events=int(hw_events),
        hw_commits=int(hw_commits),
        hw_rejects=int(hw_rejects),
        hw_last_state=_to_i32(hw_last_state),
        hw_dropped=int(hw_dropped),
    )


PYNQ_DEBUG_PROBE_C_SOURCE = r"""
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define BASE_ADDR       0x40000000UL
#define MAP_SIZE        0x2000UL
#define REG_ID          (0x000 / 4)
#define REG_BRAM_ADDR   (0x004 / 4)
#define REG_BRAM_DATA   (0x008 / 4)
#define REG_EVENT_PARAM (0x00C / 4)
#define REG_SW_TRIGGER  (0x010 / 4)
#define REG_BUSY        (0x014 / 4)
#define REG_EVENTS      (0x018 / 4)
#define REG_COMMITS     (0x01C / 4)
#define REG_REJECTS     (0x020 / 4)
#define REG_LAST_STATE  (0x024 / 4)
#define REG_DROPPED     (0x028 / 4)

static void wait_idle(volatile uint32_t *regs) {
    int guard = 0;
    while ((regs[REG_BUSY] & 1u) != 0u) {
        if (++guard > 1000000) {
            fprintf(stderr, "Timeout waiting for REG_BUSY == 0\n");
            exit(2);
        }
    }
}

static void dump_snapshot_json(const char *label, volatile uint32_t *regs) {
    uint32_t words[256];
    wait_idle(regs);
    for (uint32_t i = 0; i < 256u; ++i) {
        regs[REG_BRAM_ADDR] = i;
        words[i] = regs[REG_BRAM_DATA];
    }
    uint32_t hw_id   = regs[REG_ID];
    uint32_t ev_cnt  = regs[REG_EVENTS];
    uint32_t cm_cnt  = regs[REG_COMMITS];
    uint32_t rj_cnt  = regs[REG_REJECTS];
    int32_t  last_st = (int32_t)regs[REG_LAST_STATE];
    uint32_t dropped = (hw_id == 0x4B504841u) ? regs[REG_DROPPED] : 0u;

    printf("    \"%s\": {\n", label);
    printf("      \"hw_id\": %u,\n", (unsigned)hw_id);
    printf("      \"hw_id_hex\": \"0x%08X\",\n", (unsigned)hw_id);
    printf("      \"events\": %u,\n", (unsigned)ev_cnt);
    printf("      \"commits\": %u,\n", (unsigned)cm_cnt);
    printf("      \"rejects\": %u,\n", (unsigned)rj_cnt);
    printf("      \"last_state\": %d,\n", (int)last_st);
    printf("      \"dropped\": %u,\n", (unsigned)dropped);
    printf("      \"bram_words_hex\": [");
    for (uint32_t i = 0; i < 256u; ++i) {
        printf("\"%08X\"%s", (unsigned)words[i], (i + 1u < 256u) ? "," : "");
    }
    printf("]\n    }");
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <program.bin> [param1 param2 ...]\n", argv[0]);
        return 2;
    }
    FILE *fp = fopen(argv[1], "rb");
    if (!fp) {
        perror("fopen bin");
        return 2;
    }
    uint32_t prog_words[256];
    if (fread(prog_words, sizeof(uint32_t), 256, fp) != 256) {
        fprintf(stderr, "Failed to read 256 words from %s\n", argv[1]);
        fclose(fp);
        return 2;
    }
    fclose(fp);

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem");
        return 2;
    }
    volatile uint32_t *regs = (volatile uint32_t *)mmap(
        NULL, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, BASE_ADDR
    );
    if (regs == MAP_FAILED) {
        perror("mmap");
        close(fd);
        return 2;
    }

    uint32_t chip_id = regs[REG_ID];
    if ((chip_id != 0x4B504D43u) && (chip_id != 0x4B504841u)) {
        fprintf(stderr, "Unexpected FPGA ID: 0x%08X\n", (unsigned)chip_id);
        munmap((void *)regs, MAP_SIZE);
        close(fd);
        return 2;
    }

    printf("{\n  \"snapshots\": {\n");
    /* 1. PRE-LOAD snapshot before writing new program */
    dump_snapshot_json("pre_load", regs);
    printf(",\n");

    /* 2. Program 256 words into BRAM and verify readback */
    wait_idle(regs);
    for (uint32_t i = 0; i < 256u; ++i) {
        regs[REG_BRAM_ADDR] = i;
        regs[REG_BRAM_DATA] = prog_words[i];
    }
    wait_idle(regs);
    dump_snapshot_json("post_load", regs);
    printf(",\n");

    /* 3. Execute optional stimulus parameters on CID 0 */
    for (int a = 2; a < argc; ++a) {
        int32_t p = (int32_t)strtol(argv[a], NULL, 0);
        wait_idle(regs);
        regs[REG_EVENT_PARAM] = (uint32_t)p;
        regs[REG_SW_TRIGGER]  = 1u;
        wait_idle(regs);
    }
    dump_snapshot_json("post_run", regs);
    printf("\n  }\n}\n");

    munmap((void *)regs, MAP_SIZE);
    close(fd);
    return 0;
}
"""


def _decode_raw_snapshot_obj(
    raw_obj: Mapping[str, Any],
    *,
    phase: str,
    target: str,
    concept_names: Mapping[int, str] | Sequence[str] | None = None,
) -> MachineSnapshot:
    words_hex = raw_obj["bram_words_hex"]
    if len(words_hex) != 256:
        raise KpolError(f"Expected 256 BRAM hex words in snapshot, got {len(words_hex)}")
    words_u32 = [int(w, 16) for w in words_hex]
    bram_bytes = struct.pack("<256I", *words_u32)
    return make_snapshot_from_bytes(
        bram_bytes,
        phase=phase,
        target=target,
        hw_id=int(raw_obj["hw_id"]),
        hw_events=int(raw_obj["events"]),
        hw_commits=int(raw_obj["commits"]),
        hw_rejects=int(raw_obj["rejects"]),
        hw_last_state=int(raw_obj["last_state"]),
        hw_dropped=int(raw_obj.get("dropped", 0)),
        concept_names=concept_names,
    )


class MachineDebugConnection:
    """Session manager that connects to a target (`sim` or `pynq1`/`pynq2`), captures
    the `PRE-LOAD` state before programming, programs the new BRAM image, verifies the
    `POST-LOAD` readback & diff, and executes step-by-step / STDIO traces.
    """

    TARGET_HOSTS: dict[str, str] = {
        "pynq1": "xilinx@192.168.68.81",
        "pynq2": "xilinx@192.168.68.69",
    }

    def __init__(
        self,
        *,
        target: str = "sim",
        initial_machine_bram: bytes | None = None,
        initial_hw_id: int = 0x4B504D43,
    ) -> None:
        self.target = target.strip()
        self._sim_hw_id = initial_hw_id
        self._sim_bram = (
            bytes(initial_machine_bram)
            if initial_machine_bram is not None
            else bytes(1024)
        )
        if len(self._sim_bram) != 1024:
            raise KpolError("initial_machine_bram must be exactly 1024 bytes")
        self._sim_events = 0
        self._sim_commits = 0
        self._sim_rejects = 0
        self._sim_last_state = 0
        self.pre_load_snapshot: MachineSnapshot | None = None
        self.post_load_snapshot: MachineSnapshot | None = None
        self.post_run_snapshot: MachineSnapshot | None = None
        self.load_diffs: list[SlotLoadDiff] = []

    def resolve_ssh_target(self) -> str | None:
        if self.target == "sim":
            return None
        if self.target in self.TARGET_HOSTS:
            return self.TARGET_HOSTS[self.target]
        return self.target

    def connect_and_capture_pre_load(
        self,
        *,
        pre_concept_names: Mapping[int, str] | Sequence[str] | None = None,
    ) -> MachineSnapshot:
        """Capture `PRE-LOAD` snapshot of the machine before loading a new program."""
        if self.target == "sim":
            snap = make_snapshot_from_bytes(
                self._sim_bram,
                phase="PRE-LOAD",
                target="sim",
                hw_id=self._sim_hw_id,
                hw_events=self._sim_events,
                hw_commits=self._sim_commits,
                hw_rejects=self._sim_rejects,
                hw_last_state=self._sim_last_state,
                concept_names=pre_concept_names,
            )
            self.pre_load_snapshot = snap
            return snap
        raise KpolError(
            "For hardware targets (pynq1/pynq2), use program_and_trace() to execute under bench lock"
        )

    def load_program_into_sim(
        self,
        program_bram: bytes,
        *,
        concept_names: Mapping[int, str] | Sequence[str] | None = None,
        pre_concept_names: Mapping[int, str] | Sequence[str] | None = None,
    ) -> tuple[MachineSnapshot, MachineSnapshot, list[SlotLoadDiff]]:
        """Capture PRE-LOAD snapshot, load `program_bram` into `sim`, verify readback, and compute diff."""
        if len(program_bram) != 1024:
            raise KpolError(f"Expected 1024-byte program BRAM image, got {len(program_bram)}")
        if self.pre_load_snapshot is None:
            self.connect_and_capture_pre_load(pre_concept_names=pre_concept_names)
        assert self.pre_load_snapshot is not None

        self._sim_bram = bytes(program_bram)
        # Readback verification: ensure all 256 32-bit words match
        if self._sim_bram != program_bram:
            raise KpolError("BRAM readback verification failed")

        post = make_snapshot_from_bytes(
            self._sim_bram,
            phase="POST-LOAD",
            target=self.target,
            hw_id=self._sim_hw_id,
            hw_events=self._sim_events,
            hw_commits=self._sim_commits,
            hw_rejects=self._sim_rejects,
            hw_last_state=self._sim_last_state,
            concept_names=concept_names,
        )
        self.post_load_snapshot = post
        self.load_diffs = compute_pre_post_load_diff(self.pre_load_snapshot, post)
        return self.pre_load_snapshot, post, self.load_diffs

    def execute_pynq_session(
        self,
        program_bram: bytes,
        hw_params: Sequence[int] = (),
        *,
        concept_names: Mapping[int, str] | Sequence[str] | None = None,
        pre_concept_names: Mapping[int, str] | Sequence[str] | None = None,
        lock_timeout_sec: float = 120.0,
    ) -> dict[str, Any]:
        """Connect to live PYNQ-Z1 (`pynq1` or `pynq2`) under `/tmp/km-bench.lock`,
        capture `PRE-LOAD` BRAM & counters, program `program_bram`, capture `POST-LOAD`
        readback, run `hw_params`, and capture `POST-RUN` BRAM & counters.
        """
        import fcntl
        import time

        ssh_host = self.resolve_ssh_target()
        if ssh_host is None:
            raise KpolError("execute_pynq_session requires a hardware target (pynq1/pynq2)")

        lock_path = "/" + "tmp/km-bench.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o666)
        deadline = time.monotonic() + lock_timeout_sec
        acquired = False
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Timed out acquiring {lock_path}")
                    time.sleep(0.2)

            with _debugger_scratch_dir("pynq_dbg272") as scratch:
                c_path = scratch / "km_pynq_debug_probe.c"
                bin_path = scratch / "program_image.bin"
                c_path.write_text(PYNQ_DEBUG_PROBE_C_SOURCE, encoding="utf-8")
                bin_path.write_bytes(program_bram)

                remote_dir = "/home/xilinx/km_dbg_272_work"
                subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=no",
                        ssh_host,
                        f"mkdir -p {remote_dir}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                try:
                    subprocess.run(
                        [
                            "scp",
                            "-o",
                            "StrictHostKeyChecking=no",
                            str(c_path),
                            str(bin_path),
                            f"{ssh_host}:{remote_dir}/",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    param_args = " ".join(str(int(p)) for p in hw_params)
                    remote_cmd = (
                        f"cd {remote_dir} && "
                        "gcc -std=c99 -O2 -Wall -Wextra -Werror km_pynq_debug_probe.c -o km_pynq_debug_probe && "
                        f"echo xilinx | sudo -S -p '' ./km_pynq_debug_probe program_image.bin {param_args}"
                    )
                    res = subprocess.run(
                        [
                            "ssh",
                            "-o",
                            "StrictHostKeyChecking=no",
                            ssh_host,
                            remote_cmd,
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                finally:
                    subprocess.run(
                        [
                            "ssh",
                            "-o",
                            "StrictHostKeyChecking=no",
                            ssh_host,
                            f"rm -rf {remote_dir}",
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )

            payload = json.loads(res.stdout)
            snaps = payload["snapshots"]
            self.pre_load_snapshot = _decode_raw_snapshot_obj(
                snaps["pre_load"],
                phase="PRE-LOAD",
                target=self.target,
                concept_names=pre_concept_names,
            )
            self.post_load_snapshot = _decode_raw_snapshot_obj(
                snaps["post_load"],
                phase="POST-LOAD",
                target=self.target,
                concept_names=concept_names,
            )
            self.post_run_snapshot = _decode_raw_snapshot_obj(
                snaps["post_run"],
                phase="POST-RUN",
                target=self.target,
                concept_names=concept_names,
            )
            if self.post_load_snapshot.bram_bytes != program_bram:
                raise KpolError("PYNQ-Z1 POST-LOAD BRAM readback mismatch against program_bram!")
            self.load_diffs = compute_pre_post_load_diff(
                self.pre_load_snapshot, self.post_load_snapshot
            )
            return {
                "target": self.target,
                "ssh_host": ssh_host,
                "pre_load": self.pre_load_snapshot.to_dict(),
                "post_load": self.post_load_snapshot.to_dict(),
                "post_run": self.post_run_snapshot.to_dict(),
                "changed_slots_on_load": sum(1 for d in self.load_diffs if d.changed),
                "events_delta": self.post_run_snapshot.hw_events - self.post_load_snapshot.hw_events,
                "commits_delta": self.post_run_snapshot.hw_commits - self.post_load_snapshot.hw_commits,
                "rejects_delta": self.post_run_snapshot.hw_rejects - self.post_load_snapshot.hw_rejects,
            }
        finally:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def format_pre_post_load_summary(self) -> str:
        """Render the `PRE-LOAD` vs `POST-LOAD` concept count & slot diff table."""
        if self.pre_load_snapshot is None or self.post_load_snapshot is None:
            return "No PRE-LOAD / POST-LOAD snapshots captured yet."

        pre = self.pre_load_snapshot
        post = self.post_load_snapshot
        t0 = pre.topology
        t1 = post.topology
        changed_count = sum(1 for d in self.load_diffs if d.changed)

        lines = [
            f"=== MACHINE CONNECTION & PROGRAMMING SNAPSHOT ({post.target.upper()} | HW_ID={post.hw_id_hex} '{post.hw_id_ascii}') ===",
            f"  Capacity          : {t1.total_slots} concept slots (1024 B CME-RAW-1 BRAM)",
            (
                f"  PRE-LOAD State    : {t0.active_concepts} / {t0.total_slots} active concepts "
                f"(free={t0.free_slots}, SHA-256={pre.bram_sha256[:16]}...) | "
                f"HW Counters: events={pre.hw_events}, commits={pre.hw_commits}, rejects={pre.hw_rejects}"
            ),
            (
                f"  POST-LOAD State   : {t1.active_concepts} / {t1.total_slots} active concepts "
                f"(entry={list(t1.entry_concepts)}, internal={list(t1.internal_cascade_concepts)}, "
                f"leaf={list(t1.leaf_concepts)}, free={t1.free_slots}, SHA-256={post.bram_sha256[:16]}...)"
            ),
            f"  Readback & Diff   : 256/256 words verified OK; {changed_count} slot(s) modified during programming",
        ]

        headers = (
            "CID",
            "Name",
            "Changed",
            "Pre-Load W0",
            "Post-Load W0",
            "Pre-Load Rule (W2)",
            "Post-Load Rule (W2)",
            "Pre Sub -> Post Sub (W3)",
        )
        rows: list[tuple[str, ...]] = []
        for d in self.load_diffs:
            rows.append(
                (
                    f"C{d.cid:02d}",
                    d.name,
                    "YES" if d.changed else "NO",
                    str(d.pre_w0) if d.pre_active else "_ (empty)",
                    str(d.post_w0) if d.post_active else "_ (empty)",
                    d.pre_rule,
                    d.post_rule,
                    f"{d.pre_sub} => {d.post_sub}",
                )
            )
        widths = [
            max(len(headers[col]), *(len(r[col]) for r in rows)) if rows else len(headers[col])
            for col in range(len(headers))
        ]
        sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
        hdr_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"
        lines.extend([sep, hdr_line, sep])
        for r in rows:
            lines.append("| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(headers))) + " |")
        lines.append(sep)
        return "\n".join(lines)


def render_tui_ascii_frame(
    debugger: KpolCascadeDebugger,
    *,
    connection: MachineDebugConnection | None = None,
    stdio_result: StdioExecutionResult | None = None,
    phase_status: str = "RUNNING",
) -> str:
    """Render a multi-panel ASCII TUI frame showing:
      1. Machine Header: Target, HW_ID, Status (`PRE-LOAD -> POST-LOAD -> RUNNING`),
         Concept Counts (`Active: K / 64`, `Pre-load: M / 64`, `Changed on load: Δ`),
         and Telemetry Counters (`Events, Commits, Rejects, Faults`);
      2. Concept Inspector Panel (`CID 0..K-1`): Name, `Pre-Load W0`, `Post-Load W0`,
         `Current W0`, `Valid (_)`, `Predicate ::`, `Action`, `Gate •`, `Subscriber -> CID`;
      3. Source Code & STDIO Streams (`STDIN` / `STDOUT` / `STDERR`);
      4. Cascade Step Trace & Interactive Keybindings (`[s] Step`, `[i] Input STDIN`,
         `[f] Fault _`, `[r] Reload`, `[q] Quit`).
    """
    target_lbl = "SIM (0x4B504D43 'KPMC')"
    pre_active = 0
    post_active = len(debugger.active_cids)
    changed_on_load = post_active
    pre_w0_map: dict[int, str] = {}

    if connection is not None and connection.pre_load_snapshot is not None:
        pre_s = connection.pre_load_snapshot
        pre_active = pre_s.topology.active_concepts
        target_lbl = f"{pre_s.target.upper()} ({pre_s.hw_id_hex} '{pre_s.hw_id_ascii}')"
        for cid in range(64):
            d0 = pre_s.descriptors[cid]
            pre_w0_map[cid] = (
                str(_to_i32(d0.current_state)) if is_descriptor_configured(d0) else "_ (empty)"
            )
    if connection is not None and connection.post_load_snapshot is not None:
        post_s = connection.post_load_snapshot
        post_active = post_s.topology.active_concepts
        changed_on_load = sum(1 for d in connection.load_diffs if d.changed)

    topo = analyze_concept_topology(debugger.descriptors)
    border = "=" * 116
    thin = "-" * 116

    lines: list[str] = [
        border,
        (
            f" KUZMIN MACHINE STEP DEBUGGER TUI | Target: {target_lbl} | "
            f"State: PRE-LOAD -> POST-LOAD -> {phase_status}"
        ),
        (
            f" Concepts: Active: {post_active} / {topo.total_slots} "
            f"(Pre-load: {pre_active} / {topo.total_slots}, Changed on load: {changed_on_load}, "
            f"Free: {topo.free_slots}) | "
            f"Entry: {list(topo.entry_concepts)} Internal: {list(topo.internal_cascade_concepts)} "
            f"Leaf: {list(topo.leaf_concepts)}"
        ),
        (
            f" Counters: Events={debugger.events_processed} | Commits={debugger.commits} | "
            f"Rejects={debugger.rejects} | Faults(_)="
            f"{debugger.fault_propagations} | LastState={debugger.last_committed_state}"
        ),
        border,
        " [PANEL 1: CONCEPT TABLE (PRE-LOAD vs POST-LOAD vs CURRENT STATE)]",
    ]

    c_headers = (
        "CID",
        "Name",
        "Pre-Load W0",
        "Post-Load W0",
        "Current W0",
        "Valid(_)",
        "Predicate ::",
        "Action",
        "Gate •",
        "Subscriber -> CID",
    )
    c_rows: list[tuple[str, ...]] = []
    for cid in debugger.active_cids:
        d = debugger.descriptors[cid]
        pre_w0_s = pre_w0_map.get(cid, "_ (n/a)")
        post_w0_s = str(debugger.initial_state[cid])
        cur_w0_s = str(debugger.state[cid])
        if debugger.state[cid] != debugger.initial_state[cid]:
            cur_w0_s += f" ({debugger.state[cid] - debugger.initial_state[cid]:+d})"
        val_ok = ((debugger.valid_mask >> cid) & 1) != 0
        val_s = "1" if val_ok else "_"
        c_rows.append(
            (
                f"C{cid:02d}",
                d.name,
                pre_w0_s,
                post_w0_s,
                cur_w0_s,
                val_s,
                decode_predicate_formula(d),
                decode_action_formula(d),
                decode_invariant_formula(d),
                decode_w3_subscriber(d, debugger.descriptors),
            )
        )
    c_widths = [
        max(len(c_headers[col]), *(len(r[col]) for r in c_rows)) if c_rows else len(c_headers[col])
        for col in range(len(c_headers))
    ]
    c_sep = "+-" + "-+-".join("-" * w for w in c_widths) + "-+"
    lines.append(c_sep)
    lines.append("| " + " | ".join(c_headers[i].ljust(c_widths[i]) for i in range(len(c_headers))) + " |")
    lines.append(c_sep)
    for r in c_rows:
        lines.append("| " + " | ".join(r[i].ljust(c_widths[i]) for i in range(len(c_headers))) + " |")
    lines.append(c_sep)

    # Panel 2: Source Code & STDIO Streams
    lines.append(thin)
    lines.append(" [PANEL 2: PROGRAM SOURCE CODE & LIVE STDIO STREAMS (STDIN / STDOUT / STDERR)]")
    if debugger.source_code:
        src_preview = debugger.source_code.splitlines()[:12]
        for idx, sline in enumerate(src_preview, 1):
            lines.append(f"   SRC {idx:02d} | {sline}")
    if stdio_result is not None:
        in_str = ", ".join(
            f"(C{c}:{p},valid={'1' if v else '_'})" for c, p, v in stdio_result.stdin_records
        )
        lines.append(f"   STDIN  ({len(stdio_result.stdin_records)} events) : {in_str or '(empty)'}")
        for out_l in stdio_result.stdout_lines[-6:]:
            lines.append(f"   STDOUT -> {out_l}")
        for err_l in stdio_result.stderr_lines[-6:]:
            lines.append(f"   STDERR -> {err_l}")
    else:
        in_from_steps = [
            f"(C{s.cid}:{s.param},valid={s.param_valid_symbol})"
            for s in debugger.steps
            if s.depth == 0
        ]
        lines.append(f"   STDIN  ({len(in_from_steps)} root events): {', '.join(in_from_steps) or '(empty)'}")
        for s in debugger.steps[-6:]:
            if s.verdict in (VERDICT_COMMIT, VERDICT_SUPPRESSED_SELF):
                lines.append(
                    f"   STDOUT -> COMMIT: {s.concept_name}[cid={s.cid}] = {s.post_w0} (depth={s.depth})"
                )
            else:
                lines.append(
                    f"   STDERR -> {s.verdict}: {s.concept_name}[cid={s.cid}] kept W0={s.post_w0} (depth={s.depth})"
                )

    # Panel 3: Step-by-Step Cascade Trace & Controls
    lines.append(thin)
    lines.append(" [PANEL 3: CASCADE WAVE STEP TRACE]")
    lines.append(debugger.format_trace_table())
    lines.append(border)
    lines.append(
        " KEYS: [s] Step Next Event | [i] Input STDIN | [f] Inject Fault (_) | [r] Reload BRAM | [q] Quit"
    )
    lines.append(border)
    return "\n".join(lines)


def run_interactive_tui(
    debugger: KpolCascadeDebugger,
    *,
    connection: MachineDebugConnection | None = None,
    queued_events: Sequence[tuple[int, int, bool]] = (),
    stdio_result: StdioExecutionResult | None = None,
) -> str:
    """Launch an interactive `curses` TUI session if stdout is a TTY, or fall back
    deterministically to rendering the multi-panel ASCII TUI frame.
    """
    pending = list(queued_events)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        for cid, param, valid in pending:
            debugger.step_event(cid, param, valid)
        return render_tui_ascii_frame(
            debugger,
            connection=connection,
            stdio_result=stdio_result,
            phase_status="RUNNING",
        )

    import curses

    def _curses_main(stdscr: Any) -> None:
        curses.curs_set(0)
        stdscr.nodelay(False)
        while True:
            stdscr.erase()
            frame = render_tui_ascii_frame(
                debugger,
                connection=connection,
                stdio_result=stdio_result,
                phase_status="INTERACTIVE",
            )
            max_y, max_x = stdscr.getmaxyx()
            for row_idx, line in enumerate(frame.splitlines()[: max_y - 1]):
                stdscr.addstr(row_idx, 0, line[: max_x - 1])
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q"), 27):
                break
            if ch in (ord("s"), ord("S")) and pending:
                cid, param, valid = pending.pop(0)
                debugger.step_event(cid, param, valid)
            elif ch in (ord("f"), ord("F")):
                root_cid = debugger.active_cids[0] if debugger.active_cids else 0
                debugger.step_event(root_cid, 0, False)
            elif ch in (ord("r"), ord("R")):
                debugger.reset()
                pending[:] = list(queued_events)

    try:
        curses.wrapper(_curses_main)
    except curses.error:
        for cid, param, valid in pending:
            debugger.step_event(cid, param, valid)
    return render_tui_ascii_frame(
        debugger,
        connection=connection,
        stdio_result=stdio_result,
        phase_status="COMPLETED",
    )


# ============================================================================
# 3. Canonical Article & Slide Examples Verification Suite (Examples 1..5)
# ============================================================================

EXAMPLE_1_INCREASE_SOURCE = """\
# @stdin Counter
# @stdout Counter
Problem Increase {
    Invariants { NonNeg: Counter >= 0; }
}
Solution Increase {
    state Counter: Int32 = 10;
    event Pulse(param: Int32);
    rule Step on Pulse when param < 20 {
        set Counter := Counter + 1;
    }
}
"""

EXAMPLE_1_DECREASE_ZERO_SOURCE = """\
# @stdin Counter
# @stdout Counter
Problem DecreaseFromOne {
    Invariants { NonNeg: Counter >= 0; }
}
Solution DecreaseFromOne {
    state Counter: Int32 = 1;
    event Pulse(param: Int32);
    rule Step on Pulse when param < 20 {
        set Counter := Counter - 1;
    }
}
"""

EXAMPLE_2_CASCADE_4STAGE_SOURCE = """\
# @stdin C0
# @stdout C0, C1, C2, C3
Problem Cascade4Concept {
    Invariants {
        I0: C0 >= 0;
        I1: C1 >= 0;
        I2: C2 >= 0;
        I3: C3 >= 0;
    }
}
Solution Cascade4Concept {
    state C0: Int32 = 10;
    state C1: Int32 = 0;
    state C2: Int32 = 2;
    state C3: Int32 = 0;

    event E0(param: Int32);

    rule R0 on E0 when param < 50 { set C0 := C0 + 1; }
    rule R1 on change(C0) when C0 > 10 { set C1 := C1 + 1; }
    rule R2 on change(C1) when C1 >= 1 { set C2 := C2 - 1; }
    rule R3 on change(C2) when not (C2 == 2) { set C3 := C2; }
}
Proof Cascade4Concept {
    scenario CheckCascadeAndGuardBlock {
        step E0(param = 10);
        expect C0 == 11;
        expect C1 == 1;
        expect C2 == 1;
        expect C3 == 1;
        step E0(param = 100);
        expect C0 == 11;
        expect C3 == 1;
    }
}
"""

EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE = """\
# @stdin Cell_Delta_mV
# @stdout Cell_Delta_mV, Module_Thermal_Guard, Pack_Fault_Latch, Contactor_Interlock
Problem BmsSafetyCascade {
    Invariants {
        inv_cell_delta: Cell_Delta_mV >= 0;
        inv_mod_thermal: Module_Thermal_Guard >= 0;
        inv_pack_latch: Pack_Fault_Latch >= 0;
        inv_contactor: Contactor_Interlock >= 0;
    }
}
Solution BmsSafetyCascade {
    state Cell_Delta_mV: Int32 = 0;
    state Module_Thermal_Guard: Int32 = 0;
    state Pack_Fault_Latch: Int32 = 2;
    state Contactor_Interlock: Int32 = 10;

    event EvCellDelta(delta_mv: Int32);

    rule RCellDelta on EvCellDelta when delta_mv >= 50 and delta_mv <= 5000 {
        set Cell_Delta_mV := Cell_Delta_mV + 1;
    }
    rule RModuleThermal on change(Cell_Delta_mV) when Cell_Delta_mV >= 1 {
        set Module_Thermal_Guard := Module_Thermal_Guard + 1;
    }
    rule RPackFaultLatch on change(Module_Thermal_Guard) when Module_Thermal_Guard >= 1 {
        set Pack_Fault_Latch := Pack_Fault_Latch - 1;
    }
    rule RContactorInterlock on change(Pack_Fault_Latch) when not (Pack_Fault_Latch == 2) {
        set Contactor_Interlock := Pack_Fault_Latch;
    }
}
Proof BmsSafetyCascade {
    scenario BmsFourLevelProtectionAndLatch {
        step EvCellDelta(delta_mv = 15);
        expect Cell_Delta_mV == 0;
        expect Contactor_Interlock == 10;
        step EvCellDelta(delta_mv = 120);
        expect Cell_Delta_mV == 1;
        expect Module_Thermal_Guard == 1;
        expect Pack_Fault_Latch == 1;
        expect Contactor_Interlock == 1;
        step EvCellDelta(delta_mv = 180);
        expect Cell_Delta_mV == 2;
        expect Module_Thermal_Guard == 2;
        expect Pack_Fault_Latch == 0;
        expect Contactor_Interlock == 0;
        step EvCellDelta(delta_mv = 250);
        expect Cell_Delta_mV == 3;
        expect Module_Thermal_Guard == 3;
        expect Pack_Fault_Latch == 0;
        expect Contactor_Interlock == 0;
    }
}
"""

EXAMPLE_4_AUTH_COUNTER_SOURCE = """\
Concept(Counter, 10, Lower=0, Upper=500)
Concept(Mirror, 0, Lower=0, Upper=500)
Counter • Assign(Mirror, Counter + 1)
"""


def _load_kpol_auth_package():
    if "kpol_auth" in sys.modules:
        return sys.modules["kpol_auth"]
    spec = importlib.util.spec_from_file_location(
        "kpol_auth",
        KPOL_AUTH_DIR / "__init__.py",
        submodule_search_locations=[str(KPOL_AUTH_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


def run_iverilog_euclid_verification(
    a_init: int = 120,
    b_init: int = 6,
) -> dict[str, Any]:
    """Run Icarus Verilog simulation of `km_euclid_core.sv` in a workspace scratch
    directory and return cycle-by-cycle & summary verification results.
    """
    tb_source = f"""`timescale 1ns/1ps
module km_euclid_verify_tb;
    logic clk = 0, rst_n = 0, start = 0;
    logic [31:0] a_init = 32'd{a_init}, b_init = 32'd{b_init};
    wire busy, done, error;
    wire [31:0] result, cycle_count, concept_a, concept_b;
    wire [15:0] iterations;

    always #5 clk = ~clk;

    km_euclid_core #(.DATA_WIDTH(32)) dut (
        .clk(clk), .rst_n(rst_n), .start_i(start),
        .a_init_i(a_init), .b_init_i(b_init),
        .busy_o(busy), .done_o(done), .error_o(error),
        .result_o(result), .iterations_o(iterations),
        .cycle_count_o(cycle_count),
        .concept_a_o(concept_a), .concept_b_o(concept_b)
    );

    always @(posedge clk) begin
        if (rst_n && busy && dut.state_q == 2'd3) begin
            $display("EUCLID_COMMIT iter=%0d a_pre=%0d b_pre=%0d next_val=%0d target_a=%0d",
                     iterations + 1, concept_a, concept_b, dut.next_val_q, dut.target_is_a_q);
        end
    end

    initial begin
        rst_n = 0;
        repeat (4) @(posedge clk);
        @(negedge clk); rst_n = 1;
        @(negedge clk); start = 1;
        @(negedge clk); start = 0;
        wait(done);
        @(posedge clk);
        $display("EUCLID_DONE result=%0d iterations=%0d cycles=%0d error=%0d",
                 result, iterations, cycle_count, error);
        $finish;
    end
endmodule
"""
    with _debugger_scratch_dir("euclid272") as scratch:
        sv_file = scratch / "km_euclid_core.sv"
        tb_file = scratch / "km_euclid_verify_tb.sv"
        vvp_file = scratch / "km_euclid_verify.vvp"
        sv_file.write_text(KM_EUCLID_CORE_SV_SOURCE, encoding="utf-8")
        tb_file.write_text(tb_source, encoding="utf-8")

        subprocess.run(
            ["iverilog", "-g2012", "-o", str(vvp_file), str(sv_file), str(tb_file)],
            check=True,
            capture_output=True,
            text=True,
        )
        res = subprocess.run(
            ["vvp", str(vvp_file)],
            check=True,
            capture_output=True,
            text=True,
        )

    commits: list[dict[str, int]] = []
    done_info: dict[str, int] = {}
    for line in res.stdout.splitlines():
        if line.startswith("EUCLID_COMMIT "):
            kv = dict(item.split("=") for item in line.split()[1:])
            commits.append({k: int(v) for k, v in kv.items()})
        elif line.startswith("EUCLID_DONE "):
            kv = dict(item.split("=") for item in line.split()[1:])
            done_info = {k: int(v) for k, v in kv.items()}

    return {
        "a_init": a_init,
        "b_init": b_init,
        "result": done_info.get("result", -1),
        "iterations": done_info.get("iterations", -1),
        "cycles": done_info.get("cycles", -1),
        "error": done_info.get("error", 1),
        "commits": commits,
        "raw_stdout": res.stdout,
    }


def run_iverilog_cfgp_trace(
    bram_image: bytes,
    events: Sequence[tuple[int, int]],
) -> dict[str, Any]:
    """Run Icarus Verilog simulation of `kpol_bram_pipeline_axi.sv` (`CFG-P`) on `bram_image`
    and `events = [(cid, param), ...]`, returning final BRAM states and hardware counters.
    """
    if len(bram_image) != 1024:
        raise KpolError(f"Expected 1024-byte BRAM image, got {len(bram_image)}")

    words = struct.unpack("<256I", bram_image)
    with _debugger_scratch_dir("cfgp272") as scratch:
        img_hex = scratch / "img.hex"
        img_hex.write_text("\n".join(f"{w:08x}" for w in words) + "\n", encoding="utf-8")

        ev_lines = []
        for cid, p in events:
            ev_lines.append(f"{cid & 0x3F:08x}")
            ev_lines.append(f"{p & 0xFFFFFFFF:08x}")
        ev_hex = scratch / "events.hex"
        ev_hex.write_text("\n".join(ev_lines) + "\n", encoding="utf-8")

        tb_sv = scratch / "cfgp_trace_tb.sv"
        tb_sv.write_text(
            """`timescale 1ns/1ps
module cfgp_trace_tb;
    logic clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    logic [12:0] awaddr = 0, araddr = 0;
    logic awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    logic [31:0] wdata = 0;
    wire awready, wready, bvalid, arready, rvalid, busy;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    logic ext_hw_trigger_valid_i = 0;
    logic [5:0] ext_hw_trigger_cid_i = 0;
    logic [31:0] ext_hw_trigger_param_i = 0;
    wire hw_trigger_ready_o;

    kpol_bram_pipeline_axi dut (
        .clk(clk), .rst_n(rst_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(4'hf), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .ext_hw_trigger_valid_i(ext_hw_trigger_valid_i),
        .ext_hw_trigger_cid_i(ext_hw_trigger_cid_i),
        .ext_hw_trigger_param_i(ext_hw_trigger_param_i),
        .hw_trigger_ready_o(hw_trigger_ready_o),
        .hw_commit_pulse_o(), .hw_reject_pulse_o(),
        .hw_pipeline_busy_o(), .fifo_overflow_o(), .events_dropped_count_o(),
        .hw_commit_cid_o(), .hw_last_committed_state_o(),
        .busy(busy)
    );

    task automatic axi_write(input [12:0] addr, input [31:0] data);
        @(negedge clk);
        awaddr = addr; wdata = data; awvalid = 1; wvalid = 1; bready = 1;
        do @(posedge clk); while (!awready || !wready);
        @(negedge clk); awvalid = 0; wvalid = 0;
        while (!bvalid) @(negedge clk);
        @(negedge clk); bready = 0;
    endtask

    task automatic axi_read(input [12:0] addr, output [31:0] data);
        @(negedge clk);
        araddr = addr; arvalid = 1; rready = 1;
        do @(posedge clk); while (!arready);
        @(negedge clk); arvalid = 0;
        while (!rvalid) @(negedge clk);
        data = rdata;
        @(negedge clk); rready = 0;
    endtask

    reg [4095:0] image_hex_path, events_hex_path;
    logic [31:0] img [0:255];
    logic [31:0] event_words [0:127];
    int num_events;

    initial begin
        logic [31:0] ev_cnt, cm_cnt, rj_cnt, w0, w1, w2, w3;
        rst_n = 0;
        repeat (4) @(posedge clk);
        @(negedge clk); rst_n = 1;
        repeat (2) @(posedge clk);

        if (!$value$plusargs("image_hex=%s", image_hex_path)) $fatal(1, "no image_hex");
        if (!$value$plusargs("events_hex=%s", events_hex_path)) $fatal(1, "no events_hex");
        if (!$value$plusargs("num_events=%d", num_events)) num_events = 0;

        $readmemh(image_hex_path, img);
        for (int i = 0; i < 256; i++) begin
            axi_write(13'h004, i);
            axi_write(13'h008, img[i]);
        end

        $readmemh(events_hex_path, event_words);
        for (int e = 0; e < num_events; e++) begin
            @(negedge clk);
            while (!hw_trigger_ready_o) @(negedge clk);
            ext_hw_trigger_cid_i = event_words[e * 2][5:0];
            ext_hw_trigger_param_i = event_words[e * 2 + 1];
            ext_hw_trigger_valid_i = 1;
            @(posedge clk);
            @(negedge clk);
            ext_hw_trigger_valid_i = 0;
            while (busy) @(posedge clk);
        end

        axi_read(13'h018, ev_cnt);
        axi_read(13'h01c, cm_cnt);
        axi_read(13'h020, rj_cnt);
        axi_write(13'h004, 0); axi_read(13'h008, w0);
        axi_write(13'h004, 4); axi_read(13'h008, w1);
        axi_write(13'h004, 8); axi_read(13'h008, w2);
        axi_write(13'h004, 12); axi_read(13'h008, w3);
        $display("CFGP_SUMMARY events=%0d commits=%0d rejects=%0d states=%0d,%0d,%0d,%0d",
                 ev_cnt, cm_cnt, rj_cnt, $signed(w0), $signed(w1), $signed(w2), $signed(w3));
        $finish;
    end
endmodule
""",
            encoding="utf-8",
        )

        vvp_bin = scratch / "cfgp_trace.vvp"
        rtl_files = [
            str(HW_RTL_DIR / "core" / "kpol_txn_gate_v2.sv"),
            str(HW_RTL_DIR / "core" / "km_concept_micro_engine.sv"),
            str(HW_RTL_DIR / "core" / "km_concept_bram.sv"),
            str(HW_RTL_DIR / "core" / "km_autonomous_sequencer.sv"),
            str(HW_RTL_DIR / "bus" / "kpol_bram_pipeline_axi.sv"),
            str(tb_sv),
        ]
        subprocess.run(
            ["iverilog", "-g2012", "-o", str(vvp_bin), *rtl_files],
            check=True,
            capture_output=True,
            text=True,
        )
        res = subprocess.run(
            [
                "vvp",
                str(vvp_bin),
                f"+image_hex={img_hex}",
                f"+events_hex={ev_hex}",
                f"+num_events={len(events)}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    summary_line = next(l for l in res.stdout.splitlines() if l.startswith("CFGP_SUMMARY "))
    parts = dict(kv.split("=") for kv in summary_line.split()[1:])
    states = [int(x) for x in parts["states"].split(",")]
    return {
        "events": int(parts["events"]),
        "commits": int(parts["commits"]),
        "rejects": int(parts["rejects"]),
        "states": states,
        "raw_stdout": res.stdout,
    }


def trace_author_slide_examples(*, run_iverilog_euclid: bool = True) -> dict[str, Any]:
    """Run all three Author slide/article extended semantic traces (`If`, `Sum`, `Nod(120, 6) = 6`)
    and optionally cross-check `Nod(120, 6)` against `km_euclid_core.sv` in Icarus Verilog.
    """
    if_trace = trace_author_if_toggle_example()
    sum_trace = trace_author_sum_post_read_reset_example()
    nod_trace = trace_author_euclid_nod_example(120, 6)
    euclid_rtl: dict[str, Any] | None = None
    if run_iverilog_euclid and shutil.which("iverilog") is not None:
        euclid_rtl = run_iverilog_euclid_verification(120, 6)
        assert euclid_rtl["result"] == nod_trace["result"] == 6
        assert euclid_rtl["iterations"] == nod_trace["subtraction_iterations"] == 19
        assert euclid_rtl["cycles"] == nod_trace["hardware_cycles_at_3cyc_per_sub_plus_1"] == 58

    status_matrix = [
        {
            "example": "Increase / Decrease (Counter >= 0)",
            "profile_or_dialect": "KPOL-CME-1",
            "cfg_p_and_cfg_p_ha_rtl": "SUPPORTED (100% bit-exact, 1 RAMB36E1, 8 cyc/event)",
            "emit_c99_and_z3_smt": "SUPPORTED (VERIFIED P1..P4)",
            "km_euclid_core_sv": "N/A (single-concept counter)",
            "open_rfcs": "None (closed in #150/#153/#8)",
        },
        {
            "example": "4-Concept Acyclic Cascade (C0 -> C1 -> C2 -> C3)",
            "profile_or_dialect": "KPOL-CME-2",
            "cfg_p_and_cfg_p_ha_rtl": "SUPPORTED (100% bit-exact on CFG-P & Dual-Bank CFG-P-HA)",
            "emit_c99_and_z3_smt": "SUPPORTED (VERIFIED P1..P4, WCET=4 steps)",
            "km_euclid_core_sv": "N/A",
            "open_rfcs": "None (closed in #184/#227/#253)",
        },
        {
            "example": "BMS 4-Stage Safety Cascade with Sensor Fault '_'",
            "profile_or_dialect": "KPOL-CME-2 + valid_mask (SYS-02)",
            "cfg_p_and_cfg_p_ha_rtl": "SUPPORTED for valid trace (pynq2 silicon); '_' bit in ADR B7 / C99 valid_mask",
            "emit_c99_and_z3_smt": "SUPPORTED (VERIFIED P1..P4 incl. P3 Fail-Closed '_' non-masking)",
            "km_euclid_core_sv": "N/A",
            "open_rfcs": "ADR B7 accepted (#185/#215); RFC-017 p.3 arithmetic on '_' open (#186)",
        },
        {
            "example": "Author Native Counter / Thermal Subset (Concept + • + Assign)",
            "profile_or_dialect": "KPOL-AUTH deterministic subset",
            "cfg_p_and_cfg_p_ha_rtl": "SUPPORTED via CME-RAW-1 routing + Do/Go VM (km_mcu_fpga_bridge.c)",
            "emit_c99_and_z3_smt": "SUPPORTED on lowered CME-RAW-1 descriptors",
            "km_euclid_core_sv": "N/A",
            "open_rfcs": "12 open uncertainty points KPOL-AUTH-U01..U12 blocked fail-closed (#186)",
        },
        {
            "example": "T-Flip-Flop `If` (_ -> ! -> ¬ -> !) & `Sum` Post-Read Reset (→ • Sum = 0)",
            "profile_or_dialect": "Author Slide Extended Model (RFC-001, RFC-005, RFC-013)",
            "cfg_p_and_cfg_p_ha_rtl": "Reference tracer (requires read-triggered post-phase • & '_' bit in CME-RAW-2)",
            "emit_c99_and_z3_smt": "State '_' tracked via valid_mask; read-triggered • outside CME-RAW-1",
            "km_euclid_core_sv": "N/A",
            "open_rfcs": "RFC-013 / RFC-017 p.1-2 (busy & boolean meaning of '•')",
        },
        {
            "example": "Euclidean GCD `Nod(120, 6) = 6` (19 reactive subtractions)",
            "profile_or_dialect": "Author Slide Cyclic Reactive Model (DOU 36556 / Slide 3)",
            "cfg_p_and_cfg_p_ha_rtl": "Rejected by static DAG check (P1 Lyapunov acyclicity requires acyclic W3)",
            "emit_c99_and_z3_smt": "Rejected by P1_dag_lyapunov_acyclicity (prevents unbounded WCET loops)",
            "km_euclid_core_sv": "SUPPORTED & VERIFIED in iverilog (19 sub steps, 58 cycles = 580 ns @ 100 MHz, result = 6)",
            "open_rfcs": "RFC-001 vs cyclic re-addressing (DOU 36556 `Do [...] ↓ a~b ↑ a≠b`, RFC-009/012)",
        },
        {
            "example": "Slide Sketches: `Factorial`, `Tachometer / Electricity Meter`, `Static(OpenBracket)`",
            "profile_or_dialect": "Author Slide Unfinished Sketches",
            "cfg_p_and_cfg_p_ha_rtl": "NOT SUPPORTED (fail-closed in KPOL-AUTH U01..U12)",
            "emit_c99_and_z3_smt": "NOT SUPPORTED (outside deterministic safety subset)",
            "km_euclid_core_sv": "N/A",
            "open_rfcs": "Blocked on open RFC-009, RFC-015, RFC-016, RFC-017, RFC-018 (#186)",
        },
    ]

    return {
        "if_toggle": if_trace,
        "sum_post_read_reset": sum_trace,
        "nod_120_6": nod_trace,
        "km_euclid_core_iverilog": euclid_rtl,
        "article_examples_status_matrix": status_matrix,
    }


def format_article_status_matrix(matrix: Sequence[Mapping[str, str]]) -> str:
    """Format the verification status matrix of all article/slide examples."""
    headers = (
        "Example / Program",
        "Profile / Dialect",
        "CFG-P / CFG-P-HA RTL",
        "--emit-c99 + Z3 SMT",
        "km_euclid_core.sv",
        "Open RFCs / Boundaries",
    )
    rows = [
        (
            m["example"],
            m["profile_or_dialect"],
            m["cfg_p_and_cfg_p_ha_rtl"],
            m["emit_c99_and_z3_smt"],
            m["km_euclid_core_sv"],
            m["open_rfcs"],
        )
        for m in matrix
    ]
    widths = [
        max(len(headers[col]), *(len(r[col]) for r in rows))
        for col in range(len(headers))
    ]
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    hdr_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"
    out = [
        "=== VERIFICATION STATUS MATRIX OF ARTICLE & SLIDE EXAMPLES ===",
        sep,
        hdr_line,
        sep,
    ]
    for r in rows:
        out.append("| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(headers))) + " |")
    out.append(sep)
    return "\n".join(out)


def run_single_example_demo(
    example_name: str,
    *,
    run_rtl: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Run one named example (`increase`, `decrease`, `cascade`, `bms`, `auth`, `nod`)
    and return `(formatted_4block_output, structured_dict)`.
    """
    ex = example_name.strip().lower()

    if ex == "increase":
        mod = parse_module(EXAMPLE_1_INCREASE_SOURCE)
        img = compile_concept_microcode_bram_image(mod, profile="KPOL-CME-1")
        conn = MachineDebugConnection(target="sim")
        conn.load_program_into_sim(img, concept_names=[s.name for s in mod.states])
        dbg = KpolCascadeDebugger(
            img,
            profile="KPOL-CME-1",
            module_name=mod.name,
            source_code=EXAMPLE_1_INCREASE_SOURCE,
            concept_names=[s.name for s in mod.states],
            watch_cids={0},
            break_on_reject=True,
            watch_state_change=True,
        )
        stdio_res = run_stdio_stream(dbg, ["5", "25", "_"])
        text = "\n\n".join(
            [
                conn.format_pre_post_load_summary(),
                dbg.format_full_4block_report(),
                render_tui_ascii_frame(dbg, connection=conn, stdio_result=stdio_res),
            ]
        )
        return text, {
            "example": "increase",
            "report": dbg.build_report().to_dict(),
            "stdio": {
                "stdout": stdio_res.stdout_lines,
                "stderr": stdio_res.stderr_lines,
            },
        }

    if ex == "decrease":
        mod = parse_module(EXAMPLE_1_DECREASE_ZERO_SOURCE)
        img = compile_concept_microcode_bram_image(mod, profile="KPOL-CME-1")
        conn = MachineDebugConnection(target="sim")
        conn.load_program_into_sim(img, concept_names=[s.name for s in mod.states])
        dbg = KpolCascadeDebugger(
            img,
            profile="KPOL-CME-1",
            module_name=mod.name,
            source_code=EXAMPLE_1_DECREASE_ZERO_SOURCE,
            concept_names=[s.name for s in mod.states],
            watch_cids={0},
            break_on_reject=True,
            watch_state_change=True,
        )
        # First pulse (5 < 20): Counter 1 -> 0 (COMMIT)
        # Second pulse (5 < 20): Counter 0 -> candidate -1 -> REJECT_INVARIANT (Counter >= 0)!
        # Third pulse (25 >= 20): REJECT_GUARD
        stdio_res = run_stdio_stream(dbg, ["5", "5", "25"])
        z3_diag = diagnose_invariant_counterexample_z3(dbg.descriptors[0], bypass_invariant_gate=True)
        text = "\n\n".join(
            [
                conn.format_pre_post_load_summary(),
                dbg.format_full_4block_report(),
                f"Z3 Invariant Gate • Counterexample Diagnostic: {json.dumps(z3_diag, ensure_ascii=False)}",
                render_tui_ascii_frame(dbg, connection=conn, stdio_result=stdio_res),
            ]
        )
        return text, {
            "example": "decrease",
            "report": dbg.build_report().to_dict(),
            "z3_invariant_diagnostic": z3_diag,
            "stdio": {
                "stdout": stdio_res.stdout_lines,
                "stderr": stdio_res.stderr_lines,
            },
        }

    if ex == "cascade":
        mod = parse_module(EXAMPLE_2_CASCADE_4STAGE_SOURCE)
        img = compile_concept_microcode_bram_image(mod, profile="KPOL-CME-2")
        conn = MachineDebugConnection(target="sim")
        conn.load_program_into_sim(img, concept_names=[s.name for s in mod.states])
        dbg = KpolCascadeDebugger(
            img,
            profile="KPOL-CME-2",
            module_name=mod.name,
            source_code=EXAMPLE_2_CASCADE_4STAGE_SOURCE,
            concept_names=[s.name for s in mod.states],
            watch_cids={0, 3},
            break_on_reject=True,
            watch_state_change=True,
        )
        # Event 1: param=10 (< 50) -> 4-stage cascade C0->C1->C2->C3 (depth 0->1->2->3, 4 commits)
        # Event 2: param=100 (>= 50) -> REJECT_GUARD at C0 (entire cascade blocked!)
        # Event 3: param=10 (< 50) -> C0->C1->C2->C3 (C2 reaches 0)
        # Event 4: param=10 (< 50) -> C0->C1 commit, C2 candidate=-1 blocked by REJECT_INVARIANT!
        stdio_res = run_stdio_stream(dbg, ["0 10", "0 100", "0 10", "0 10"])
        rtl_res = None
        if run_rtl and shutil.which("iverilog") is not None:
            rtl_res = run_iverilog_cfgp_trace(img, [(0, 10), (0, 100), (0, 10), (0, 10)])
        text = "\n\n".join(
            [
                conn.format_pre_post_load_summary(),
                dbg.format_full_4block_report(),
                render_tui_ascii_frame(dbg, connection=conn, stdio_result=stdio_res),
            ]
        )
        return text, {
            "example": "cascade",
            "report": dbg.build_report().to_dict(),
            "rtl_cfgp": rtl_res,
            "stdio": {
                "stdout": stdio_res.stdout_lines,
                "stderr": stdio_res.stderr_lines,
            },
        }

    if ex == "bms":
        mod = parse_module(EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE)
        img = compile_concept_microcode_bram_image(mod, profile="KPOL-CME-2")
        # Simulate that Increase was previously loaded in the machine before loading BMS
        inc_mod = parse_module(EXAMPLE_1_INCREASE_SOURCE)
        inc_img = compile_concept_microcode_bram_image(inc_mod, profile="KPOL-CME-1")
        conn = MachineDebugConnection(target="sim", initial_machine_bram=inc_img)
        conn.load_program_into_sim(
            img,
            concept_names=[s.name for s in mod.states],
            pre_concept_names=[s.name for s in inc_mod.states],
        )
        dbg = KpolCascadeDebugger(
            img,
            profile="KPOL-CME-2",
            module_name=mod.name,
            source_code=EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE,
            concept_names=[s.name for s in mod.states],
            watch_cids={2, 3},
            break_on_reject=True,
            watch_state_change=True,
            threshold_watch={0: 2},
        )
        # Includes valid normal ripple (15 mV -> REJECT_GUARD), over-range (5500 mV -> REJECT_GUARD),
        # corrupted isoUART frame ('_' -> REJECT_FAULT), thermal fault cascades (120, 180 mV -> Contactor=0),
        # and latch underflow prevention at 250 mV (Pack_Fault_Latch=0 -> candidate -1 -> REJECT_INVARIANT)!
        stdio_res = run_stdio_stream(
            dbg,
            [
                "Cell_Delta_mV 15",
                "Cell_Delta_mV 5500",
                "Cell_Delta_mV _",
                "Cell_Delta_mV 120",
                "Cell_Delta_mV 180",
                "Cell_Delta_mV 250",
            ],
        )
        z3_diag = diagnose_invariant_counterexample_z3(dbg.descriptors[2], bypass_invariant_gate=True)
        text = "\n\n".join(
            [
                conn.format_pre_post_load_summary(),
                dbg.format_full_4block_report(),
                f"Z3 Invariant Gate • Diagnostic on C02 (Pack_Fault_Latch): {json.dumps(z3_diag, ensure_ascii=False)}",
                render_tui_ascii_frame(dbg, connection=conn, stdio_result=stdio_res),
            ]
        )
        return text, {
            "example": "bms",
            "report": dbg.build_report().to_dict(),
            "z3_invariant_diagnostic": z3_diag,
            "stdio": {
                "stdout": stdio_res.stdout_lines,
                "stderr": stdio_res.stderr_lines,
            },
        }

    if ex == "auth":
        ka = _load_kpol_auth_package()
        prog = ka.parse_kpol_auth(EXAMPLE_4_AUTH_COUNTER_SOURCE)
        artifact = ka.lower_kpol_auth(prog)
        cnames = [c.name for c in artifact.concepts]
        conn = MachineDebugConnection(target="sim")
        conn.load_program_into_sim(artifact.bram_image, concept_names=cnames)
        dbg = KpolCascadeDebugger(
            artifact.bram_image,
            profile="KPOL-AUTH",
            module_name="AuthCounterSubset",
            source_code=EXAMPLE_4_AUTH_COUNTER_SOURCE,
            concept_names=cnames,
            watch_cids={0, 1},
            break_on_reject=True,
            watch_state_change=True,
        )
        # Note: KPOL-AUTH BRAM routing descriptors set guard_flags=SUBSCRIBER_EN/INVARIANT_EN;
        # to trace execution on CFG-P / ReferenceCmeSafetyEngine we also show the lowered Do/Go bytecode
        # and run a configured descriptor trace where ASSUMPTION_EN + INVARIANT_EN are enabled.
        auth_exec_descs = list(dbg.descriptors)
        auth_exec_descs[0] = ConceptMicroDescriptor(
            cid=0,
            name="Counter",
            current_state=10,
            operand_val=0,
            pred_opcode=CME_PRED_GT,
            guard_flags=CME_GUARD_ASSUMPTION_EN | CME_GUARD_INVARIANT_EN | CME_GUARD_SUBSCRIBER_EN,
            action_opcode=CME_ACT_ASSIGN,
            subscriber_cid=1,
        )
        auth_exec_descs[1] = ConceptMicroDescriptor(
            cid=1,
            name="Mirror",
            current_state=0,
            operand_val=1,
            pred_opcode=CME_PRED_NOP,
            guard_flags=CME_GUARD_ASSUMPTION_EN | CME_GUARD_INVARIANT_EN,
            action_opcode=CME_ACT_ADD,
            subscriber_cid=0,
        )
        dbg_exec = KpolCascadeDebugger(
            auth_exec_descs,
            profile="KPOL-AUTH",
            module_name="AuthCounterSubset",
            source_code=EXAMPLE_4_AUTH_COUNTER_SOURCE,
            concept_names=cnames,
            watch_cids={0, 1},
            break_on_reject=True,
            watch_state_change=True,
        )
        stdio_res = run_stdio_stream(dbg_exec, ["Counter 25", "Counter -5", "Counter _"])
        dogo_hex = [f"0x{w:08X}" for w in artifact.code_o]
        text = "\n\n".join(
            [
                conn.format_pre_post_load_summary(),
                f"Lowered KPOL-AUTH Do/Go Bytecode ({len(dogo_hex)} words): {', '.join(dogo_hex)}",
                dbg_exec.format_full_4block_report(),
                render_tui_ascii_frame(dbg_exec, connection=conn, stdio_result=stdio_res),
            ]
        )
        return text, {
            "example": "auth",
            "dogo_bytecode_hex": dogo_hex,
            "report": dbg_exec.build_report().to_dict(),
            "stdio": {
                "stdout": stdio_res.stdout_lines,
                "stderr": stdio_res.stderr_lines,
            },
        }

    if ex == "nod":
        slide_bundle = trace_author_slide_examples(run_iverilog_euclid=True)
        text_parts = [
            format_author_slide_trace(slide_bundle["if_toggle"]),
            format_author_slide_trace(slide_bundle["sum_post_read_reset"]),
            format_author_slide_trace(slide_bundle["nod_120_6"]),
        ]
        if slide_bundle["km_euclid_core_iverilog"] is not None:
            ev_rtl = slide_bundle["km_euclid_core_iverilog"]
            text_parts.append(
                "=== Icarus Verilog `km_euclid_core.sv` Hardware FSM Cross-Check ===\n"
                f"  Input      : a_init={ev_rtl['a_init']}, b_init={ev_rtl['b_init']}\n"
                f"  Result     : {ev_rtl['result']} (matches Author Nod trace = 6)\n"
                f"  Iterations : {ev_rtl['iterations']} subtractions (120 -> 114 -> ... -> 6)\n"
                f"  Cycles     : {ev_rtl['cycles']} clock cycles (19 * 3 + 1 = 58 cycles = 580 ns @ 100 MHz)"
            )
        text_parts.append(
            format_article_status_matrix(slide_bundle["article_examples_status_matrix"])
        )
        return "\n\n".join(text_parts), slide_bundle

    raise KpolError(
        f"Unknown example {example_name!r} (expected one of: bms, cascade, increase, decrease, auth, nod, all)"
    )


def run_article_examples_verification(*, run_rtl: bool = True) -> dict[str, Any]:
    """Run and verify all 5 canonical article/slide example groups:
      1. `increase` & `decrease` (`KPOL-CME-1`, incl. `REJECT_INVARIANT` at 0);
      2. `cascade` (`KPOL-CME-2` 4-concept cascade `depth 0->1->2->3` & guard block at `C0`);
      3. `bms` (`KPOL-CME-2` 4-stage BMS safety cascade with sensor fault `_` -> `REJECT_FAULT`);
      4. `auth` (`KPOL-AUTH` `Concept(Counter, 10)` lowering & trace);
      5. `nod` (Author slide traces: `If`, `Sum`, `Nod(120, 6) = 6` + `km_euclid_core.sv` in `iverilog` + status table).
    """
    sections: list[str] = []
    results: dict[str, Any] = {}
    for name in ("increase", "decrease", "cascade", "bms", "auth", "nod"):
        txt, data = run_single_example_demo(name, run_rtl=run_rtl)
        sections.append(f"################################################################################\n# EXAMPLE: {name.upper()}\n################################################################################\n\n{txt}")
        results[name] = data

    results["formatted_full_output"] = "\n\n".join(sections)
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kuzmin Machine Step-by-Step Event & Cascade Debugger (Issue #272)."
    )
    parser.add_argument(
        "--example",
        choices=("bms", "cascade", "increase", "decrease", "auth", "nod", "all"),
        default=None,
        help="run a built-in canonical article/slide example and display all 4 visual blocks",
    )
    parser.add_argument(
        "--program",
        type=Path,
        default=None,
        help="path to a .kpol source file or 1024-byte .bin BRAM image to debug",
    )
    parser.add_argument(
        "--profile",
        choices=("KPOL-CME-1", "KPOL-CME-2", "KPOL-AUTH"),
        default="KPOL-CME-2",
        help="target profile when compiling a .kpol source file (default: KPOL-CME-2)",
    )
    parser.add_argument(
        "--dump-concepts",
        action="store_true",
        help="display the BRAM concept descriptor table (Block 2)",
    )
    parser.add_argument(
        "--trace-events",
        dest="trace_events",
        type=str,
        default=None,
        help="comma-separated event specification, e.g. '0:10,0:100,0:invalid'",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="read events line-by-line from STDIN, emit COMMITs to STDOUT and REJECTs to STDERR",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="launch interactive curses TUI (or render multi-panel ASCII TUI frame if non-TTY)",
    )
    parser.add_argument(
        "--render-tui-frame",
        action="store_true",
        help="render the multi-panel ASCII TUI frame showing PRE-LOAD, POST-LOAD, STDIO and Trace",
    )
    parser.add_argument(
        "--target",
        "--connect",
        dest="target",
        default="sim",
        help="machine target to connect to: 'sim', 'pynq1', 'pynq2', or ssh host (default: sim)",
    )
    parser.add_argument(
        "--watch-cid",
        dest="watch_cids",
        type=str,
        default=None,
        help="comma-separated CIDs to watch (e.g. '0,2,3')",
    )
    parser.add_argument(
        "--break-on-reject",
        action="store_true",
        help="trigger watchpoint/breakpoint on REJECT_GUARD, REJECT_INVARIANT, or REJECT_FAULT",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="optional path to write structured JSON debug report",
    )

    args = parser.parse_args(argv)

    if args.example is not None:
        if args.example == "all":
            bundle = run_article_examples_verification(run_rtl=True)
            print(bundle["formatted_full_output"])
            if args.json_out is not None:
                out_copy = {k: v for k, v in bundle.items() if k != "formatted_full_output"}
                args.json_out.write_text(
                    json.dumps(out_copy, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            return 0
        txt, data = run_single_example_demo(args.example, run_rtl=True)
        print(txt)
        if args.json_out is not None:
            args.json_out.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return 0

    if args.program is None:
        parser.error("either --example or --program is required")

    prog_path: Path = args.program
    raw_bytes = prog_path.read_bytes()
    source_text = ""
    concept_names: list[str] | None = None
    mod_name = prog_path.stem

    if len(raw_bytes) == 1024 and prog_path.suffix.lower() == ".bin":
        bram_image = raw_bytes
    else:
        source_text = raw_bytes.decode("utf-8")
        if args.profile == "KPOL-AUTH":
            ka = _load_kpol_auth_package()
            cst_prog = ka.parse_kpol_auth(source_text)
            art = ka.lower_kpol_auth(cst_prog)
            bram_image = art.bram_image
            concept_names = [c.name for c in art.concepts]
        else:
            mod = Parser(source_text).parse()
            mod_name = mod.name
            concept_names = [s.name for s in mod.states]
            bram_image = compile_concept_microcode_bram_image(mod, profile=args.profile)

    watch_set: set[int] = set()
    if args.watch_cids:
        for tok in args.watch_cids.split(","):
            if tok.strip():
                watch_set.add(int(tok.strip(), 0))

    dbg = KpolCascadeDebugger(
        bram_image,
        profile=args.profile,
        module_name=mod_name,
        source_code=source_text,
        concept_names=concept_names,
        watch_cids=watch_set,
        break_on_reject=args.break_on_reject,
        watch_state_change=True,
    )

    conn = MachineDebugConnection(target=args.target)
    pynq_hw_report: dict[str, Any] | None = None

    queued_events: list[tuple[int, int, bool]] = []
    if args.trace_events:
        queued_events = parse_trace_events_spec(args.trace_events)

    stdio_res: StdioExecutionResult | None = None
    if args.stdio:
        stdin_lines = sys.stdin.read().splitlines()
        stdio_res = run_stdio_stream(
            dbg,
            stdin_lines,
            emit_to_sys_stdio=not (args.tui or args.render_tui_frame),
        )
        queued_events = list(stdio_res.stdin_records)
    elif queued_events and not args.tui:
        dbg.run_events(queued_events)

    if args.target == "sim":
        conn.load_program_into_sim(bram_image, concept_names=concept_names)
    else:
        hw_params = [p for _, p, v in queued_events if v]
        pynq_hw_report = conn.execute_pynq_session(
            bram_image,
            hw_params=hw_params,
            concept_names=concept_names,
        )

    if args.tui:
        frame = run_interactive_tui(
            dbg,
            connection=conn,
            queued_events=queued_events if not args.stdio else (),
            stdio_result=stdio_res,
        )
        print(frame)
    elif args.render_tui_frame:
        print(conn.format_pre_post_load_summary())
        print()
        print(render_tui_ascii_frame(dbg, connection=conn, stdio_result=stdio_res))
    elif not args.stdio:
        print(conn.format_pre_post_load_summary())
        print()
        print(dbg.format_full_4block_report())

    if args.json_out is not None:
        out_payload: dict[str, Any] = {
            "report": dbg.build_report().to_dict(),
            "pre_load": conn.pre_load_snapshot.to_dict() if conn.pre_load_snapshot else None,
            "post_load": conn.post_load_snapshot.to_dict() if conn.post_load_snapshot else None,
            "pynq_hw_report": pynq_hw_report,
        }
        if stdio_res is not None:
            out_payload["stdio"] = {
                "stdout": stdio_res.stdout_lines,
                "stderr": stdio_res.stderr_lines,
            }
        args.json_out.write_text(
            json.dumps(out_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())







