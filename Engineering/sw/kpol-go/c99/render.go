package c99

import (
	"fmt"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

const (
	defaultVerdictLabel = "VERIFIED"
	defaultSolverLabel  = "Z3 SMT QF_LIA + QF_BV BitVec32"
)

const tplHeaderScope = ` *
 * Scope of Z3 SMT verification (prove_c99_descriptor_safety_z3):
 *   1. P1: Strict DAG acyclicity (Lyapunov rank[src] < rank[dst]) and topological schedule
 *      consistency of parsed KM_SAFETY_TOPO_ORDER against all W3 subscription edges.
 *   2. P2: Structural & BitVec(32) invariant preservation (state >= 0 and no signed 32-bit
 *      overflow on commit) for the parsed C99 descriptor table and gate expression.
 *   3. P3: Fail-Closed non-masking of invalid sensor inputs (!ev_param_valid || !concept_valid)
 *      in the parsed C99 transition template.
 *   4. P4: BitVec(32) miter equivalence between the input CFG-P descriptor specification
 *      and the parsed C99 descriptor table & predicate/action/guard expressions
 *      (template-level SMT verification, complemented by differential execution of the
 *      GCC-compiled binary against CFG-P RTL simulation and Zynq-7020 PL silicon).
 *
 * MISRA-C99 oriented design notes (single-header static inline inclusion model;
 * structural subset, not certified by an external MISRA static checker):
 *   - Zero dynamic memory allocation (no malloc/calloc/free)
 *   - Zero recursion
 *   - Zero data-dependent unbounded while loops (bounded topological cascade pass, WCET = O(K))
 *   - Two's-complement arithmetic performed in uint32_t with portable km_u32_to_i32 helper
 * ============================================================================ */

`

const tplDefines = `#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define KM_SAFETY_NUM_CONCEPTS       64u
`

const tplOpcodes = `#define KM_SAFETY_VALID_MASK_ALL_OK  0xFFFFFFFFFFFFFFFFULL

/* --- Concept Micro-Engine Predicate Opcodes (CME-RAW-1) --- */
#define KM_CME_PRED_NOP              0x00u
#define KM_CME_PRED_EQ               0x01u
#define KM_CME_PRED_NEQ              0x02u
#define KM_CME_PRED_GT               0x03u
#define KM_CME_PRED_LT               0x04u
#define KM_CME_PRED_RANGE            0x05u
#define KM_CME_PRED_BITMASK          0x06u

/* --- Concept Micro-Engine Action Opcodes (CME-RAW-1) --- */
#define KM_CME_ACT_ASSIGN            0x00u
#define KM_CME_ACT_INC               0x01u
#define KM_CME_ACT_DEC               0x02u
#define KM_CME_ACT_ADD               0x03u
#define KM_CME_ACT_SUB               0x04u

/* --- Concept Micro-Engine Guard Flags (CME-RAW-1) --- */
#define KM_CME_GUARD_ASSUMPTION_EN   0x01u
#define KM_CME_GUARD_INVARIANT_EN    0x02u
#define KM_CME_GUARD_HAZARD_EN       0x04u
#define KM_CME_GUARD_INVERT          0x08u
#define KM_CME_GUARD_SUBSCRIBER_EN   0x10u

/* --- Active Concept Symbolic Identifiers --- */
typedef enum {
`

const tplTypes = `    KM_CID_MAX_LIMIT = 64u
} km_safety_cid_t;

/* --- Step Execution Status Codes --- */
typedef enum {
    KM_SAFETY_STEP_COMMITTED         = 0,
    KM_SAFETY_STEP_REJECTED_GUARD    = 1,
    KM_SAFETY_STEP_REJECTED_FAULT    = 2,
    KM_SAFETY_STEP_REJECTED_BAD_CID  = 3
} km_safety_status_t;

/* --- Immutable 16-Byte Concept Descriptor (W0..W3) --- */
typedef struct {
    int32_t  init_state;
    uint32_t operand;
    uint8_t  pred_opcode;
    uint8_t  guard_flags;
    uint8_t  hazard_limit;
    uint8_t  action_opcode;
    uint32_t subscriber_cid;
} km_safety_desc_t;

/* --- Deterministic Safety State Context --- */
typedef struct {
    int32_t  state[64];
    uint64_t valid_mask;
    uint32_t events_processed;
    uint32_t commits;
    uint32_t rejects;
    uint32_t fault_propagations;
    int32_t  last_committed_state;
} km_safety_ctx_t;

/* --- Per-Event Cascade Step Telemetry --- */
typedef struct {
    uint32_t           steps_executed;
    uint32_t           commits;
    uint32_t           rejects;
    bool               fault_propagated;
    int32_t            last_state;
    km_safety_status_t status;
} km_safety_step_result_t;

/* --- Verified Topological Order of Active Concepts (Strict DAG) --- */
static const uint8_t KM_SAFETY_TOPO_ORDER[KM_SAFETY_NUM_ACTIVE_TOPO] = {
`

const tplTableHead = `
};

/* --- Verified 64-Slot Descriptor Table (CME-RAW-1) --- */
static const km_safety_desc_t KM_SAFETY_DESCRIPTORS[KM_SAFETY_NUM_CONCEPTS] = {
`

const tplBody = `
};

/* --- Portable Two's-Complement Conversions (Avoids implementation-defined casts) --- */
static inline int32_t km_u32_to_i32(uint32_t u) {
    return (u <= 0x7FFFFFFFu) ? (int32_t)u : (-1 - (int32_t)(0xFFFFFFFFu - u));
}

static inline int32_t km_u16_to_i32_sext(uint16_t u16) {
    return (u16 <= 0x7FFFu) ? (int32_t)u16 : (-1 - (int32_t)(0xFFFFu - (uint32_t)u16));
}

/* --- Context Initialization --- */
static inline void km_safety_init(km_safety_ctx_t *ctx) {
    uint32_t idx;
    if (ctx == NULL) {
        return;
    }
    for (idx = 0u; idx < KM_SAFETY_NUM_CONCEPTS; ++idx) {
        ctx->state[idx] = KM_SAFETY_DESCRIPTORS[idx].init_state;
    }
    ctx->valid_mask           = KM_SAFETY_VALID_MASK_ALL_OK;
    ctx->events_processed     = 0u;
    ctx->commits              = 0u;
    ctx->rejects              = 0u;
    ctx->fault_propagations   = 0u;
    ctx->last_committed_state = 0;
}

/* --- Explicit Uncertainty ('_') / Sensor Fault Injection & Recovery --- */
static inline void km_safety_invalidate_concept(km_safety_ctx_t *ctx, uint8_t cid) {
    if ((ctx == NULL) || (cid >= KM_SAFETY_NUM_CONCEPTS)) {
        return;
    }
    ctx->valid_mask &= ~(1ULL << cid);
}

static inline void km_safety_revalidate_concept(km_safety_ctx_t *ctx, uint8_t cid, int32_t recovered_state) {
    if ((ctx == NULL) || (cid >= KM_SAFETY_NUM_CONCEPTS)) {
        return;
    }
    if (recovered_state < 0) {
        ctx->valid_mask &= ~(1ULL << cid);
        return;
    }
    ctx->state[cid]  = recovered_state;
    ctx->valid_mask |= (1ULL << cid);
}

/* --- Single-Concept Micro-Engine & Transaction Gate v2 Evaluation --- */
static inline bool km_safety_eval_single_cid(
    km_safety_ctx_t *ctx,
    uint8_t cid,
    int32_t ev_param,
    bool ev_param_valid,
    uint8_t *next_cid_out,
    bool *trigger_next_out,
    bool *fault_rejected_out
) {
    const km_safety_desc_t *d = &KM_SAFETY_DESCRIPTORS[cid];
    uint32_t param_u32        = (uint32_t)ev_param;
    uint32_t cur_u32          = (uint32_t)ctx->state[cid];
    uint32_t cand_u32         = cur_u32;
    int32_t  op_i32           = km_u32_to_i32(d->operand);
    bool     pred_raw         = false;
    bool     action_valid     = true;
    bool     arith_overflow   = false;
    bool     assumption_known = false;
    bool     assumption_true  = false;
    bool     invariant_known  = false;
    bool     invariant_true   = false;
    bool     hazard_true      = false;
    bool     commit           = false;
    bool     concept_valid    = ((ctx->valid_mask & (1ULL << cid)) != 0ULL);

    *next_cid_out       = 0u;
    *trigger_next_out   = false;
    *fault_rejected_out = false;

    ctx->events_processed++;

    /* 1. Fail-Closed Uncertainty / Sensor Fault Gate (No zero-masking) */
    if ((!ev_param_valid) || (!concept_valid)) {
        ctx->rejects++;
        ctx->fault_propagations++;
        *fault_rejected_out = true;
        return false;
    }

    /* 2. Decode Predicate Micro-Opcode (km_concept_micro_engine.sv §2) */
    switch (d->pred_opcode) {
        case KM_CME_PRED_NOP:
            pred_raw = true;
            break;
        case KM_CME_PRED_EQ:
            pred_raw = (param_u32 == d->operand);
            break;
        case KM_CME_PRED_NEQ:
            pred_raw = (param_u32 != d->operand);
            break;
        case KM_CME_PRED_GT:
            pred_raw = (ev_param > op_i32);
            break;
        case KM_CME_PRED_LT:
            pred_raw = (ev_param < op_i32);
            break;
        case KM_CME_PRED_RANGE: {
            int32_t lo_i32 = km_u16_to_i32_sext((uint16_t)(d->operand & 0xFFFFu));
            int32_t hi_i32 = km_u16_to_i32_sext((uint16_t)((d->operand >> 16) & 0xFFFFu));
            pred_raw = (ev_param >= lo_i32) && (ev_param <= hi_i32);
            break;
        }
        case KM_CME_PRED_BITMASK:
            pred_raw = ((param_u32 & d->operand) != 0u);
            break;
        default:
            pred_raw = false;
            break;
    }

    /* 3. Compute Candidate State & Two's-Complement Overflow (km_concept_micro_engine.sv §3) */
    switch (d->action_opcode) {
        case KM_CME_ACT_ASSIGN:
            cand_u32 = param_u32;
            break;
        case KM_CME_ACT_INC:
            cand_u32       = cur_u32 + 1u;
            arith_overflow = (cur_u32 == 0x7FFFFFFFu);
            break;
        case KM_CME_ACT_DEC:
            cand_u32       = cur_u32 - 1u;
            arith_overflow = (cur_u32 == 0x80000000u);
            break;
        case KM_CME_ACT_ADD:
            cand_u32       = cur_u32 + d->operand;
            arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) == 0u) &&
                             (((cand_u32 ^ cur_u32) & 0x80000000u) != 0u);
            break;
        case KM_CME_ACT_SUB:
            cand_u32       = cur_u32 - d->operand;
            arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) != 0u) &&
                             (((cand_u32 ^ cur_u32) & 0x80000000u) != 0u);
            break;
        default:
            cand_u32     = cur_u32;
            action_valid = false;
            break;
    }

    /* 4. Evaluate Guards & Transaction Gate v2 (kpol_txn_gate_v2.sv) */
    assumption_known = ((d->guard_flags & KM_CME_GUARD_ASSUMPTION_EN) != 0u);
    assumption_true  = ((d->guard_flags & KM_CME_GUARD_INVERT) != 0u) ? (!pred_raw) : pred_raw;
    invariant_known  = ((d->guard_flags & KM_CME_GUARD_INVARIANT_EN) != 0u);
    invariant_true   = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);
    hazard_true      = ((d->guard_flags & KM_CME_GUARD_HAZARD_EN) != 0u) &&
                       (d->hazard_limit != 0u) &&
                       (ev_param > (int32_t)(uint32_t)d->hazard_limit);

    commit = action_valid &&
             assumption_known && assumption_true &&
             invariant_known && invariant_true &&
             (!hazard_true);

    if (!commit) {
        ctx->rejects++;
        return false;
    }

    /* 5. Commit Candidate State & Evaluate Acyclic Cascade Trigger (with self_suppress) */
    ctx->state[cid]           = km_u32_to_i32(cand_u32);
    ctx->commits++;
    ctx->last_committed_state = ctx->state[cid];

    if ((d->subscriber_cid < KM_SAFETY_NUM_CONCEPTS) &&
        (((d->guard_flags & KM_CME_GUARD_SUBSCRIBER_EN) != 0u) || (d->subscriber_cid != 0u))) {
        uint8_t target_cid = (uint8_t)(d->subscriber_cid & 0x3Fu);
        if (target_cid != cid) {
            *next_cid_out     = target_cid;
            *trigger_next_out = true;
        }
    }

    return true;
}

/* --- Deterministic Topological Cascade Execution (WCET = O(K), No Dynamic Loops) --- */
static inline km_safety_step_result_t km_safety_step_event(
    km_safety_ctx_t *ctx,
    uint8_t root_cid,
    int32_t param,
    bool param_valid
) {
    km_safety_step_result_t res;
    uint32_t topo_idx;
    bool     has_pending;
    uint8_t  pending_cid;
    int32_t  pending_param;
    bool     pending_valid;

    res.steps_executed   = 0u;
    res.commits          = 0u;
    res.rejects          = 0u;
    res.fault_propagated = false;
    res.last_state       = (ctx != NULL) ? ctx->last_committed_state : 0;
    res.status           = KM_SAFETY_STEP_REJECTED_BAD_CID;

    if (ctx == NULL) {
        return res;
    }

    if (root_cid >= KM_SAFETY_NUM_CONCEPTS) {
        ctx->events_processed++;
        ctx->rejects++;
        ctx->fault_propagations++;
        res.steps_executed   = 1u;
        res.rejects          = 1u;
        res.fault_propagated = true;
        res.status           = KM_SAFETY_STEP_REJECTED_BAD_CID;
        return res;
    }

    /* Fast path for unconfigured concept slots (guard_flags == 0) */
    if ((KM_SAFETY_ACTIVE_MASK_INIT & (1ULL << root_cid)) == 0ULL) {
        uint8_t unused_next = 0u;
        bool    unused_trig = false;
        bool    fault_rej   = false;
        (void)km_safety_eval_single_cid(
            ctx, root_cid, param, param_valid, &unused_next, &unused_trig, &fault_rej
        );
        res.steps_executed   = 1u;
        res.rejects          = 1u;
        res.fault_propagated = fault_rej;
        res.last_state       = ctx->last_committed_state;
        res.status           = fault_rej ? KM_SAFETY_STEP_REJECTED_FAULT : KM_SAFETY_STEP_REJECTED_GUARD;
        return res;
    }

    has_pending   = true;
    pending_cid   = root_cid;
    pending_param = param;
    pending_valid = param_valid;

    /* Fixed-bound single pass in verified topological order (no while queue, WCET = const) */
    for (topo_idx = 0u; topo_idx < KM_SAFETY_NUM_ACTIVE_TOPO; ++topo_idx) {
        uint8_t cid = KM_SAFETY_TOPO_ORDER[topo_idx];
        if (has_pending && (cid == pending_cid)) {
            uint8_t next_cid     = 0u;
            bool    trigger_next = false;
            bool    fault_rej    = false;
            bool    committed    = km_safety_eval_single_cid(
                ctx,
                cid,
                pending_param,
                pending_valid,
                &next_cid,
                &trigger_next,
                &fault_rej
            );
            res.steps_executed++;
            if (committed) {
                res.commits++;
                res.last_state = ctx->last_committed_state;
                res.status     = KM_SAFETY_STEP_COMMITTED;
                if (trigger_next) {
                    pending_cid   = next_cid;
                    pending_param = ctx->state[cid];
                    pending_valid = ((ctx->valid_mask & (1ULL << cid)) != 0ULL);
                    has_pending   = true;
                } else {
                    has_pending = false;
                }
            } else {
                res.rejects++;
                if (fault_rej) {
                    res.fault_propagated = true;
                }
                if (res.commits == 0u) {
                    res.status = fault_rej
                        ? KM_SAFETY_STEP_REJECTED_FAULT
                        : KM_SAFETY_STEP_REJECTED_GUARD;
                }
                has_pending = false;
            }
        }
    }

    return res;
}

#endif /* KM_SAFETY_AUTOGEN_`

// renderC99 mirrors _render_c99_source; descs must be normalised.
func renderC99(descs []kpol.Descriptor, topo []int, moduleName, imageSHA256, verdictLabel, solverLabel string) string {
	var activeMask uint64
	for _, cid := range topo {
		if IsDescriptorConfigured(descs[cid]) {
			activeMask |= 1 << uint(cid)
		}
	}
	modClean := sanitizeIdent(moduleName, DefaultModuleName)
	modUpper := strings.ToUpper(modClean)

	topoElems := make([]string, len(topo))
	topoPlain := make([]string, len(topo))
	enumLines := make([]string, len(topo))
	for i, cid := range topo {
		topoElems[i] = fmt.Sprintf("%du", cid)
		topoPlain[i] = fmt.Sprint(cid)
		cname := strings.ToUpper(sanitizeIdent(descs[cid].Name, fmt.Sprintf("Concept_%d", cid)))
		enumLines[i] = fmt.Sprintf("    KM_CID_%s_%d = %du,", cname, cid, cid)
	}

	descLines := make([]string, NumConcepts)
	for cid := 0; cid < NumConcepts; cid++ {
		d := descs[cid]
		init := int32(d.CurrentState)
		initLit := fmt.Sprint(init)
		if init == -2147483648 {
			initLit = "(-2147483647 - 1)"
		}
		comma := ","
		if cid == NumConcepts-1 {
			comma = ""
		}
		descLines[cid] = fmt.Sprintf("    { %s, 0x%08Xu, 0x%02Xu, 0x%02Xu, 0x%02Xu, 0x%02Xu, %du }%s /* CID %02d: %s */",
			initLit, d.OperandVal, d.PredOpcode, d.GuardFlags, d.HazardLimit, d.ActionOpcode,
			d.SubscriberCID, comma, cid, d.Name)
	}

	var b strings.Builder
	b.WriteString("/* ============================================================================\n")
	b.WriteString(" * Auto-generated by Engineering/sw/kpol-ref/c99_emitter.py (Issue #270)\n")
	fmt.Fprintf(&b, " * Module: %s\n", modClean)
	fmt.Fprintf(&b, " * Descriptor Table SHA-256: %s\n", imageSHA256)
	fmt.Fprintf(&b, " * Z3 SMT Template & Table Verification Verdict: %s (%s)\n", verdictLabel, solverLabel)
	fmt.Fprintf(&b, " * Active Concepts: %d (Topological Order: [%s])\n", len(topo), strings.Join(topoPlain, ", "))
	b.WriteString(tplHeaderScope)
	fmt.Fprintf(&b, "#ifndef KM_SAFETY_AUTOGEN_%s_H\n#define KM_SAFETY_AUTOGEN_%s_H\n\n", modUpper, modUpper)
	b.WriteString(tplDefines)
	fmt.Fprintf(&b, "#define KM_SAFETY_NUM_ACTIVE_TOPO    %du\n", len(topo))
	fmt.Fprintf(&b, "#define KM_SAFETY_ACTIVE_MASK_INIT   0x%016XULL\n", activeMask)
	b.WriteString(tplOpcodes)
	b.WriteString(strings.Join(enumLines, "\n"))
	b.WriteString("\n")
	b.WriteString(tplTypes)
	b.WriteString("    " + strings.Join(topoElems, ", "))
	b.WriteString(tplTableHead)
	b.WriteString(strings.Join(descLines, "\n"))
	b.WriteString(tplBody)
	b.WriteString(modUpper)
	b.WriteString("_H */\n")
	return b.String()
}
