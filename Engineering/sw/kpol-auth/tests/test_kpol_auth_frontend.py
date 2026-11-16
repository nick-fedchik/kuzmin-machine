"""Unit and negative-control tests for the KPOL-AUTH native dialect frontend."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

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
        with self.assertRaises(ValueError):
            ka.AuthFrontendConfig(name_length_unit="tokens_guess")

    def test_single_config_place_can_switch_all_uncertainties_to_record_diagnostic(self) -> None:
        samples = {
            "KPOL-AUTH-U01": "Collection(A, B)[Min=1, Max=2, Logic=AND]",
            "KPOL-AUTH-U02": "Array(A, B)[Min=Byte(1), Max=2]",
            "KPOL-AUTH-U03": "Static(OpenBracket, A, CloseBracked)",
            "KPOL-AUTH-U04": "Static(@runtime, OpenBracket, A, CloseBracket)",
            "KPOL-AUTH-U05": "#legacy",
            "KPOL-AUTH-U06": '"text \\" quote"',
            "KPOL-AUTH-U07": 'Name("Абвгдеєжз")',
            "KPOL-AUTH-U08": "Flag := (A • B)",
            "KPOL-AUTH-U09": "A • busy(A)",
            "KPOL-AUTH-U10": "C := _ + B",
            "KPOL-AUTH-U11": "Def(1, 0, 0, 0, 0, 0, 0, 1)",
            "KPOL-AUTH-U12": "Property(DefBit=1, Value=_)",
        }
        self.assertEqual(set(samples.keys()), set(ka.UNCERTAINTY_REGISTRY.keys()))
        for code, source in samples.items():
            with self.subTest(uncertainty_code=code):
                cfg = ka.AuthFrontendConfig(policies={code: "record-diagnostic"})
                prog = ka.parse_kpol_auth(source, config=cfg)
                matching = [d for d in prog.diagnostics if d.code == code]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0].uncertainty_code, code)
                self.assertEqual(matching[0].severity, "warning")

    def test_author_corpus_examples_match_expected_cst_and_diagnostics(self) -> None:
        expected_ids = tuple(f"EX-{i:02d}" for i in range(1, 19))
        actual_ids = tuple(ex.id for ex in ka.AUTHOR_CORPUS)
        self.assertEqual(actual_ids, expected_ids)

        in_scope_ids = {ex.id for ex in ka.AUTHOR_CORPUS if ex.in_source_scope}
        outside_scope_ids = {ex.id for ex in ka.AUTHOR_CORPUS if not ex.in_source_scope}
        self.assertEqual(in_scope_ids, {"EX-01", "EX-02", "EX-03", "EX-04", "EX-05", "EX-06"})
        self.assertEqual(outside_scope_ids, {f"EX-{i:02d}" for i in range(7, 19)})

        for ex in ka.AUTHOR_CORPUS:
            with self.subTest(example_id=ex.id, title=ex.title):
                self.assertTrue(ex.source_refs, f"{ex.id} must cite Author sources")
                self.assertTrue(
                    ex.source_boundary_note.strip(),
                    f"{ex.id} must document source boundary",
                )
                if ex.in_source_scope:
                    if ex.expected_status == "ok":
                        prog = ka.parse_kpol_auth(ex.source_text)
                        self.assertEqual(prog.diagnostics, ())
                        self.assertEqual(len(prog.items), 1)
                        self.assertEqual(type(prog.items[0]).__name__, ex.expected_cst_kind)
                    else:
                        self.assertEqual(ex.id, "EX-06")
                        self.assertEqual(ex.expected_status, "fail-closed")
                        self.assertNotIn(
                            "поза межами джерела",
                            ex.source_boundary_note.lower(),
                        )
                        with self.assertRaises(ka.KpolAuthError) as ctx:
                            ka.parse_kpol_auth(ex.source_text)
                        self.assertIn(
                            ctx.exception.diagnostic.code,
                            ex.expected_diagnostics,
                        )
                else:
                    self.assertEqual(ex.expected_status, "fail-closed")
                    self.assertIn(
                        "поза межами джерела",
                        ex.source_boundary_note.lower(),
                    )
                    self.assertTrue(
                        any(d.startswith("KPOL-AUTH-U") for d in ex.expected_diagnostics)
                    )
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

        for bad_name in ('Name("ПривітСвітДовгеІм")', 'Name("SeventeenChars123")', 'Name("Абвгдеєжз")'):
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ka.KpolAuthError) as ctx_len:
                    ka.parse_kpol_auth(bad_name)
                self.assertEqual(ctx_len.exception.diagnostic.code, "KPOL-AUTH-U07")

    def test_u07_name_length_unit_is_configurable_for_multibyte_cyrillic(self) -> None:
        # 9 Cyrillic characters = 9 Unicode codepoints, 18 UTF-8 bytes
        cyrillic_9 = "Абвгдеєжз"
        self.assertEqual(len(cyrillic_9), 9)
        self.assertEqual(len(cyrillic_9.encode("utf-8")), 18)
        source = f'Name("{cyrillic_9}")'

        # Default "fail-closed" rejects ambiguous >16 UTF-8 bytes
        with self.assertRaises(ka.KpolAuthError) as ctx_default:
            ka.parse_kpol_auth(source)
        self.assertEqual(ctx_default.exception.diagnostic.code, "KPOL-AUTH-U07")

        # Explicit "utf8_bytes" also rejects 18 > 16
        cfg_bytes = ka.AuthFrontendConfig(name_length_unit="utf8_bytes")
        with self.assertRaises(ka.KpolAuthError) as ctx_bytes:
            ka.parse_kpol_auth(source, config=cfg_bytes)
        self.assertEqual(ctx_bytes.exception.diagnostic.code, "KPOL-AUTH-U07")

        # Explicit "codepoints" accepts 9 <= 16
        cfg_cp = ka.AuthFrontendConfig(name_length_unit="codepoints")
        prog_cp = ka.parse_kpol_auth(source, config=cfg_cp)
        self.assertEqual(prog_cp.diagnostics, ())
        self.assertIsInstance(prog_cp.items[0], ka.CallOrConstructCST)

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

        for bad_def in ("Def(1, 0, 1)", "Def(1, 0, 0, 0, 0, 0, 0, 0, 1)"):
            with self.subTest(bad_def=bad_def):
                with self.assertRaises(ka.KpolAuthError) as ctx_width:
                    ka.parse_kpol_auth(bad_def)
                self.assertEqual(ctx_width.exception.diagnostic.code, "KPOL-AUTH-SYNTAX-04")

    def test_mutant_controls_catch_lexer_cst_and_uncertainty_defects(self) -> None:
        cst_mod = sys.modules["kpol_auth.cst"]
        lexer_mod = sys.modules["kpol_auth.lexer"]

        # Mutant 1: CST treats unary '•' as valid 'not' instead of rejecting with SYNTAX-03
        orig_parse_primary = cst_mod._Parser.parse_primary

        def mutant_dot_as_not(parser_self):
            tok = parser_self.peek()
            if tok is not None and tok.kind == "SUBSCRIPTION_SEQ":
                dot_tok = parser_self.advance()
                operand = orig_parse_primary(parser_self)
                return ka.ParamCST(span=dot_tok.span, at_token=dot_tok, target=operand)
            return orig_parse_primary(parser_self)

        with mock.patch.object(cst_mod._Parser, "parse_primary", mutant_dot_as_not):
            with self.assertRaises(AssertionError):
                with self.assertRaises(ka.KpolAuthError):
                    ka.parse_kpol_auth("• Flag")

        # Mutant 2: CST skips bracket-pair matching check
        with mock.patch.dict(cst_mod.BRACKET_PAIRS, {"{": ")"}):
            with self.assertRaises(AssertionError):
                with self.assertRaises(ka.KpolAuthError):
                    ka.parse_kpol_auth("{ A )")

        # Mutant 3: Uncertainty gate silently ignores U05 instead of raising/recording
        def mutant_silent_uncertainty(*args, **kwargs):
            return None

        with mock.patch.object(lexer_mod, "emit_uncertainty", mutant_silent_uncertainty):
            with self.assertRaises(AssertionError):
                with self.assertRaises(ka.KpolAuthError):
                    ka.parse_kpol_auth("#legacy")


if __name__ == "__main__":
    unittest.main()
