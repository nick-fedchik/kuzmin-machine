"""Frozen tasks and acceptance checks for Q3 LLM pilot (#216).

Frozen BEFORE launching isolated LLM sessions.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[5]
KPOL_REF_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-ref"
CLI_SCRIPT = REPO_ROOT / "Engineering" / "hw" / "scripts" / "compile_kpol_bram_image.py"

if str(KPOL_REF_DIR) not in sys.path:
    sys.path.insert(0, str(KPOL_REF_DIR))

from kpol_reference import (  # noqa: E402
    CME_ACT_DEC,
    CME_ACT_INC,
    CME_GUARD_SUBSCRIBER_EN,
    CME_PRED_RANGE,
    EventInput,
    Interpreter,
    Parser,
    compile_concept_microcode_bram_image,
    disassemble_concept_microcode,
    verify_module,
)

TASKS_PROMPT = """Виконай 3 окремі задачі з мови KPOL, спираючись ВИКЛЮЧНО на надані вище специфікації.
Для кожної задачі надай повний, готовий до компіляції код модуля KPOL у окремому блоці коду ```kpol ... ``` (за потреби можеш коротко зазначити виявлені неоднозначності чи проблеми специфікацій окремо після коду).

### Задача 1 (профіль `KPOL-CME-1`)
Напиши програму на профілі `KPOL-CME-1` (один концепт / стан типу `Int32` з інваріантом `S >= 0`), яка:
- має початковий стан `5`;
- має одну подію з одним параметром типу `Int32`;
- при настанні події, якщо параметр строго менший за `10` (`P < 10`), збільшує стан на `1` (`S + 1`);
- містить блок `Proof` зі сценарієм, що перевіряє:
  1) крок із параметром `4` (очікується стан `6`);
  2) крок із параметром `10` (очікується стан `6`).

### Задача 2 (профіль `KPOL-CME-2`)
Напиши програму на профілі `KPOL-CME-2` (один концепт / стан типу `Int32` з інваріантом `S >= 0`), яка:
- має початковий стан `1`;
- має одну подію з одним параметром типу `Int32`;
- при настанні події, якщо параметр лежить у діапазоні від `0` до `100` включно (`0 <= P and P <= 100`), зменшує стан на `1` (`S - 1`);
- містить блок `Proof` зі сценарієм, що перевіряє:
  1) крок із параметром `50` (очікується стан `0`);
  2) крок із параметром `50` на вже нульовому стані (відмова інваріанта `S >= 0`, очікується стан `0`);
  3) крок із параметром `101` (охоронець хибний, очікується стан `0`).

### Задача 3 (профіль `KPOL-CME-2`)
Напиши програму на профілі `KPOL-CME-2` з двома концептами (два стани типу `Int32` з інваріантами `>= 0`) та ациклічним каскадом `on change(...)` без колізії операндів:
- концепт 1: початковий стан `0`, реагує на зовнішню подію з одним параметром `Int32`, якщо параметр `>= 10`, і збільшує свій стан на `1`;
- концепт 2: початковий стан `0`, підписаний через `on change(<стан_концепту_1>)`, спрацьовує коли `<стан_концепту_1> >= 2`, і збільшує свій стан на `1` (без колізії операндів);
- містить блок `Proof` зі сценарієм, що перевіряє:
  1) крок зовнішньої події з параметром `5` (очікується стан 1 == `0`, стан 2 == `0`);
  2) крок зовнішньої події з параметром `10` (очікується стан 1 == `1`, стан 2 == `0`);
  3) крок зовнішньої події з параметром `10` (очікується стан 1 == `2`, стан 2 == `1`).
