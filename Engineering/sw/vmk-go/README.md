# Модуль `Engineering/sw/vmk-go`: Віртуальна Машина Кузьміна (VMK) та 4-панельний TUI-дебагер на Go

* **Версія:** 1.0.0
* **Дата:** 2026-11-18
* **Тип WP:** Guide
* **Issue:** `Closes` [#276](https://github.com/nick-fedchik/kuzmin-machine/issues/276); реалізація — [#274](https://github.com/nick-fedchik/kuzmin-machine/issues/274) ([PR #275](https://github.com/nick-fedchik/kuzmin-machine/pull/275)).
* **Відповідальний:** власник Микола Федчик; укладач — GitHub Copilot CLI.

## Призначення

Каталог `Engineering/sw/vmk-go/` містить самодостатній Go-модуль (`github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go`, SemVer `0.1.0`, `go >= 1.22`, виключно стандартна бібліотека `std` без жодних зовнішніх залежностей), який реалізує двомодовий емулятор **VMK (Virtual Machine of Kuzmin)**, потоковий інтерфейс `STDIO` та 4-панельний TUI-дебагер реактивних каскадів подій.

## Навігація чи використання

### Основні документи та артефакти

* **Повний практичний Посібник користувача:** [`Engineering/guides/vmk-users-guide.md`](../../guides/vmk-users-guide.md) (`1.0.0`) — детальний розбір обох режимів (`conceptual` та `bram64`), читання знімків `PRE-LOAD -> POST-LOAD`, анатомії 4 панелей TUI, гарячих клавіш, потоків `STDIO` (`# @stdin` / `# @stdout`), 10 вбудованих прикладів, роботи з фізичною платою `PYNQ-Z1` та усіх прапорців CLI.
* **Нормативна специфікація ПЗ:** [`Engineering/specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md`](../../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md) (`1.0.1`).
* **Звіт верифікації та натурного HIL на `pynq2`:** [`Engineering/validation/kpol-cme/vmk-go-274/report.md`](../../validation/kpol-cme/vmk-go-274/report.md) (`1.0.1`) та інтеграційно-мутаційний пакет [`Engineering/sw/tests/test_vmk_go_274.py`](../tests/test_vmk_go_274.py) (`M1..M5`).

### Структура пакета

* [`go.mod`](go.mod) — маніфест модуля (`go 1.22`, `0` директив `require`);
* [`cmd/vmk/main.go`](cmd/vmk/main.go) — точка входу виконуваного файлу `vmk`;
* [`internal/vmk/cli.go`](internal/vmk/cli.go) — парсер прапорців командного рядка та маршрутизація режимів;
* [`internal/vmk/bram64.go`](internal/vmk/bram64.go) — апаратно-точний 64-слотовий BRAM-режим (`CME-RAW-1`, `CFG-P` / `CFG-P-HA`, `Bank 0 / Bank 1` з `CRC-8-CCITT`, `FIFO 16`);
* [`internal/vmk/conceptual.go`](internal/vmk/conceptual.go) — навчально-концептуальна віртуальна машина за `RFC-001..018` (`?`, `Int32`, `U64`, `Float`, біт `_`, адресації `←`, `→`, `|`, `:`, бар'єр `→ •`, захист `Busy`);
* [`internal/vmk/kpol_compiler.go`](internal/vmk/kpol_compiler.go) — вбудований компілятор профілів `KPOL-CME-1`, `KPOL-CME-2` та `KPOL-AUTH`;
* [`internal/vmk/snapshot.go`](internal/vmk/snapshot.go) — життєвий цикл підключення `PRE-LOAD -> POST-LOAD -> RUNNING`, диференціальна таблиця слотів і SSH/MMIO-драйвер для `PYNQ-Z1` під `flock /tmp/km-bench.lock`;
* [`internal/vmk/stdio.go`](internal/vmk/stdio.go) — потоковий інтерфейс `STDIO` (`stdin` / `stdout` / `stderr`) і прагми `# @stdin` / `# @stdout`;
* [`internal/vmk/tui.go`](internal/vmk/tui.go) — 4-панельний TUI-дебагер (`--tui`, `--render-tui-frame`);
* [`internal/vmk/examples.go`](internal/vmk/examples.go) — каталог 10 вбудованих прикладів (`if`, `sum`, `nod`, `factorial`, `tachometer`, `bms`, `increase`, `decrease`, `cascade`, `auth`);
* [`internal/vmk/vmk_test.go`](internal/vmk/vmk_test.go) — модульні тести Go.

### Швидкі команди збірки, тестування та запуску

```bash
# 1. Запуск модульних тестів Go (офлайн, < 0.05 с)
cd Engineering/sw/vmk-go
go test -v ./...

# 2. Перевірка версії та прогін усіх 10 вбудованих прикладів
go run ./cmd/vmk --version
go run ./cmd/vmk --example all

# 3. 4-панельний TUI-кадр та потокове STDIO для 4-рівневого каскаду безпеки BMS
printf "Cell_Delta_mV 15\nCell_Delta_mV _\nCell_Delta_mV 120\nCell_Delta_mV 180\nCell_Delta_mV 250\n" | \
  go run ./cmd/vmk --mode bram64 --example bms --stdio --render-tui-frame
```

## Обмеження

1. Автор концепції Машини Кузьміна — **М. Ю. Кузьмін** ([`Research/sources/`](../../../Research/sources/README.md)); цей Go-модуль є похідною інженерною реалізацією проєкту (`AGENTS.md §6.1`).
2. Режим `--mode conceptual` призначений для навчально-концептуального моделювання (`RFC-001..018`) і не знімає блокування з 12 відкритих точок `KPOL-AUTH-U01..U12` у [#186](https://github.com/nick-fedchik/kuzmin-machine/issues/186).
3. Підключення до фізичних плат `PYNQ-Z1` (`--target pynq1 | pynq2`) вимагає доступу до стендової мережі та автоматично синхронізується через `/tmp/km-bench.lock`. Детальний перелік обмежень наведено у [Посібнику користувача VMK §«Обмеження»](../../guides/vmk-users-guide.md#обмеження).

## Історія версій

| Версія | Дата | Зміни |
| :--- | :--- | :--- |
| 1.0.0 | 2026-11-18 | Перша редакція навігаційного посібника каталогу `Engineering/sw/vmk-go/` за Issue #276. |

## Абревіатури та глосарій

| Термін | Значення |
| :--- | :--- |
| **VMK** | Virtual Machine of Kuzmin — двомодовий емулятор і TUI-дебагер Машини Кузьміна на Go (`v0.1.0`). |
| **`CME-RAW-1`** | 16-байтний (`W0..W3`) двійковий формат дескриптора концепту в 64-слотовій BRAM (`1024 B`). |
| **`TUI`** | Text-based User Interface — 4-панельний текстовий інтерфейс налагодження каскадів подій. |
| **`STDIO`** | Потоковий інтерфейс вводу/виводу через стандартні потоки UNIX (`stdin`, `stdout`, `stderr`). |
