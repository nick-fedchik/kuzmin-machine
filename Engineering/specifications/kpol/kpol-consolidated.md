# KPOL: консолідований робочий контракт фронтенду та CME-бекенду

* **Версія:** 0.6.1 (версія документа; чернетка, не стандарт KPOL v1.0)
* **Дата:** 2026-11-14
* **Issue:** [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19), [#183](https://github.com/nick-fedchik/kuzmin-machine/issues/183), [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184), вхід для [#8](https://github.com/nick-fedchik/kuzmin-machine/issues/8)
* **База реалізації:** `0ada974` у `nick-fedchik/kuzmin-machine`.
* **Виконавець:** GitHub Copilot CLI, Auto. За повідомленням власника від 2026-11-12, поточною моделлю автора була ChatGPT 6.1 Sol; модель усіх попередніх кроків окремо не встановлено.
* **Рецензент:** [Review Report](https://github.com/nick-fedchik/kuzmin-machine/pull/131#issuecomment-6824069657) для `a3715fc`; зміни за рецензією потребують повторної перевірки.


* **Тип WP редакції NG:** Specification
* **Укладач редакції NG:** GitHub Copilot CLI, Auto; конкретна модель не атестована.
* **Підстава редакції NG:** команда власника від 2026-11-12; локальне перенесення без legacy.
* **Походження:** [оригінал 0.1.0](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-consolidated-0.1.0.md), `707fdba697d92ef9874c9013eb6f4f3cb2796d70`.
* **Стан редакції NG:** адаптовано до нової структури; незалежна рецензія не проведена.

> **Межі редакції NG.** Перенесення й оформлення не є новим експериментом,
> повторною науковою перевіркою або затвердженням baseline. Авторство,
> рішення, числа й рецензії нижче стосуються зазначених оригінальних
> об'єктів та версій, а не автоматично цієї локальної копії.

## 1. Призначення та межі

Один робочий вхід для розробника компілятора: синтаксис поточного
фронтенду, семантика еталонного інтерпретатора, відмінні формати образів
та межі перенесення правил у CME. Не потрібно послідовно застосовувати
дев'ять історичних дельт, щоб запустити приклад §4.

Це опис і консолідація **наявної реалізації з явними прогалинами**,
не проголошення її правильною для кожного прийнятого входу. Граматика
парсера ширша за виконувану підмножину CME. Успішне створення образу
саме по собі не доводить збереження семантики. Виявлені помилки не
стають правилами мови.

Документ не затверджує системну межу S2, повний KPOL або нові релізні
критерії. Це похідна інженерна робота, не авторська специфікація
М. Ю. Кузьміна. Історичні пропозиції залишаються джерелами (§8);
неперенесені можливості не оголошуються реалізованими.

**Оновлення #150:** додано окремий профільний шлях
`compile_concept_microcode_bram_image(module, profile="KPOL-CME-1")`
та ввімкнено його в CLI. Він перевіряє вузький контракт, відхиляє
позапрофільні конструкції й виконує дозволений Proof перед емісією.
Безпрофільний виклик зберігає старе експериментальне lowering:
розриви §7 стосуються саме цього шляху, не нового профільного.
Джерела й вимоги — [KPOL](../../requirements/kpol.md);
фактичні перевірки — [Report #150](../../validation/kpol-cme/profile-150/report.md).

### 1.1. Авторський синтаксис і нинішній діалект

[Новий Source #155](../../../Research/sources/author/introduction-2026-11-13.md)
описує native Concept/Define, Collection/Array, Name/Help,
перелічувані концепти й адресні групи. Current Problem/Solution/Proof
є окремим похідним DSL, не реалізацією цього повного синтаксису.
Непідтримані авторські конструкції не можна переписувати мовчки в
наявний AST або оголошувати реалізованими завдяки схожим словам.

Слайд 3 визначає `•` як результат виконання й метаподію, тоді як
Parser нині дає `Unary("not")`. Слайди 1/2/5/7 вимагають збереження
імен/Help/структури; current raw CME не містить їх. Авторська Name-межа,
Boolean-коди та адресна розкладка не переносяться автоматично в DSL.
[Report #155](../../../Research/studies/author-semantics/kpol-syntax-155-report.md)
містить прямі probes, зіставлення й Q-AUTH; кандидати майбутнього
native контракту — у [Requirement §3.1](../../requirements/kpol.md#31-кандидати-за-новою-презентацією).

[Редакція #157](../../../Research/sources/author/introduction-revision-2026-11-13.md)
змінює текст лише слайда 5: OpenBracket/CloseBracket у Static,
пояснення порожніх/непорожніх дужок. Їхню виконувану роль уточнено
[окремим повідомленням](../../../Research/sources/author/clarifications-2026-11-13.md).
Це не робить дужки current DSL виконуваними native концептами й не
додає opcode до CME-RAW-1. Канонічні імена, фаза й ефекти — Q-AUTH-07;
лексика `#`, повна граматика та native ABI не вважаються завершеними.
[Report #157](../../../Research/studies/author-semantics/kpol-syntax-157-report.md)
містить точний diff і поточну оцінку AUTH/Q-AUTH; правила §2–7 не змінені.

[Окремий Source #159](../../../Research/sources/author/group-execution-2026-11-13.md)
уточнює роль індексів залежно від типу: для Token підрядкове → Min, надрядкове →
Max; успіх вмісту відділено від кратності успіху групи.
Це не підтримана можливість current DSL/CME. Max=0 та інші типи індексів
не отримали повної семантики; [Report #159](../../../Research/studies/author-semantics/kpol-syntax-159-report.md)
частково уточнює Q-AUTH-01, не змінює поточну граматику/ABI.

## 2. Синтаксис поточного фронтенду

Джерело: `tokenize`, `Parser`, `check_module` у
[`kpol_reference.py`](../../sw/kpol-ref/kpol_reference.py).
Публічна функція `parse_module(source)` виконує парсинг і перевірку типів.

### 2.1. Структура модуля

```text
module      = Problem NAME { section* }
              Solution NAME { declaration* }
              [ Proof NAME { proof-item* } ]
section     = (Assumptions | Invariants | Hazards | Alerts | Goals)
              { requirement* }
requirement = NAME [on EVENT] [to STATE] : expression ;
declaration = event NAME ( [PARAM : type {, PARAM : type}] ) ;
            | state NAME : type = expression ;
            | rule NAME on [reject] EVENT [when expression]
              [covers HAZARD] { action* }
            | rule NAME on change ( STATE {, STATE} ) [when expression]
              { action* }
action      = set STATE := expression ;
proof-item  = assert NAME on EVENT [when expression] expect expression ;
            | scenario NAME { (step EVENT ( arguments ) ;
                              | expect expression ;)* }
arguments   = [PARAM (: | =) expression
              {, PARAM (: | =) expression}]
```

Це стислий запис структури, а не повна EBNF усіх лексичних обмежень.
Імена трьох блоків збігаються; `Problem` і `Solution` обов'язкові,
`Proof` у `parse_module` необов'язковий. Парсер також приймає блокові
дужки навколо тіла `assert`. Кожен вид секції Problem оголошують
щонайбільше раз; дублікати подій, станів і правил відхиляються.
Параметри події не можуть дублюватися або затінювати імена станів.

`Hazards` і `Alerts` прив'язані до події. Hazard має Bool-ціль `to`
та правило `covers`, яке точно повторює його вираз і записує `true`
в ціль. `Invariants` і `Goals` є предикатами стану без `on`;
`to` дозволено лише для Hazard. Вирази контрактів і охоронців — Bool.
Ці обмеження перевіряє `check_module`, а не лише граматика.

### 2.2. Лексика, типи та вирази

- Ідентифікатори утворюються з літер, цифр та `_`, не починаються з
  цифри; ключові слова не є іменами оголошень. Регістр значущий.
- Коментарі: `#`, `//` до кінця рядка та `/* ... */` без вкладення.
- Літерали: цілі й десяткові числа, `true`, `false`, `Unknown`.
  Від'ємне число — унарний `-` і числовий літерал.
- Типи: `Bool`, `Int32`, `U32`, `U64`, `Float<unit>`, `Pin` і
  `Pin<identifier,...>`. `Void` зарезервовано, але `type_ref` його
  не приймає. `Pin` не встановлює сам собою фізичного з'єднання.
- Одиниці Float: `V`, `A`, `W`, `s`, `J`, `degC`, `bar`,
  `ns`, `us`, `ms`, `min`, `h`, `mm_s`, `L_min`.
  Наявність одиниці не означає перетворення між `ms` і `s`.
- Вирази: імена, дужки, `gcd(a,b)`, унарні `not` і `-`;
  двомісні `or`, `and`, `== != < <= > >=`, `+ -`, `* /`.
  Пріоритет зростає в наведеному порядку, унарні операції найсильніші;
  двомісні операції лівоасоціативні.
- `•` і `(*)` у виразі нормалізуються до `not`. Лексер також розпізнає
  стрілки, але `set X ← value` та фази апаратного виконання не є
  реалізованими від цього конструкціями парсера.

Це **опис нинішньої поведінки**, не авторська семантика `•`.
Авторські `@`, `!`, `¬`, квадратні й текстові/іменні дужки,
Help-компонент та Define/Concept не підтримані як native граматика.
Token лексера з line/column не є авторською одиницею пам'яті 4 біти.

У референсі Int32 має межі `[-2^31, 2^31-1]`, U32 — `[0, 2^32-1]`,
U64 — `[0, 2^64-1]`; переповнення не задається як модульна арифметика.
Pin приймає 0/1 або Bool. Float виконується через Python Decimal;
обмеження підтриманих операцій задає `infer`, зокрема арифметика
абсолютного `degC` відхиляється. Це не ABI апаратного CME.

## 3. Семантика референсного виконання

Джерело: `Interpreter`, `_eval`, `_normalize`, `verify_module`.

1. Початкові стани обчислюються в порядку оголошення. Перевіряються
   початкові Assumptions без події та Invariants. `Unknown` не можна
   зберегти як стан; вхідний payload може містити `Unknown`.
2. Payload звичайної події має рівно оголошені параметри з допустимими
   значеннями типів. Вхідні події обробляються послідовно.
3. Непідтверджена подієва Assumption відхиляє звичайну транзакцію.
   За типової політики `fail_closed_hazards=True` активний або
   невідомий Hazard також відхиляє її. Alert спостерігається, але не
   блокує транзакцію сам собою.
4. Вибрані правила обчислюють охоронці й праві частини на знімку
   стану до транзакції, не на проміжних записах інших правил.
   Невідомий охоронець/запис або суперечливі записи скасовують
   відповідне застосування; діагностика повертається в RunResult.
   Різні типи помилок також можуть підняти `KpolError`, а не діагностику.
5. Invariants перевіряються на кандидатному стані до його прийняття.
   Для відхиленої події існують правила `on reject`; спостережений
   Hazard може встановити свій Bool-прапорець. Це не коміт звичайної
   прикладної транзакції.
6. `change(...)` — внутрішні події: по одній для кожного набору
   спостереження один раз на старті інстансу `Interpreter` (перший виклик `run`),
   а далі лише при фактичній зміні спостережуваного стану (повторні інкрементні
   виклики `run` не перезапускають незмінені підписки). Це не паралельні потоки, CSP або гарантія fairness.
7. Goals перевіряються наприкінці `run`. У Proof сценарій виконує
   конкретні `step` та `expect`; `assert` застосовується до подій,
   які дійсно з'являються в сценаріях. `verify_module` відхиляє вакуумні
   елементи `Proof`: оголошений `assert`, чия умова `when` жодного разу
   не стала істинною в сценаріях, а також оголошений `scenario` без жодної
   виконаної перевірки (явно порожній `Proof {}` має `total_checks == 0`,
   тому відсікається мутаційним гейтом і профільним компілятором).
   Це скінченна перевірка трас, не SMT-доказ або доказ усіх можливих виконань.

`and/or/not` працюють із Unknown; `false and Unknown = false`,
`true or Unknown = true`, `not Unknown = Unknown`. Рівність має окреме
правило: `Unknown == Unknown` істинне, рівність Unknown з відомим
значенням хибна. Ці правила не замінюють відомість апаратних сигналів.

## 4. Перевірений наскрізний приклад для CME

```kpol
Problem CounterDemo {
    Invariants { NonNeg: Counter >= 0; }
}
Solution CounterDemo {
    state Counter: Int32 = 10;
    event Pulse(param: Int32);
    rule Step on Pulse when param < 20 {
        set Counter := Counter + 1;
    }
}
Proof CounterDemo {
    scenario TwoEvents {
        step Pulse(param = 5);
        expect Counter == 11;
        step Pulse(param = 25);
        expect Counter == 11;
    }
}
```

Для окремого варіанта decrease замінюють дію на `Counter - 1`,
очікування після обох подій — 9. Збережені джерела:
[`increase`](../../hw/tests/kpol_bram_pipeline_increase.kpol),
[`decrease`](../../hw/tests/kpol_bram_pipeline_decrease.kpol).
[Інтеграційний тест](../../hw/tests/test_kpol_bram_pipeline.py) порівнює
референс і direct/AXI RTL-симуляцію та вміє впасти при перестановці
образів. Це два конкретні сценарії, не універсальна відповідність
парсера, бекенду й довільної програми.

```bash
python3 Engineering/hw/scripts/compile_kpol_bram_image.py \
  Engineering/hw/tests/kpol_bram_pipeline_increase.kpol /tmp/kpol-increase-new.bin
python3 -m pytest -q Engineering/hw/tests/test_kpol_bram_pipeline.py
```

Ім'я вихідного файла має бути новим: CLI відкриває його в режимі `xb`
і не перезаписує наявний файл. Компіляція не запускає FPGA; HIL для
цих двох образів не доведено самим інтеграційним тестом.

## 5. Формати образів і контракт CME

Дві функції повертають по 1024 байти, але це **несумісні формати**:

| API | Призначення | Вміст 16-байтного слота |
|---|---|---|
| `compile_bram_image` | Історична таблиця даних/метаданих, не виконуваний CME-мікрокод | Два слова значення, метадані типу/маски правил, статусні предикати |
| `compile_concept_microcode_bram_image` | Образ для `km_concept_micro_engine` | Стан, спільний операнд, коди предиката/дії та guard-прапорці, підписник |

Обидва образи складаються з 64 слотів по 16 байтів; слот відповідає
порядку оголошення стану. Ці числа описують наявний формат, не нову
універсальну вимогу до KPOL. CME-пакування — little-endian `<IIII>`:

| Байти слота | Поле | Семантика поточного RTL |
|---|---|---|
| 0–3 | `current_state` | 32-бітний стан |
| 4–7 | `operand_val` | Одне поле, спільне для предиката та ADD/SUB |
| 8 | `pred_opcode` | 00 NOP; 01 EQ; 02 NEQ; 03 GT; 04 LT; 05 RANGE; 06 BITMASK; інші коди дають `0` |
| 9 | `guard_flags` | bit 0 — assumption known; bit 1 — invariant known; bit 2 — hazard enabled; bit 3 — інверсія предиката; bit 4 — explicit subscriber enable (дозволяє каскад зокрема на `CID 0`) |
| 10 | `hazard_limit` | 8-бітна межа; RTL перевіряє активований ненульовий поріг `event_param > limit` |
| 11 | `action_opcode` | 00 ASSIGN **з event_param**; 01 INC; 02 DEC; 03 ADD operand; 04 SUB operand; `> 04` — fail-closed відхилення (`action_valid_w = 0`) |
| 12–15 | `subscriber_cid` | Індекс підписника; при `guard_flags[4] == 1` дозволено будь-який `CID 0..63`, при `guard_flags[4] == 0` діє legacy-правило `subscriber_cid != 0` |

GT/LT порівнюють знакові 32-бітні значення. RANGE використовує дві
знакові 16-бітні межі зі спільного операнда (`int16` зі знаковим розширенням `[lo, hi]`).
Апаратний invariant після [#167](https://github.com/nick-fedchik/kuzmin-machine/issues/167) перевіряє
`signed(candidate_state) >= 0` та відсутність знакового дводоповняльного переповнення `arith_overflow_w`,
а не довільний вираз Invariants.
Для валідної події нуль у bit 0 або bit 1 означає невідому відповідну
умову, а не вимкнену перевірку: gate v2 відхиляє транзакцію. Поточний
lowering встановлює bit 1, лише якщо його евристика пов'язала Invariant
із цим станом; за відсутності Invariants біт залишається нульовим.

Порожні CME-слоти мають нульові поля і ASSIGN, а не окремий тег типу.
Формат не містить повного AST, списку всіх правил, імен подій або
їхніх параметрів. Існування opcode в RTL не доводить правильної
трансляції відповідної конструкції з вихідного тексту.

Джерела:
[`ConceptMicroDescriptor.pack`, компілятор і дизасемблер](../../sw/kpol-ref/kpol_reference.py),
[`CME RTL`](../../hw/rtl/core/km_concept_micro_engine.sv),
[`секвенсер`](../../hw/rtl/core/km_autonomous_sequencer.sv).
HMAC-обгортка з `compile_signed_bram_image` додає 64-байтний заголовок;
це інший контейнер, його не можна завантажувати як сирий образ CME.
Криптографічний контейнер не доводить апаратного Secure Boot.

## 6. Матриця підтримки й межі доказів

«Реалізовано» нижче стосується конкретного шляху та наявних перевірок,
не всіх комбінацій конструкції. Основні тести — у
[`test_kpol_reference.py`](../../sw/kpol-ref/tests/test_kpol_reference.py);
назви наведено як локатори. Історичний аудит — [окреме джерело](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/reviews/kpol-0.2-0.9-audit-review.md),
його статус не переноситься автоматично на поточний код.

| Конструкція / можливість | Стан фронтенду / референсу | CME та інші межі / тест |
|---|---|---|
| Native Concept/Define/Group (`Def` як 8-бітна маска присутності й безіменний атрибут `Token` за RFC-010), типізовані Min/Max, виконувані дужки Static, Name/Help, адресні групи Source | Не реалізовано як native frontend; `•` має розбіжну семантику NOT | KPOL-AUTH/Q-AUTH і Reports #155/#157/#159 + [уточнення RFC-010](../../../Research/sources/author/clarifications-2026-11-13.md#2-витяги-та-локатори); дефекти/прогалини не змінюють CME-RAW-1 |
| Problem/Solution, event/state/rule/set | Реалізовано парсером і перевіркою типів | Наскрізно перевірено лише обмежені сценарії §4; `test_all_documented_examples_parse_and_typecheck` — приклади історичного v0.1, `test_consolidated_example_proof_and_cme_pipeline` — приклад §4 та його зв'язок з образом increase |
| Assumptions, Invariants, Hazards, Alerts, Goals | Реалізовано в Interpreter | Не всі вирази переносяться в CME; `test_v02_alert_observation_and_fail_closed_hazard`, `test_invariant_failure_rolls_back_whole_transaction` |
| `on reject`, `covers` | Реалізовано в референсі з перевіркою hazard-цілі | Не доказ довільних reject-дій у CME; `test_rejected_unknown_sensor_data_latches_fault` |
| `change(...)` | Реалізовано як послідовні внутрішні події | Не апаратний планувальник усіх change-підписок; `test_change_rule_runs_only_for_its_watched_state` |
| Bool, Int32, U64 | Реалізовано в референсі з обмеженнями типів | CME має 32-бітні слова, не загальну U64-семантику; `test_euclid_properties_for_bounded_positive_inputs` |
| U32 | Реалізовано в референсі | Кодогенератори явно відхиляють; `test_v02_u32_codegen_rejects_undefined_abi` |
| Float і одиниці | Реалізовано частково за таблицею `infer` | Не Floating Point бекенд CME; `test_meter_integrates_each_sample_with_units`, `test_unit_mismatch_and_unresolved_names_are_rejected` |
| Pin | Парсинг/типи/нормалізація реалізовані | Не встановлює автоматичного фізичного binding; `test_v03_physical_time_units_and_pin_types` |
| Unknown і транзакційне скасування | Реалізовано в референсі | Не повний перенос у бінарний образ; `test_unknown_guard_aborts_the_transaction` |
| `not`, `•`, `(*)`, арифметика, порівняння, gcd | Реалізовано у виразах з обмеженнями типів | Не всі оператори мають еквівалентне lowering; лексичний тест стрілок не доводить їх граматичної підтримки |
| Proof/assert/scenario/step/expect | Реалізовано для скінченних сценаріїв | Не універсальний доказ; `test_v02_triad_detects_proof_assertion_failure` |
| `every`, `within`, `timeout`, `supervise` | Не реалізовано як конструкції поточного Parser; слова зарезервовані | Наявність одиниць часу не створює таймерів |
| `channel`, Rendezvous, Stream, send/receive, ownership | Не реалізовано як декларації поточного Parser | `cascade_map` не є реалізацією CSP або перевіркою deadlock-freedom |
| Образ метаданих v0.5 | Реалізовано `compile_bram_image`, ліміт 16 правил | Не кодує виконувані охоронці/дії; `test_v05_compiler_bram_binary_generation` |
| CME-образ | Реалізовано пакування, часткове lowering | `test_v10_concept_microcode_bram_generation` перевіряє поля, а не повну семантику; наскрізний тест — §4 |
| C header / runtime, Verilog interconnect, AXI generator | Часткові окремі API, не синтаксис мови | Не оголошені еквівалентними CME; існують GCC/Icarus-тести вибраних сценаріїв |
| HMAC/ACL/anti-replay | Програмні API та тести після виправлень [#115](https://github.com/nick-fedchik/kuzmin-machine/issues/115) і [#164](https://github.com/nick-fedchik/kuzmin-machine/issues/164) (свіжий 16-байтний `nonce`, захист від pre-auth nonce poisoning, `CME-RAW-1` payload за замовчуванням) | Програмна перевірка, не апаратний Secure Boot ([Report #115](../../validation/kpol-cme/signature-115/report.md), [Report #164](../../validation/kpol-cme/secure-boot-164/report.md)) |
| Мутанти та гейт Поппера | Реалізовано як бібліотечні функції | Не обов'язковий релізний gate; не bounded SMT-generator |
| `.kproblem/.ksolution/.kproof` | `parse_triad_files` вимагає три непорожні джерела та Proof-item | Хеші не доводять незалежність авторів; `test_v09_triad_cryptographic_independence_enforcement` |
| `namespace/import` | У звичайному Parser не реалізовано; тріадний API видаляє такі рядки | Це не резолюція просторів імен |
| Лінкування модулів | Реалізовано функцією `link_modules` з перевіркою колізій та ліміту станів | Не резолюція namespace/import; `test_v09_link_modules_bram_limit_exceeded` |
| Розділення графів, `.kmc`, ASN.1, повний історичний опис МК | Не входить до описаного фронтенду/шляху CLI | Історична архітектурна пропозиція, не підтримка поточного компілятора |

## 7. Розриви безпрофільного компілятора та новий профільний шлях

Під час консолідації на базі документа відтворено три прийняті
фронтендом входи. Нижче — результат референсу і видимого lowering,
не новий фізичний експеримент:

| Зміна правила прикладу §4 | Очікування референсу | Поточний CME-образ / розрив |
|---|---|---|
| `when true { set Counter := 42; }`, param=5 | Counter=42 | ASSIGN бере event_param, а не константу 42 |
| `when false { set Counter := Counter + 1; }`, param=5 | Counter=10 | NOP-предикат з INC не зберігає false-охоронець |
| Два правила: `<20` збільшує, `>20` зменшує; param=25 | Counter=9 | Вибрано лише перше правило, його LT-предикат відхиляє подію |

Для відтворення слід замінити відповідний фрагмент Solution, виконати
`parse_module`, `Interpreter(...).run`, `compile_concept_microcode_bram_image`
і `disassemble_concept_microcode`. Під час консолідації RTL для цих
трьох випадків не запускався; їхню direct RTL-симуляцію та додаткові
контрприклади наведено в [Review Report](https://github.com/nick-fedchik/kuzmin-machine/pull/131#issuecomment-6824069657)
на `a3715fc`. Це симуляція, не HIL.

Перелік розривів не вичерпний. Додаткові історичні випадки зі згаданої
симуляції на коміті `a3715fc`, також на основі прикладу §4, та їхній поточний стан після [#183](https://github.com/nick-fedchik/kuzmin-machine/issues/183):

| Зміна | Параметр | Референс | Історичний стан на `a3715fc` та поточний статус |
|---|---|---|---|
| Назвати правило `NotifyStep` | 5 | Counter=11 | На `a3715fc`: евристика імені встановлювала інверсію через підрядок `not` (Counter=10). **Виправлено в #183**: ім'я правила не інвертує охоронець ([Report #183](../../validation/kpol-cme/verifier-lowering-183/report.md)). |
| Охоронець `param >= 5` (або `<=`, або двосторонній `int16` інтервал) | 5 | Counter=11 | На `a3715fc`: емітувався `RANGE` з межами `[5, 0]` (Counter=10). **Виправлено в #183**: `>=` та `<=` транслюються через `INVERT + LT/GT` на всьому `Int32`, двосторонній `int16`-інтервал — у знаковий `RANGE` із fail-closed `KpolError` поза `[-32768, 32767]`; перевірено в RTL-симуляції `km_concept_micro_engine.sv`. |
| Прибрати Invariants, зберегти Goal `Counter >= 0` | 5 | Counter=11 | **Зберігається в безпрофільному шляху**: `invariant known=0`, подію відхилено (Counter=10); у `KPOL-CME-1` відхиляється компілятором до емісії. |
| Охоронець `Counter < 20` | 25 | Counter=11 | **Структурна межа `CME-RAW-1`**: RTL порівнює параметр події, а не стан (Counter=10); у `KPOL-CME-1` відхиляється до емісії (виділено в [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185)). |

Також із читання безпрофільного компілятора: поза двостороннім `RANGE` допоміжний `_eval_int`
повертає 0, якщо правий операнд неможливо обчислити без оточення, а одночасна потреба в операнді
предиката та `ADD/SUB` впирається у спільне поле `operand_val` (структурні межі виділено в [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184) і [#185](https://github.com/nick-fedchik/kuzmin-machine/issues/185)).

Перший інкремент #8 реалізовано в #150 для **явного KPOL-CME-1**:
підтримуваність перевіряється до емісії. Константний ASSIGN, false-guard,
друге правило, state-guard, `>=` та відсутній invariant відхиляються,
а перейменування `Step` → `NotifyStep` не змінює образу.
Безпрофільний API не переписано й не слід використовувати як прийнятий
профільний компілятор. Далі — відокремити/перевірити використання
спільного операнда предиката й дії, відображення Invariants/Hazards,
подій та підписників. Повний референсний синтаксис не треба обіцяти
бекенду до реалізації цих контрактів.

Цей інкремент не закриває #8. Погодження B3-01 вже зафіксовано у
профільному контракті; у [#184](https://github.com/nick-fedchik/kuzmin-machine/issues/184) додано багатоконцептний профіль [`KPOL-CME-2`](kpol-cme2-profile.md) (до 64 концептів, ациклічні каскади, `ADD/SUB/ASSIGN`, `>=`/`<=`/`int16` `RANGE` і явна відмова `CME2-OPERAND-COLLISION`, [Report #184](../../validation/kpol-cme/cme2-profile-184/report.md)), який залишає `KPOL-CME-1` незмінним. Наявність профільних шляхів не приховує прогалин безпрофільного API.

## 8. Походження та історичні дельти

| Вхід | Що перенесено в поточний контракт / де межа |
|---|---|
| [v0.1](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.1.0.md) | Каркас Problem/Solution, типи, контракти й приклади; синтаксис уточнено за поточним Parser |
| [v0.2](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.2.0.md) | Hazard/Alert, Unknown, Proof; апаратна фазова модель не ототожнена з унарним not |
| [v0.3](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.3.0.md) | Одиниці й Pin; таймери та supervision явно не реалізовані |
| [v0.4](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.4.0.md) | Ownership/CSP/backpressure/deadlock — історичні пропозиції, не поточний синтаксис |
| [v0.5](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.5.0.md) | Таблиця метаданих відділена від виконуваного CME-образу; C/RTL/RTM — окремі API |
| [v0.6](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.6.0.md) | Програмні HMAC/ACL не видані за апаратний захист |
| [v0.7](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.7.0.md) | Бібліотечне mutation testing відділено від релізного gate і SMT-доведення |
| [v0.8](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.8.0.md) | C/AXI API відділено від доведення фіксованого фізичного виконавця |
| [v0.9](https://github.com/nick-fedchik/kuzmin-machine/blob/707fdba697d92ef9874c9013eb6f4f3cb2796d70/specs/kpol/kpol-0.9.0.md) | Тріадний API та linker відділено від незалежності авторів і namespace resolution |

Дельти залишено незмінними на стабільних шляхах: на них посилаються
історичні звіти й тести. Вони є входами/історією, не дев'ятьма
одночасними нормативними стандартами. Суцільної повторної перевірки
всіх тверджень цих документів ця консолідація не виконує. Старий
No-Go для v1.0 не скасовується автоматично.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.6.1 | 2026-11-14 | #184: зафіксовано додавання багатоконцептного профілю `KPOL-CME-2` (`kpol-cme2-profile.md`) зі збереженням `KPOL-CME-1` без змін. |
| 0.6.0 | 2026-11-14 | #183: синхронізовано §3 (`change(...)`, анти-вакуумність `verify_module`), §5 (`guard_flags[4]`, знаковий `RANGE`, fail-closed `action_opcode`, знакове переповнення за #167), §6 (#115, #164, RFC-010) та §7 (виправлення `NotifyStep` і `>=`/`<=`/`RANGE` у референсі зі збереженням структурних меж `CME-RAW-1`). |
| 0.5.0 | 2026-11-13 | #159: межа підтримки типізованих індексів Collection/Array; current grammar/ABI незмінні. |
| 0.4.0 | 2026-11-13 | #157: межа підтримки виконуваних дужок Static, оцінка уточнень; current grammar/ABI не змінено. |
| 0.3.0 | 2026-11-13 | #155: явна межа native авторського синтаксису й current DSL; `•`, Name/Help та адреси, без змін реалізації. |
| 0.2.0 | 2026-11-12 | #150: окремий strict KPOL-CME-1 і CLI Proof gate; відмежовано незмінний експериментальний API та його контрприклади. |
| 0.1.1 | 2026-11-12 | Редакція NG: структура, навігація та оформлення WP; нових результатів не заявлено. |
| 0.1.0 | 2026-11-12 | Один робочий контракт фронтенду/CME, формати образів, матриця підтримки та відтворені розриви для початку #8; за рецензією уточнено прапорці, межі тестів і додаткові контрприклади. |

## Абревіатури та глосарій

| Термін | Значення |
|---|---|
| AST | Дерево абстрактного синтаксису |
| BRAM / CME | Блокова пам'ять FPGA / Concept Micro-Engine |
| Frontend / backend | Парсинг і типи / цільове перетворення та емісія |
| Lowering | Перетворення конструкції в представлення, доступне цільовому виконавцю |
| ABI | Контракт бінарного представлення й взаємодії |
| HIL | Перевірка з фізичним обладнанням |
| RTM | Матриця трасування вимог |
