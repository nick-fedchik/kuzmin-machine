#!/usr/bin/env python3
"""Відтворюване перенесення PoC з drafts/KuzminMachine у kuzmin-machine.

Використання:
    git -C <drafts> archive <commit> KuzminMachine | tar -x -C /tmp/src
    python3 process/migration/migrate_from_drafts.py /tmp/src/KuzminMachine <commit>

Скрипт копіює лише файли з MAP (див. process/MIGRATION-REGISTER.md),
нормалізує версії документів до SemVer 2 (X.Y -> X.Y.0), додає рядок
походження й переписує відносні посилання Markdown на нові шляхи.
Посилання на неперенесені файли ведуть на drafts@<commit>.
Ручні правки після скрипта (шляхи в коді, F11) — окремими комітами.
"""
import os
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRAFTS_URL = "https://github.com/nick-fedchik/drafts/blob/{commit}/KuzminMachine/{path}"

HW = "02-engineering-hardware"
SW = "03-engineering-software"
QA = "04-verification-and-qa"
REP = f"{QA}/Reports"
REV = f"{QA}/Review_Reports"
BEN = f"{QA}/benchmarks"

MAP = {
    # process
    "Kuzmin-Machine-Document-Review-and-Audit-Rules-UA.md": "process/review-rules.md",
    "Kuzmin-Machine-Safety-and-Security-Standards-Position-UA.md": "process/standards-position.md",
    "Kuzmin-Machine-ASPICE4-Improvement-Steps-UA.md": "process/aspice-steps.md",
    # requirements / architecture
    "Kuzmin-Machine-Requirements-UA.md": "requirements/requirements.md",
    "01-concepts-and-theory/Kuzmin-Machine-Refactoring-and-Evolution-Plan-UA.md": "architecture/refactoring-plan.md",
    f"{SW}/Kuzmin-Machine-Compiler-and-Assembler-Architecture-UA.md": "architecture/software/compiler.md",
    # specs
    f"{SW}/Kuzmin-Machine-KPOL-Language-Draft-UA.md": "specs/kpol/kpol-0.1.0.md",
    **{f"{SW}/Kuzmin-Machine-KPOL-Language-v0.{n}-Specification-UA.md": f"specs/kpol/kpol-0.{n}.0.md" for n in range(2, 10)},
    f"{REV}/KPOL-v0.2-v0.9_Audit_Review_Report_UA.md": "specs/kpol/reviews/kpol-0.2-0.9-audit-review.md",
    # docs
    "01-concepts-and-theory/Kuzmin-Machine-ASN-Specification-UA.md": "docs/theory/asn.md",
    "01-concepts-and-theory/Kuzmin-Machine-Formal-Analysis-UA.md": "docs/theory/formal-analysis.md",
    f"{HW}/Kuzmin-Machine-Open-Source-XC7-Toolchain-Architecture-UA.md": "docs/toolchain/xc7.md",
    "07-scientific-opposition/Пример для АН.pptx": "docs/sources/author/kuzmin-2024-example-for-AN.pptx",
    "07-scientific-opposition/Пример для АН.pdf": "docs/sources/author/kuzmin-2024-example-for-AN.pdf",
    # TRL 2 evidence (MIGRATION-REGISTER §3.10)
    "07-scientific-opposition/KUZMIN_MACHINE_APPLICATION_PROSPECTS_MEMO_UA_v1.2.md": "docs/trl-evidence/application-prospects-memo.md",
    "07-scientific-opposition/SCIENTIFIC_OPPOSITION_REPORT_UA.md": "docs/trl-evidence/scientific-opposition-report.md",
    # hw: rtl
    **{f"{HW}/rtl/{f}": f"hw/rtl/core/{f}" for f in (
        "kpol_txn_gate.sv", "kpol_txn_gate_v2.sv", "km_predicate_evaluator.sv",
        "km_concept_bram.sv", "km_concept_bram_core.sv",
        "km_concept_micro_engine.sv", "km_autonomous_sequencer.sv")},
    f"{HW}/rtl/kpol_txn_gate_axi_lite.sv": "hw/rtl/bus/kpol_txn_gate_axi_lite.sv",
    f"{HW}/rtl/km_io_trigger_engine.sv": "hw/rtl/io/km_io_trigger_engine.sv",
    **{f"{HW}/rtl/{f}": f"hw/rtl/poc-demo/{f}" for f in (
        "km_euclid_core.sv", "km_rcfc_engine.sv",
        "km_cascade_arbiter_engine.sv", "km_stream_pipeline_engine.sv")},
    # hw: testbenches
    **{f"{HW}/tb/{f}": f"hw/tb/{f}" for f in (
        "kpol_txn_gate_tb.sv", "kpol_txn_gate_v2_tb.sv", "kpol_txn_gate_axi_lite_tb.sv",
        "km_concept_bram_tb.sv", "km_concept_micro_engine_tb.sv", "km_autonomous_sequencer_tb.sv",
        "km_io_trigger_engine_tb.sv", "km_euclid_core_tb.sv", "km_rcfc_engine_tb.sv",
        "km_cascade_arbiter_engine_tb.sv", "km_stream_pipeline_engine_tb.sv")},
    # hw: board, build
    f"{HW}/rtl/kpol_txn_gate_pynq_z1_top.v": "hw/boards/pynq-z1/kpol_txn_gate_pynq_z1_top.v",
    f"{HW}/pynq_z1.xdc": "hw/boards/pynq-z1/pynq_z1.xdc",
    f"{HW}/build_pynq_z1_openxc7.sh": "hw/boards/pynq-z1/build_openxc7.sh",
    f"{HW}/pynq_z1_hw_predicate_eval_test.py": "hw/boards/pynq-z1/hil/hil_predicate_eval.py",
    f"{HW}/pynq_z1_bram_concepts_test.py": "hw/boards/pynq-z1/hil/hil_bram_concepts.py",
    f"{HW}/pynq_z1_manual_mmio_test.py": "hw/boards/pynq-z1/hil/hil_manual_mmio.py",
    f"{HW}/pynq_z1_io_trigger_test.py": "hw/boards/pynq-z1/hil/hil_io_trigger.py",
    f"{HW}/Hardware_Procurement.md": "hw/boards/bench-procurement.md",
    f"{HW}/run_open_flow.sh": "hw/scripts/run_open_flow.sh",
    f"{HW}/Kuzmin-Machine-Open-Source-Verification-and-Synthesis-Runbook-UA.md": "hw/RUNBOOK.md",
    # sw
    f"{SW}/kpol_reference.py": "sw/kpol-ref/kpol_reference.py",
    f"{SW}/test_kpol_reference.py": "sw/kpol-ref/tests/test_kpol_reference.py",
    f"{HW}/deploy/kpol_direct_mmio_driver.py": "sw/runtime/pynq/kpol_direct_mmio_driver.py",
    f"{QA}/test_kpol_direct_mmio.py": "sw/runtime/pynq/tests/test_kpol_direct_mmio.py",
    f"{SW}/km_mcu_fpga_bridge.c": "sw/runtime/mcu/km_mcu_fpga_bridge.c",
    f"{QA}/test_km_mcu_fpga_bridge.py": "sw/runtime/mcu/tests/test_km_mcu_fpga_bridge.py",
    f"{QA}/km_static_analyzer.py": "sw/tools/static-analyzer/km_static_analyzer.py",
    f"{QA}/test_km_static_analyzer.py": "sw/tools/static-analyzer/tests/test_km_static_analyzer.py",
    f"{QA}/Kuzmin-Machine-Static-Analysis-and-Termination-Checker-UA.md": "sw/tools/static-analyzer/README.md",
    # experiments
    f"{QA}/Kuzmin-Machine-Experiment-Plan-Available-Hardware-UA.md": "experiments/PLAN.md",
    f"{REP}/AV-03_SW_Gate_Decision_Report_UA.md": "experiments/AV-03/report.md",
    f"{REV}/AV-03_SW_Gate_Decision_Review_Report_UA.md": "experiments/AV-03/review.md",
    f"{REP}/AV-04_Formal_Verification_Report_UA.md": "experiments/AV-04/report.md",
    f"{REV}/AV-04_Formal_Verification_Review_Report_UA.md": "experiments/AV-04/review.md",
    f"{REP}/AV-07_Mutation_Testing_Report_UA.md": "experiments/AV-07/report.md",
    f"{REV}/AV-07_Mutation_Testing_Review_Report_UA.md": "experiments/AV-07/review.md",
    f"{REP}/AV-08_Scaling_Report_UA.md": "experiments/AV-08/report.md",
    f"{REV}/AV-08_Scaling_Review_Report_UA.md": "experiments/AV-08/review.md",
    f"{REP}/KPOL_Verification_Program_Report_UA.md": "experiments/KPOL-FIX/report.md",
    **{f"{BEN}/av03_sw_gate/{f}": f"experiments/AV-03/scripts/{f}" for f in (
        "benchmark_av03.c", "kpol_gate.c", "kpol_gate.h", "run_av03.py", "test_av03_differential.py")},
    f"{BEN}/av04_formal/av04_gate_props.sv": "experiments/AV-04/scripts/av04_gate_props.sv",
    f"{BEN}/av04_formal/run_av04_formal.py": "experiments/AV-04/scripts/run_av04_formal.py",
    f"{BEN}/av07_mutation/run_av07_mutation.py": "experiments/AV-07/scripts/run_av07_mutation.py",
    f"{BEN}/av08_scaling/run_av08_scaling.py": "experiments/AV-08/scripts/run_av08_scaling.py",
    f"{BEN}/av08_scaling/analyze_av08.py": "experiments/AV-08/scripts/analyze_av08.py",
}

