import math
import struct
from decimal import Decimal
from pathlib import Path
import os
import sys
import unittest
import subprocess
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from kpol_reference import (
    EventInput,
    Interpreter,
    KpolError,
    UNKNOWN,
    parse_module,
    tokenize,
    compile_bram_image,
    compile_c_header,
    compile_verilog_interconnect,
    compile_compliance_rtm,
    compile_signed_bram_image,
    verify_bram_signature,
    check_module_security_acl,
    CAP_READ,
    CAP_WRITE,
    CAP_PIN_OUT,
    KPOL_SEC_MAGIC,
    KPOL_SEC_VERSION,
    generate_mutants,
    run_falsification_suite,
    enforce_popperian_gate,
    FalsificationResult,
    compile_baremetal_runtime,
    compile_axi_lite_wrapper,
    parse_triad_files,
    link_modules,
    compile_concept_microcode_bram_image,
    disassemble_concept_microcode,
    ConceptMicroDescriptor,
    CME_PRED_NOP,
    CME_PRED_EQ,
    CME_PRED_GT,
    CME_ACT_ASSIGN,
    CME_ACT_INC,
    CME_ACT_ADD,
    CME_GUARD_ASSUMPTION_EN,
    CME_GUARD_INVARIANT_EN,
    CME_GUARD_HAZARD_EN,
    CME_GUARD_INVERT_ASSUMPTION,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "specs" / "kpol" / "kpol-0.1.0.md"


def examples_from_spec():
    examples = []
    current = None
    for line in SPEC_PATH.read_text(encoding="utf-8").splitlines():
        if current is None and line.strip() == "```kpol":
            current = []
        elif current is not None and line.strip() == "```":
            examples.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    if current is not None:
        raise AssertionError("unterminated KPOL example fence")
    return examples


class KpolReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = examples_from_spec()
        if len(cls.sources) != 3:
            raise AssertionError(f"expected 3 KPOL examples, found {len(cls.sources)}")
        cls.modules = [parse_module(source) for source in cls.sources]

    def test_all_documented_examples_parse_and_typecheck(self):
        self.assertEqual([module.name for module in self.modules],
                         ["ReactorMonitor", "EuclidGCD", "EnergyMeter"])

    def test_reactor_hazard_and_false_alarm_boundary(self):
        module = self.modules[0]
        result = Interpreter(module).run([
            EventInput("Sample", {"Temp": 121, "Pressure": 16}),
            EventInput("Sample", {"Temp": 120, "Pressure": 16}),
        ])
        self.assertEqual(result.hazards, ["CriticalCombination"])
        self.assertFalse(result.state["Trip"])
        self.assertFalse(result.state["SensorFault"])
        self.assertEqual(result.goal_failures, [])

    def test_rejected_unknown_sensor_data_latches_fault(self):
        result = Interpreter(self.modules[0]).run([
            EventInput("Sample", {"Temp": UNKNOWN, "Pressure": 20}),
        ])
        self.assertEqual(result.rejected, ["RejectedInput:Sample"])
        self.assertIn("UnknownHazard:CriticalCombination", result.diagnostics)
        self.assertTrue(result.state["SensorFault"])
        self.assertTrue(result.state["Trip"])
        self.assertEqual(result.goal_failures, ["NormalInputClearsFault"])

    def test_valid_sample_clears_a_rejected_input_fault(self):
        result = Interpreter(self.modules[0]).run([
            EventInput("Sample", {"Temp": UNKNOWN, "Pressure": 10}),
            EventInput("Sample", {"Temp": 80, "Pressure": 10}),
        ])
        self.assertEqual(result.rejected, ["RejectedInput:Sample"])
        self.assertFalse(result.state["SensorFault"])
        self.assertFalse(result.state["Trip"])
        self.assertEqual(result.goal_failures, [])

    def test_out_of_range_input_is_rejected_but_boundary_is_accepted(self):
        result = Interpreter(self.modules[0]).run([
            EventInput("Sample", {"Temp": -50, "Pressure": 0}),
            EventInput("Sample", {"Temp": 301, "Pressure": 20}),
        ])
        self.assertEqual(result.rejected, ["RejectedInput:Sample"])
        self.assertEqual(result.hazards, ["CriticalCombination"])
        self.assertTrue(result.state["SensorFault"])
        self.assertTrue(result.state["Trip"])

    def test_euclid_properties_for_bounded_positive_inputs(self):
        module = self.modules[1]
        for a in range(1, 13):
            for b in range(1, 13):
                with self.subTest(a=a, b=b):
                    result = Interpreter(module, {
                        "A": a, "B": b, "OriginalA": a, "OriginalB": b,
                    }).run(max_events=100)
                    self.assertTrue(result.state["Done"])
                    self.assertEqual(result.state["Result"], math.gcd(a, b))
                    self.assertEqual(result.state["A"], result.state["B"])
                    self.assertEqual(result.goal_failures, [])
                    self.assertFalse(any(d.startswith("InvariantViolation") for d in result.diagnostics))

    def test_meter_integrates_each_sample_with_units(self):
        samples = [
            (120, 2, Decimal("0.1")),
            (230, 1, Decimal("0.05")),
            (12, 3, Decimal("2.5")),
        ]
        events = [
            EventInput("Sample", {"V": voltage, "I": current, "dt": dt})
            for voltage, current, dt in samples
        ]
        result = Interpreter(self.modules[2]).run(events)
        expected = sum(
            (Decimal(voltage) * Decimal(current) * dt for voltage, current, dt in samples),
            Decimal(0),
        )
        self.assertEqual(result.state["EnergyJ"], expected)
        self.assertEqual(result.goal_failures, [])

    def test_meter_rejects_unknown_without_losing_accumulated_energy(self):
        result = Interpreter(self.modules[2]).run([
            EventInput("Sample", {"V": 100, "I": 2, "dt": Decimal("0.5")}),
            EventInput("Sample", {"V": UNKNOWN, "I": 2, "dt": Decimal("0.5")}),
        ])
        self.assertEqual(result.state["EnergyJ"], Decimal("100.0"))
        self.assertTrue(result.state["SensorFault"])
        self.assertEqual(result.rejected, ["RejectedInput:Sample"])

    def test_nested_blocks_and_both_comment_forms(self):
        source = """
        Problem Nested {
            /* braces in comments do not alter nesting: { } */
            Invariants { IsBoolean: Flag == true or Flag == false; }
            Goals { BecomesTrue: Flag == true; }
        }
        Solution Nested {
            state Flag: Bool = false; # line comment with }
            event Tick(); // line comment
            rule set_flag on Tick { set Flag := true; }
        }
        """
        result = Interpreter(parse_module(source)).run([EventInput("Tick")])
        self.assertTrue(result.state["Flag"])
        self.assertEqual(result.goal_failures, [])

    def test_ascii_and_unicode_aliases_normalize_identically(self):
        def normalized(source):
            return [(token.kind, token.value) for token in tokenize(source) if token.kind != "EOF"]

        self.assertEqual(normalized("x <- y;"), normalized("x ← y;"))
        self.assertEqual(normalized("x -> y;"), normalized("x → y;"))
        self.assertEqual(normalized("• (*)"), normalized("(*) •"))
        self.assertEqual(normalized("/* { } */ x <- y;"), normalized("# { }\nx ← y;"))

    def test_missing_or_incorrect_hazard_implementation_is_rejected(self):
        source = self.sources[0]
        missing_cover = source.replace(" covers CriticalCombination", "")
        with self.assertRaisesRegex(KpolError, "without a covers rule"):
            parse_module(missing_cover)
        wrong_guard = source.replace(
            "when Temp > 120 and Pressure > 15 covers CriticalCombination",
            "when Temp > 121 and Pressure > 15 covers CriticalCombination",
        )
        with self.assertRaisesRegex(KpolError, "does not exactly implement"):
            parse_module(wrong_guard)
        wrong_target = source.replace(
            "CriticalCombination on Sample to Trip:",
            "CriticalCombination on Sample to SensorFault:",
        )
        with self.assertRaisesRegex(KpolError, "must set target"):
            parse_module(wrong_target)
        wrong_effect = source.replace(
            "set Trip := true;",
            "set Trip := false;",
            1,
        )
        with self.assertRaisesRegex(KpolError, "must set target 'Trip' to true"):
            parse_module(wrong_effect)

    def test_unit_mismatch_and_unresolved_names_are_rejected(self):
        wrong_units = self.sources[2].replace("V * I * dt", "V + I + dt")
        with self.assertRaisesRegex(KpolError, "incompatible numeric types"):
            parse_module(wrong_units)
        unresolved = self.sources[2].replace("EnergyJ >= 0;", "MissingState >= 0;")
        with self.assertRaisesRegex(KpolError, "unresolved name"):
            parse_module(unresolved)
        fractional_integer = """
        Problem BadInteger {}
        Solution BadInteger { state Count: U64 = 1.5; }
        """
        with self.assertRaisesRegex(KpolError, "initial value"):
            parse_module(fractional_integer)
        absolute_temperature_arithmetic = self.sources[0].replace(
            "Temp > 120 and Pressure > 15",
            "Temp + 1 > 120 and Pressure > 15",
            1,
        )
        with self.assertRaisesRegex(KpolError, "absolute degC"):
            parse_module(absolute_temperature_arithmetic)

    def test_invariant_failure_rolls_back_whole_transaction(self):
        source = """
        Problem Rollback {
            Invariants { Bounded: Counter <= 1; }
        }
        Solution Rollback {
            state Counter: U64 = 0;
            event Tick();
            rule increment on Tick { set Counter := Counter + 2; }
        }
        """
        result = Interpreter(parse_module(source)).run([EventInput("Tick")])
        self.assertEqual(result.state["Counter"], 0)
        self.assertEqual(result.diagnostics, ["InvariantViolation:Bounded"])

    def test_change_rule_runs_only_for_its_watched_state(self):
        source = """
        Problem Watchers {}
        Solution Watchers {
            state A: U64 = 0;
            state C: U64 = 0;
            state Marker: Bool = false;
            event Trigger();
            rule update_a on Trigger { set A := 1; }
            rule mark_on_c on change(C) when A > 0 { set Marker := true; }
        }
        """
        result = Interpreter(parse_module(source)).run([EventInput("Trigger")])
        self.assertFalse(result.state["Marker"])

    def test_unknown_guard_aborts_the_transaction(self):
        source = """
        Problem UnknownGuard {}
        Solution UnknownGuard {
            event Sample(Value: Float<V>);
            state Alarm: Bool = false;
            rule alarm_on_positive on Sample when Value > 0 {
                set Alarm := true;
            }
        }
        """
        result = Interpreter(parse_module(source)).run([
            EventInput("Sample", {"Value": UNKNOWN}),
        ])
        self.assertFalse(result.state["Alarm"])
        self.assertEqual(result.diagnostics, ["UnknownGuard:alarm_on_positive"])

    def test_v02_alert_observation_and_fail_closed_hazard(self):
        """KPOL v0.2: Перевірка розділення Alert (спостереження) та Hazard Fail-Closed (замок)."""
        source = """
        Problem AlertAndHazard {
            Alerts {
                MildWarm on Sample: Temp > 50;
            }
            Hazards {
                Overheat on Sample to Trip: Temp > 100;
            }
        }
        Solution AlertAndHazard {
            event Sample(Temp: Int32);
            state CurrentVal: Int32 = 0;
            state Trip: Bool = false;
            rule trip_cov on Sample when Temp > 100 covers Overheat {
                set Trip := true;
            }
            rule normal_sample on Sample when Temp <= 100 {
                set CurrentVal := Temp;
            }
        }
        """
        module = parse_module(source)

        # 1. Alert спостереження: Temp = 60 (> 50, але <= 100) -> Alert активний, коміт проходить
        interp = Interpreter(module, fail_closed_hazards=True)
        res1 = interp.run([EventInput("Sample", {"Temp": 60})])
        self.assertEqual(res1.alerts, ["MildWarm"])
        self.assertEqual(res1.hazards, [])
        self.assertEqual(res1.state["CurrentVal"], 60)
        self.assertFalse(res1.state["Trip"])

        # 2. Hazard Fail-Closed блокування: Temp = 110 (> 100) -> транзакція відхиляється!
        res2 = interp.run([EventInput("Sample", {"Temp": 110})])
        self.assertIn("Overheat", res2.hazards)
        self.assertIn("RejectedHazard:Overheat", res2.rejected)
        # CurrentVal не змінився з 60, коміт заблоковано!
        self.assertEqual(res2.state["CurrentVal"], 60)

    def test_v02_triad_problem_solution_proof_syntax_and_verification(self):
        """KPOL v0.2: Тріада Проблема-Вирішення-Доказ (Problem-Solution-Proof Docs-as-Code)."""
        source = """
        Problem HydraulicPump {
            Invariants {
                SafePressure: Pressure <= 250;
            }
            Hazards {
                Overpressure on PressureSample to EmergencyLock: P > 250;
            }
            Alerts {
                HighTemp on TempSample: T > 85;
            }
        }
        Solution HydraulicPump {
            event PressureSample(P: Int32);
            event TempSample(T: Int32);
            state Pressure: Int32 = 100;
            state Temperature: Int32 = 40;
            state PumpActive: Bool = true;
            state EmergencyLock: Bool = false;

            rule handle_pressure on PressureSample when P <= 250 {
                set Pressure := P;
            }
            rule handle_overpressure on PressureSample when P > 250 covers Overpressure {
                set EmergencyLock := true;
                set PumpActive := false;
            }
            rule handle_temp on TempSample when T <= 120 {
                set Temperature := T;
            }
        }
        Proof HydraulicPump {
            assert SafeEmergencyState on PressureSample {
                when P > 250 expect PumpActive == false;
            }
            scenario NominalOperation {
                step PressureSample(P = 150);
                expect Pressure == 150;
                expect PumpActive == true;
                expect EmergencyLock == false;
            }
            scenario OverpressureShutdown {
                step PressureSample(P = 260);
                expect PumpActive == false;
                expect EmergencyLock == true;
            }
        }
        """
        module = parse_module(source)
        self.assertEqual(len(module.proofs), 3)

        interp = Interpreter(module, fail_closed_hazards=False)
        report = interp.verify()
        self.assertTrue(report.passed)
        self.assertEqual(report.total_checks, 7)
        self.assertEqual(report.passed_checks, 7)
        self.assertEqual(report.failures, [])

    def test_v02_triad_detects_proof_assertion_failure(self):
        """KPOL v0.2: Тестування виявлення розбіжностей між доказом (Proof) та кодом (Solution)."""
        source = """
        Problem FailingValve {
            Invariants {
                AlwaysOpen: IsOpen == true;
            }
        }
        Solution FailingValve {
            event Toggle();
            state IsOpen: Bool = true;
            rule toggle_rule on Toggle when true {
                set IsOpen := false;
            }
        }
        Proof FailingValve {
            scenario ExpectClosedAfterToggle {
                step Toggle();
                expect IsOpen == false;
            }
        }
        """
        module = parse_module(source)
        interp = Interpreter(module)
        report = interp.verify()
        self.assertFalse(report.passed)
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.failures[0].scenario_or_assert, "ExpectClosedAfterToggle")

    def test_v02_triad_typecheck_errors_in_proof(self):
        """KPOL v0.2: Компілятор виявляє помилки типів у блоці Proof на етапі статичного аналізу."""
        bad_source = """
        Problem Dummy {
            Invariants {
                Ok: Val >= 0;
            }
        }
        Solution Dummy {
            event Step(Delta: Int32);
            state Val: Int32 = 0;
            rule do_step on Step when true {
                set Val := Val;
            }
        }
        Proof Dummy {
            scenario BadEvent {
                step UnknownEvent(Delta = 10);
                expect Val == 10;
            }
        }
        """
        with self.assertRaises(KpolError) as ctx:
            parse_module(bad_source)
        self.assertIn("references unknown event 'UnknownEvent'", str(ctx.exception))

    def test_v03_physical_time_units_and_pin_types(self):
        """KPOL v0.3: Перевірка підтримки одиниць фізичного часу (ms, us, ns) та типізації Pin."""
        source = """
        Problem WatchdogTimer {
            Invariants {
                ValidInterval: TimeoutMs > 0.0;
            }
            Hazards {
                HeartbeatLoss on Sample to Panic: Interval > 50.0;
            }
        }
        Solution WatchdogTimer {
            event Sample(Interval: Float<ms>);
            event Configure(PinRef: Pin<In, ActiveLow>);
            state TimeoutMs: Float<ms> = 50.0;
            state Panic: Bool = false;

            rule on_sample on Sample when Interval <= 50.0 {
                set TimeoutMs := Interval;
            }
            rule on_loss on Sample when Interval > 50.0 covers HeartbeatLoss {
                set Panic := true;
            }
        }
        Proof WatchdogTimer {
            assert SafeLoss on Sample {
                when Interval > 50.0 expect Panic == true;
            }
            scenario NominalHeartbeat {
                step Sample(Interval = 10.0);
                expect TimeoutMs == 10.0;
                expect Panic == false;
            }
            scenario HeartbeatTimeoutPanic {
                step Sample(Interval = 65.0);
                expect Panic == true;
            }
        }
        """
        module = parse_module(source)
        self.assertEqual(module.name, "WatchdogTimer")
        report = Interpreter(module, fail_closed_hazards=False).verify()
        self.assertTrue(report.passed)
        self.assertEqual(report.total_checks, 5)
        self.assertEqual(report.failures, [])

    def test_v05_compiler_bram_binary_generation(self):
        """KPOL v0.5: Перевірка генерації 1024-байтного бінарного образу BRAM (64 x 16)."""
        source = """
        Problem PumpController {
            Invariants {
                LimitP: Pressure <= 250;
            }
        }
        Solution PumpController {
            event Tick();
            state Pressure: Int32 = 120;
            state PumpActive: Bool = true;
            rule do_tick on Tick when true {
                set Pressure := Pressure;
            }
        }
        """
        module = parse_module(source)
        bram_bytes = compile_bram_image(module)
        self.assertEqual(len(bram_bytes), 1024)

        # Перевірка дескриптора CID 0 (Pressure: 120)
        # 4 uint32 words: val_lo, val_hi, meta, status
        val_lo, val_hi, meta, status = struct.unpack_from("<IIII", bram_bytes, 0)
        self.assertEqual(val_lo, 120)
        self.assertEqual(val_hi, 0)
        self.assertEqual(meta & 0x0F, 0)  # Type Int32 = 0
        self.assertTrue(status & (1 << 1))  # Positive = bit 1
        self.assertTrue(status & (1 << 3))  # Even = bit 3

        # Перевірка дескриптора CID 1 (PumpActive: true)
        p_val_lo, p_val_hi, p_meta, p_status = struct.unpack_from("<IIII", bram_bytes, 16)
        self.assertEqual(p_val_lo, 1)
        self.assertEqual(p_meta & 0x0F, 2)  # Type Bool = 2

        # Перевірка порожнього слота CID 63
        empty_slot = struct.unpack_from("<IIII", bram_bytes, 63 * 16)
        self.assertEqual(empty_slot, (0, 0, 0, 0))

    def test_v05_compiler_c_header_and_verilog_generation(self):
        """KPOL v0.5: Генерація C-заголовків для MCU та Verilog RTL для FPGA."""
        source = """
        Problem Reactor {
            Invariants {
                SafeT: Temp <= 100;
            }
            Hazards {
                Overheat on Sample to Trip: MeasuredT > 100;
            }
        }
        Solution Reactor {
            event Sample(MeasuredT: Int32);
            state Temp: Int32 = 40;
            state Trip: Bool = false;
            rule on_sample on Sample when MeasuredT <= 100 {
                set Temp := MeasuredT;
            }
            rule on_overheat on Sample when MeasuredT > 100 covers Overheat {
                set Trip := true;
            }
        }
        Proof Reactor {
            assert Cutoff on Sample {
                when MeasuredT > 100 expect Trip == true;
            }
        }
        """
        module = parse_module(source)

        # 1. C-Header
        c_code = compile_c_header(module)
        self.assertIn("#ifndef KM_KPOL_REACTOR_H", c_code)
        self.assertIn("CID_Temp = 0,", c_code)
        self.assertIn("CID_Trip = 1,", c_code)
        self.assertIn("REACTOR_BRAM_INIT", c_code)

        # 2. Verilog Interconnect
        v_code = compile_verilog_interconnect(module)
        self.assertIn("module km_reactor_interconnect", v_code)
        self.assertIn("committed_o", v_code)
        self.assertIn("state_Temp_q", v_code)

        # 3. Compliance RTM Matrix
        rtm_md = compile_compliance_rtm(module)
        self.assertIn("Requirements Traceability Matrix (RTM): Reactor", rtm_md)
        self.assertIn("`Overheat`", rtm_md)
        self.assertIn("`on_overheat`", rtm_md)

    def test_v06_secure_boot_signed_bram_image_success(self):
        source = """
        Problem SecureCore {}
        Solution SecureCore {
            state Counter: Int32 = 42;
        }
        Proof SecureCore {}
        """
        module = parse_module(source)
        secret_key = b"super_secret_auth_key_kpol_2026"
        signed_img = compile_signed_bram_image(module, secret_key, key_id=7)

        # 1. Image structure assertions
        self.assertEqual(len(signed_img), 1088)
        self.assertEqual(signed_img[:4], b"KPOL")

        # 2. Signature verification
        valid, msg = verify_bram_signature(signed_img, secret_key)
        self.assertTrue(valid, msg)
        self.assertEqual(msg, "OK: Valid signature")

    def test_v06_tamper_resistance_payload_modification(self):
        source = """
        Problem TamperTest {}
        Solution TamperTest {
            state Val: Int32 = 10;
        }
        Proof TamperTest {}
        """
        module = parse_module(source)
        secret_key = b"tamper_proof_secret_key_32bytes"
        signed_img = bytearray(compile_signed_bram_image(module, secret_key))

        # Corrupt 1 single bit in payload (byte 120)
        signed_img[120] ^= 0x01

        valid, msg = verify_bram_signature(bytes(signed_img), secret_key)
        self.assertFalse(valid)
        self.assertIn("tampering detected", msg)

    def test_v06_tamper_resistance_header_modification(self):
        source = """
        Problem HeaderTamper {}
        Solution HeaderTamper {
            state Val: Int32 = 10;
        }
        Proof HeaderTamper {}
        """
        module = parse_module(source)
        secret_key = b"tamper_proof_secret_key_32bytes"
        signed_img = bytearray(compile_signed_bram_image(module, secret_key))

        # Corrupt 1 byte in header prefix (flags or key_id)
        signed_img[6] ^= 0x02

        valid, msg = verify_bram_signature(bytes(signed_img), secret_key)
        self.assertFalse(valid)
        self.assertIn("tampering detected", msg)

    def test_v06_wrong_secret_key(self):
        source = """
        Problem WrongKeyTest {}
        Solution WrongKeyTest {
            state Val: Int32 = 10;
        }
        Proof WrongKeyTest {}
        """
        module = parse_module(source)
        real_key = b"real_secret_key_123456789012345"
        attacker_key = b"attacker_secret_key_fake_999999"
        signed_img = compile_signed_bram_image(module, real_key)

        valid, msg = verify_bram_signature(signed_img, attacker_key)
        self.assertFalse(valid)
        self.assertIn("tampering detected", msg)

    def test_v06_corrupted_image_length_and_magic(self):
        secret_key = b"test_key_for_magic_and_length"
        # Truncated image
        valid, msg = verify_bram_signature(b"short", secret_key)
        self.assertFalse(valid)
        self.assertIn("Invalid image length", msg)

        # Invalid magic
        fake_img = b"FAKE" + b"\x00" * 1084
        valid, msg = verify_bram_signature(fake_img, secret_key)
        self.assertFalse(valid)
        self.assertIn("Invalid magic header", msg)

    def test_v06_hardware_capabilities_acl(self):
        source = """
        Problem AclTest {}
        Solution AclTest {
            event Trigger();
            state ValveOut: Pin<Out> = 0;
            state Status: Int32 = 1;
            rule on_trig on Trigger {
                set ValveOut := 1;
                set Status := 2;
            }
        }
        Proof AclTest {}
        """
        module = parse_module(source)

        # Without CAP_PIN_OUT for ValveOut, audit detects violation
        violations = check_module_security_acl(module, {"ValveOut": CAP_WRITE, "Status": CAP_WRITE})
        self.assertTrue(any("CAP_PIN_OUT" in v for v in violations))

        # With CAP_PIN_OUT granted, no pin violation
        violations_ok = check_module_security_acl(module, {"ValveOut": CAP_PIN_OUT | CAP_WRITE, "Status": CAP_WRITE})
        self.assertEqual(len(violations_ok), 0)

        # Without CAP_WRITE for Status, audit detects write violation
        violations_ro = check_module_security_acl(module, {"ValveOut": CAP_PIN_OUT | CAP_WRITE, "Status": CAP_READ})
        self.assertTrue(any("CAP_WRITE" in v and "Status" in v for v in violations_ro))

    def test_v07_mutant_generation(self):
        source = """
        Problem FuzzSample {}
        Solution FuzzSample {
            event Tick();
            state Count: Int32 = 0;
            state Enabled: Bool = false;
            rule on_tick on Tick when Count < 10 {
                set Count := 1;
                set Enabled := true;
            }
        }
        Proof FuzzSample {}
        """
        module = parse_module(source)
        mutants = generate_mutants(module)
        self.assertGreater(len(mutants), 0)
        names = [m[0] for m in mutants]
        # Should have ROR, BSR, and SVR mutants
        self.assertTrue(any("ROR" in n for n in names))
        self.assertTrue(any("BSR" in n for n in names))
        self.assertTrue(any("SVR" in n for n in names))

    def test_v07_popperian_falsification_score_and_gate_failure(self):
        # Module has empty Proof: any mutant will survive!
        source = """
        Problem WeakProof {}
        Solution WeakProof {
            event Sample(Val: Int32);
            state Alarm: Bool = false;
            rule on_high on Sample when Val > 50 {
                set Alarm := true;
            }
        }
        Proof WeakProof {}
        """
        module = parse_module(source)
        res = run_falsification_suite(module)
        self.assertLess(res.mutation_score, 1.0)
        self.assertGreater(len(res.survived_mutants), 0)

        # Gate should reject compilation due to surviving mutants
        with self.assertRaises(KpolError) as ctx:
            enforce_popperian_gate(module)
        self.assertIn("Popperian falsification gate failed", str(ctx.exception))

    def test_v07_popperian_falsification_perfect_score_and_corroboration(self):
        source = """
        Problem RobustProof {}
        Solution RobustProof {
            event Ev(Val: Int32);
            state Flag: Bool = false;
            rule on_ev on Ev when Val > 10 {
                set Flag := true;
            }
        }
        Proof RobustProof {
            scenario S1 {
                step Ev(Val: 10);
                expect Flag == false;
                step Ev(Val: 11);
                expect Flag == true;
                step Ev(Val: 9);
                expect Flag == true;
            }
            assert Bound on Ev {
                when Val > 10 expect Flag == true;
            }
        }
        """
        module = parse_module(source)
        res = run_falsification_suite(module)
        self.assertEqual(res.killed_mutants, res.total_mutants)
        self.assertEqual(res.mutation_score, 1.0)
        self.assertGreater(res.corroboration_score, 0.5)

        # Gate passes cleanly
        passed_res = enforce_popperian_gate(module)
        self.assertEqual(passed_res.mutation_score, 1.0)

    def test_v08_compile_baremetal_runtime(self):
        source = """
        Problem EngineCtrl {
            Hazards {
                Overheat on Sample to Shutdown: Param > 100;
            }
        }
        Solution EngineCtrl {
            event Sample(Param: Int32);
            state Temp: Int32 = 25;
            state Shutdown: Bool = false;
            rule on_sample on Sample when Param <= 100 {
                set Temp := Param;
            }
            rule on_trip on Sample when Param > 100 covers Overheat {
                set Shutdown := true;
            }
        }
        Proof EngineCtrl {}
        """
        module = parse_module(source)
        h_code, c_code = compile_baremetal_runtime(module)

        # 1. Header assertions
        self.assertIn("#ifndef KM_ENGINECTRL_RUNTIME_H", h_code)
        self.assertIn("typedef struct {", h_code)
        self.assertIn("state_Temp;", h_code)
        self.assertIn("km_enginectrl_dispatch", h_code)
        self.assertNotIn("malloc", h_code)

        # 2. Source assertions
        self.assertIn('#include "km_enginectrl_runtime.h"', c_code)
        self.assertIn("void km_enginectrl_init(km_enginectrl_context_t *ctx)", c_code)
        self.assertIn("ctx->state_Temp = 25;", c_code)
        self.assertIn("km_enginectrl_dispatch", c_code)
        self.assertIn("KM_TXN_HAZARD_BLOCKED", c_code)
        self.assertNotIn("malloc", c_code)
        self.assertNotIn("free", c_code)

    def test_v08_compile_axi_lite_wrapper(self):
        source = """
        Problem AxiModule {}
        Solution AxiModule {
            state Counter: Int32 = 0;
        }
        Proof AxiModule {}
        """
        module = parse_module(source)
        sv_code = compile_axi_lite_wrapper(module)

        self.assertIn("module km_aximodule_axi_lite_slave", sv_code)
        self.assertIn("s_axi_aclk", sv_code)
        self.assertIn("s_axi_awaddr", sv_code)
        self.assertIn("cycle_counter_reg", sv_code)
        self.assertIn("cr_status_reg", sv_code)

    def test_v09_parse_triad_files_success(self):
        problem_file = """
        namespace Avionics::Sensors;

        Problem SensorNode {
            Invariants {
                ValidReading: Value >= 0;
            }
        }
        """
        solution_file = """
        namespace Avionics::Sensors;
        import Avionics::Sensors::SensorNode;

        Solution SensorNode {
            event Read(Raw: Int32);
            state Value: Int32 = 0;
            rule on_read on Read when Raw >= 0 {
                set Value := Raw;
            }
        }
        """
        proof_file = """
        namespace Avionics::Sensors;
        import Avionics::Sensors::SensorNode;

        Proof SensorNode {
            scenario S1 {
                step Read(Raw: 10);
                expect Value == 10;
            }
        }
        """
        module = parse_triad_files(problem_file, solution_file, proof_file)
        self.assertEqual(module.name, "SensorNode")
        self.assertEqual(len(module.requirements), 1)
        self.assertEqual(len(module.states), 1)
        self.assertEqual(len(module.proofs), 1)

    def test_v09_link_modules_success(self):
        src1 = """
        Problem ModA {}
        Solution ModA {
            state StateA: Int32 = 1;
        }
        Proof ModA {}
        """
        src2 = """
        Problem ModB {}
        Solution ModB {
            state StateB: Int32 = 2;
        }
        Proof ModB {}
        """
        mod1 = parse_module(src1)
        mod2 = parse_module(src2)

        composite = link_modules([mod1, mod2], "IntegratedNode")
        self.assertEqual(composite.name, "IntegratedNode")
        self.assertEqual(len(composite.states), 2)
        state_names = [s.name for s in composite.states]
        self.assertIn("StateA", state_names)
        self.assertIn("StateB", state_names)

    def test_v09_link_modules_bram_limit_exceeded(self):
        # Create a module with 35 states and another with 30 states (total 65 > 64)
        states1 = "\n".join(f"state S_{i}: Int32 = 0;" for i in range(35))
        src1 = f"Problem Big1 {{}} Solution Big1 {{\n{states1}\n}} Proof Big1 {{}}"
        states2 = "\n".join(f"state S_{i+35}: Int32 = 0;" for i in range(30))
        src2 = f"Problem Big2 {{}} Solution Big2 {{\n{states2}\n}} Proof Big2 {{}}"

        mod1 = parse_module(src1)
        mod2 = parse_module(src2)

        with self.assertRaises(KpolError) as ctx:
            link_modules([mod1, mod2])
        self.assertIn("exceeds 64-concept BRAM hardware limit", str(ctx.exception))

    def test_v05_real_iverilog_interconnect_with_gate_v2(self):
        source = """
        Problem InterconnectRealTest {}
        Solution InterconnectRealTest {
            state S1: Int32 = 0;
        }
        Proof InterconnectRealTest {
            scenario Scen1 { expect S1 == 0; }
        }
        """
        mod = parse_module(source)
        ic_sv = compile_verilog_interconnect(mod)
        gate_v2_path = REPO_ROOT / "hw" / "rtl" / "core" / "kpol_txn_gate_v2.sv"
        self.assertTrue(gate_v2_path.exists(), f"Missing {gate_v2_path}")

        tb_code = """`timescale 1ns / 1ps
module tb_interconnect_real;
    logic clk = 0;
    logic rst_n = 0;
    always #5 clk = ~clk;

    logic event_strobe = 0;
    logic hazard_active = 0;
    logic alert_active = 0;
    logic committed;
    logic rejected;
    logic hazard_blocked;
    logic alert_observed;

    km_interconnectrealtest_interconnect dut (
        .clk(clk),
        .rst_n(rst_n),
        .event_strobe_i(event_strobe),
        .hazard_active_i(hazard_active),
        .alert_active_i(alert_active),
        .committed_o(committed),
        .rejected_o(rejected),
        .hazard_blocked_o(hazard_blocked),
        .alert_observed_o(alert_observed)
    );

    initial begin
        #20 rst_n = 1;
        #10;

        // 1. Normal event strobe
        @(posedge clk);
        event_strobe = 1;
        hazard_active = 0;
        @(posedge clk);
        #1;
        if (committed != 1 || rejected != 0) begin
            $display("ERROR Test 1: Normal event failed to commit");
            $fatal(1);
        end
        event_strobe = 0;

        // 2. Event strobe with active hazard (Fail-Closed)
        @(posedge clk);
        event_strobe = 1;
        hazard_active = 1;
        @(posedge clk);
        #1;
        if (committed != 0 || rejected != 1 || hazard_blocked != 1) begin
            $display("ERROR Test 2: Hazard failed to block transaction fail-closed");
            $fatal(1);
        end
        event_strobe = 0;
        hazard_active = 0;

        // 3. Alert active does not block transaction
        @(posedge clk);
        event_strobe = 1;
        alert_active = 1;
        hazard_active = 0;
        @(posedge clk);
        #1;
        if (committed != 1 || alert_observed != 1) begin
            $display("ERROR Test 3: Alert blocked or was not observed");
            $fatal(1);
        end
        event_strobe = 0;
        alert_active = 0;

        $display("ALL_INTERCONNECT_HARDWARE_CHECKS_PASSED");
        $finish;
    end
endmodule
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ic_path = os.path.join(tmpdir, "km_interconnect.sv")
            tb_path = os.path.join(tmpdir, "tb_interconnect.sv")
            out_bin = os.path.join(tmpdir, "sim.vvp")
            with open(ic_path, "w", encoding="utf-8") as f:
                f.write(ic_sv)
            with open(tb_path, "w", encoding="utf-8") as f:
                f.write(tb_code)

            compile_res = subprocess.run(
                ["iverilog", "-g2012", "-o", out_bin, str(gate_v2_path), ic_path, tb_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_res.returncode, 0, f"iverilog failed:\n{compile_res.stderr}")

            run_res = subprocess.run(["vvp", out_bin], capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0, f"vvp failed:\n{run_res.stdout}\n{run_res.stderr}")
            self.assertIn("ALL_INTERCONNECT_HARDWARE_CHECKS_PASSED", run_res.stdout)

    def test_v06_security_anti_replay_and_key_enforcement(self):
        source = """
        Problem ReplayTest {}
        Solution ReplayTest {
            state Counter: Int32 = 0;
        }
        Proof ReplayTest {
            scenario S1 { expect Counter == 0; }
        }
        """
        module = parse_module(source)

        # 1. Reject key shorter than 16 bytes
        short_key = b"short_8b"
        with self.assertRaises(KpolError) as ctx:
            compile_signed_bram_image(module, short_key)
        self.assertIn("at least 16 bytes", str(ctx.exception))

        # 2. Valid 32-byte key produces signed image
        valid_key = b"0123456789abcdef0123456789abcdef"
        img1 = compile_signed_bram_image(module, valid_key, nonce=1001)

        # 3. First verification succeeds and logs nonce
        seen_nonces = set()
        ok, msg = verify_bram_signature(img1, valid_key, seen_nonces=seen_nonces)
        self.assertTrue(ok, msg)
        expected_nonce = struct.pack("<Q", 1001).ljust(16, b"\x00")
        self.assertIn(expected_nonce, seen_nonces)

        # 4. Replay attempt with same nonce is rejected
        ok_replay, msg_replay = verify_bram_signature(img1, valid_key, seen_nonces=seen_nonces)
        self.assertFalse(ok_replay)
        self.assertIn("replay attack detected", msg_replay.lower())

    def test_v06_security_acl_blocks_unauthorized_pin_compilation(self):
        source = """
        Problem PinSecurity {}
        Solution PinSecurity {
            event Fire();
            state Actuator: Pin<Out> = 0;
            rule on_fire on Fire {
                set Actuator := 1;
            }
        }
        Proof PinSecurity {
            scenario S1 {
                step Fire();
                expect Actuator == 1;
            }
        }
        """
        module = parse_module(source)

        # Compilation without CAP_PIN_OUT must fail
        with self.assertRaises(KpolError) as ctx:
            compile_bram_image(module, acl_table={"Actuator": CAP_WRITE})
        self.assertIn("Security ACL violation", str(ctx.exception))
        self.assertIn("CAP_PIN_OUT", str(ctx.exception))

        # Compilation with CAP_PIN_OUT granted succeeds
        img = compile_bram_image(module, acl_table={"Actuator": CAP_PIN_OUT | CAP_WRITE})
        self.assertEqual(len(img), 1024)

    def test_v07_popperian_falsification_anti_vacuum(self):
        source = """
        Problem VacuumModule {}
        Solution VacuumModule {
            state Flag: Bool = true;
        }
        Proof VacuumModule {
            scenario S1 { expect Flag == true; }
        }
        """
        module = parse_module(source)
        mutants = generate_mutants(module)
        self.assertEqual(len(mutants), 0)

        # Popperian gate on module with rules must not vacuum pass
        source_with_rule = """
        Problem MutCompModule {}
        Solution MutCompModule {
            event Sample(Val: Int32);
            state Safe: Bool = true;
            rule on_sample on Sample when Val > 10 and Val < 50 {
                set Safe := true;
            }
        }
        Proof MutCompModule {
            scenario S1 {
                step Sample(Val: 20);
                expect Safe == true;
            }
        }
        """
        mod_with_rule = parse_module(source_with_rule)
        muts_comp = generate_mutants(mod_with_rule)
        self.assertGreater(len(muts_comp), 0)
        # Verify mutation of compound operator (and -> or)
        mut_names = [m[0] for m in muts_comp]
        self.assertTrue(any("and_to_or" in m for m in mut_names))

    def test_v08_real_gcc_baremetal_runtime_compilation_and_execution(self):
        source = """
        Problem SafetyEngine {
            Assumptions {
                ValidSensor on Sample: Param >= 0 and Param <= 200;
            }
            Hazards {
                Overheat on Sample to Fault: Param > 120;
            }
            Invariants {
                FaultSafe: Fault == false or Fault == true;
            }
        }
        Solution SafetyEngine {
            event Sample(Param: Int32);
            state CurrentTemp: Int32 = 25;
            state Fault: Bool = false;
            rule on_sample on Sample when Param <= 120 {
                set CurrentTemp := Param;
            }
            rule on_trip on Sample when Param > 120 covers Overheat {
                set Fault := true;
            }
        }
        Proof SafetyEngine {
            scenario S1 {
                step Sample(Param: 50);
                expect CurrentTemp == 50;
            }
        }
        """
        module = parse_module(source)
        h_code, c_code = compile_baremetal_runtime(module)

        driver_c = """
