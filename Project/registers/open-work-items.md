# Відкриті роботи та рішення власника

* **Версія:** 0.4.4
* **Дата:** 2026-11-14
* **Тип WP:** Register
* **Власник рішень:** Микола Федчик.
* **База:** [знімок GitHub після оновлення](../assessments/ng-migration/raw/owner-status-decisions-20261112.json).
* **Повторна перевірка з #148:** [фактичні стани під час міграції](../assessments/structure-migration/raw/execution-results.json).

## Межі та схема

Початковий запис п'яти розглянутих Issues та окремої міграції
[#148](https://github.com/nick-fedchik/kuzmin-machine/issues/148) актуалізовано станом на
`2026-11-14` за фактичними злиттями `PR #149–#161`, стеку аудиту `#176` (`PR #163`, `#170–#175`),
правок за рецензіями (`PR #180–#182`), стеку розвитку KPOL `#190` (`PR #187–#189`) та новою декомпозицією (`#183–#186`, `#191–#192`); це не повторний аудит усього історичного беклогу.
GitHub Issue має стан Open/Closed; окреме поле Project має
Todo/In progress/Postponed/Done. Відкладення або закриття епіка в GitHub без окремого акту приймання не є автоматичним затвердженням усієї нормативної бази.

## Рішення та записи

### Базові задачі першого зрізу (оновлено станом на 2026-11-14)

| Issue | GitHub | Project | Рішення та залишок |
|---|---|---|---|
| [#20 — ліцензія й авторство](https://github.com/nick-fedchik/kuzmin-machine/issues/20) | Closed, completed | Done | Власник визначив пропрієтарний, не відкритий режим і доручив закриття. `LICENSE`, `AUTHORS.md`, `NOTICE` влиті до `main` у складі [PR #149](https://github.com/nick-fedchik/kuzmin-machine/pull/149). |
| [#5 — S2](https://github.com/nick-fedchik/kuzmin-machine/issues/5) | Closed, completed (2026-11-13) | Postponed (рішення 2026-11-12) | За рішенням власника 2026-11-12 роботу відкладено (`Postponed`), а 2026-11-13 Issue закрито в GitHub; результати B1–B5 збережено, але повну нормативну базу MVP цим кроком автоматично не проголошено. |
| [#8 — компілятор](https://github.com/nick-fedchik/kuzmin-machine/issues/8) | Open | Todo | Часткові кроки [#150](https://github.com/nick-fedchik/kuzmin-machine/issues/150) ([PR #152](https://github.com/nick-fedchik/kuzmin-machine/pull/152)), [#153](https://github.com/nick-fedchik/kuzmin-machine/issues/153) ([PR #154](https://github.com/nick-fedchik/kuzmin-machine/pull/154)), [#155](https://github.com/nick-fedchik/kuzmin-machine/issues/155) ([PR #156](https://github.com/nick-fedchik/kuzmin-machine/pull/156)), [#157](https://github.com/nick-fedchik/kuzmin-machine/issues/157) ([PR #158](https://github.com/nick-fedchik/kuzmin-machine/pull/158)) та [#159](https://github.com/nick-fedchik/kuzmin-machine/issues/159) ([PR #160](https://github.com/nick-fedchik/kuzmin-machine/pull/160)) влиті до `main`; повний lowering, native-фронтенд і приймальні критерії залишаються відкритою роботою. |
| [#120 — зручність KPOL](https://github.com/nick-fedchik/kuzmin-machine/issues/120) | Open | Todo | Потрібне погодження протоколу до дослідження користувачів. Залежність [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19) закрита ([PR #142](https://github.com/nick-fedchik/kuzmin-machine/pull/142)), але дослідження не виконане. |
| [#115 — assert підпису](https://github.com/nick-fedchik/kuzmin-machine/issues/115) | Closed, completed | Done | Перевірку булевого результату `verify_bram_signature` та вивід причини відмови виправлено і влито до `main` у [PR #161](https://github.com/nick-fedchik/kuzmin-machine/pull/161) ([звіт](../../Engineering/validation/kpol-cme/signature-115/report.md)). |
| [#148 — структура Research/Engineering/Project](https://github.com/nick-fedchik/kuzmin-machine/issues/148) | Closed, completed | Done | Міграцію дерева `Research / Engineering / Project` влито до `main` у [PR #149](https://github.com/nick-fedchik/kuzmin-machine/pull/149). |

### Пакет виправлень за науково-інженерним аудитом та рецензіями (злито 2026-11-14)

| Issue | GitHub | Стан виконання | Зміст і межа |
|---|---|---|---|
| [#151 — черга B5 без втрат і арбітраж каскаду](https://github.com/nick-fedchik/kuzmin-machine/issues/151) | Closed, completed | Done ([PR #163](https://github.com/nick-fedchik/kuzmin-machine/pull/163)) | Утримання без втрат за `valid && ready`, резервування слота каскадом і `sw_trigger`, буфер `cascade_pending_*_q` ([звіт](../../Engineering/validation/kpol-cme/queue-retention-151/report.md)). |
| [#162 — метадані WP у `j501-hardware-interface.md`](https://github.com/nick-fedchik/kuzmin-machine/issues/162) | Closed, completed | Done ([PR #163](https://github.com/nick-fedchik/kuzmin-machine/pull/163)) | Усунення блокера `check_wp_documents.py` додаванням «Історії версій» і «Глосарію». |
| [#164 — контейнер підпису Secure Boot у `kpol_reference.py`](https://github.com/nick-fedchik/kuzmin-machine/issues/164) | Closed, completed | Done ([PR #170](https://github.com/nick-fedchik/kuzmin-machine/pull/170)) | Свіжий `os.urandom(16)` nonce за замовчуванням, оновлення anti-replay лише після валідного HMAC, `CME-RAW-1` payload ([звіт](../../Engineering/validation/kpol-cme/secure-boot-164/report.md)). |
| [#165 — узгодження `KM-PAT-01/02` та ADR `B6`](https://github.com/nick-fedchik/kuzmin-machine/issues/165) | Closed, completed | Done ([PR #171](https://github.com/nick-fedchik/kuzmin-machine/pull/171)) | Розмежування L2/DRAM vs L1/Shared Memory GPU, двопортовості BRAM/B4 та цільових гіпотез vs виміряних даних. |
| [#166 — фізичні невідповідності протоколів `EXP-GPU-01/02`](https://github.com/nick-fedchik/kuzmin-machine/issues/166) | Closed, completed | Done ([PR #172](https://github.com/nick-fedchik/kuzmin-machine/pull/172)) | Тільки цифрові 3,3 В щупи `1x` на RP2040, реальна шина AXI GP0 у Zynq-7020 і явна роль Port B BRAM. |
| [#167 — семантика ядра `km_concept_micro_engine.sv`](https://github.com/nick-fedchik/kuzmin-machine/issues/167) | Closed, completed | Done ([PR #173](https://github.com/nick-fedchik/kuzmin-machine/pull/173)) | Каскад на `CID 0` (`guard_flags[4]`), по-концептний `state_changed_o`, знакове переповнення, знаковий `RANGE` та fail-closed для невідомих `action_opcode` ([звіт](../../Engineering/validation/kpol-cme/cme-semantics-167/report.md)). |
| [#168 — AXI B4 `Load vs Run`, W1C `0x02C` і `pynq_z1_top`](https://github.com/nick-fedchik/kuzmin-machine/issues/168) | Closed, completed | Done ([PR #174](https://github.com/nick-fedchik/kuzmin-machine/pull/174)) | Закриття 1-тактової гонитви `Load vs Run`, W1C-очищення `0x02C` при `busy == 0`, 2-FF CDC `sw[1:0]`, антибрязкіт `btn[0]` (1 мс) і `param = 1` ([звіт](../../Engineering/validation/kpol-cme/axi-b4-pynq-168/report.md)). |
| [#169 — синхронізація реєстрів, формального аналізу, B1/S2 і TRL](https://github.com/nick-fedchik/kuzmin-machine/issues/169) | Closed, completed | Done ([PR #175](https://github.com/nick-fedchik/kuzmin-machine/pull/175)) | Узгодження `open-work-items.md`, `formal-analysis.md`, `system-boundary-allocation-b1.md`, `s2-candidate-system.md`, `trl/report.md` та реєстрів WP. |
| [#177 — уточнення `KM-PAT-01/02` та ADR `B6` за рецензією](https://github.com/nick-fedchik/kuzmin-machine/issues/177) | Closed, completed | Done ([PR #181](https://github.com/nick-fedchik/kuzmin-machine/pull/181)) | Розширення глосарію, часова шкала залежних пунктів формули й межі L2/PCIe для дискретних GPU. |
| [#178 — уточнення `EXP-GPU-01/protocol.md` за рецензією](https://github.com/nick-fedchik/kuzmin-machine/issues/178) | Closed, completed | Done ([PR #180](https://github.com/nick-fedchik/kuzmin-machine/pull/180)) | Виправлення відносного шляху до `pynq_z1_top` і таблиці напрямків ліній PMOD JA. |
| [#179 — уточнення специфікації B5, CME та шаблону Report](https://github.com/nick-fedchik/kuzmin-machine/issues/179) | Closed, completed | Done ([PR #182](https://github.com/nick-fedchik/kuzmin-machine/pull/182)) | Переріз черги до вибірки BRAM, дводоповняльна формула overflow та обов'язкова фіксація команди й ISO 8601 timestamp у `raw/*.log`. |

### Декомпозиція подальшого розвитку мови KPOL (2026-11-14)

| Issue | GitHub | Стан виконання | Зміст і межа |
|---|---|---|---|
| [#183 — дефекти верифікатора й CME-lowering у `kpol_reference.py` та синхронізація `RFC-010`](https://github.com/nick-fedchik/kuzmin-machine/issues/183) | Closed, completed | Done ([PR #187](https://github.com/nick-fedchik/kuzmin-machine/pull/187), стек [#190](https://github.com/nick-fedchik/kuzmin-machine/issues/190), sub-issue `#8`) | Одноразовий початковий `change(...)`, відхилення вакуумних `Proof`, усунення евристики імені правила, точне lowering `>=`/`<=`/`int16` `RANGE` та фіксація `RFC-010` ([звіт](../../Engineering/validation/kpol-cme/verifier-lowering-183/report.md)); рецензія `claude-sonnet-5.5` — `APPROVE`. |
| [#184 — профіль `KPOL-CME-2` на `CME-RAW-1`](https://github.com/nick-fedchik/kuzmin-machine/issues/184) | Closed, completed | Done ([PR #188](https://github.com/nick-fedchik/kuzmin-machine/pull/188), sub-issue `#8`) | Багатоконцептна компіляція до 64 станів, ациклічні каскади (включно з `CID 0`), `ADD/SUB/ASSIGN`, розширені предикати, детектор `CME2-OPERAND-COLLISION` і AXI RTL-еквівалентність ([специфікація](../../Engineering/specifications/kpol/kpol-cme2-profile-0.1.0.md), [звіт](../../Engineering/validation/kpol-cme/cme2-profile-184/report.md)); повторна рецензія `claude-sonnet-5.5` — «Прийнято із зауваженнями» (залишок — [#191](https://github.com/nick-fedchik/kuzmin-machine/issues/191)). |
| [#185 — CR `KPOL-SYS-02` і дескриптор `CME-RAW-2`](https://github.com/nick-fedchik/kuzmin-machine/issues/185) | Closed, completed | Done ([PR #189](https://github.com/nick-fedchik/kuzmin-machine/pull/189), sub-issue `#8`; ADR у статусі `Proposed`, рішення власника щодо варіантів А/Б/В очікується) | Проєкт рішення [ADR B7](../../Engineering/decisions/cme-raw2-kpol-sys02.md) (Proposed): 32-байтний слот `W0..W7`, `W1.state_valid` для `_`, розділені 32-бітні операнди охоронця й дії, двобанкова пам'ять `2 × RAMB36E1` (проєктна ціль 8 тактів, не перевірено без RTL `CME-RAW-2`) і сумісність із `Secure Boot` ([звіт](../../Engineering/validation/kpol-cme/cr-cme-raw2-185/report.md)); повторна рецензія `claude-sonnet-5.5` — «Прийнято із зауваженнями» (залишок — [#192](https://github.com/nick-fedchik/kuzmin-machine/issues/192)). |
| [#186 — Native-діалект `KPOL-AUTH` після відповідей на `RFC-009`, `015–017`](https://github.com/nick-fedchik/kuzmin-machine/issues/186) | Open | Blocked | Очікує відповідей Автора Машини у `drafts` (`PR #4`: оновлений `RFC-009` і нові `RFC-015..017`). |
| [#191 — специфікація й тести `KPOL-CME-2` проти коду (знахідки рецензії PR #188)](https://github.com/nick-fedchik/kuzmin-machine/issues/191) | Open | Ready (sub-issue `#8`) | Розбіжність §2.1 специфікації з поведінкою парсера, golden-файл `KPOL-CME-1`, авторство редакції звіту. |
| [#192 — недоведені твердження про `CME-RAW-2` у похідних документах (знахідки рецензії PR #189)](https://github.com/nick-fedchik/kuzmin-machine/issues/192) | Open | Ready (sub-issue `#8`) | «8 тактів» без позначки «ціль / не перевірено» у README і реєстрах, скрипт `verify_cr_cme_raw2.py`, джерело латентності, статус критерію Secure Boot. |

Джерела рішень:
[пропрієтарний режим](https://github.com/nick-fedchik/kuzmin-machine/issues/20#issuecomment-6829699920),
[відкладення S2 та відкритий беклог](https://github.com/nick-fedchik/kuzmin-machine/issues/5#issuecomment-6829701768).

## Ведення й обмеження

При новому рішенні оновлюють GitHub і цей запис, не переписуючи
первинний знімок. Новий знімок зберігають окремо.
Заміна структури не повинна автоматично закривати #5/#8/#120/#115.
Нове розміщення у GitHub-посиланнях вводять після появи файлів у main;
старі посилання на конкретні коміти не змінюють.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.4.4 | 2026-11-14 | #192: у рядку #185 позначено «8 тактів» для `CME-RAW-2` як проєктну ціль (не перевірено без RTL). |
| 0.4.3 | 2026-11-14 | #193: зафіксовано злиття стеку #190 (`PR #187–#189`, `#183–#185` закрито), нові знахідки рецензій #191 і #192. |
| 0.4.2 | 2026-11-14 | #185: зафіксовано публікацію PR #188 (`#184`) та підготовку проєкту рішення ADR B7 (`KPOL-SYS-02` і дескриптор `CME-RAW-2`, `#185`). |
| 0.4.1 | 2026-11-14 | #184: зафіксовано рецензію PR #187 (`#183`) та реалізацію багатоконцептного профілю `KPOL-CME-2` (`#184`). |
| 0.4.0 | 2026-11-14 | #183: зафіксовано закриття злитого стеку #176 (`PR #163`, `#170–#175`) та правок за рецензіями (`#177–#179` у `PR #180–#182`), а також додано підзадачі розвитку мови KPOL `#183–#186`. |
| 0.3.0 | 2026-11-14 | #169: актуалізовано статуси закритих #148 (PR #149), #115 (PR #161), #5 (закрито в GitHub зі збереженням Postponed за рішенням 2026-11-12), часткових кроків #8 (PR #152–#160) та додано відкритий стек аудиту #151/#162/#164–#169. |
| 0.1.0 | 2026-11-12 | Рішення власника про #20, Postponed для #5 та відкриті #8/#120/#115. |
| 0.2.0 | 2026-11-12 | Окрема міграція #148 без поновлення S2 чи закриття compiler/usability/finding. |

## Абревіатури та глосарій

WI — робоча задача; Project — GitHub Projects із власним полем Status;
S2 — вимоги, архітектура та трасування; Todo — беклог, не почате виконання.
