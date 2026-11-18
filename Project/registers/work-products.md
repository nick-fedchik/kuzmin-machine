# Реєстр Work Products NG

* **Версія:** 0.11.0
* **Дата:** 2026-11-18
* **Тип WP:** Register
* **Власник:** Микола Федчик; укладач — GitHub Copilot CLI.
* **База складу:** [маніфест](migration-manifest.json), [карта шляхів](path-map.json).

## 1. Призначення та схема

Тип WP визначає призначення, а напрям — відповідальність і контекст.
Наведені входи є основними; повний файловий [індекс](wp-index.json)
має шлях, тип, напрям і ознаку незмінного входу. Один файл може
реалізувати кілька WP розділами. Відсутність окремої папки не означає
відсутності типу.

## 2. Research

| WP | Основне місце / шаблон | Стан і межа |
|---|---|---|
| Source | [Каталог](../../Research/sources/README.md), [уточнення RFC](../../Research/sources/author/rfc-2026-11-12.md), [відповіді 2026-11-15](../../Research/sources/author/rfc-answers-2026-11-15.md); [форма](../templates/work-products/source.md) | 4 дописи, презентація у двох форматах і vendor-схема — незмінні копії; картки переданих відповідей мають окремі межі походження. |
| Problem | [Q01–Q21](../../Research/studies/concept-assessment/problem.md), [fpga-gpu-symbiosis](../../Research/studies/fpga-gpu-symbiosis/problem.md); [форма](../templates/work-products/problem.md) | Додано постановку проблеми Callback Bottleneck. |
| Model | [Формальний розбір](../../Research/studies/author-semantics/formal-analysis.md), модель у [#77](../../Research/studies/turing-construction/report.md), [fpga-gpu-symbiosis](../../Research/studies/fpga-gpu-symbiosis/model.md), [epistemology](../../Research/studies/fpga-gpu-symbiosis/epistemology-and-learning.md); [форма](../templates/work-products/model.md) | Додано дворівневу модель детермінізму FPGA-GPU та аналіз онтології навчання. |
| Protocol | [Опозиція](../../Research/studies/concept-assessment/protocol.md), [fpga-gpu-symbiosis](../../Research/studies/fpga-gpu-symbiosis/protocol.md), [EXP-GPU-01](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/protocol.md), [EXP-GPU-02](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-02/protocol.md); [форма](../templates/work-products/protocol.md) | Додано методику дослідження симбіозу та протоколи HIL EXP-GPU-01 й EXP-GPU-02. |
| Report | [Шість досліджень](../../Research/README.md), [fpga-gpu-symbiosis](../../Research/studies/fpga-gpu-symbiosis/report.md), [EXP-GPU-01 Фаза 3–4 #225/#235/#240](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase3-warp-scaling.md), [EXP-GPU-01 Фази 1–2, 4 #226](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/report-phase1-2-4-crossboard-egress.md), [EXP-GPU-02 Етапи 1–3 #252/#259/#253](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-02/report-stage1-2-cfg-p-ha.md), [EXP-GPU-03 #256](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-03/report.md), [порівняльний Baseline #254](../../Research/studies/comparative-baseline-254/report.md), [вплив RFC і Q3 #201/#203](../../Research/studies/author-semantics/rfc-impact-and-q3-draft-report.md), [пілот Q3 #216](../../Research/studies/author-semantics/q3-llm-pilot-216-report.md), [підсумковий інженерно-комерційний висновок #270](../../Research/studies/commercialization-and-final-conclusions.md); [Analysis](../templates/work-products/analysis-report.md) | Додано звіти GPU/FPGA-експериментів (`EXP-GPU-01` Фаза 3–4 v0.4.0 та Фази 1–2, 4 v0.1.0, `EXP-GPU-02` Етапи 1–3 v1.0.0 з P&R `100.69 МГц` та HIL на `PYNQ-Z1`, `EXP-GPU-03` v0.1.0), порівняльного Baseline (`#254`, $K^* = 26\text{ SLICE\_LUTX}$), аналізу RFC, LLM-пілота Q3 та підсумкового висновку комерціалізації і верифікації `--emit-c99 + Z3` (`#270`, `1.0.0`). |
| Data | [Проходи опозиції](../../Research/studies/concept-assessment/data/opposition-passes/), двокоміркова траса у [#77](../../Research/studies/turing-construction/report.md) | Сирі тексти не переформатовано; хеші в маніфесті. Окремого файла для формальної траси немає. |

## 3. Engineering

| WP | Основне місце / шаблон | Стан і межа |
|---|---|---|
| Requirement | [Реєстр v0.3.0](../../Engineering/requirements/requirements.md), [KPOL v0.6.0](../../Engineering/requirements/kpol.md); [SYS](../templates/work-products/requirement-sys.md), [HW](../templates/work-products/requirement-hw.md), [SW](../templates/work-products/requirement-sw.md) | Актуалізовано трасування за результатами `#227/#237`, `#230/#234`, `#245`, `#252/#253`, `#254`, `#255` та закриття S5 (`#8`); B4 оновлено до v2.4.0 (`CFG-P-HA` HIL), B5 — v2.2.0. |
| Specification | [KPOL](../../Engineering/specifications/kpol/README.md), [`KPOL-CME-2`](../../Engineering/specifications/kpol/kpol-cme2-profile-0.1.0.md), [`EKPOL 0.1.0`](../../Engineering/specifications/kpol/ekpol-specification.md), [`KPOL-AUTH` (підмножина)](../../Engineering/specifications/kpol/kpol-auth-subset-0.1.0.md), [Go VMK v0.2.0](../../Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger.md), [HW](../../Engineering/specifications/hw/README.md), [B4 v2.4.0](../../Engineering/specifications/hw/kpol-image-loader-pipeline-contract.md); [форма](../templates/work-products/specification.md) | Профілі `KPOL-CME-1` і `KPOL-CME-2` (#184) та ергономічна мова `EKPOL 0.1.0` (#278) відокремлені від ізольованого прототипу `KPOL-AUTH` (#245, частина #186/#8); оновлено специфікацію двомодового емулятора VMK v0.2.0 та TUI-дебагера на Go (#274, #278); у B4 v2.4.0 зафіксовано натурно верифікований двобанковий `CFG-P-HA` (#252/#253). |
| Design | [B1](../../Engineering/design/system-boundary-allocation-b1.md), [B2](../../Engineering/design/bram-pipeline-event-integration.md); [форма](../templates/work-products/design.md) | Межа й інтеграція, не доказ готовності всього продукту. |
| Decision | [Карта v0.4.1](../../Engineering/decisions/README.md), [B6 v0.5.0](../../Engineering/decisions/b6-gpu-persistent-kernel-subscribers.md), [B7 (`CME-RAW-2` / `KPOL-SYS-02`)](../../Engineering/decisions/cme-raw2-kpol-sys02.md), розділи контрактів; [форма ADR](../templates/work-products/decision.md) | B6 v0.5.0 інтегрує емпіричні дані `EXP-GPU-01` (#225/#235/#240/#226) та `EXP-GPU-03` (#256); B7 v0.2.0 прийнято власником за Варіантом А (#185/#215). |
| Solution | [Пакет](../../Engineering/solutions/compiler-bram-pipeline.md); [форма](../templates/work-products/solution.md) | Явний склад, залежності й обмеження. |
| Source Code | [HW](../../Engineering/hw/), [SW](../../Engineering/sw/) | Чинні компоненти й тести; демо-FSM виключено. |
| Configuration | [Карта](../../Engineering/configurations/README.md), файли біля компонентів | CFG-R ≠ CFG-P. |
| Hardware | [Платформа](../../Engineering/hw/boards/pynq-z1/README.md), [стенд](../../Engineering/hw/boards/pynq-z1/hil-bench-wiring-guide.md), [план HIL-експериментів](../../Engineering/hw/boards/pynq-z1/hil-hardware-experiment-plan.md), [інвентар](hardware-inventory.md) | Опис об'єкта, схема монтажу, план HIL-експериментів та актуальний інвентарний реєстр апаратного стенда. |

## 4. Project і поперечні типи

| WP | Основне місце / шаблон | Стан і межа |
|---|---|---|
| Plan | [NG](../plans/ng-transition.md), [EXP-GPU-01](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-01/plan.md), [EXP-GPU-02](../../Research/studies/fpga-gpu-symbiosis/experiments/EXP-GPU-02/plan.md); [форма](../templates/work-products/plan.md) | Додано плани експериментів EXP-GPU-01 та EXP-GPU-02. |
| Specification / Patent Draft | [Портфель](../patents/README.md), [KM-PAT-01](../patents/patent-apparatus-heterogeneous-event-engine.md), [KM-PAT-02](../patents/patent-method-hierarchical-event-control.md), [звіт #177](../patents/report-177-timing-dependent-claims.md) | Чернетки заявок на винахід (пристрій та спосіб) для УКРНОІВІ/PCT/USPTO. |
| Guide | [Навігація](../README.md), [Посібник користувача VMK v1.1.0](../../Engineering/guides/vmk-users-guide.md), [`vmk-go` README](../../Engineering/sw/vmk-go/README.md), [fpga-gpu-symbiosis](../../Research/studies/fpga-gpu-symbiosis/README.md); [форма](../templates/work-products/guide.md) | Практичний посібник користувача VMK (`bram64` + `conceptual`, `EKPOL`, `STDIO`, 4-панельний TUI, `PYNQ-Z1`) та навігаційні README пакетів. |
| Policy | [Розміщення](../policies/layout.md), [ліцензійний режим](../policies/licensing.md), [WP](../policies/work-products.md); [форма](../templates/work-products/policy.md) | Межі й повноваження визначає власник. |
| Register | Цей запис, [цілі](goals-needs-work-items.md), [відкриті WI](open-work-items.md), [CI](configuration-items.md), [інвентар обладнання](hardware-inventory.md); [форма](../templates/work-products/register.md) | Нові актуальні карти та інвентар, не копії історичних зрізів. |
| Template | [Єдине місце](../templates/README.md), [покриття](../templates/work-products/README.md) | Усі 19 типів, 4 підтипи Report, SYS/HW/SW; placeholder дозволений у формі. |
| Report / Analysis / Experiment | [Перевірки](../../Engineering/validation/README.md), [профіль #150](../../Engineering/validation/kpol-cme/profile-150/report.md), [підпис #115](../../Engineering/validation/kpol-cme/signature-115/report.md), [черга #151](../../Engineering/validation/kpol-cme/queue-retention-151/report.md), [Secure Boot #164](../../Engineering/validation/kpol-cme/secure-boot-164/report.md), [ядро CME #167](../../Engineering/validation/kpol-cme/cme-semantics-167/report.md), [AXI B4 / PYNQ-Z1 #168](../../Engineering/validation/kpol-cme/axi-b4-pynq-168/report.md), [реєстри #169](../../Engineering/validation/kpol-cme/docs-registers-169/report.md), [верифікатор і lowering #183](../../Engineering/validation/kpol-cme/verifier-lowering-183/report.md), [`KPOL-CME-2` #184](../../Engineering/validation/kpol-cme/cme2-profile-184/report.md), [CR `CME-RAW-2` #185](../../Engineering/validation/kpol-cme/cr-cme-raw2-185/report.md), [`KPOL-AUTH` #219](../../Engineering/validation/kpol-cme/kpol-auth-frontend-219/report.md), [формальна індукція $N=16$ #227](../../Engineering/validation/kpol-cme/cme2-formal-227/report.md), [PMOD egress #230](../../Engineering/validation/kpol-cme/pmod-event-egress-230/report.md), [багатоядерний кластер $N=1..8$ #255](../../Engineering/validation/kpol-cme/manycore-scaling-255/report.md), [приймальний звіт S5 #8](../../Engineering/validation/kpol-cme/s5-compiler-8/report.md), [генератор C99 + Z3 #270](../../Engineering/validation/kpol-cme/c99-emitter-270/report.md), [покроковий дебагер каскадів #272](../../Engineering/validation/kpol-cme/debugger-trace-272/report.md), [двомодовий Go-емулятор VMK та TUI-дебагер #274](../../Engineering/validation/kpol-cme/vmk-go-274/report.md), [мова `EKPOL 0.1.0` та `VMK v0.2.0` #278](../../Engineering/validation/kpol-cme/ekpol-278/report.md); [форма](../templates/report.md) | Пакети мають різні об'єкти та класи доказів (хостові/RTL/SMT/P&R `OpenXC7`/HIL PS/GPU). |
| Report / Review | Рецензії біля об'єктів; [форма](../templates/review.md) | Успадковані рецензії оригіналів, не нове прийняття NG. |
| Report / Assessment | [TRL](../assessments/trl/report.md); [форма](../templates/work-products/assessment-report.md) | Самооцінка, не сертифікація. |

## 5. Ведення та контроль

Для нового WP оновлюють основний README й індекс; важливі залежності —
також карту цілей. Типи нетекстових артефактів визначено
[правилами](../templates/README.md#3-wp-для-яких-markdown-форма-не-замінює-сам-артефакт).

`check_wp_documents.py` перевіряє зовнішню структуру Markdown і хеші
перелічених незмінних входів, не науковий зміст чи повну відповідність
кожного розділу шаблону. Змістову відповідність звіряють за питаннями
відповідного шаблону; невідоме позначають, не заповнюють вигадкою.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Поточні WP й місця зберігання, без старого інвентаризаційного зрізу. |
| 0.1.1 | 2026-11-12 | Політика пропрієтарного режиму та реєстр поточних рішень щодо WI. |
| 0.2.0 | 2026-11-12 | Source уточнень RFC, Requirement KPOL, Report профільного compiler #150 та файловий індекс. |
| 0.3.0 | 2026-11-12 | Додано реєстрацію B6 (ADR GPU симбіоз) та пакету експерименту EXP-GPU-01 (Protocol, Plan, Guide). |
| 0.4.0 | 2026-11-13 | #151: оновлено стан B5 v2.1 та додано реєстрацію звіту верифікації черги `queue-retention-151/report.md`. |
| 0.5.0 | 2026-11-14 | #169: зареєстровано звіти перевірок #115, #164, #167, #168, #169 та оновлено стан специфікацій B4/B5 v2.2.0 і `wp-index.json`. |
| 0.11.0 | 2026-11-18 | #280: зареєстровано повноекранний інтерактивний TUI-дебагер `Engineering/sw/vmk-go/internal/vmk/tui_fullscreen.go` (`VMK v0.3.0`), сирий лог сесії `Engineering/validation/kpol-cme/vmk-go-274/raw/vmk_fullscreen_tui_280.log`, оновлено `vmk-users-guide.md` (`1.2.0`), `vmk-go-emulator-and-tui-debugger.md` (`1.2.0`), `vmk-go-274/report.md` (`1.1.0`) та `wp-index.json`. |
| 0.10.0 | 2026-11-18 | #278: зареєстровано специфікацію `Engineering/specifications/kpol/ekpol-specification.md` (`1.0.0`), Python-фронтенд `Engineering/sw/kpol-ref/ekpol_frontend.py`, Go-парсер `Engineering/sw/vmk-go/internal/vmk/ekpol.go` (`VMK v0.2.0`), каталог прикладів `Engineering/sw/vmk-go/examples/*.ekpol`, звіт `Engineering/validation/kpol-cme/ekpol-278/report.md` (`1.0.0`), тести `Engineering/sw/tests/test_ekpol_278.py` та оновлено `wp-index.json` (`0.25.0`). |
| 0.9.1 | 2026-11-18 | #276: зареєстровано практичний Посібник користувача VMK `Engineering/guides/vmk-users-guide.md` (`1.0.1`, тип WP `Guide`), `Engineering/sw/vmk-go/README.md` (`1.0.0`) та оновлено `wp-index.json` (`0.23.0`). |
| 0.9.0 | 2026-11-18 | #274: зареєстровано Go-модуль двомодового емулятора VMK та 4-панельного TUI-дебагера `Engineering/sw/vmk-go/`, специфікацію `Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger.md`, пакет верифікації `Engineering/validation/kpol-cme/vmk-go-274/`, тести `Engineering/sw/tests/test_vmk_go_274.py` та оновлено `wp-index.json` (`0.22.0`). |
| 0.8.0 | 2026-11-18 | #272: зареєстровано покроковий дебагер каскадів МК `Engineering/sw/kpol-ref/kpol_debugger.py`, пакет верифікації `Engineering/validation/kpol-cme/debugger-trace-272/`, тести `Engineering/sw/tests/test_kpol_debugger_272.py` та оновлено `wp-index.json` (`0.21.0`). |
| 0.7.0 | 2026-11-17 | #270: зареєстровано підсумковий інженерно-комерційний висновок `Research/studies/commercialization-and-final-conclusions.md` (`1.0.0`), генератор детермінованого C99 `Engineering/sw/kpol-ref/c99_emitter.py`, референсний пакет BMS `Engineering/validation/kpol-cme/c99-emitter-270/`, тести `Engineering/sw/tests/test_c99_emitter_270.py` та оновлено `wp-index.json` (`0.20.0`). |
| 0.6.2 | 2026-11-17 | #253: зареєстровано звіт Етапів 1–3 `EXP-GPU-02` (`1.0.0`), HIL-раннер `hil_exp_gpu_02_runner.py` та натурні артефакти `exp-gpu-02-hil/` (`pynq2 + LOGICTRACER_PICO_0.5.0`), оновлено статус B4 v2.4.0 та `wp-index.json` (`0.19.0`). |
| 0.6.1 | 2026-11-17 | #226: зареєстровано звіт `EXP-GPU-01` Фаз 1–2, 4 (`report-phase1-2-4-crossboard-egress.md`), скрипт `build_bram_pipeline_egress.sh`, натурний міжплатний пакет (`crossboard_frame.py`, `crossboard_egress_server.cu`, `crossboard_egress_client.c`, `test_crossboard_egress_226.py`), оновлено `ADR B6` (`0.5.0`) та `wp-index.json` (`0.18.0`). |
| 0.6.0 | 2026-11-17 | #8: зареєстровано звіти `EXP-GPU-01` v0.4.0 (#240), `EXP-GPU-03` (#256), порівняльного Baseline (#254), багатоядерного кластера `CFG-P` $N=1..8$ (#255), формальної індукції $N=16$ (#227/#242), модуля `km_pmod_event_egress` (#230/#241), фронтенду `KPOL-AUTH` (#219/#245) та приймального звіту кроку S5 (`s5-compiler-8/report.md`), а також актуалізовано `wp-index.json` (`0.17.0`). |
| 0.5.6 | 2026-11-16 | #252: зареєстровано звіт Етапів 1–2 `EXP-GPU-02` (`report-stage1-2-cfg-p-ha.md`), двобанковий RTL `CFG-P-HA`, пакет формальної SMT-верифікації та симуляційні дані `exp-gpu-02-sim/` у `work-products.md` та `wp-index.json` (`0.16.0`). |
| 0.5.5 | 2026-11-16 | #245 (частина #186, #8): зареєстровано специфікацію `Engineering/specifications/kpol/kpol-auth-subset-0.1.0.md` і пакет `Engineering/sw/kpol-auth/` у `work-products.md` та `wp-index.json` (`0.15.0`). |
| 0.5.4 | 2026-11-14 | #203: зареєстровано звіт `Research/studies/author-semantics/rfc-impact-and-q3-draft-report.md` у `work-products.md` та `wp-index.json` (`0.14.0`). |
| 0.5.3 | 2026-11-14 | #185: зареєстровано архітектурне рішення B7 (`cme-raw2-kpol-sys02.md`), звіт перевірки `cr-cme-raw2-185/report.md` та оновлено `wp-index.json`. |
| 0.5.2 | 2026-11-14 | #184: зареєстровано специфікацію багатоконцептного профілю `kpol-cme2-profile-0.1.0.md`, звіт перевірки `cme2-profile-184/report.md` та оновлено `wp-index.json`. |
| 0.5.1 | 2026-11-14 | #183: зареєстровано звіт перевірки верифікатора `Proof`, `change(...)` і базового CME-lowering (`verifier-lowering-183/report.md`) та оновлено `wp-index.json`. |

## Абревіатури та глосарій

WP — результат роботи; CI — елемент конфігурації; ADR — запис рішення;
sidecar — окремий машиночитаний запис походження.
