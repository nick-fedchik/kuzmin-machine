"""Derived engineering lowering backend for a deterministic subset of KPOL-AUTH CST.

IMPORTANT ATTRIBUTION NOTE (AGENTS.md §6.1):
This module is a derived engineering backend (M. Fedchik / engineering agents),
NOT an Author specification by M. Yu. Kuzmin. It lowers a deterministic subset of
KPOL-AUTH CST into:
  1) 32-bit Do/Go stack-VM bytecode (`code_o`) and subscription tables (`km_sub_t`)
     bit-compatible with `Engineering/sw/runtime/mcu/km_mcu_fpga_bridge.c`;
  2) 1024-byte `CME-RAW-1` BRAM routing descriptors (`W0..W3`, 64 x 16 bytes)
     compatible with `Engineering/specifications/kpol/kpol-cme2-profile-0.1.0.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

from .cst import (
    BracketGroupCST,
    BinaryExprCST,
    CSTNode,
    CallOrConstructCST,
    IdentifierCST,
    LiteralCST,
    ProgramCST,
    SubscriptionSeqCST,
)
from .uncertainty import Span

# --- C99 VM constants (km_mcu_fpga_bridge.c) ---
KM_MAX_CONCEPTS = 64
KM_MAX_SUBSCRIPTIONS = 128
KM_MAX_INSTRUCTIONS = 512

KM_OPC_NOP = 0x0
KM_OPC_GO = 0x1
KM_OPC_DO = 0x2
KM_OPC_IMM = 0x3
KM_OPC_EXIT = 0x5

KM_GO_EXEC = 0x0
KM_GO_WRITE = 0x1
KM_GO_READ = 0x2

KM_FLAG_SELF_SUPPRESS = 0x01
KM_FLAG_HW_PROTECTED = 0x08

KM_DO_ADD = 0
KM_DO_SUB = 1
KM_DO_MUL = 2

KM_EV_POSITIVE = 1 << 2
KM_EV_CHANGED = 1 << 6
KM_EV_ALWAYS = 1 << 7

KM_PHASE_PRE_WRITE = 0
KM_PHASE_POST_CHANGE = 1
KM_PHASE_ON_READ = 2
KM_PHASE_ON_EXEC = 3
KM_PHASE_ON_ABORT = 4

# --- CME-RAW-1 BRAM constants ---
CME_SLOT_COUNT = 64
CME_IMAGE_BYTES = 1024
CME_GUARD_INVARIANT_EN = 0x02
CME_GUARD_SUBSCRIBER_EN = 0x10

_BINOP_TO_DO = {
    "PLUS": KM_DO_ADD,
    "MINUS": KM_DO_SUB,
    "STAR": KM_DO_MUL,
}


def km_pack_instr(opc: int, sub_op: int, flags: int, operand: int) -> int:
    """Pack a 32-bit Do/Go instruction word matching km_pack_instr in km_mcu_fpga_bridge.c."""
    return (
        ((opc & 0x0F) << 28)
        | ((sub_op & 0x0F) << 24)
        | ((flags & 0xFF) << 16)
        | (operand & 0xFFFF)
    )


class KpolAuthLoweringError(Exception):
    """Fail-closed error raised when CST is outside the deterministic lowering subset."""

    def __init__(self, code: str, message: str, span: Span | None = None) -> None:
        self.code = code
        self.message = message
        self.span = span
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class LoweredConcept:
    cid: int
    name: str
    init_val: int
    flags: int
    lower_bound: int | None
    upper_bound: int | None
    first_sub_idx: int
    sub_count: int


@dataclass(frozen=True)
class LoweredSubscription:
    sub_idx: int
    owner_cid: int
    target_cid: int
    phase: int
    trigger_mask: int
    line_start_pc: int
    line_len: int


@dataclass(frozen=True)
class LoweredArtifact:
    concepts: tuple[LoweredConcept, ...]
    subscriptions: tuple[LoweredSubscription, ...]
    code_o: tuple[int, ...]
    bram_image: bytes


def _parse_int32(node: CSTNode) -> int:
    if not isinstance(node, LiteralCST) or node.token.kind != "INT":
        raise KpolAuthLoweringError(
            "KPOL-LOWER-LITERAL",
            "Очікувався цілочисельний літерал.",
            node.span,
        )
    val = int(node.token.value)
    if val < -2147483648 or val > 2147483647:
        raise KpolAuthLoweringError(
            "KPOL-LOWER-RANGE",
            f"Значення {val} виходить за межі Int32.",
            node.span,
        )
    return val


def _emit_expr(
    node: CSTNode,
    concept_by_name: dict[str, int],
    out_words: list[int],
) -> None:
    if isinstance(node, BracketGroupCST) and node.kind == "collection_paren":
        if len(node.elements) != 1:
            raise KpolAuthLoweringError(
                "KPOL-LOWER-EXPR",
                "Дужковий вираз повинен містити рівно один елемент.",
                node.span,
            )
        _emit_expr(node.elements[0], concept_by_name, out_words)
        return

    if isinstance(node, LiteralCST) and node.token.kind == "INT":
        val = int(node.token.value)
        if val < -32768 or val > 32767:
            raise KpolAuthLoweringError(
                "KPOL-LOWER-RANGE",
                f"Константа {val} не вміщується у 16-бітний знаковий операнд KM_OPC_IMM.",
                node.span,
            )
        out_words.append(km_pack_instr(KM_OPC_IMM, 0, 0, val & 0xFFFF))
        return

    if isinstance(node, IdentifierCST):
        name = node.token.value
        if name not in concept_by_name:
            raise KpolAuthLoweringError(
                "KPOL-LOWER-UNKNOWN-CONCEPT",
                f"Невідомий концепт '{name}' у виразі.",
                node.span,
            )
        cid = concept_by_name[name]
        out_words.append(km_pack_instr(KM_OPC_GO, KM_GO_READ, 0, cid))
        return

    if isinstance(node, BinaryExprCST):
        sub_op = _BINOP_TO_DO.get(node.op_token.kind)
        if sub_op is None:
            raise KpolAuthLoweringError(
                "KPOL-LOWER-UNSUPPORTED-OP",
                f"Оператор '{node.op_token.value}' не підтримується в Do/Go lowering.",
                node.op_token.span,
            )
        _emit_expr(node.left, concept_by_name, out_words)
        _emit_expr(node.right, concept_by_name, out_words)
        out_words.append(km_pack_instr(KM_OPC_DO, sub_op, 0, 0))
        return

    raise KpolAuthLoweringError(
        "KPOL-LOWER-UNSUPPORTED-CST",
        f"Конструкція '{type(node).__name__}' поза детермінованою підмножиною виразів.",
        node.span,
    )


def _extract_assigns(node: CSTNode) -> list[CallOrConstructCST]:
    if isinstance(node, CallOrConstructCST) and node.name.token.value == "Assign":
        return [node]
    if isinstance(node, BracketGroupCST):
        assigns: list[CallOrConstructCST] = []
        for el in node.elements:
            if not isinstance(el, CallOrConstructCST) or el.name.token.value != "Assign":
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-UNSUPPORTED-CST",
                    "Очікувався виклик Assign(Dst, Expr) у блоці підписки.",
                    el.span,
                )
            assigns.append(el)
        if not assigns:
            raise KpolAuthLoweringError(
                "KPOL-LOWER-EMPTY-SUB",
                "Порожній блок підписки не допускається.",
                node.span,
            )
        return assigns
    raise KpolAuthLoweringError(
        "KPOL-LOWER-UNSUPPORTED-CST",
        "Права частина підписки повинна мати вигляд Assign(Dst, Expr).",
        node.span,
    )


def lower_kpol_auth(program: ProgramCST) -> LoweredArtifact:
    """Lower a deterministic KPOL-AUTH CST into Do/Go bytecode and CME-RAW-1 BRAM."""
    if program.diagnostics:
        first_diag = program.diagnostics[0]
        raise KpolAuthLoweringError(
            "KPOL-LOWER-UNCERTAINTY",
            f"Присутня незакрита точка невизначеності/діагностика: {first_diag.code}.",
            first_diag.span,
        )

    raw_concepts: list[tuple[str, int, int, int | None, int | None]] = []
    concept_by_name: dict[str, int] = {}
    pending_subs: list[tuple[int, int, int, int, list[int]]] = []

    for item in program.items:
        if isinstance(item, CallOrConstructCST) and item.name.token.value == "Concept":
            els = item.group.elements
            if len(els) < 2 or not isinstance(els[0], IdentifierCST):
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-CONCEPT",
                    "Concept(...) вимагає (Name, Init[, Lower=..., Upper=...]).",
                    item.span,
                )
            cname = els[0].token.value
            if cname in concept_by_name:
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-DUPLICATE-CONCEPT",
                    f"Повторне оголошення концепту '{cname}'.",
                    els[0].span,
                )
            if len(raw_concepts) >= KM_MAX_CONCEPTS:
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-LIMIT",
                    f"Перевищено ліміт концептів ({KM_MAX_CONCEPTS}).",
                    item.span,
                )
            init_val = _parse_int32(els[1])
            lower_b: int | None = None
            upper_b: int | None = None
            for opt in els[2:]:
                if (
                    not isinstance(opt, BinaryExprCST)
                    or opt.op_token.kind != "EQ"
                    or not isinstance(opt.left, IdentifierCST)
                ):
                    raise KpolAuthLoweringError(
                        "KPOL-LOWER-CONCEPT",
                        "Непідтримуваний параметр Concept(...).",
                        opt.span,
                    )
                key = opt.left.token.value
                if key == "Lower":
                    lower_b = _parse_int32(opt.right)
                elif key == "Upper":
                    upper_b = _parse_int32(opt.right)
                else:
                    raise KpolAuthLoweringError(
                        "KPOL-LOWER-CONCEPT",
                        f"Невідомий параметр Concept '{key}'.",
                        opt.span,
                    )
            flags = KM_FLAG_HW_PROTECTED if (lower_b is not None or upper_b is not None) else 0
            if lower_b is not None and upper_b is not None and lower_b > upper_b:
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-RANGE",
                    f"Нижня межа ({lower_b}) більша за верхню ({upper_b}).",
                    item.span,
                )
            cid = len(raw_concepts)
            concept_by_name[cname] = cid
            raw_concepts.append((cname, init_val, flags, lower_b, upper_b))
            continue

        if isinstance(item, SubscriptionSeqCST):
            if isinstance(item.left, IdentifierCST):
                src_name = item.left.token.value
                phase = KM_PHASE_POST_CHANGE
                trigger_mask = KM_EV_CHANGED
            elif (
                isinstance(item.left, CallOrConstructCST)
                and item.left.name.token.value in ("OnAbort", "OnPositive")
                and len(item.left.group.elements) == 1
                and isinstance(item.left.group.elements[0], IdentifierCST)
            ):
                src_name = item.left.group.elements[0].token.value
                if item.left.name.token.value == "OnAbort":
                    phase = KM_PHASE_ON_ABORT
                    trigger_mask = KM_EV_ALWAYS
                else:
                    phase = KM_PHASE_POST_CHANGE
                    trigger_mask = KM_EV_POSITIVE
            else:
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-UNSUPPORTED-CST",
                    "Ліва частина підписки повинна бути Concept, OnPositive(Concept) або OnAbort(Concept).",
                    item.left.span,
                )

            if src_name not in concept_by_name:
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-UNKNOWN-CONCEPT",
                    f"Невідомий концепт-джерело '{src_name}'.",
                    item.left.span,
                )
            owner_cid = concept_by_name[src_name]

            assigns = _extract_assigns(item.right)
            for assign in assigns:
                if len(assign.group.elements) != 2 or not isinstance(
                    assign.group.elements[0], IdentifierCST
                ):
                    raise KpolAuthLoweringError(
                        "KPOL-LOWER-ASSIGN",
                        "Assign вимагає рівно 2 аргументи: (DstConcept, Expr).",
                        assign.span,
                    )
                dst_name = assign.group.elements[0].token.value
                if dst_name not in concept_by_name:
                    raise KpolAuthLoweringError(
                        "KPOL-LOWER-UNKNOWN-CONCEPT",
                        f"Невідомий цільовий концепт '{dst_name}'.",
                        assign.group.elements[0].span,
                    )
                dst_cid = concept_by_name[dst_name]
                words: list[int] = []
                _emit_expr(assign.group.elements[1], concept_by_name, words)
                words.append(km_pack_instr(KM_OPC_GO, KM_GO_WRITE, 0, dst_cid))
                words.append(km_pack_instr(KM_OPC_EXIT, 0, 0, 0))
                pending_subs.append((owner_cid, dst_cid, phase, trigger_mask, words))
            continue

        raise KpolAuthLoweringError(
            "KPOL-LOWER-UNSUPPORTED-CST",
            f"Конструкція '{type(item).__name__}' не підтримується в lowering.",
            item.span,
        )

    if len(pending_subs) > KM_MAX_SUBSCRIPTIONS:
        raise KpolAuthLoweringError(
            "KPOL-LOWER-LIMIT",
            f"Перевищено ліміт підписок ({KM_MAX_SUBSCRIPTIONS}).",
        )

    # Group subscriptions by owner_cid to match km_concept_t(first_sub_idx, sub_count)
    subs_by_owner: dict[int, list[tuple[int, int, int, int, list[int]]]] = {
        cid: [] for cid in range(len(raw_concepts))
    }
    for sub_entry in pending_subs:
        subs_by_owner[sub_entry[0]].append(sub_entry)

    code_o: list[int] = []
    lowered_subs: list[LoweredSubscription] = []
    lowered_concepts: list[LoweredConcept] = []

    for cid, (cname, init_val, flags, lower_b, upper_b) in enumerate(raw_concepts):
        owner_subs = subs_by_owner[cid]
        first_sub_idx = len(lowered_subs) if owner_subs else 0
        sub_count = len(owner_subs)
        lowered_concepts.append(
            LoweredConcept(
                cid=cid,
                name=cname,
                init_val=init_val,
                flags=flags,
                lower_bound=lower_b,
                upper_bound=upper_b,
                first_sub_idx=first_sub_idx,
                sub_count=sub_count,
            )
        )
        for owner_cid, dst_cid, phase, trigger_mask, words in owner_subs:
            start_pc = len(code_o)
            code_o.extend(words)
            if len(code_o) > KM_MAX_INSTRUCTIONS:
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-LIMIT",
                    f"Перевищено ліміт інструкцій code_o ({KM_MAX_INSTRUCTIONS}).",
                )
            lowered_subs.append(
                LoweredSubscription(
                    sub_idx=len(lowered_subs),
                    owner_cid=owner_cid,
                    target_cid=dst_cid,
                    phase=phase,
                    trigger_mask=trigger_mask,
                    line_start_pc=start_pc,
                    line_len=len(words),
                )
            )

    # Build 1024-byte CME-RAW-1 BRAM routing image (64 slots x 16 bytes)
    bram_chunks: list[bytes] = []
    for cid in range(CME_SLOT_COUNT):
        if cid < len(lowered_concepts):
            c = lowered_concepts[cid]
            post_subs = [
                s
                for s in lowered_subs
                if s.owner_cid == cid and s.phase == KM_PHASE_POST_CHANGE
            ]
            if len(post_subs) > 1:
                raise KpolAuthLoweringError(
                    "KPOL-LOWER-FANOUT",
                    f"Концепт C{cid} ('{c.name}') має {len(post_subs)} POST_CHANGE підписок; CME-RAW-1 підтримує fan-out <= 1.",
                )
            guard_flags = CME_GUARD_INVARIANT_EN if (c.flags & KM_FLAG_HW_PROTECTED) else 0
            subscriber_cid = 0
            if len(post_subs) == 1:
                dst_cid = post_subs[0].target_cid
                if dst_cid <= cid:
                    raise KpolAuthLoweringError(
                        "KPOL-LOWER-CYCLE",
                        f"Порушення ациклічності каскаду BRAM: dst_cid ({dst_cid}) <= src_cid ({cid}).",
                    )
                guard_flags |= CME_GUARD_SUBSCRIBER_EN
                subscriber_cid = dst_cid

            word0 = c.init_val & 0xFFFFFFFF
            word1 = 0
            word2 = (guard_flags & 0xFF) << 8
            word3 = subscriber_cid & 0xFFFFFFFF
            bram_chunks.append(struct.pack("<4I", word0, word1, word2, word3))
        else:
            bram_chunks.append(struct.pack("<4I", 0, 0, 0, 0))

    bram_image = b"".join(bram_chunks)
    assert len(bram_image) == CME_IMAGE_BYTES

    return LoweredArtifact(
        concepts=tuple(lowered_concepts),
        subscriptions=tuple(lowered_subs),
        code_o=tuple(code_o),
        bram_image=bram_image,
    )
