from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root / "sw" / "kpol-ref"))

from kpol_reference import KpolError, parse_triad_files


problem_src = """\
namespace Avionics::FlightControl;
Problem PitchController {}
"""

solution_src = """\
namespace Avionics::FlightControl;
import Avionics::FlightControl::MissingController;
Solution PitchController {
    event Tick();
    state PitchAngle: Int32 = 0;
}
"""

proof_src = """\
namespace Avionics::FlightControl;
import Avionics::FlightControl::PitchController;
Proof PitchController {
    assert Holds on Tick {
        when true expect PitchAngle == 0;
    }
}
"""

try:
    parse_triad_files(problem_src, solution_src, proof_src)
except KpolError as error:
    print(f"PASS: unresolved import rejected: {error}")
else:
    raise AssertionError("unresolved import was silently accepted")
