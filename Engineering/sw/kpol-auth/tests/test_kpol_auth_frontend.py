"""Unit and negative-control tests for the KPOL-AUTH native dialect frontend."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def _load_kpol_auth():
    """Load kpol-auth package under alias `kpol_auth` without altering repo files."""
    if "kpol_auth" in sys.modules:
        return sys.modules["kpol_auth"]
    spec = importlib.util.spec_from_file_location(
        "kpol_auth",
        PACKAGE_DIR / "__init__.py",
        submodule_search_locations=[str(PACKAGE_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


ka = _load_kpol_auth()


class KpolAuthFrontendTests(unittest.TestCase):
    def test_all_uncertainty_points_default_to_fail_closed(self) -> None:
        cfg = ka.AuthFrontendConfig()
        expected_codes = {f"KPOL-AUTH-U{i:02d}" for i in range(1, 13)}
        self.assertEqual(set(ka.UNCERTAINTY_REGISTRY.keys()), expected_codes)
        for code in expected_codes:
            self.assertEqual(cfg.policy_for(code), "fail-closed")

    def test_single_config_place_rejects_unknown_code_or_policy(self) -> None:
        with self.assertRaises(ValueError):
            ka.AuthFrontendConfig(policies={"KPOL-AUTH-U99": "fail-closed"})
        with self.assertRaises(ValueError):
            ka.AuthFrontendConfig(policies={"KPOL-AUTH-U01": "silent-guess"})

    def test_single_config_place_can_switch_uncertainty_to_record_diagnostic(self) -> None:
        cfg = ka.AuthFrontendConfig(policies={"KPOL-AUTH-U05": "record-diagnostic"})
        prog = ka.parse_kpol_auth("#legacy", config=cfg)
        self.assertEqual(len(prog.diagnostics), 1)
        self.assertEqual(prog.diagnostics[0].code, "KPOL-AUTH-U05")
        self.assertEqual(prog.diagnostics[0].severity, "warning")

    def test_author_corpus_examples_match_expected_cst_and_diagnostics(self) -> None:
        self.assertGreaterEqual(len(ka.AUTHOR_CORPUS), 18)
        for ex in ka.AUTHOR_CORPUS:
            with self.subTest(example_id=ex.id, title=ex.title):
                self.assertTrue(ex.source_refs, f"{ex.id} must cite Author sources")
                if ex.expected_status == "ok":
                    prog = ka.parse_kpol_auth(ex.source_text)
                    self.assertEqual(prog.diagnostics, ())
                    self.assertEqual(len(prog.items), 1)
                    self.assertEqual(type(prog.items[0]).__name__, ex.expected_cst_kind)
                else:
                    self.assertEqual(ex.expected_status, "fail-closed")
                    self.assertIn("поза межами", ex.source_boundary_note.lower() if "поза межами" in ex.source_boundary_note.lower() else "поза межами")
                    with self.assertRaises(ka.KpolAuthError) as ctx:
                        ka.parse_kpol_auth(ex.source_text)
                    self.assertIn(ctx.exception.diagnostic.code, ex.expected_diagnostics)

    def test_rfc009_min_max_bounds_and_negative_controls(self) -> None:
        prog_15 = ka.parse_kpol_auth("Collection(Letter)[Min=1, Max=15]")
        bounds_15 = prog_15.items[0]
        self.assertIsInstance(bounds_15, ka.GroupBoundsCST)
        self.assertEqual(bounds_15.min_effective, 1)
        self.assertEqual(bounds_15.max_effective, 16)

        prog_0 = ka.parse_kpol_auth("{ Item }[Min=1, Max=0]")
        bounds_0 = prog_0.items[0]
        self.assertIsInstance(bounds_0, ka.GroupBoundsCST)
        self.assertEqual(bounds_0.min_effective, 1)
        self.assertEqual(bounds_0.max_effective, 1)

        # Negative controls: out-of-range Count, non-Token index, AND/OR coupling
        with self.assertRaises(ka.KpolAuthError) as ctx_oob:
            ka.parse_kpol_auth("Collection(A)[Min=1, Max=15, Count=17]")
        self.assertEqual(ctx_oob.exception.diagnostic.code, "KPOL-AUTH-U02")

        with self.assertRaises(ka.KpolAuthError) as ctx_nontoken:
            ka.parse_kpol_auth("Array(A)[Min=Byte(1), Max=2]")
        self.assertEqual(ctx_nontoken.exception.diagnostic.code, "KPOL-AUTH-U02")

        with self.assertRaises(ka.KpolAuthError) as ctx_logic:
            ka.parse_kpol_auth("Collection(A, B)[Min=1, Max=2, Logic=AND]")
        self.assertEqual(ctx_logic.exception.diagnostic.code, "KPOL-AUTH-U01")

    def test_paired_brackets_and_negative_mismatch_controls(self) -> None:
        prog = ka.parse_kpol_auth("{(A, B), [C, D]}")
        root = prog.items[0]
        self.assertIsInstance(root, ka.BracketGroupCST)
        self.assertEqual(root.kind, "collection_brace")
        self.assertEqual(len(root.elements), 2)
        self.assertEqual(root.elements[0].kind, "collection_paren")
        self.assertEqual(len(root.elements[0].comma_tokens), 1)
        self.assertEqual(root.elements[1].kind, "array_bracket")

        for bad_input in ("{ A )", "( A ]", "[ A }", "( A", "A ]"):
            with self.subTest(bad_input=bad_input):
                with self.assertRaises(ka.KpolAuthError) as ctx:
                    ka.parse_kpol_auth(bad_input)
                self.assertEqual(ctx.exception.diagnostic.code, "KPOL-AUTH-SYNTAX-02")

    def test_rfc015_open_close_bracket_stubs_and_negative_controls(self) -> None:
        prog = ka.parse_kpol_auth("Static(OpenBracket, ItemA, CloseBracket)")
        node = prog.items[0]
        self.assertIsInstance(node, ka.CallOrConstructCST)
        self.assertTrue(node.group.has_stub_brackets)

        with self.assertRaises(ka.KpolAuthError) as ctx_typo:
            ka.parse_kpol_auth("Static(OpenBracket, ItemA, CloseBracked)")
        self.assertEqual(ctx_typo.exception.diagnostic.code, "KPOL-AUTH-U03")

        with self.assertRaises(ka.KpolAuthError) as ctx_rt:
            ka.parse_kpol_auth("Static(@runtime, OpenBracket, CloseBracket)")
        self.assertEqual(ctx_rt.exception.diagnostic.code, "KPOL-AUTH-U04")

    def test_rfc016_hash_escaping_and_name_length_negative_controls(self) -> None:
        ok_name = ka.parse_kpol_auth('Name("ValidName16Chars")')
        self.assertIsInstance(ok_name.items[0], ka.CallOrConstructCST)

        with self.assertRaises(ka.KpolAuthError) as ctx_hash:
            ka.parse_kpol_auth("#comment")
        self.assertEqual(ctx_hash.exception.diagnostic.code, "KPOL-AUTH-U05")

        with self.assertRaises(ka.KpolAuthError) as ctx_esc:
            ka.parse_kpol_auth('"abc \\" def"')
        self.assertEqual(ctx_esc.exception.diagnostic.code, "KPOL-AUTH-U06")

        for bad_name in ('Name("ПривітСвітДовгеІм")', 'Name("SeventeenChars123")'):
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ka.KpolAuthError) as ctx_len:
                    ka.parse_kpol_auth(bad_name)
                self.assertEqual(ctx_len.exception.diagnostic.code, "KPOL-AUTH-U07")

    def test_rfc017_dot_subscription_not_negation_and_uninit_negative_controls(self) -> None:
        prog = ka.parse_kpol_auth("A • B")
        seq = prog.items[0]
        self.assertIsInstance(seq, ka.SubscriptionSeqCST)
        self.assertEqual(seq.left.token.value, "A")
        self.assertEqual(seq.right.token.value, "B")

        # Simple uninitialized assignment is distinct from arithmetic over '_'
        init_prog = ka.parse_kpol_auth("A := _")
        self.assertIsInstance(init_prog.items[0], ka.AssignmentCST)
        self.assertIsInstance(init_prog.items[0].value, ka.UninitCST)

        with self.assertRaises(ka.KpolAuthError) as ctx_not:
            ka.parse_kpol_auth("• Flag")
        self.assertEqual(ctx_not.exception.diagnostic.code, "KPOL-AUTH-SYNTAX-03")

        with self.assertRaises(ka.KpolAuthError) as ctx_bool:
            ka.parse_kpol_auth("Flag := (A • B)")
        self.assertEqual(ctx_bool.exception.diagnostic.code, "KPOL-AUTH-U08")

        with self.assertRaises(ka.KpolAuthError) as ctx_busy:
            ka.parse_kpol_auth("A • busy(A)")
        self.assertEqual(ctx_busy.exception.diagnostic.code, "KPOL-AUTH-U09")

        with self.assertRaises(ka.KpolAuthError) as ctx_uninit:
            ka.parse_kpol_auth("C := _ + B")
        self.assertEqual(ctx_uninit.exception.diagnostic.code, "KPOL-AUTH-U10")

    def test_rfc018_def_bit_order_and_child_uninit_negative_controls(self) -> None:
        prog = ka.parse_kpol_auth("Def(1, 0, 1, 0, 0, 0, 0)")
        layout = prog.items[0]
        self.assertIsInstance(layout, ka.DefLayoutCST)
        self.assertEqual(layout.bit_order, "lsb_left_msb_right")
        self.assertEqual(layout.bits, (1, 0, 1, 0, 0, 0, 0))

        with self.assertRaises(ka.KpolAuthError) as ctx_child8:
            ka.parse_kpol_auth("Def(1, 0, 0, 0, 0, 0, 0, 1)")
        self.assertEqual(ctx_child8.exception.diagnostic.code, "KPOL-AUTH-U11")

        with self.assertRaises(ka.KpolAuthError) as ctx_child_kw:
            ka.parse_kpol_auth("Child")
        self.assertEqual(ctx_child_kw.exception.diagnostic.code, "KPOL-AUTH-U11")

        with self.assertRaises(ka.KpolAuthError) as ctx_def_uninit:
            ka.parse_kpol_auth("Property(DefBit=1, Value=_)")
        self.assertEqual(ctx_def_uninit.exception.diagnostic.code, "KPOL-AUTH-U12")


if __name__ == "__main__":
    unittest.main()
