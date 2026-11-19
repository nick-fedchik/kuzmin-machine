# Модуль `Engineering/sw/vmk-go`: Віртуальна Машина Кузьміна (VMK) та повноекранний інтерактивний TUI-дебагер на Go (`SemVer 0.3.1`)

* **Версія:** 1.3.0
* **Дата:** 2026-11-19
* **Тип WP:** Guide
* **Issue:** `Closes` [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276), оновлено в [#278](https://github.com/nick-fedchik/kuzmin-machine/issues/278), [#280](https://github.com/nick-fedchik/kuzmin-machine/issues/280) та [#289](https://github.com/nick-fedchik/kuzmin-machine/issues/289); реалізація — [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274) ([PR #275](https://github.com/nick-fedchik/kuzmin-machine/pull/275)).
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI.

## Призначення

Каталог `Engineering/sw/vmk-go/` містить єдиний канонічний самодостатній Go-модуль (`github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go`, SemVer `0.3.1`, `go >= 1.22`, виключно стандартна бібліотека `std` без жодних зовнішніх залежностей, `CGO_ENABLED=0`), який реалізує двомодовий емулятор **VMK (Virtual Machine of Kuzmin)**, нативний компілятор і двосторонній транспайлер мови **EKPOL (`Ergonomic KPOL 0.1.0`)**, потоковий інтерфейс `STDIO`, крос-платформний повноекранний інтерактивний TUI-дебагер реактивних каскадів подій (`Linux / macOS / Windows`: `--tui`, `--tui-canvas`, `--render-fullscreen-tui`, `--render-tui-frame`), а також build-тег ізоляції публічної збірки (`-tags public`) і скрипти крос-компіляції та експорту автономного публічного пакета.

## Навігація чи використання

### Основні документи та артефакти

* **Повний практичний Посібник користувача:** [`Engineering/guides/vmk-users-guide.md`](../../guides/vmk-users-guide.md) (`1.3.0`) — детальний розбір обох режимів (`conceptual` та `bram64`), читання знімків `PRE-LOAD -> POST-LOAD`, повноекранного TUI-дебагера (`Concept Inspector`, `Manual Event Creator [e]`, `Single Micro-Step [n/Space]`, `Modify State [m]`, `Diff/Source [d]`), потоків `STDIO` (`# @stdin` / `# @stdout`), 10 вбудованих прикладів, написання програм на `EKPOL` (`symbolic` та `keyword`), роботи з фізичною платою `PYNQ-Z1`, крос-компіляції релізів (`build_releases.sh`) та експорту автономного пакета (`export_public_bundle.sh`).
* **Нормативні специфікації:** [`Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger.md`](../../specifications/sw/vmk-go-emulator-and-tui-debugger.md) (`1.3.0`) та [`Engineering/specifications/kpol/ekpol-specification.md`](../../specifications/kpol/ekpol-specification.md) (`1.0.1`).
* **Звіти верифікації:** [`Engineering/validation/kpol-cme/vmk-go-274/report.md`](../../validation/kpol-cme/vmk-go-274/report.md) (`1.1.0`), [`Engineering/validation/kpol-cme/ekpol-278/report.md`](../../validation/kpol-cme/ekpol-278/report.md) (`1.0.1`) та тестові пакети [`Engineering/sw/tests/test_vmk_go_274.py`](../tests/test_vmk_go_274.py) (`M1..M7`) і [`Engineering/sw/tests/test_ekpol_278.py`](../tests/test_ekpol_278.py) (`M1..M5`).

### Структура пакета

* [`go.mod`](go.mod) — маніфест модуля (`go 1.22`, `0` директив `require`);
* [`cmd/vmk/main.go`](cmd/vmk/main.go) — точка входу виконуваного файлу `vmk`;
* [`internal/vmk/cli.go`](internal/vmk/cli.go) — парсер прапорців командного рядка та маршрутизація режимів;
* [`internal/vmk/tui_fullscreen.go`](internal/vmk/tui_fullscreen.go), [`internal/vmk/term_linux.go`](internal/vmk/term_linux.go), [`internal/vmk/term_darwin.go`](internal/vmk/term_darwin.go), [`internal/vmk/term_other.go`](internal/vmk/term_other.go) — крос-платформний повноекранний інтерактивний TUI-дебагер (`VMK v0.3.1`: платформні термінальні драйвери `Linux TCGETS/TCSETS`, `macOS TIOCGETA/TIOCSETA` та non-POSIX fallback для `Windows` при `CGO_ENABLED=0`, `TIOCGWINSZ`, `alternate screen`, UTF-8 псевдографіка `┌─┬─┐`, `Concept Inspector`, `Manual Event Creator [e]`, `Single Micro-Step [n/Space]`, `Modify State [m]`, `Source/Diff [d]`);
* [`internal/vmk/tui.go`](internal/vmk/tui.go) — детермінований 4-панельний ASCII-рендер (`--render-tui-frame`);
* [`internal/vmk/ekpol.go`](internal/vmk/ekpol.go) — нативний парсер, статичний верифікатор, компілятор `CME-RAW-1` та двосторонній транспайлер `EKPOL 0.1.0 <-> KPOL` (`--to-kpol`, `--to-ekpol`, `--ekpol-style symbolic|keyword`);
* [`examples/`](examples/bms_safety_cascade.ekpol) — 9 канонічних прикладів на мові `EKPOL` ([`bms_safety_cascade.ekpol`](examples/bms_safety_cascade.ekpol), [`cascade_4concept.ekpol`](examples/cascade_4concept.ekpol), [`increase.ekpol`](examples/increase.ekpol), [`decrease.ekpol`](examples/decrease.ekpol), [`if_toggle.ekpol`](examples/if_toggle.ekpol), [`sum_autoreset.ekpol`](examples/sum_autoreset.ekpol), [`nod_euclid.ekpol`](examples/nod_euclid.ekpol), [`factorial.ekpol`](examples/factorial.ekpol), [`tachometer.ekpol`](examples/tachometer.ekpol)) та 4 парні класичні відповідники `.kpol` ([`bms_safety_cascade.kpol`](examples/bms_safety_cascade.kpol), [`cascade_4concept.kpol`](examples/cascade_4concept.kpol), [`increase.kpol`](examples/increase.kpol), [`decrease.kpol`](examples/decrease.kpol));
* [`internal/vmk/bram64.go`](internal/vmk/bram64.go) — апаратно-точний 64-слотовий BRAM-режим (`CME-RAW-1`, `CFG-P` / `CFG-P-HA`, `Bank 0 / Bank 1` з `CRC-8-CCITT`, `FIFO 16`, `StepSingleHop`, `ModifyConceptState`);
* [`internal/vmk/conceptual.go`](internal/vmk/conceptual.go) — навчально-концептуальна віртуальна машина за `RFC-001..018` (`?`, `Int32`, `U64`, `Float`, біт `_`, адресації `←`, `→`, `|`, `:`, бар'єр `→ •`, захист `Busy`);
* [`internal/vmk/kpol_compiler.go`](internal/vmk/kpol_compiler.go) — вбудований компілятор профілів `KPOL-CME-1`, `KPOL-CME-2`, `KPOL-AUTH` та `EKPOL`;
* [`internal/vmk/snapshot.go`](internal/vmk/snapshot.go) — життєвий цикл підключення `PRE-LOAD -> POST-LOAD -> RUNNING`, аналіз топології та диференціальна таблиця слотів;
* [`internal/vmk/pynq.go`](internal/vmk/pynq.go) (`//go:build !public`) та [`internal/vmk/pynq_public.go`](internal/vmk/pynq_public.go) (`//go:build public`) — штатний інженерний SSH/MMIO-драйвер для фізичних плат `PYNQ-Z1` під `flock /tmp/km-bench.lock` (`!public`) та ізольована публічна заглушка (`-tags public`, підтримує лише `--target sim` без `/dev/mem` та лабораторних IP);
* [`internal/vmk/stdio.go`](internal/vmk/stdio.go) — потоковий інтерфейс `STDIO` (`stdin` / `stdout` / `stderr`) і прагми `# @stdin` / `# @stdout`;
* [`internal/vmk/examples.go`](internal/vmk/examples.go) — каталог 10 вбудованих прикладів (`if`, `sum`, `nod`, `factorial`, `tachometer`, `bms`, `increase`, `decrease`, `cascade`, `auth`);
* [`internal/vmk/vmk_test.go`](internal/vmk/vmk_test.go), [`internal/vmk/pynq_test.go`](internal/vmk/pynq_test.go), [`internal/vmk/pynq_public_test.go`](internal/vmk/pynq_public_test.go) — модульні тести Go для штатної та публічної збірок;
* [`scripts/build_releases.sh`](scripts/build_releases.sh) та [`scripts/export_public_bundle.sh`](scripts/export_public_bundle.sh) — крос-компіляція статичних бінарників (`CGO_ENABLED=0 -tags public` для `linux/{amd64,arm64}`, `darwin/{arm64,amd64}`, `windows/amd64.exe` + `SHA256SUMS` у `dist/`) та однокроковий експорт очищеного автономного пакета `module vmk` із автоматичним аудитом відсутності приватних даних.

### Швидкі команди збірки, тестування та запуску

```bash
# 1. Запуск модульних тестів Go у штатному інженерному та ізольованому публічному режимах (офлайн, < 0.06 с)
cd Engineering/sw/vmk-go
go test -v ./...
go test -tags public -v ./...

# 2. Збірка бінарника ./vmk (доданий у .gitignore), крос-компіляція 5 релізів і запуск повноекранного TUI
go build -o vmk ./cmd/vmk
bash scripts/build_releases.sh
./vmk --tui --program examples/bms_safety_cascade.ekpol
./vmk --example bms --render-fullscreen-tui

# 3. Інспекція дескрипторів зовнішнього файлу .kpol відносно Engineering/sw/vmk-go
./vmk --program ../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol \
  --profile KPOL-CME-2 --dump-concepts

# 4. Детермінований 4-панельний TUI-кадр та потокове STDIO для 4-рівневого каскаду безпеки BMS
printf "Cell_Delta_mV 15\nCell_Delta_mV _\nCell_Delta_mV 120\nCell_Delta_mV 180\nCell_Delta_mV 250\n" | \
  ./vmk --mode bram64 --example bms --stdio --render-tui-frame
```

## Обмеження

1. Автор концепції Машини Кузьміна — **М. Ю. Кузьмін** ([`Research/sources/`](../../../Research/sources/README.md)); цей Go-модуль є похідною інженерною реалізацією проєкту (`AGENTS.md §6.1`).
2. Режим `--mode conceptual` призначений для навчально-концептуального моделювання (`RFC-001..018`) і не знімає блокування з 12 відкритих точок `KPOL-AUTH-U01..U12` у [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).
3. Підключення до фізичних плат `PYNQ-Z1` (`--target pynq1 | pynq2`) вимагає доступу до стендової мережі та автоматично синхронізується через `/tmp/km-bench.lock`. Детальний перелік обмежень наведено у [Посібнику користувача VMK §«Обмеження»](../../guides/vmk-users-guide.md#обмеження).

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.3.0 | 2026-11-19 | #289: консолідовано крос-платформний пакет `VMK v0.3.1` із `drafts/KuzminMachine/vmk` у єдиний канонічний модуль `Engineering/sw/vmk-go/` (`term_{linux,darwin,other}.go`, build-тег ізоляції `pynq.go` / `pynq_public.go`, 4 класичні приклади `examples/*.kpol`, `scripts/build_releases.sh` та `scripts/export_public_bundle.sh`). |
| 1.2.0 | 2026-11-18 | #280: оновлено під `VMK v0.3.0`, додано опис повноекранного інтерактивного TUI-дебагера `internal/vmk/tui_fullscreen.go` (`--tui`, `--tui-canvas`, `--render-fullscreen-tui`). |
| 1.1.0 | 2026-11-18 | #278: оновлено під `VMK v0.2.0`, додано опис `internal/vmk/ekpol.go` та каталогу `examples/*.ekpol`. |
| 1.0.0 | 2026-11-18 | Перша редакція навігаційного посібника каталогу `Engineering/sw/vmk-go/` за Issue #276. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **VMK** | Virtual Machine of Kuzmin — двомодовий емулятор, транспайлер і повноекранний TUI-дебагер Машини Кузьміна на Go (`v0.3.1`). |
| **EKPOL** | Ergonomic KPOL (`0.1.0`) — ергономічна концептно-орієнтована мова програмування МК у 7-бітному ASCII (`.ekpol`). |
| **`CME-RAW-1`** | 16-байтний (`W0..W3`) двійковий формат дескриптора концепту в 64-слотовій BRAM (`1024 B`). |
| **`TUI`** | Text-based User Interface — повноекранний багатопанельний інтерактивний інтерфейс налагодження каскадів подій (`tui_fullscreen.go`) та детермінований 4-панельний рендер (`tui.go`). |
| **`STDIO`** | Потоковий інтерфейс вводу/виводу через стандартні потоки UNIX (`stdin`, `stdout`, `stderr`). |
