`timescale 1ns/1ps

/**
 * Модуль: km_predicate_evaluator
 * Призначення:
 *   Апаратний паралельний обчислювач предикатів Машини Кузьміна (оператор '::')
 *   та транзакційний формувач прапорця «Велика точка» (•).
 *
 * Теоретична база (Науково-інженерне досьє МК, §2 та §4):
 *   - Гіпотеза H1: Паралельна безпобічна перевірка предикатів нульового порядку
 *     (Read-Only логіка задовольняє умови Бернштейна W(pred) = ∅).
 *   - Гіпотеза H6: Алгебра фазового оператора «Велика точка» (•):
 *     якщо предикат порушено (• = ¬), запис блокується і стан лишається незмінним.
 *
 * Канонічні класи подій стану даних '::':
 *   [0] '_'        : Неініціалізоване / поліморфне значення (0xFFFFFFFF або !known)
 *   [1] 'Null'     : x == 0
 *   [2] 'Positive' : $signed(x) > 0
 *   [3] 'Negative' : $signed(x) < 0
 *   [4] 'Even'     : x[0] == 0 (парне)
 *   [5] 'Uneven'   : x[0] == 1 (непарне)
 *   [6] '~'        : x != current_state (зміна значення)
 *   [7] 'Range'    : lower_bound <= x <= upper_bound
 */

module km_predicate_evaluator #(
    parameter integer DATA_WIDTH = 32
) (
    input  logic [DATA_WIDTH-1:0] candidate_value_i,
    input  logic                  candidate_known_i,
    input  logic [DATA_WIDTH-1:0] current_state_i,
    input  logic [DATA_WIDTH-1:0] lower_bound_i,
    input  logic [DATA_WIDTH-1:0] upper_bound_i,
    input  logic [7:0]            rule_cfg_i,

    // Повний 8-бітний вектор обчислених предикатів
    output logic [7:0]            predicate_vector_o,

    // Рішення апаратного інваріанта та Велика точка (•)
    output logic                  hw_invariant_ok_o,
    output logic                  big_dot_flag_o
);
    // 1. Комбінаційне обчислення канонічних предикатів '::' за 0 нс
    wire pred_uninit   = (!candidate_known_i) || (candidate_value_i == {DATA_WIDTH{1'b1}});
    wire pred_null     = (candidate_value_i == '0);
    wire pred_positive = ($signed(candidate_value_i) > $signed({DATA_WIDTH{1'b0}}));
    wire pred_negative = ($signed(candidate_value_i) < $signed({DATA_WIDTH{1'b0}}));
    wire pred_even     = (candidate_value_i[0] == 1'b0);
    wire pred_uneven   = (candidate_value_i[0] == 1'b1);
    wire pred_changed  = (candidate_value_i != current_state_i);

    // Додатковий пороговий/діапазонний компаратор
    wire pred_range    = ($signed(candidate_value_i) >= $signed(lower_bound_i)) &&
                         ($signed(candidate_value_i) <= $signed(upper_bound_i));

    assign predicate_vector_o = {
        pred_range,
        pred_changed,
        pred_uneven,
        pred_even,
        pred_negative,
        pred_positive,
        pred_null,
        pred_uninit
    };

    // 2. Апаратна перевірка правил інваріанта
    // rule_cfg_i біти:
    //   [0]: REQUIRE_EVEN     (вимагає парності)
    //   [1]: REQUIRE_POSITIVE (вимагає додатності)
    //   [2]: REQUIRE_NON_NULL (вимагає ненульового значення)
    //   [3]: REQUIRE_RANGE    (вимагає потрапляння в діапазон)
    //   [4]: REQUIRE_CHANGED  (вимагає зміни стану)
    //   [5]: USE_HW_EVAL      (використовується на рівні обгортки)
    //   [6]: REQUIRE_UNEVEN   (вимагає непарності)
    //   [7]: Резерв
    wire rule_even_viol     = rule_cfg_i[0] && !pred_even;
    wire rule_pos_viol      = rule_cfg_i[1] && !pred_positive;
    wire rule_non_null_viol = rule_cfg_i[2] && pred_null;
    wire rule_range_viol    = rule_cfg_i[3] && !pred_range;
    wire rule_changed_viol  = rule_cfg_i[4] && !pred_changed;
    wire rule_uneven_viol   = rule_cfg_i[6] && !pred_uneven;

    wire any_rule_violated  = rule_even_viol || rule_pos_viol ||
                              rule_non_null_viol || rule_range_viol ||
                              rule_changed_viol || rule_uneven_viol;

    // Велика точка (•): 1 = ! (істина / commit дозволено), 0 = ¬ (хиба / fail-closed reject)
    assign hw_invariant_ok_o = !any_rule_violated;
    assign big_dot_flag_o    = hw_invariant_ok_o;

    // Вказівка синтезатору/лінтеру для невикористаних бітів конфігурації
    /* verilator lint_off UNUSEDSIGNAL */
    wire _unused_cfg_bits = &{1'b0, rule_cfg_i[7], rule_cfg_i[5]};
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