"""


def _run_cli(source: str, profile: str) -> bytes:
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        tmp_path = Path(tmp)
        src_path = tmp_path / "prog.kpol"
        out_path = tmp_path / "out.bin"
        src_path.write_text(source, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(CLI_SCRIPT), "--profile", profile, str(src_path), str(out_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(f"CLI failed ({proc.returncode}): {proc.stderr.strip()}")
        return out_path.read_bytes()


def check_task1(source: str) -> dict:
    module = Parser(source).parse()
    image = compile_concept_microcode_bram_image(module, profile="KPOL-CME-1")
    assert len(image) == 1024
    cli_image = _run_cli(source, "KPOL-CME-1")
    assert cli_image == image

    assert module.proof_present and module.proofs, "Task 1 requires non-empty Proof"
    report = verify_module(module)
    assert report.passed and report.total_checks > 0

    descs = disassemble_concept_microcode(image)
    assert descs[0].action_opcode == CME_ACT_INC
    assert descs[0].current_state == 5
    assert descs[0].operand_val == 10

    state_name = module.states[0].name
    event = module.events[0]
    param_name = event.parameters[0][0]
    interp = Interpreter(module)
    assert interp.state[state_name] == 5

    r1 = interp.run([EventInput(event.name, {param_name: 4})])
    assert not r1.rejected and interp.state[state_name] == 6
    interp.run([EventInput(event.name, {param_name: 10})])
    assert interp.state[state_name] == 6
    r3 = interp.run([EventInput(event.name, {param_name: 9})])
    assert not r3.rejected and interp.state[state_name] == 7
    return {"profile": "KPOL-CME-1", "state": state_name, "event": event.name}


def check_task2(source: str) -> dict:
    module = Parser(source).parse()
    image = compile_concept_microcode_bram_image(module, profile="KPOL-CME-2")
    assert len(image) == 1024
    cli_image = _run_cli(source, "KPOL-CME-2")
    assert cli_image == image

    report = verify_module(module)
    assert report.passed and report.total_checks > 0

    descs = disassemble_concept_microcode(image)
    assert descs[0].action_opcode == CME_ACT_DEC
    assert descs[0].pred_opcode == CME_PRED_RANGE
    assert descs[0].current_state == 1
    assert descs[0].operand_val == ((100 << 16) | 0)

    state_name = module.states[0].name
    event = module.events[0]
    param_name = event.parameters[0][0]
    interp = Interpreter(module)
    assert interp.state[state_name] == 1

    # 1) valid decrement 1 -> 0
    r1 = interp.run([EventInput(event.name, {param_name: 50})])
    assert not r1.rejected and interp.state[state_name] == 0
    # 2) invariant rejection at 0 -> stays 0
    r2 = interp.run([EventInput(event.name, {param_name: 50})])
    assert any("InvariantViolation" in d for d in r2.diagnostics) and interp.state[state_name] == 0
    # 3) guard false at 101 -> stays 0
    interp.run([EventInput(event.name, {param_name: 101})])
    assert interp.state[state_name] == 0
    # 4) guard false at -1 -> stays 0
    interp.run([EventInput(event.name, {param_name: -1})])
    assert interp.state[state_name] == 0
    return {"profile": "KPOL-CME-2", "state": state_name, "event": event.name}


def check_task3(source: str) -> dict:
    module = Parser(source).parse()
    image = compile_concept_microcode_bram_image(module, profile="KPOL-CME-2")
    assert len(image) == 1024
    cli_image = _run_cli(source, "KPOL-CME-2")
    assert cli_image == image

    report = verify_module(module)
    assert report.passed and report.total_checks > 0

    assert len(module.states) == 2
    assert len(module.events) == 1
    ext_rule = next(r for r in module.rules if r.event != "change")
    chg_rule = next(r for r in module.rules if r.event == "change")
    s1 = ext_rule.actions[0].name
    s2 = chg_rule.actions[0].name
    assert list(chg_rule.watch) == [s1]

    descs = disassemble_concept_microcode(image)
    cid1 = [s.name for s in module.states].index(s1)
    cid2 = [s.name for s in module.states].index(s2)
    assert descs[cid1].guard_flags & CME_GUARD_SUBSCRIBER_EN
    assert descs[cid1].subscriber_cid == cid2

    event = module.events[0]
    param_name = event.parameters[0][0]
    interp = Interpreter(module)
    assert interp.state[s1] == 0 and interp.state[s2] == 0

    interp.run([EventInput(event.name, {param_name: 5})])
    assert interp.state[s1] == 0 and interp.state[s2] == 0

    interp.run([EventInput(event.name, {param_name: 10})])
    assert interp.state[s1] == 1 and interp.state[s2] == 0

    interp.run([EventInput(event.name, {param_name: 10})])
    assert interp.state[s1] == 2 and interp.state[s2] == 1
    return {"profile": "KPOL-CME-2", "states": [s1, s2], "event": event.name}