# Каталоги сирих даних переносяться цілком і без змін.
RAW_DIRS = {
    f"{REP}/raw/av04_formal": "experiments/AV-04/raw/av04_formal",
    f"{REP}/raw/av04_formal_cvc5": "experiments/AV-04/raw/av04_formal_cvc5",
    f"{REP}/raw/av08_scaling": "experiments/AV-08/raw/av08_scaling",
}
RAW_FILES = {
    **{f"{REP}/raw/{f}": f"experiments/AV-03/raw/{f}" for f in (
        "av03_host_raw_samples.csv", "av03_host_summary.json",
        "av03_jetson_orin_raw_samples.csv", "av03_jetson_orin_summary.json",
        "av03_pynq2_cortex_a9_raw_samples.csv", "av03_pynq2_cortex_a9_summary.json")},
    **{f"{REP}/raw/{f}": f"experiments/AV-04/raw/{f}" for f in (
        "av04_console_cvc5.txt", "av04_console_z3.txt", "av04_sva_checker_probe.txt")},
    f"{REP}/raw/av07_mutation_results.json": "experiments/AV-07/raw/av07_mutation_results.json",
    **{f"{REP}/raw/{f}": f"experiments/AV-08/raw/{f}" for f in (
        "av08_console.txt", "av08_console_reparse.txt")},
}

