#include "kpol_gate.h"

void kpol_txn_gate_decision(const kpol_gate_input_t *in, kpol_gate_output_t *out) {
    out->state_next = in->state_current;
    out->committed = 0;
    out->rejected = 0;
    out->rejected_input = 0;
    out->rejected_invariant = 0;
    out->changed = 0;
    out->hazard_observed = 0;
    out->unknown_hazard = 0;

    if (in->event_valid) {
        if (!in->hazard_known) {
            out->unknown_hazard = 1;
        } else if (in->hazard_true) {
            out->hazard_observed = 1;
        }

        uint8_t input_ok = in->candidate_known && in->assumption_known && in->assumption_true;
        uint8_t invariant_ok = in->invariant_known && in->invariant_true;

        if (!input_ok) {
            out->rejected = 1;
            out->rejected_input = 1;
        } else if (!invariant_ok) {
            out->rejected = 1;
            out->rejected_invariant = 1;
        } else {
            out->state_next = in->candidate_value;
            out->committed = 1;
            out->changed = (in->candidate_value != in->state_current) ? 1 : 0;
        }
    }
}
