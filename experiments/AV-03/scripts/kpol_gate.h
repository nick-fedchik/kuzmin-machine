#ifndef KPOL_GATE_H
#define KPOL_GATE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t event_valid;
    uint8_t candidate_known;
    uint32_t candidate_value;
    uint8_t assumption_known;
    uint8_t assumption_true;
    uint8_t invariant_known;
    uint8_t invariant_true;
    uint8_t hazard_known;
    uint8_t hazard_true;
    uint32_t state_current;
} kpol_gate_input_t;

typedef struct {
    uint32_t state_next;
    uint8_t committed;
    uint8_t rejected;
    uint8_t rejected_input;
    uint8_t rejected_invariant;
    uint8_t changed;
    uint8_t hazard_observed;
    uint8_t unknown_hazard;
} kpol_gate_output_t;

void kpol_txn_gate_decision(const kpol_gate_input_t *in, kpol_gate_output_t *out);

#ifdef __cplusplus
}
#endif

#endif /* KPOL_GATE_H */