#include <stdio.h>
#include <assert.h>
#include "km_safetyengine_runtime.h"

int main() {
    km_safetyengine_context_t ctx;
    km_safetyengine_init(&ctx);
    assert(ctx.state_CurrentTemp == 25);
    assert(ctx.state_Fault == 0);

    // Case 1: param = 110 (Verifies no 100 hardcode from F-01!)
    km_safetyengine_payload_sample_t p1 = { .Param = 110 };
    km_safetyengine_status_t s1 = km_safetyengine_dispatch(&ctx, KM_EV_SAMPLE, &p1);
    assert(s1 == KM_TXN_COMMITTED);
    assert(ctx.state_CurrentTemp == 110);
    assert(ctx.state_Fault == 0);

    // Case 2: param = 120 (Nominal upper boundary)
    km_safetyengine_payload_sample_t p2 = { .Param = 120 };
    km_safetyengine_status_t s2 = km_safetyengine_dispatch(&ctx, KM_EV_SAMPLE, &p2);
    assert(s2 == KM_TXN_COMMITTED);
    assert(ctx.state_CurrentTemp == 120);
    assert(ctx.state_Fault == 0);

    // Case 3: param = 121 (Hazard threshold, fail-closed blocking)
    km_safetyengine_payload_sample_t p3 = { .Param = 121 };
    km_safetyengine_status_t s3 = km_safetyengine_dispatch(&ctx, KM_EV_SAMPLE, &p3);
    assert(s3 == KM_TXN_HAZARD_BLOCKED);
    assert(ctx.state_CurrentTemp == 120); // State preserved, not overwritten
    assert(ctx.state_Fault == 1);          // Hazard target latched

    // Case 4: param = 250 (Assumption violated, out of sensor range)
    km_safetyengine_payload_sample_t p4 = { .Param = 250 };
    km_safetyengine_status_t s4 = km_safetyengine_dispatch(&ctx, KM_EV_SAMPLE, &p4);
    assert(s4 == KM_TXN_REJECTED);

    // Case 5: param = -1 (Assumption violated, negative)
    km_safetyengine_payload_sample_t p5 = { .Param = -1 };
    km_safetyengine_status_t s5 = km_safetyengine_dispatch(&ctx, KM_EV_SAMPLE, &p5);
    assert(s5 == KM_TXN_REJECTED);

    printf("ALL_GCC_BAREMETAL_CHECKS_PASSED\\n");
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            h_path = os.path.join(tmpdir, "km_safetyengine_runtime.h")
            c_path = os.path.join(tmpdir, "km_safetyengine_runtime.c")
            main_path = os.path.join(tmpdir, "main.c")
            bin_path = os.path.join(tmpdir, "test_runtime_bin")

            with open(h_path, "w", encoding="utf-8") as f:
                f.write(h_code)
            with open(c_path, "w", encoding="utf-8") as f:
                f.write(c_code)
            with open(main_path, "w", encoding="utf-8") as f:
                f.write(driver_c)

            compile_res = subprocess.run(
                ["gcc", "-std=c99", "-Wall", "-Wextra", "-pedantic", "-I" + tmpdir, c_path, main_path, "-o", bin_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_res.returncode, 0, f"GCC build failed:\n{compile_res.stderr}")

            run_res = subprocess.run([bin_path], capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0, f"Binary execution failed:\n{run_res.stderr}")
            self.assertIn("ALL_GCC_BAREMETAL_CHECKS_PASSED", run_res.stdout)

    def test_v08_real_python_c_runtime_parity(self):
        source = """
        Problem ParityEngine {
            Assumptions {
                ValidSensor on Sample: Param >= 0 and Param <= 200;
            }
            Hazards {
                Overheat on Sample to Fault: Param > 120;
            }
            Invariants {
                FaultSafe: Fault == false or Fault == true;
            }
        }
        Solution ParityEngine {
            event Sample(Param: Int32);
            state CurrentTemp: Int32 = 25;
            state Fault: Bool = false;
            rule on_sample on Sample when Param <= 120 {
                set CurrentTemp := Param;
            }
            rule on_trip on Sample when Param > 120 covers Overheat {
                set Fault := true;
            }
        }
        Proof ParityEngine {
            scenario S1 {
                step Sample(Param: 50);
                expect CurrentTemp == 50;
            }
        }
        """
        module = parse_module(source)
        h_code, c_code = compile_baremetal_runtime(module)

        driver_c = """
#include <stdio.h>
#include <stdlib.h>
#include "km_parityengine_runtime.h"

int main(int argc, char **argv) {
    if (argc < 2) return 1;
    km_parityengine_context_t ctx;
    km_parityengine_init(&ctx);

    for (int i = 1; i < argc; i++) {
        int32_t val = (int32_t)atoi(argv[i]);
        km_parityengine_payload_sample_t p = { .Param = val };
        km_parityengine_status_t s = km_parityengine_dispatch(&ctx, KM_EV_SAMPLE, &p);
        const char *status_str = "COMMITTED";
        if (s == KM_TXN_HAZARD_BLOCKED) status_str = "HAZARD_BLOCKED";
        else if (s == KM_TXN_REJECTED) status_str = "REJECTED";
        printf("%d:%s:%d:%d\\n", val, status_str, ctx.state_CurrentTemp, ctx.state_Fault);
    }
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            h_path = os.path.join(tmpdir, "km_parityengine_runtime.h")
            c_path = os.path.join(tmpdir, "km_parityengine_runtime.c")
            main_path = os.path.join(tmpdir, "main.c")
            bin_path = os.path.join(tmpdir, "parity_bin")

            with open(h_path, "w", encoding="utf-8") as f:
                f.write(h_code)
            with open(c_path, "w", encoding="utf-8") as f:
                f.write(c_code)
            with open(main_path, "w", encoding="utf-8") as f:
                f.write(driver_c)

            subprocess.run(["gcc", "-std=c99", "-I" + tmpdir, c_path, main_path, "-o", bin_path], check=True)

            test_values = [20, 110, 120, 121, 150, 50, -5, 200, 205, 90]
            args = [bin_path] + [str(v) for v in test_values]
            c_run = subprocess.run(args, capture_output=True, text=True, check=True)
            c_records = [line.split(":") for line in c_run.stdout.strip().splitlines()]

            # Python reference interpreter execution
            interp = Interpreter(module, fail_closed_hazards=True)
            for idx, v in enumerate(test_values):
                res = interp.run([EventInput("Sample", {"Param": v})])
                c_val, c_status, c_temp, c_fault = c_records[idx]

                # Verify state parity
                self.assertEqual(int(c_temp), interp.state["CurrentTemp"], f"Temp mismatch at step {idx} (input {v})")
                self.assertEqual(bool(int(c_fault)), interp.state["Fault"], f"Fault mismatch at step {idx} (input {v})")

                # Verify transaction outcome parity
                if c_status == "COMMITTED":
                    self.assertNotIn("RejectedInput:Sample", res.rejected)
                    self.assertNotIn("RejectedHazard:Overheat", res.rejected)
                elif c_status == "HAZARD_BLOCKED":
                    self.assertIn("RejectedHazard:Overheat", res.rejected)
                elif c_status == "REJECTED":
                    self.assertIn("RejectedInput:Sample", res.rejected)

    def test_v08_real_iverilog_axi_lite_slave_protocol(self):
        source = """
        Problem AxiBusParity {}
        Solution AxiBusParity {
            state Reg0: Int32 = 0;
        }
        Proof AxiBusParity {
            scenario S1 { expect Reg0 == 0; }
        }
        """
        mod = parse_module(source)
        sv_code = compile_axi_lite_wrapper(mod)

        tb_code = """`timescale 1ns / 1ps
module tb_axi_lite_compliance;
    logic aclk = 0;
    logic aresetn = 0;
    always #5 aclk = ~aclk;

    logic [5:0]  awaddr;
    logic [2:0]  awprot = 0;
    logic        awvalid = 0;
    logic        awready;

    logic [31:0] wdata = 0;
    logic [3:0]  wstrb = 4'b1111;
    logic        wvalid = 0;
    logic        wready;

    logic [1:0]  bresp;
    logic        bvalid;
    logic        bready = 0;

    logic [5:0]  araddr = 0;
    logic [2:0]  arprot = 0;
    logic        arvalid = 0;
    logic        arready;

    logic [31:0] rdata;
    logic [1:0]  rresp;
    logic        rvalid;
    logic        rready = 0;

    km_axibusparity_axi_lite_slave dut (
        .s_axi_aclk(aclk),
        .s_axi_aresetn(aresetn),
        .s_axi_awaddr(awaddr),
        .s_axi_awprot(awprot),
        .s_axi_awvalid(awvalid),
        .s_axi_awready(awready),
        .s_axi_wdata(wdata),
        .s_axi_wstrb(wstrb),
        .s_axi_wvalid(wvalid),
        .s_axi_wready(wready),
        .s_axi_bresp(bresp),
        .s_axi_bvalid(bvalid),
        .s_axi_bready(bready),
        .s_axi_araddr(araddr),
        .s_axi_arprot(arprot),
        .s_axi_arvalid(arvalid),
        .s_axi_arready(arready),
        .s_axi_rdata(rdata),
        .s_axi_rresp(rresp),
        .s_axi_rvalid(rvalid),
        .s_axi_rready(rready)
    );

    initial begin
        #10000;
        $display("ERROR: AXI simulation watchdog timeout");
        $fatal(2);
    end

    initial begin
        #20 aresetn = 1;
        #10;

        // Case A: W asserted BEFORE AW
        @(posedge aclk);
        wdata = 32'hDEADBEEF;
        wstrb = 4'b1111;
        wvalid = 1;
        bready = 0;
        @(posedge aclk);
        #1;
        if (bvalid != 0) begin
            $display("ERROR Case A: bvalid asserted before AW");
            $fatal(1);
        end
        wvalid = 0;

        awaddr = 6'h04;
        awvalid = 1;
        @(posedge aclk);
        #1;
        awvalid = 0;

        while (!bvalid) @(posedge aclk);
        #1;
        bready = 1;
        @(posedge aclk);
        #1;
        bready = 0;

        // Read back register 0x04 (EVENT_ID)
        @(posedge aclk);
        araddr = 6'h04;
        arvalid = 1;
        rready = 0;
        @(posedge aclk);
        #1;
        arvalid = 0;
        while (!rvalid) @(posedge aclk);
        #1;
        if (rdata != 32'hDEADBEEF) begin
            $display("ERROR Case A: Expected 0xDEADBEEF at 0x04, got 0x%08X", rdata);
            $fatal(1);
        end
        rready = 1;
        @(posedge aclk);
        #1;
        rready = 0;

        // Case B: AW before W with address bus changing
        @(posedge aclk);
        awaddr = 6'h08; // PARAM0
        awvalid = 1;
        bready = 0;
        @(posedge aclk);
        #1;
        awvalid = 0;
        awaddr = 6'h00; // bus changed to 0x00 while waiting for W

        @(posedge aclk);
        #1;
        wdata = 32'hCAFEBABE;
        wstrb = 4'b1111;
        wvalid = 1;
        @(posedge aclk);
        #1;
        wvalid = 0;

        while (!bvalid) @(posedge aclk);
        #1;
        bready = 1;
        @(posedge aclk);
        #1;
        bready = 0;

        // Read 0x08 - must contain CAFEBABE, NOT 0x00
        @(posedge aclk);
        #1;
        araddr = 6'h08;
        arvalid = 1;
        rready = 0;
        @(posedge aclk);
        #1;
        arvalid = 0;
        while (!rvalid) @(posedge aclk);
        #1;
        if (rdata != 32'hCAFEBABE) begin
            $display("ERROR Case B: Expected 0xCAFEBABE at 0x08, got 0x%08X", rdata);
            $fatal(1);
        end
        rready = 1;
        @(posedge aclk);
        #1;
        rready = 0;

        // Case C: WSTRB partial write
        @(posedge aclk);
        #1;
        awaddr = 6'h04;
        awvalid = 1;
        wdata = 32'h12345678;
        wstrb = 4'b0001;
        wvalid = 1;
        bready = 0;
        @(posedge aclk);
        #1;
        awvalid = 0;
        wvalid = 0;

        while (!bvalid) @(posedge aclk);
        #1;
        bready = 1;
        @(posedge aclk);
        #1;
        bready = 0;

        // Read back 0x04: 0xDEADBEEF with byte 0 replaced by 0x78 -> 0xDEADBE78
        @(posedge aclk);
        #1;
        araddr = 6'h04;
        arvalid = 1;
        rready = 0;
        @(posedge aclk);
        #1;
        arvalid = 0;
        while (!rvalid) @(posedge aclk);
        #1;
        if (rdata != 32'hDEADBE78) begin
            $display("ERROR Case C: Expected 0xDEADBE78 at 0x04, got 0x%08X", rdata);
            $fatal(1);
        end
        rready = 1;
        @(posedge aclk);
        #1;
        rready = 0;

        // Case D: Backpressure with bready = 0
        @(posedge aclk);
        #1;
        awaddr = 6'h04;
        awvalid = 1;
        wdata = 32'hA5A5A5A5;
        wstrb = 4'b1111;
        wvalid = 1;
        bready = 0;
        @(posedge aclk);
        #1;
        awvalid = 0;
        wvalid = 0;

        while (!bvalid) @(posedge aclk);
        #1;
        if (awready != 0 || wready != 0) begin
            $display("ERROR Case D: Slave did not assert backpressure on awready/wready");
            $fatal(1);
        end
        repeat (3) @(posedge aclk);
        #1;
        if (bvalid != 1) begin
            $display("ERROR Case D: bvalid dropped before bready asserted");
            $fatal(1);
        end
        bready = 1;
        @(posedge aclk);
        #1;
        bready = 0;

        $display("ALL_AXI4_LITE_SIMULATION_CHECKS_PASSED");
        $finish;
    end
endmodule
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sv_path = os.path.join(tmpdir, "km_axibusparity_axi_lite_slave.sv")
            tb_path = os.path.join(tmpdir, "tb_axi_lite.sv")
            out_bin = os.path.join(tmpdir, "sim.vvp")
            with open(sv_path, "w", encoding="utf-8") as f:
                f.write(sv_code)
            with open(tb_path, "w", encoding="utf-8") as f:
                f.write(tb_code)

            compile_res = subprocess.run(
                ["iverilog", "-g2012", "-o", out_bin, sv_path, tb_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_res.returncode, 0, f"iverilog failed:\n{compile_res.stderr}")

            run_res = subprocess.run(["vvp", out_bin], capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0, f"vvp failed:\n{run_res.stdout}\n{run_res.stderr}")
            self.assertIn("ALL_AXI4_LITE_SIMULATION_CHECKS_PASSED", run_res.stdout)

    def test_v09_triad_cryptographic_independence_enforcement(self):
        problem_file = "Problem P { Invariants { I: X >= 0; } }"
        solution_file = "Solution P { state X: Int32 = 0; }"
        empty_proof = "Proof P {}"

        # 1. Empty proof must be rejected (Anti-Mocking DO-178C)
        with self.assertRaises(KpolError) as ctx:
            parse_triad_files(problem_file, solution_file, empty_proof)
        self.assertIn("must declare at least one assert or scenario", str(ctx.exception))

        # 2. None or empty string proof must be rejected
        with self.assertRaises(KpolError) as ctx:
            parse_triad_files(problem_file, solution_file, "")
        self.assertIn("mandatory and cannot be empty", str(ctx.exception))

        # 3. Valid proof passes and attaches SHA-256 hashes
        valid_proof = "Proof P { scenario S1 { expect X == 0; } }"
        module = parse_triad_files(problem_file, solution_file, valid_proof)
        self.assertEqual(module.name, "P")
        self.assertIsNotNone(module.problem_hash)
        self.assertIsNotNone(module.solution_hash)
        self.assertIsNotNone(module.proof_hash)
        self.assertEqual(len(module.problem_hash), 64)
        self.assertEqual(len(module.solution_hash), 64)
        self.assertEqual(len(module.proof_hash), 64)

    def test_v10_concept_microcode_bram_generation(self):
        """KPOL v1.0 / Refactoring Step 3: Генерація 16-байтних мікрокод-дескрипторів для CME."""
        source = """
        Problem CME_System {
            Invariants {
                InvNonNeg: Counter >= 0;
            }
            Hazards {
                HzrdLimit on Pulse to HazardFlag: param > 90;
            }
        }
        Solution CME_System {
            state Counter: Int32 = 10;
            state CascadeTarget: Int32 = 50;
            state HazardFlag: Bool = false;

            event Pulse(param: Int32);

            rule StepRule on Pulse when param > 5 {
                set Counter := Counter + 1;
            }

            rule StepCascade on Pulse when •(param == 0) {
                set CascadeTarget := CascadeTarget + 5;
            }

            rule HazardTrip on reject Pulse when param > 90 covers HzrdLimit {
                set HazardFlag := true;
            }
        }
        """
        module = parse_module(source)
        cascade_map = {"Counter": "CascadeTarget"}

        # 1. Компіляція мікрокоду
        bram_bytes = compile_concept_microcode_bram_image(module, cascade_map=cascade_map)
        self.assertEqual(len(bram_bytes), 1024)

        # 2. Дезасемблювання
        descriptors = disassemble_concept_microcode(bram_bytes)
        self.assertEqual(len(descriptors), 64)

        # Концепт 0: Counter
        c0 = descriptors[0]
        self.assertEqual(c0.cid, 0)
        self.assertEqual(c0.current_state, 10)
        self.assertEqual(c0.operand_val, 5)
        self.assertEqual(c0.pred_opcode, CME_PRED_GT)
        self.assertEqual(c0.action_opcode, CME_ACT_INC)
        # Перевірка прапорців: Assumption (1) + Invariant (2) + Hazard (4) = 7
        self.assertTrue(c0.guard_flags & CME_GUARD_ASSUMPTION_EN)
        self.assertTrue(c0.guard_flags & CME_GUARD_INVARIANT_EN)
        self.assertTrue(c0.guard_flags & CME_GUARD_HAZARD_EN)
        self.assertEqual(c0.hazard_limit, 90)
        # subscriber_cid має вказувати на CascadeTarget (CID 1)
        self.assertEqual(c0.subscriber_cid, 1)

        # Концепт 1: CascadeTarget
        c1 = descriptors[1]
        self.assertEqual(c1.cid, 1)
        self.assertEqual(c1.current_state, 50)
        self.assertEqual(c1.action_opcode, CME_ACT_ADD)
        self.assertEqual(c1.operand_val, 5)
        self.assertEqual(c1.pred_opcode, CME_PRED_EQ)
        # Перевірка Big Dot: • = ¬ (bit 3)
        self.assertTrue(c1.guard_flags & CME_GUARD_INVERT_ASSUMPTION)
        self.assertEqual(c1.subscriber_cid, 0)

        # Порожні слоти 3..63
        for cid in range(3, 64):
            c_empty = descriptors[cid]
            self.assertEqual(c_empty.current_state, 0)
            self.assertEqual(c_empty.operand_val, 0)
            self.assertEqual(c_empty.pred_opcode, CME_PRED_NOP)
            self.assertEqual(c_empty.action_opcode, CME_ACT_ASSIGN)
            self.assertEqual(c_empty.subscriber_cid, 0)

        # 3. Криптографічний підпис образу HMAC-SHA256
        secret = b"KuzminMachineSecretKeyForCME_001"
        signed_image = compile_signed_bram_image(bram_bytes, secret_key=secret)
        self.assertEqual(len(signed_image), 1024 + 64)  # 1024 data + 64 header
        self.assertTrue(verify_bram_signature(signed_image, secret_key=secret))


if __name__ == "__main__":
    unittest.main()