VERSION_RE = re.compile(r"^(\s*(?:[*-]\s*)?\*\*Версія:\*\*\s*)v?(\d+)\.(\d+)(?!\.\d)", re.M)
SEMVER_RE = re.compile(r"\*\*Версія:\*\*\s*\d+\.\d+\.\d+")
LINK_RE = re.compile(r"(\]\()([^)\s]+)(\))")


def full_map(src: Path):
    m = dict(MAP)
    m.update(RAW_FILES)
    for s, d in RAW_DIRS.items():
        for p in (src / s).rglob("*"):
            if p.is_file():
                rel = p.relative_to(src / s).as_posix()
                m[f"{s}/{rel}"] = f"{d}/{rel}"
    return m


def rewrite_links(text: str, old: str, new: str, mapping: dict, commit: str) -> str:
    old_dir = Path(old).parent
    new_dir = Path(new).parent.as_posix() or "."

    def repl(mo):
        target = mo.group(2)
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
            anchor = "#" + anchor
        if not target or re.match(r"^(https?:|mailto:)", target):
            return mo.group(0)
        if target.startswith("file://"):
            path = target[len("file://"):]
            i = path.find("/KuzminMachine/")
            if i < 0:
                return mo.group(0)
            resolved = path[i + len("/KuzminMachine/"):]
        elif target.startswith("/"):
            return mo.group(0)
        else:
            resolved = os.path.normpath((old_dir / target).as_posix())
        if resolved in mapping:
            rel = os.path.relpath(mapping[resolved], new_dir)
            return f"{mo.group(1)}{rel}{anchor}{mo.group(3)}"
        if resolved.startswith("../") and not resolved.startswith("../../"):
            # файл поза KuzminMachine, але в репо drafts
            url = DRAFTS_URL.format(commit=commit, path="").replace("/KuzminMachine/", "/")
            return f"{mo.group(1)}{url}{resolved[3:]}{anchor}{mo.group(3)}"
        if resolved.startswith(".."):
            return mo.group(0)
        return f"{mo.group(1)}{DRAFTS_URL.format(commit=commit, path=resolved)}{anchor}{mo.group(3)}"

    return LINK_RE.sub(repl, text)


def add_header(text: str, old: str, new: str, commit: str) -> str:
    text = VERSION_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}.{m.group(3)}.0", text, count=1)
    lines = text.split("\n")
    h1 = next((i for i, l in enumerate(lines[:15]) if l.startswith("# ")), -1)
    meta = []
    if not SEMVER_RE.search("\n".join(lines[:40])):
        kpol = re.match(r"specs/kpol/kpol-(\d+\.\d+\.\d+)\.md$", new)
        meta.append(f"* **Версія:** {kpol.group(1) if kpol else '0.1.0'}")
    meta.append(f"* **Перенесено з:** `drafts/KuzminMachine/{old}` @ `{commit}` (2026-11-09)")
    # Дописати в наявний блок метаданих одразу після H1, якщо він є.
    i = h1 + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if h1 >= 0 and i < len(lines) and re.match(r"^\s*[*-] \*\*", lines[i]):
        while i < len(lines) and re.match(r"^\s*[*-] |^\s{2,}\S", lines[i]):
            i += 1
        lines[i:i] = meta
    elif h1 >= 0:
        j = h1 + 1
        lines[j:j] = [""] + meta + ([] if j < len(lines) and not lines[j].strip() else [""])
    else:
        lines[0:0] = meta + [""]
    return "\n".join(lines)


def main():
    src = Path(sys.argv[1])
    commit = sys.argv[2]
    only = set(sys.argv[3:])  # optional: migrate only these destination paths
    mapping = full_map(src)
    for old, new in sorted(mapping.items()):
        if only and new not in only:
            continue
        s, d = src / old, REPO / new
        if not s.is_file():
            sys.exit(f"missing source: {old}")
        d.parent.mkdir(parents=True, exist_ok=True)
        if d.suffix == ".md" and "/raw/" not in new:
            text = s.read_text(encoding="utf-8")
            text = add_header(text, old, new, commit)
            text = rewrite_links(text, old, new, mapping, commit)
            d.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(s, d)
    print(f"migrated {len(only) if only else len(mapping)} files")


if __name__ == "__main__":
    main()
