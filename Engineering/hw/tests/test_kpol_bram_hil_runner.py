import importlib.util
import struct
from pathlib import Path

import pytest

HIL = Path(__file__).resolve().parents[1] / "boards/pynq-z1/hil/hil_kpol_bram_pipeline.py"
spec = importlib.util.spec_from_file_location("hil_kpol_bram_pipeline", HIL)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FakeMMIO:
    def __init__(self, committed_state):
        self.memory = [0] * 256
        self.address = 0
        self.events = self.commits = self.rejects = 0
        self.committed_state = committed_state

    def write(self, offset, value):
        if offset == runner.REG_ADDR:
            self.address = value
        elif offset == runner.REG_DATA:
            self.memory[self.address] = value
        elif offset == runner.REG_TRIGGER:
            self.events += 1
            if self.events == 1:
                self.memory[0] = self.committed_state
                self.commits += 1
            else:
                self.rejects += 1

    def read(self, offset):
        return {
            runner.REG_DATA: self.memory[self.address],
            runner.REG_EVENTS: self.events,
            runner.REG_COMMITS: self.commits,
            runner.REG_REJECTS: self.rejects,
            runner.REG_BUSY: 0,
        }[offset]


def test_hil_runner_checks_readback_and_event_results_with_mock_mmio():
    image = struct.pack("<256I", *range(256))
    mmio = FakeMMIO(11)
    result = runner.run_image(mmio, image, 11, [2, 1, 1])
    assert result["states"] == [11, 11]
    assert mmio.memory[1:] == list(range(1, 256))

    with pytest.raises(AssertionError, match="expected 11, got 12"):
        runner.run_image(FakeMMIO(12), image, 11, [2, 1, 1])
