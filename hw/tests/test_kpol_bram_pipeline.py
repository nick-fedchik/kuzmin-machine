import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HW = ROOT / "hw"
sys.path.insert(0, str(ROOT / "sw" / "kpol-ref"))

from kpol_reference import (  # noqa: E402
    EventInput,
    Interpreter,
    parse_module,
)


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
@pytest.mark.parametrize("interface", ["direct", "axi"])
def test_kpol_images_change_behavior_in_same_simulated_hardware(tmp_path, interface):
    images = []
    for name, expected in (("increase", 11), ("decrease", 9)):
        source_path = HW / "tests" / f"kpol_bram_pipeline_{name}.kpol"
        source = source_path.read_text(encoding="utf-8")
        module = parse_module(source)
        reference = Interpreter(module).run([
            EventInput("Pulse", {"param": 5}),
            EventInput("Pulse", {"param": 25}),
        ])
        assert reference.state["Counter"] == expected
        assert not reference.diagnostics
        image_path = tmp_path / f"{name}.bin"
        subprocess.run(
            [sys.executable, str(HW / "scripts/compile_kpol_bram_image.py"),
             str(source_path), str(image_path)],
            check=True, capture_output=True, text=True,
        )
        image = image_path.read_bytes()
        duplicate = subprocess.run(
            [sys.executable, str(HW / "scripts/compile_kpol_bram_image.py"),
             str(source_path), str(image_path)],
            capture_output=True, text=True,
        )
        assert duplicate.returncode != 0
        assert image_path.read_bytes() == image
        assert len(image) == 1024
        words = struct.unpack("<256I", image)
        path = tmp_path / f"{name}.hex"
        path.write_text("".join(f"{word:08x}\n" for word in words))
        images.append(path)

    assert images[0].read_bytes() != images[1].read_bytes()
    simulation = tmp_path / "pipeline.vvp"
    top = f"kpol_bram_pipeline_{interface}_tb" if interface == "axi" else "kpol_bram_pipeline_tb"
    bus = [str(HW / "rtl/bus/kpol_bram_pipeline_axi.sv")] if interface == "axi" else []
    subprocess.run(
        [
            "iverilog", "-g2012", "-s", top, "-o", str(simulation),
            str(HW / "rtl/core/kpol_txn_gate_v2.sv"),
            str(HW / "rtl/core/km_concept_micro_engine.sv"),
            str(HW / "rtl/core/km_concept_bram.sv"),
            str(HW / "rtl/core/km_autonomous_sequencer.sv"),
            *bus, str(HW / "tests" / f"{top}.sv"),
        ],
        check=True, capture_output=True, text=True,
    )

    def run(first, second):
        return subprocess.run(
            ["vvp", "-n", str(simulation), f"+image_a={first}", f"+image_b={second}"],
            capture_output=True, text=True, timeout=30,
        )

    result = run(*images)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: both compiled images" in result.stdout

    swapped = run(*reversed(images))
    assert swapped.returncode != 0
    assert "image A: expected state 11" in swapped.stdout + swapped.stderr
