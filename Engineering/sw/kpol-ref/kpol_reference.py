"""Reference parser, type checker, and interpreter for the KPOL v0.1 draft."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import math
import secrets
import struct
from typing import Any, Iterable


class KpolError(Exception):
    """A source, type, contract, or execution error."""


class _Unknown:
    def __repr__(self) -> str:
        return "Unknown"


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i, line, column = 0, 1, 1

    def advance(text: str) -> None:
        nonlocal line, column
        count = text.count("\n")
        if count:
            line += count
            column = len(text.rsplit("\n", 1)[-1]) + 1
        else:
            column += len(text)

    aliases = {
        "<-": "ALIAS_WRITE",
        "←": "ALIAS_WRITE",
        "->": "ALIAS_READ",
        "→": "ALIAS_READ",
        "(*)": "ALIAS_PHASE",
        "•": "ALIAS_PHASE",
    }
    operators = ("==", "!=", "<=", ">=", ":=")

    while i < len(source):
        ch = source[i]
        if ch.isspace():
            advance(ch)
            i += 1
            continue
        if source.startswith("#", i) or source.startswith("//", i):
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
            advance(source[i:end])
            i = end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            if end < 0:
                raise KpolError(f"{line}:{column}: unterminated block comment")
            end += 2
            advance(source[i:end])
            i = end
            continue
        alias = next((a for a in ("(*)", "<-", "->", "←", "→", "•")
                      if source.startswith(a, i)), None)
        if alias:
            tokens.append(Token(aliases[alias], aliases[alias], line, column))
            advance(alias)
            i += len(alias)
            continue
        operator = next((op for op in operators if source.startswith(op, i)), None)
        if operator:
            tokens.append(Token("OP", operator, line, column))
            advance(operator)
            i += len(operator)
            continue
        if ch in "{}()<>:,;=+-*/":
            kind = "OP" if ch in "<>+-*/" else "PUNCT"
            tokens.append(Token(kind, ch, line, column))
            advance(ch)
            i += 1
            continue
        if ch.isdigit():
            start = i
            while i < len(source) and source[i].isdigit():
                i += 1
            if i < len(source) and source[i] == ".":
                i += 1
                if i == len(source) or not source[i].isdigit():
                    raise KpolError(f"{line}:{column}: malformed numeric literal")
                while i < len(source) and source[i].isdigit():
                    i += 1
            value = source[start:i]
            tokens.append(Token("NUMBER", value, line, column))
            advance(value)
            continue
        if ch == "_" or ch.isalpha():
            start = i
            while i < len(source) and (source[i] == "_" or source[i].isalnum()):
                i += 1
            value = source[start:i]
            tokens.append(Token("ID", value, line, column))
            advance(value)
            continue
        raise KpolError(f"{line}:{column}: unexpected character {ch!r}")

    tokens.append(Token("EOF", "", line, column))
    return tokens


@dataclass(frozen=True)
class Expr:
    pass


@dataclass(frozen=True)
class Literal(Expr):
    value: Any


@dataclass(frozen=True)
class Name(Expr):
    value: str


@dataclass(frozen=True)
class Unary(Expr):
    operator: str
    operand: Expr


@dataclass(frozen=True)
class Binary(Expr):
    operator: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Call(Expr):
    name: str
    arguments: tuple[Expr, ...]


@dataclass(frozen=True)
class TypeRef:
    name: str
    unit: str | None = None


@dataclass(frozen=True)
class Requirement:
    kind: str
    name: str
    event: str | None
    target: str | None
    expression: Expr


@dataclass(frozen=True)
class EventDecl:
    name: str
    parameters: tuple[tuple[str, TypeRef], ...]


@dataclass(frozen=True)
class StateDecl:
    name: str
    type_ref: TypeRef
    initial: Expr


@dataclass(frozen=True)
class SetAction:
    name: str
    expression: Expr


@dataclass(frozen=True)
class Rule:
    name: str
    event: str
    reject: bool
    watch: tuple[str, ...]
    guard: Expr
    covers: str | None
    actions: tuple[SetAction, ...]


@dataclass(frozen=True)
class StepAction:
    event_name: str
    arguments: tuple[tuple[str, Expr], ...]


@dataclass(frozen=True)
class ExpectCheck:
    expression: Expr


@dataclass(frozen=True)
class AssertPropertyDecl:
    name: str
    event: str
    guard: Expr
    expectation: Expr


@dataclass(frozen=True)
class ScenarioDecl:
    name: str
    steps: tuple[StepAction | ExpectCheck, ...]


ProofItem = AssertPropertyDecl | ScenarioDecl


@dataclass(frozen=True)
class Module:
    name: str
    requirements: tuple[Requirement, ...]
    events: tuple[EventDecl, ...]
    states: tuple[StateDecl, ...]
    rules: tuple[Rule, ...]
    proofs: tuple[ProofItem, ...] = ()
    problem_hash: str | None = None
    solution_hash: str | None = None
    proof_hash: str | None = None
    proof_present: bool = False


@dataclass
class VerificationFailure:
    scenario_or_assert: str
    message: str


@dataclass
class VerificationReport:
    total_checks: int
    passed_checks: int
    failures: list[VerificationFailure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


class Parser:
    _reserved = {
        "Problem", "Solution", "Proof", "Assumptions", "Invariants", "Hazards", "Alerts", "Goals",
        "event", "state", "rule", "on", "reject", "change", "when", "covers",
        "set", "to", "Bool", "Int32", "U32", "U64", "Float", "Pin", "Void",
        "true", "false", "Unknown", "gcd", "and", "or", "not",
        "assert", "scenario", "step", "expect",
        "every", "within", "timeout", "supervise",
        "channel", "Rendezvous", "Stream", "send", "receive",
    }

    def __init__(self, source: str):
        self.tokens = tokenize(source)
        self.index = 0

    @property
    def token(self) -> Token:
        return self.tokens[self.index]

    def fail(self, message: str) -> None:
        token = self.token
        raise KpolError(f"{token.line}:{token.column}: {message}")

    def accept(self, value: str) -> bool:
        if self.token.value == value:
            self.index += 1
            return True
        return False

    def expect(self, value: str) -> None:
        if not self.accept(value):
            self.fail(f"expected {value!r}, got {self.token.value!r}")

    def identifier(self) -> str:
        if self.token.kind != "ID":
            self.fail("expected identifier")
        value = self.token.value
        if value in self._reserved:
            self.fail(f"reserved keyword {value!r} cannot be an identifier")
        self.index += 1
        return value

    def parse(self) -> Module:
        self.expect("Problem")
        name = self.identifier()
        self.expect("{")
        requirements: list[Requirement] = []
        seen_sections: set[str] = set()
        section_kinds = {
            "Assumptions": "Assumption",
            "Invariants": "Invariant",
            "Hazards": "Hazard",
            "Alerts": "Alert",
            "Goals": "Goal",
        }
        while not self.accept("}"):
            if self.token.kind != "ID":
                self.fail("expected Problem section")
            section = self.token.value
            self.index += 1
            if section not in section_kinds:
                self.fail(f"unknown Problem section {section!r}")
            if section in seen_sections:
                self.fail(f"duplicate Problem section {section!r}")
            seen_sections.add(section)
            self.expect("{")
            while not self.accept("}"):
                req_name = self.identifier()
                event = self.identifier() if self.accept("on") else None
                target = self.identifier() if self.accept("to") else None
                self.expect(":")
                expression = self.expression()
                self.expect(";")
                requirements.append(
                    Requirement(section_kinds[section], req_name, event, target, expression)
                )

        self.expect("Solution")
        solution_name = self.identifier()
        if solution_name != name:
            self.fail(f"Problem/Solution name mismatch: {name!r} vs {solution_name!r}")
        self.expect("{")
        events: list[EventDecl] = []
        states: list[StateDecl] = []
        rules: list[Rule] = []
        while not self.accept("}"):
            if self.accept("event"):
                events.append(self.event_decl())
            elif self.accept("state"):
                states.append(self.state_decl())
            elif self.accept("rule"):
                rules.append(self.rule())
            else:
                self.fail("expected event, state, or rule declaration")

        proofs: list[ProofItem] = []
        proof_present = self.accept("Proof")
        if proof_present:
            proof_name = self.identifier()
            if proof_name != name:
                self.fail(f"Problem/Proof name mismatch: {name!r} vs {proof_name!r}")
            self.expect("{")
            while not self.accept("}"):
                if self.accept("assert"):
                    proofs.append(self.assert_decl())
                elif self.accept("scenario"):
                    proofs.append(self.scenario_decl())
                else:
                    self.fail("expected 'assert' or 'scenario' in Proof block")

        if self.token.kind != "EOF":
            self.fail("unexpected text after module")
        return Module(
            name,
            tuple(requirements),
            tuple(events),
            tuple(states),
            tuple(rules),
            tuple(proofs),
            proof_present=proof_present,
        )

    def assert_decl(self) -> AssertPropertyDecl:
        name = self.identifier()
        self.expect("on")
        event = self.identifier()
        has_block = self.accept("{")
        guard: Expr = Literal(True)
        if self.accept("when"):
            guard = self.expression()
        self.expect("expect")
        expectation = self.expression()
        self.expect(";")
        if has_block:
            self.expect("}")
        return AssertPropertyDecl(name, event, guard, expectation)

    def scenario_decl(self) -> ScenarioDecl:
        name = self.identifier()
        self.expect("{")
        steps: list[StepAction | ExpectCheck] = []
        while not self.accept("}"):
            if self.accept("step"):
                event_name = self.identifier()
                self.expect("(")
                args: list[tuple[str, Expr]] = []
                if not self.accept(")"):
                    while True:
                        arg_name = self.identifier()
                        if not (self.accept(":") or self.accept("=")):
                            self.fail("expected ':' or '=' in step argument")
                        arg_val = self.expression()
                        args.append((arg_name, arg_val))
                        if self.accept(")"):
                            break
                        self.expect(",")
                self.expect(";")
                steps.append(StepAction(event_name, tuple(args)))
            elif self.accept("expect"):
                expr = self.expression()
                self.expect(";")
                steps.append(ExpectCheck(expr))
            else:
                self.fail("expected 'step' or 'expect' inside scenario")
        return ScenarioDecl(name, tuple(steps))

    def event_decl(self) -> EventDecl:
        name = self.identifier()
        self.expect("(")
        parameters: list[tuple[str, TypeRef]] = []
        if not self.accept(")"):
            while True:
                parameter = self.identifier()
                self.expect(":")
                parameters.append((parameter, self.type_ref()))
                if self.accept(")"):
                    break
                self.expect(",")
        self.expect(";")
        return EventDecl(name, tuple(parameters))

    def type_ref(self) -> TypeRef:
        if self.token.kind != "ID":
            self.fail("expected type")
        name = self.token.value
        self.index += 1
        if name == "Float":
            self.expect("<")
            unit = self.identifier()
            self.expect(">")
            valid_units = {
                "V", "A", "W", "s", "J", "degC", "bar",
                "ns", "us", "ms", "min", "h", "mm_s", "L_min",
            }
            if unit not in valid_units:
                self.fail(f"unknown unit {unit!r}")
            return TypeRef(name, unit)
        if name == "Pin":
            if self.accept("<"):
                parts = [self.identifier()]
                while self.accept(","):
                    parts.append(self.identifier())
                self.expect(">")
                return TypeRef(name, ",".join(parts))
            return TypeRef(name)
        if name not in {"Bool", "Int32", "U32", "U64"}:
            self.fail(f"unknown type {name!r}")
        return TypeRef(name)

    def state_decl(self) -> StateDecl:
        name = self.identifier()
        self.expect(":")
        type_ref = self.type_ref()
        self.expect("=")
        initial = self.expression()
        self.expect(";")
        return StateDecl(name, type_ref, initial)

    def rule(self) -> Rule:
        name = self.identifier()
        self.expect("on")
        reject = self.accept("reject")
        if self.accept("change"):
            event = "change"
        else:
            event = self.identifier()
        watch: tuple[str, ...] = ()
        if event == "change":
            self.expect("(")
            watched = [self.identifier()]
            while self.accept(","):
                watched.append(self.identifier())
            self.expect(")")
            watch = tuple(watched)
        guard: Expr = Literal(True)
        if self.accept("when"):
            guard = self.expression()
        covers = self.identifier() if self.accept("covers") else None
        self.expect("{")
        actions: list[SetAction] = []
        while not self.accept("}"):
            self.expect("set")
            target = self.identifier()
            self.expect(":=")
            actions.append(SetAction(target, self.expression()))
            self.expect(";")
        return Rule(name, event, reject, watch, guard, covers, tuple(actions))

    _precedence = {
        "or": 1,
        "and": 2,
        "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
        "+": 4, "-": 4,
        "*": 5, "/": 5,
    }

    def expression(self, minimum: int = 0) -> Expr:
        token = self.token
        if token.value in {"not", "-"} or token.kind == "ALIAS_PHASE" or token.value == "•":
            self.index += 1
            op_name = "not" if (token.kind == "ALIAS_PHASE" or token.value == "•") else token.value
            left: Expr = Unary(op_name, self.expression(6))
        elif token.value == "(":
            self.index += 1
            left = self.expression()
            self.expect(")")
        elif token.kind == "NUMBER":
            self.index += 1
            try:
                value = Decimal(token.value) if "." in token.value else int(token.value)
            except InvalidOperation as error:
                raise KpolError(f"{token.line}:{token.column}: invalid number") from error
            left = Literal(value)
        elif token.kind == "ID":
            self.index += 1
            if token.value == "true":
                left = Literal(True)
            elif token.value == "false":
                left = Literal(False)
            elif token.value == "Unknown":
                left = Literal(UNKNOWN)
            elif token.value == "gcd" and self.accept("("):
                first = self.expression()
                self.expect(",")
                second = self.expression()
                self.expect(")")
                left = Call("gcd", (first, second))
            else:
                left = Name(token.value)
        else:
            self.fail("expected expression")

        while True:
            operator = self.token.value
            precedence = self._precedence.get(operator)
            if precedence is None or precedence < minimum:
                break
            self.index += 1
            right = self.expression(precedence + 1)
            left = Binary(operator, left, right)
        return left


@dataclass(frozen=True)
class KType:
    name: str
    unit: str | None = None


BOOL = KType("Bool")
UNKNOWN_TYPE = KType("Unknown")
NUMBER = KType("Number")
_UNIT_PRODUCTS = {
    ("V", "A"): "W",
    ("A", "V"): "W",
    ("W", "s"): "J",
    ("s", "W"): "J",
}


def as_ktype(type_ref: TypeRef) -> KType:
    return KType(type_ref.name, type_ref.unit)


def _is_numeric(value: KType) -> bool:
    return value.name in {"Number", "Int32", "U32", "U64", "Float"}


def _compatible(expected: KType, actual: KType) -> bool:
    if actual.name == "Unknown":
        return True
    if expected == actual:
        return True
    if actual.name == "Number" and _is_numeric(expected):
        return True
    if expected.name == "Float" and actual.name == "Float":
        return expected.unit == actual.unit
    if expected.name == "Pin" and (actual.name in {"Number", "Int32", "Bool"} or _is_numeric(actual)):
        return True
    return False


def _constant_number(expression: Expr) -> int | Decimal | None:
    if isinstance(expression, Literal) and type(expression.value) in {int, Decimal}:
        return expression.value
    if isinstance(expression, Unary) and expression.operator == "-":
        value = _constant_number(expression.operand)
        return -value if value is not None else None
    if isinstance(expression, Binary) and expression.operator in {"+", "-", "*"}:
        left = _constant_number(expression.left)
        right = _constant_number(expression.right)
        if left is None or right is None:
            return None
        if expression.operator == "+":
            return left + right
        if expression.operator == "-":
            return left - right
        return left * right
    return None


def _compatible_expression(expected: KType, actual: KType, expression: Expr) -> bool:
    if actual.name == "Number" and expected.name in {"U64", "U32", "Int32"}:
        value = _constant_number(expression)
        if value is not None:
            if value != int(value):
                return False
            if expected.name in {"U32", "U64"}:
                bits = 32 if expected.name == "U32" else 64
                lower, upper = 0, 2**bits - 1
            else:
                lower, upper = -(2**31), 2**31 - 1
            return lower <= int(value) <= upper
    if expected.name == "Pin" and actual.name == "Number":
        value = _constant_number(expression)
        if value is not None:
            return value in (0, 1)
    return _compatible(expected, actual)


def _join_numeric(left: KType, right: KType) -> KType:
    if left.name == "Unknown":
        return right
    if right.name == "Unknown":
        return left
    if left.name == "Number":
        return right
    if right.name == "Number":
        return left
    if left != right:
        raise KpolError(f"incompatible numeric types: {left} and {right}")
    return left


def infer(expression: Expr, environment: dict[str, KType]) -> KType:
    if isinstance(expression, Literal):
        if expression.value is UNKNOWN:
            return UNKNOWN_TYPE
        if isinstance(expression.value, bool):
            return BOOL
        return NUMBER
    if isinstance(expression, Name):
        try:
            return environment[expression.value]
        except KeyError as error:
            raise KpolError(f"unresolved name {expression.value!r}") from error
    if isinstance(expression, Call):
        if expression.name != "gcd" or len(expression.arguments) != 2:
            raise KpolError(f"unsupported function {expression.name!r}")
        argument_types = [infer(arg, environment) for arg in expression.arguments]
        if any(
            not _compatible_expression(KType("U64"), typ, argument)
            for typ, argument in zip(argument_types, expression.arguments)
        ):
            raise KpolError("gcd arguments must be U64")
        return KType("U64")
    if isinstance(expression, Unary):
        operand = infer(expression.operand, environment)
        if expression.operator == "not":
            if operand not in {BOOL, UNKNOWN_TYPE}:
                raise KpolError("not requires Bool")
            return BOOL
        if expression.operator == "-" and _is_numeric(operand):
            return operand
        raise KpolError(f"invalid unary operation {expression.operator!r}")
    if not isinstance(expression, Binary):
        raise KpolError("invalid expression node")

    left = infer(expression.left, environment)
    right = infer(expression.right, environment)
    op = expression.operator
    if op in {"and", "or"}:
        if left not in {BOOL, UNKNOWN_TYPE} or right not in {BOOL, UNKNOWN_TYPE}:
            raise KpolError(f"{op} requires Bool operands")
        return BOOL
    if op in {"==", "!=", "<", "<=", ">", ">="}:
        if left.name == "Unknown" or right.name == "Unknown":
            return BOOL
        if not (
            _compatible_expression(left, right, expression.right)
            or _compatible_expression(right, left, expression.left)
        ):
            raise KpolError(f"incompatible comparison: {left} {op} {right}")
        if op not in {"==", "!="} and not (_is_numeric(left) and _is_numeric(right)):
            raise KpolError(f"{op} requires numeric operands")
        return BOOL
    if op in {"+", "-"}:
        if not (_is_numeric(left) and _is_numeric(right)):
            raise KpolError(f"{op} requires numeric operands")
        if left.name in {"U64", "U32", "Int32"} and not _compatible_expression(
            left, right, expression.right
        ):
            raise KpolError(f"{op} has an invalid integer literal")
        if right.name in {"U64", "U32", "Int32"} and not _compatible_expression(
            right, left, expression.left
        ):
            raise KpolError(f"{op} has an invalid integer literal")
        if (left.name == "Float" and left.unit == "degC") or (
            right.name == "Float" and right.unit == "degC"
        ):
            raise KpolError("arithmetic on absolute degC values is unsupported")
        return _join_numeric(left, right)
    if op == "*":
        if not (_is_numeric(left) and _is_numeric(right)):
            raise KpolError("* requires numeric operands")
        if left.name in {"U64", "U32", "Int32"} and not _compatible_expression(
            left, right, expression.right
        ):
            raise KpolError("* has an invalid integer literal")
        if right.name in {"U64", "U32", "Int32"} and not _compatible_expression(
            right, left, expression.left
        ):
            raise KpolError("* has an invalid integer literal")
        if (left.name == "Float" and left.unit == "degC") or (
            right.name == "Float" and right.unit == "degC"
        ):
            raise KpolError("arithmetic on absolute degC values is unsupported")
        if left.name == "Number":
            return right
        if right.name == "Number":
            return left
        if left.name == "Float" and right.name == "Float":
            unit = _UNIT_PRODUCTS.get((left.unit or "", right.unit or ""))
            if unit is None:
                raise KpolError(f"unsupported unit product: {left.unit}*{right.unit}")
            return KType("Float", unit)
        return _join_numeric(left, right)
    if op == "/":
        if not (_is_numeric(left) and _is_numeric(right)):
            raise KpolError("/ requires numeric operands")
        if left.name == "Float" and left.unit == "degC":
            raise KpolError("arithmetic on absolute degC values is unsupported")
        if right.name == "Number":
            return left
        if left.name == right.name == "Float" and left.unit == right.unit:
            return NUMBER
        raise KpolError(f"unsupported unit division: {left}/{right}")
    raise KpolError(f"unsupported operator {op!r}")


def check_module(module: Module) -> None:
    if len({event.name for event in module.events}) != len(module.events):
        raise KpolError("duplicate event declaration")
    if len({state.name for state in module.states}) != len(module.states):
        raise KpolError("duplicate state declaration")
    if len({rule.name for rule in module.rules}) != len(module.rules):
        raise KpolError("duplicate rule declaration")

    event_map = {event.name: event for event in module.events}
    state_map = {state.name: state for state in module.states}
    state_types = {name: as_ktype(state.type_ref) for name, state in state_map.items()}

    for event in module.events:
        if event.name == "change":
            raise KpolError("'change' is reserved for generated state-change events")
        names = [name for name, _ in event.parameters]
        if len(set(names)) != len(names) or set(names) & set(state_types):
            raise KpolError(f"duplicate/colliding parameters in event {event.name!r}")

    init_types: dict[str, KType] = {}
    for state in module.states:
        actual = infer(state.initial, init_types)
        expected = as_ktype(state.type_ref)
        if not _compatible_expression(expected, actual, state.initial):
            raise KpolError(f"initial value of {state.name!r} has type {actual}, expected {expected}")
        init_types[state.name] = expected

    requirements = {(req.kind, req.name): req for req in module.requirements}
    if len(requirements) != len(module.requirements):
        raise KpolError("duplicate requirement name within a contract kind")
    for req in module.requirements:
        if req.event is not None and req.event not in event_map:
            raise KpolError(f"requirement {req.name!r} references unknown event {req.event!r}")
        if req.kind in {"Invariant", "Goal"} and req.event is not None:
            raise KpolError(f"{req.kind} {req.name!r} must be a state-only predicate")
        if req.kind in {"Hazard", "Alert"} and req.event is None:
            raise KpolError(f"{req.kind} {req.name!r} must be scoped to an event")
        if req.target is not None and req.kind != "Hazard":
            raise KpolError(f"only Hazard may declare a response target ({req.name!r})")
        if req.kind == "Hazard":
            if req.target is None:
                raise KpolError(f"Hazard {req.name!r} must declare a response target")
            if req.target not in state_types or state_types[req.target] != BOOL:
                raise KpolError(f"Hazard {req.name!r} target must be a declared Bool state")
        context = dict(state_types)
        if req.event:
            context.update({name: as_ktype(typ) for name, typ in event_map[req.event].parameters})
        if infer(req.expression, context) != BOOL:
            raise KpolError(f"{req.kind} {req.name!r} must have type Bool")

    covered: set[str] = set()
    for rule in module.rules:
        if rule.event == "change":
            if rule.reject or not rule.watch:
                raise KpolError(f"invalid change rule {rule.name!r}")
            if any(name not in state_types for name in rule.watch):
                raise KpolError(f"change rule {rule.name!r} watches unknown state")
        elif rule.event not in event_map:
            raise KpolError(f"rule {rule.name!r} references unknown event {rule.event!r}")
        context = dict(state_types)
        if rule.event in event_map:
            context.update({name: as_ktype(typ) for name, typ in event_map[rule.event].parameters})
        if infer(rule.guard, context) != BOOL:
            raise KpolError(f"guard of rule {rule.name!r} must have type Bool")
        for action in rule.actions:
            if action.name not in state_types:
                raise KpolError(f"rule {rule.name!r} writes undeclared state {action.name!r}")
            actual = infer(action.expression, context)
            expected = state_types[action.name]
            if not _compatible_expression(expected, actual, action.expression):
                raise KpolError(
                    f"assignment to {action.name!r} has type {actual}, expected {expected}"
                )
        if rule.covers:
            matches = [
                req for req in module.requirements
                if req.kind == "Hazard" and req.name == rule.covers
            ]
            if len(matches) != 1:
                raise KpolError(f"rule {rule.name!r} covers unknown hazard {rule.covers!r}")
            hazard = matches[0]
            if hazard.event != rule.event or hazard.expression != rule.guard:
                raise KpolError(f"rule {rule.name!r} does not exactly implement hazard guard")
            true_target_write = any(
                action.name == hazard.target
                and isinstance(action.expression, Literal)
                and action.expression.value is True
                for action in rule.actions
            )
            if not true_target_write:
                raise KpolError(
                    f"hazard rule {rule.name!r} must set target {hazard.target!r} to true"
                )
            covered.add(hazard.name)

    missing = {
        req.name for req in module.requirements
        if req.kind == "Hazard" and req.name not in covered
    }
    if missing:
        raise KpolError(f"hazards without a covers rule: {', '.join(sorted(missing))}")

    for proof in module.proofs:
        if isinstance(proof, AssertPropertyDecl):
            if proof.event not in event_map:
                raise KpolError(f"assert {proof.name!r} references unknown event {proof.event!r}")
            context = dict(state_types)
            context.update({name: as_ktype(typ) for name, typ in event_map[proof.event].parameters})
            if infer(proof.guard, context) != BOOL:
                raise KpolError(f"guard of assert {proof.name!r} must have type Bool")
            if infer(proof.expectation, context) != BOOL:
                raise KpolError(f"expectation of assert {proof.name!r} must have type Bool")
        elif isinstance(proof, ScenarioDecl):
            context = dict(state_types)
            for step in proof.steps:
                if isinstance(step, StepAction):
                    if step.event_name not in event_map:
                        raise KpolError(
                            f"scenario {proof.name!r} references unknown event {step.event_name!r}"
                        )
                    decl = event_map[step.event_name]
                    param_dict = {p_name: as_ktype(p_type) for p_name, p_type in decl.parameters}
                    arg_dict = dict(step.arguments)
                    if set(arg_dict) != set(param_dict):
                        raise KpolError(
                            f"scenario {proof.name!r} step {step.event_name!r} arguments do not match event parameters"
                        )
                    for p_name, p_type in param_dict.items():
                        arg_expr = arg_dict[p_name]
                        arg_type = infer(arg_expr, context)
                        if not _compatible_expression(p_type, arg_type, arg_expr):
                            raise KpolError(
                                f"scenario {proof.name!r} argument {p_name!r} type {arg_type} incompatible with {p_type}"
                            )
                elif isinstance(step, ExpectCheck):
                    if infer(step.expression, context) != BOOL:
                        raise KpolError(f"scenario {proof.name!r} expect expression must have type Bool")


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _normalize(value: Any, type_ref: TypeRef, allow_unknown: bool = False) -> Any:
    if value is UNKNOWN:
        if allow_unknown:
            return value
        raise KpolError("Unknown cannot be stored in a state")
    if type_ref.name == "Bool":
        if isinstance(value, bool):
            return value
        raise KpolError("expected Bool value")
    if type_ref.name in {"U32", "U64"}:
        bits = 32 if type_ref.name == "U32" else 64
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**bits:
            raise KpolError(f"expected {type_ref.name} value")
        return value
    if type_ref.name == "Int32":
        if isinstance(value, bool) or not isinstance(value, int) or not -(2**31) <= value < 2**31:
            raise KpolError("expected Int32 value")
        return value
    if type_ref.name == "Float":
        try:
            result = _decimal(value)
        except (InvalidOperation, ValueError) as error:
            raise KpolError("expected finite Float value") from error
        if not result.is_finite():
            raise KpolError("expected finite Float value")
        return result
    if type_ref.name == "Pin":
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, int) and value in (0, 1):
            return value
        raise KpolError("expected Pin value (0, 1, or Bool)")
    raise KpolError(f"unsupported runtime type {type_ref.name!r}")


def _eval(expression: Expr, environment: dict[str, Any]) -> Any:
    if isinstance(expression, Literal):
        return expression.value
    if isinstance(expression, Name):
        try:
            return environment[expression.value]
        except KeyError as error:
            raise KpolError(f"unresolved runtime name {expression.value!r}") from error
    if isinstance(expression, Call):
        values = [_eval(arg, environment) for arg in expression.arguments]
        if expression.name == "gcd" and len(values) == 2:
            if any(value is UNKNOWN for value in values):
                return UNKNOWN
            return math.gcd(int(values[0]), int(values[1]))
        raise KpolError(f"unsupported function {expression.name!r}")
    if isinstance(expression, Unary):
        value = _eval(expression.operand, environment)
        if expression.operator == "not":
            return UNKNOWN if value is UNKNOWN else not value
        if expression.operator == "-":
            return UNKNOWN if value is UNKNOWN else -value
        raise KpolError(f"unsupported unary operator {expression.operator!r}")
    if not isinstance(expression, Binary):
        raise KpolError("invalid expression node")
    op = expression.operator
    if op == "and":
        left = _eval(expression.left, environment)
        if left is False:
            return False
        right = _eval(expression.right, environment)
        if right is False:
            return False
        return True if left is True and right is True else UNKNOWN
    if op == "or":
        left = _eval(expression.left, environment)
        if left is True:
            return True
        right = _eval(expression.right, environment)
        if right is True:
            return True
        return False if left is False and right is False else UNKNOWN
    left = _eval(expression.left, environment)
    right = _eval(expression.right, environment)
    if op in {"==", "!="} and (left is UNKNOWN or right is UNKNOWN):
        equal = left is UNKNOWN and right is UNKNOWN
        return equal if op == "==" else not equal
    if left is UNKNOWN or right is UNKNOWN:
        return UNKNOWN
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        if right == 0:
            raise KpolError("division by zero")
        return left / right
    raise KpolError(f"unsupported operator {op!r}")


@dataclass(frozen=True)
class EventInput:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    state: dict[str, Any]
    rejected: list[str] = field(default_factory=list)
    hazards: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    goal_failures: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    steps: int = 0


class Interpreter:
    def __init__(self, module: Module, initial: dict[str, Any] | None = None, fail_closed_hazards: bool = True):
        check_module(module)
        self.module = module
        self.fail_closed_hazards = fail_closed_hazards
        self.event_map = {event.name: event for event in module.events}
        self.state_types = {state.name: state.type_ref for state in module.states}
        self.change_watches = list(dict.fromkeys(
            rule.watch for rule in module.rules if rule.event == "change"
        ))
        self.state: dict[str, Any] = {}
        initial = initial or {}
        unknown_overrides = set(initial) - set(self.state_types)
        if unknown_overrides:
            raise KpolError(f"unknown initial state: {', '.join(sorted(unknown_overrides))}")
        for state in module.states:
            raw = initial.get(state.name, _eval(state.initial, self.state))
            self.state[state.name] = _normalize(raw, state.type_ref)
        self._check_initial_contracts()

    def _check_initial_contracts(self) -> None:
        for req in self.module.requirements:
            if req.kind not in {"Assumption", "Invariant"} or req.event is not None:
                continue
            if _eval(req.expression, self.state) is not True:
                raise KpolError(f"initial {req.kind} {req.name!r} is not true")

    def run(self, events: Iterable[EventInput] = (), max_events: int = 10000) -> RunResult:
        result = RunResult(dict(self.state))
        queue: list[EventInput] = []
        for watch in self.change_watches:
            queue.append(EventInput("change", {"_watch": watch}))
        queue.extend(events)
        while queue:
            if result.steps >= max_events:
                raise KpolError(f"event limit exceeded ({max_events})")
            event = queue.pop(0)
            result.steps += 1
            if event.name != "change" and event.name not in self.event_map:
                raise KpolError(f"unknown input event {event.name!r}")
            payload = self._validate_payload(event)
            snapshot = dict(self.state)
            environment = {**snapshot, **payload}

            if event.name != "change":
                # Pre-Phase 1: Assumptions (Input Boundary Validation)
                assumptions = [
                    req for req in self.module.requirements
                    if req.kind == "Assumption" and req.event == event.name
                ]
                if any(_eval(req.expression, environment) is not True for req in assumptions):
                    # Also observe hazards and alerts for telemetry diagnostics
                    for req in self.module.requirements:
                        if req.kind == "Hazard" and req.event == event.name:
                            observed = _eval(req.expression, environment)
                            if observed is True:
                                result.hazards.append(req.name)
                            elif observed is UNKNOWN:
                                result.diagnostics.append(f"UnknownHazard:{req.name}")
                        elif req.kind == "Alert" and req.event == event.name:
                            observed = _eval(req.expression, environment)
                            if observed is True:
                                result.alerts.append(req.name)
                    result.rejected.append(f"RejectedInput:{event.name}")
                    self._execute(event, payload, result, rejecting=True, queue=queue)
                    continue

                # Pre-Phase 2: Hazards (Fail-Closed Safety Interlock)
                hazard_blocked = False
                for req in self.module.requirements:
                    if req.kind == "Hazard" and req.event == event.name:
                        observed = _eval(req.expression, environment)
                        if observed is True:
                            result.hazards.append(req.name)
                            if self.fail_closed_hazards:
                                hazard_blocked = True
                                result.rejected.append(f"RejectedHazard:{req.name}")
                        elif observed is UNKNOWN:
                            result.diagnostics.append(f"UnknownHazard:{req.name}")
                            if self.fail_closed_hazards:
                                hazard_blocked = True
                                result.rejected.append(f"RejectedHazardUnknown:{req.name}")
                    elif req.kind == "Alert" and req.event == event.name:
                        observed = _eval(req.expression, environment)
                        if observed is True:
                            result.alerts.append(req.name)
                        elif observed is UNKNOWN:
                            result.diagnostics.append(f"UnknownAlert:{req.name}")

                if hazard_blocked:
                    self._execute(event, payload, result, rejecting=True, queue=queue)
                    continue

            self._execute(event, payload, result, rejecting=False, queue=queue)

        for req in self.module.requirements:
            if req.kind == "Goal" and _eval(req.expression, self.state) is not True:
                result.goal_failures.append(req.name)
        result.state = dict(self.state)
        return result

    def _validate_payload(self, event: EventInput) -> dict[str, Any]:
        if event.name == "change":
            watch = event.payload.get("_watch")
            if set(event.payload) != {"_watch"} or watch not in self.change_watches:
                raise KpolError("invalid internal change event")
            return {"_watch": watch}
        declaration = self.event_map[event.name]
        expected = {name: typ for name, typ in declaration.parameters}
        if set(event.payload) != set(expected):
            raise KpolError(
                f"payload for {event.name!r} must contain exactly {', '.join(expected)}"
            )
        return {
            name: _normalize(event.payload[name], typ, allow_unknown=True)
            for name, typ in expected.items()
        }

    def _execute(
        self,
        event: EventInput,
        payload: dict[str, Any],
        result: RunResult,
        rejecting: bool,
        queue: list[EventInput],
    ) -> None:
        snapshot = dict(self.state)
        environment = {**snapshot, **payload}
        selected = [
            rule for rule in self.module.rules
            if rule.event == event.name and rule.reject == rejecting
        ]
        if event.name == "change":
            selected = [
                rule for rule in self.module.rules
                if rule.event == "change"
                and not rule.reject
                and rule.watch == payload["_watch"]
            ]
        writes: dict[str, Any] = {}
        for rule in selected:
            guard = _eval(rule.guard, environment)
            if guard is UNKNOWN:
                result.diagnostics.append(f"UnknownGuard:{rule.name}")
                return
            if guard is not True:
                continue
            for action in rule.actions:
                value = _eval(action.expression, environment)
                if value is UNKNOWN:
                    result.diagnostics.append(f"UnknownWrite:{rule.name}:{action.name}")
                    return
                value = _normalize(value, self.state_types[action.name])
                if action.name in writes and writes[action.name] != value:
                    result.diagnostics.append(f"ConflictingWrites:{action.name}")
                    return
                writes[action.name] = value

        # If transaction was rejected due to hazard, latch hazard target states
        if rejecting:
            for req in self.module.requirements:
                if req.kind == "Hazard" and req.event == event.name and req.target:
                    if req.name in result.hazards and req.target not in writes:
                        writes[req.target] = True

        candidate = {**snapshot, **writes}
        for req in self.module.requirements:
            if req.kind == "Invariant" and _eval(req.expression, candidate) is not True:
                result.diagnostics.append(f"InvariantViolation:{req.name}")
                return

        changed = {name for name in writes if candidate[name] != snapshot[name]}
        self.state = candidate
        for watch in self.change_watches:
            if changed.intersection(watch):
                queue.append(EventInput("change", {"_watch": watch}))

    def verify(self) -> VerificationReport:
        """Verifies this module's declared Proof block."""
        return verify_module(self.module, fail_closed_hazards=self.fail_closed_hazards)


def verify_module(module: Module, fail_closed_hazards: bool = True) -> VerificationReport:
    """Verifies a KPOL module using its declared Proof block (scenarios and asserts)."""
    failures: list[VerificationFailure] = []
    total_checks = 0
    passed_checks = 0

    asserts = [p for p in module.proofs if isinstance(p, AssertPropertyDecl)]
    scenarios = [p for p in module.proofs if isinstance(p, ScenarioDecl)]

    for scenario in scenarios:
        interp = Interpreter(module, fail_closed_hazards=fail_closed_hazards)
        for idx, item in enumerate(scenario.steps, 1):
            if isinstance(item, StepAction):
                payload: dict[str, Any] = {}
                for arg_name, expr in item.arguments:
                    val = _eval(expr, interp.state)
                    payload[arg_name] = val

                pre_env = {**interp.state, **payload}
                active_asserts = []
                for prop in asserts:
                    if prop.event == item.event_name:
                        total_checks += 1
                        guard_val = _eval(prop.guard, pre_env)
                        if guard_val is True:
                            active_asserts.append(prop)
                        else:
                            passed_checks += 1

                interp.run([EventInput(item.event_name, payload)])

                post_env = {**interp.state, **payload}
                for prop in active_asserts:
                    expect_val = _eval(prop.expectation, post_env)
                    if expect_val is True:
                        passed_checks += 1
                    else:
                        failures.append(
                            VerificationFailure(
                                prop.name,
                                f"Assert violated in scenario {scenario.name} step {idx} ({item.event_name})",
                            )
                        )

            elif isinstance(item, ExpectCheck):
                total_checks += 1
                res = _eval(item.expression, interp.state)
                if res is True:
                    passed_checks += 1
                else:
                    failures.append(
                        VerificationFailure(
                            scenario.name,
                            f"Expectation failed at step {idx}: state={interp.state}",
                        )
                    )

    return VerificationReport(
        total_checks=total_checks,
        passed_checks=passed_checks,
        failures=failures,
    )


def parse_module(source: str) -> Module:
    module = Parser(source).parse()
    check_module(module)
    return module


def _reject_unsupported_u32_codegen(module: Module) -> None:
    if any(state.type_ref.name == "U32" for state in module.states) or any(
        typ.name == "U32" for event in module.events for _, typ in event.parameters
    ):
        raise KpolError("U32 code generation is not supported; use the reference interpreter")


def compile_bram_image(module: Module, acl_table: dict[str, int] | None = None) -> bytes:
    """Compiles a KPOL module into a 1024-byte BRAM descriptor binary image (64 concepts x 16 bytes)."""
    _reject_unsupported_u32_codegen(module)
    violations = check_module_security_acl(module, acl_table)
    if violations:
        raise KpolError(f"Security ACL violation: {'; '.join(violations)}")
    if len(module.rules) > 16:
        raise KpolError(f"Maximum 16 rules supported for BRAM descriptor subscription mask, got {len(module.rules)}")
    type_ids = {"Int32": 0, "Float": 1, "Bool": 2, "U64": 3, "Pin": 4}
    descriptors: list[bytes] = []

    for cid, state in enumerate(module.states):
        if cid >= 64:
            raise KpolError("Maximum number of concepts (64) exceeded for BRAM descriptor table")
        init_val = _eval(state.initial, {})
        if isinstance(init_val, bool):
            val_lo = 1 if init_val else 0
            val_hi = 0
            int_for_pred = val_lo
        elif isinstance(init_val, (int, Decimal)):
            v_int = int(init_val)
            val_lo = v_int & 0xFFFFFFFF
            val_hi = (v_int >> 32) & 0xFFFFFFFF
            int_for_pred = v_int
        else:
            val_lo, val_hi, int_for_pred = 0, 0, 0

        type_id = type_ids.get(state.type_ref.name, 0)
        size_mask = 4  # 4 bytes
        init_flag = 1
        big_dot_flag = 1
        sub_mask = 0
        for r_idx, rule in enumerate(module.rules[:16]):
            if any(action.name == state.name for action in rule.actions):
                sub_mask |= (1 << r_idx)

        meta_word = (
            ((sub_mask & 0xFFFF) << 16)
            | ((big_dot_flag & 1) << 9)
            | ((init_flag & 1) << 8)
            | ((size_mask & 0x0F) << 4)
            | (type_id & 0x0F)
        )

        status_word = 0
        if int_for_pred == 0:
            status_word |= (1 << 0)  # Null
        if int_for_pred > 0:
            status_word |= (1 << 1)  # Positive
        if int_for_pred < 0:
            status_word |= (1 << 2)  # Negative
        if int_for_pred % 2 == 0:
            status_word |= (1 << 3)  # Even
        else:
            status_word |= (1 << 4)  # Uneven

        descriptors.append(struct.pack("<IIII", val_lo, val_hi, meta_word, status_word))

    # Fill remaining slots up to 64
    empty_slot = struct.pack("<IIII", 0, 0, 0, 0)
    while len(descriptors) < 64:
        descriptors.append(empty_slot)

    return b"".join(descriptors)


# ============================================================================
# Concept Micro-Engine (CME) BRAM Microcode Opcodes & Compiler
# ============================================================================

CME_PRED_NOP = 0x00
CME_PRED_EQ = 0x01
CME_PRED_NEQ = 0x02
CME_PRED_GT = 0x03
CME_PRED_LT = 0x04
CME_PRED_RANGE = 0x05
CME_PRED_BITMASK = 0x06

CME_ACT_ASSIGN = 0x00
CME_ACT_INC = 0x01
CME_ACT_DEC = 0x02
CME_ACT_ADD = 0x03
CME_ACT_SUB = 0x04

CME_GUARD_ASSUMPTION_EN = 0x01
CME_GUARD_INVARIANT_EN = 0x02
CME_GUARD_HAZARD_EN = 0x04
CME_GUARD_INVERT_ASSUMPTION = 0x08  # Big Dot: • = ¬


@dataclass
class ConceptMicroDescriptor:
    """16-byte BRAM descriptor for the Universal Concept Micro-Engine (km_concept_micro_engine)."""
    cid: int
    name: str = ""
    current_state: int = 0
    operand_val: int = 0
    pred_opcode: int = CME_PRED_NOP
    guard_flags: int = 0
    hazard_limit: int = 0
    action_opcode: int = CME_ACT_ASSIGN
    subscriber_cid: int = 0

    def pack(self) -> bytes:
        word0 = self.current_state & 0xFFFFFFFF
        word1 = self.operand_val & 0xFFFFFFFF
        word2 = (
            (self.pred_opcode & 0xFF)
            | ((self.guard_flags & 0xFF) << 8)
            | ((self.hazard_limit & 0xFF) << 16)
            | ((self.action_opcode & 0xFF) << 24)
        )
        word3 = self.subscriber_cid & 0xFFFFFFFF
        return struct.pack("<IIII", word0, word1, word2, word3)


def disassemble_concept_microcode(data: bytes) -> list[ConceptMicroDescriptor]:
    """Unpacks a 1024-byte BRAM microcode image into a list of 64 ConceptMicroDescriptors."""
    if len(data) != 1024:
        raise KpolError(f"Expected exactly 1024 bytes for CME microcode, got {len(data)}")
    descriptors: list[ConceptMicroDescriptor] = []
    for cid in range(64):
        offset = cid * 16
        w0, w1, w2, w3 = struct.unpack_from("<IIII", data, offset)
        pred_op = w2 & 0xFF
        guard_fl = (w2 >> 8) & 0xFF
        haz_lim = (w2 >> 16) & 0xFF
        act_op = (w2 >> 24) & 0xFF
        desc = ConceptMicroDescriptor(
            cid=cid,
            name=f"Concept_{cid}",
            current_state=w0,
            operand_val=w1,
            pred_opcode=pred_op,
            guard_flags=guard_fl,
            hazard_limit=haz_lim,
            action_opcode=act_op,
            subscriber_cid=w3,
        )
        descriptors.append(desc)
    return descriptors


def _compile_cme1_profile(
    module: Module,
    cascade_map: dict[str | int, str | int] | None,
    acl_table: dict[str, int] | None,
) -> bytes:
    try:
        check_module(module)
    except KpolError as error:
        raise KpolError(f"B3-TYPE: module {module.name}: {error}") from error

    def fail(code: str, message: str) -> None:
        raise KpolError(f"{code}: module {module.name}: {message}")

    def integer(expr: Expr, code: str, location: str, minimum: int = -2147483648) -> int:
        if isinstance(expr, Literal) and type(expr.value) is int:
            value = expr.value
        elif (
            isinstance(expr, Unary) and expr.operator == "-"
            and isinstance(expr.operand, Literal) and type(expr.operand.value) is int
        ):
            value = -expr.operand.value
        else:
            fail(code, f"{location}: expected an Int32 literal")
        if not minimum <= value <= 2147483647:
            fail(code, f"{location}: literal outside [{minimum}, 2147483647]")
        return value

    if cascade_map is not None:
        fail("B3-SHAPE", "cascade_map is outside KPOL-CME-1")
    if len(module.states) != 1 or len(module.events) != 1 or len(module.rules) != 1:
        fail("B3-SHAPE", "expected exactly one state, event and rule")
    state, event, rule = module.states[0], module.events[0], module.rules[0]
    if state.type_ref != TypeRef("Int32") or len(event.parameters) != 1:
        fail("B3-SHAPE", f"state {state.name} and event {event.name}: expected Int32 state and one parameter")
    parameter, parameter_type = event.parameters[0]
    if parameter_type != TypeRef("Int32"):
        fail("B3-SHAPE", f"event {event.name}: parameter {parameter} must be Int32")
    initial = integer(state.initial, "B3-SHAPE", f"state {state.name} initial", minimum=0)
    if rule.event != event.name or rule.reject or rule.watch or rule.covers is not None:
        fail("B3-SHAPE", f"rule {rule.name}: expected an ordinary rule on {event.name}")
    if len(rule.actions) != 1 or rule.actions[0].name != state.name:
        fail("B3-SHAPE", f"rule {rule.name}: expected one assignment to {state.name}")
    if (
        len(module.requirements) != 1
        or module.requirements[0].kind != "Invariant"
        or module.requirements[0].event is not None
        or module.requirements[0].target is not None
        or module.requirements[0].expression != Binary(">=", Name(state.name), Literal(0))
    ):
        fail("B3-INVARIANT", f"expected only the invariant {state.name} >= 0")

    action = rule.actions[0].expression
    if not (
        isinstance(action, Binary) and action.operator in {"+", "-"}
        and action.left == Name(state.name)
        and isinstance(action.right, Literal) and type(action.right.value) is int
        and action.right.value == 1
    ):
        fail("B3-ACTION", f"rule {rule.name}: expected {state.name} + 1 or {state.name} - 1")
    action_opcode = CME_ACT_INC if action.operator == "+" else CME_ACT_DEC
    guard = rule.guard
    operand = 0
    if isinstance(guard, Literal) and guard.value is True:
        predicate = CME_PRED_NOP
    elif (
        isinstance(guard, Binary) and guard.operator in {"<", ">", "==", "!="}
        and guard.left == Name(parameter)
    ):
        predicate = {
            "<": CME_PRED_LT, ">": CME_PRED_GT, "==": CME_PRED_EQ, "!=": CME_PRED_NEQ,
        }[guard.operator]
        operand = integer(guard.right, "B3-GUARD", f"rule {rule.name} guard")
    else:
        fail("B3-GUARD", f"rule {rule.name}: expected true or {parameter} compared with an Int32 literal")

    if module.proof_present and not module.proofs:
        fail("B3-PROOF", "Proof must contain at least one scenario")
    for scenario in module.proofs:
        if not isinstance(scenario, ScenarioDecl):
            fail("B3-PROOF", "only scenario is supported, not Proof/assert")
        location = f"scenario {scenario.name}"
        seen_step = False
        expects = 0
        for item in scenario.steps:
            if isinstance(item, StepAction):
                if (
                    item.event_name != event.name or len(item.arguments) != 1
                    or item.arguments[0][0] != parameter
                ):
                    fail("B3-PROOF", f"{location}: expected step {event.name}({parameter}=integer)")
                integer(item.arguments[0][1], "B3-PROOF", location)
                seen_step = True
            elif isinstance(item, ExpectCheck):
                expr = item.expression
                if not (
                    seen_step and isinstance(expr, Binary) and expr.operator == "=="
                    and expr.left == Name(state.name)
                ):
                    fail("B3-PROOF", f"{location}: expected {state.name} == integer after a step")
                integer(expr.right, "B3-PROOF", location)
                expects += 1
            else:
                fail("B3-PROOF", f"{location}: unsupported scenario item")
        if not seen_step or not expects:
            fail("B3-PROOF", f"{location}: expected at least one step and expect")
    if module.proofs:
        try:
            report = verify_module(module)
        except KpolError as error:
            fail("B3-PROOF", f"reference execution failed: {error}")
        if not report.total_checks or report.passed_checks != report.total_checks or report.failures:
            reasons = "; ".join(f"{f.scenario_or_assert}: {f.message}" for f in report.failures)
            fail("B3-PROOF", f"Proof failed: {reasons}")

    violations = check_module_security_acl(module, acl_table)
    if violations:
        fail("B3-ACL", "; ".join(violations))
    descriptor = ConceptMicroDescriptor(
        cid=0, name=state.name, current_state=initial, operand_val=operand,
        pred_opcode=predicate, guard_flags=CME_GUARD_ASSUMPTION_EN | CME_GUARD_INVARIANT_EN,
        action_opcode=action_opcode,
    )
    return descriptor.pack() + bytes(63 * 16)


def compile_concept_microcode_bram_image(
    module: Module,
    cascade_map: dict[str | int, str | int] | None = None,
    acl_table: dict[str, int] | None = None,
    *,
    profile: str | None = None,
) -> bytes:
    """Compile a named CME profile, or use the experimental legacy lowering when unset."""
    if profile is not None:
        if profile != "KPOL-CME-1":
            raise KpolError(f"B3-PROFILE: unsupported profile {profile!r}")
        return _compile_cme1_profile(module, cascade_map, acl_table)
    _reject_unsupported_u32_codegen(module)
    violations = check_module_security_acl(module, acl_table)
    if violations:
        raise KpolError(f"Security ACL violation: {'; '.join(violations)}")

    if len(module.states) > 64:
        raise KpolError(f"Maximum 64 concepts supported by CME BRAM, got {len(module.states)}")

    state_index = {st.name: idx for idx, st in enumerate(module.states)}

    def _eval_int(expr: Expr) -> int:
        try:
            val = _eval(expr, {})
            if isinstance(val, bool):
                return 1 if val else 0
            if isinstance(val, (int, Decimal)):
                return int(val)
        except Exception:
            pass
        return 0

    descriptors: list[ConceptMicroDescriptor] = []

    for cid, st in enumerate(module.states):
        init_val = _eval_int(st.initial)
        operand_val = 0
        pred_opcode = CME_PRED_NOP
        guard_flags = 0
        hazard_limit = 0
        action_opcode = CME_ACT_ASSIGN
        subscriber_cid = 0

        # Пошук правил, що змінюють цей концепт
        matching_rules = [r for r in module.rules if any(act.name == st.name for act in r.actions)]
        if matching_rules:
            rule = matching_rules[0]
            action_operand = 0
            pred_operand = 0

            # Дія
            action = next(act for act in rule.actions if act.name == st.name)
            a_expr = action.expression
            if isinstance(a_expr, Binary):
                if a_expr.operator == "+" and isinstance(a_expr.left, Name) and a_expr.left.value == st.name:
                    rhs = _eval_int(a_expr.right)
                    if rhs == 1:
                        action_opcode = CME_ACT_INC
                    else:
                        action_opcode = CME_ACT_ADD
                        action_operand = rhs
                elif a_expr.operator == "-" and isinstance(a_expr.left, Name) and a_expr.left.value == st.name:
                    rhs = _eval_int(a_expr.right)
                    if rhs == 1:
                        action_opcode = CME_ACT_DEC
                    else:
                        action_opcode = CME_ACT_SUB
                        action_operand = rhs
                else:
                    action_opcode = CME_ACT_ASSIGN
            elif isinstance(a_expr, Unary):
                if a_expr.operator == "++":
                    action_opcode = CME_ACT_INC
                elif a_expr.operator == "--":
                    action_opcode = CME_ACT_DEC
                else:
                    action_opcode = CME_ACT_ASSIGN
            else:
                action_opcode = CME_ACT_ASSIGN

            # Охоронець / Предикат
            guard = rule.guard
            is_inverted = False
            if isinstance(guard, Unary) and guard.operator in ("not", "!"):
                is_inverted = True
                guard = guard.operand
            elif "•" in rule.name or "not" in rule.name.lower() or "negat" in rule.name.lower():
                is_inverted = True

            if is_inverted:
                guard_flags |= CME_GUARD_INVERT_ASSUMPTION

            if isinstance(guard, Binary):
                guard_flags |= CME_GUARD_ASSUMPTION_EN
                op = guard.operator
                rhs = _eval_int(guard.right)
                if op == "==":
                    pred_opcode = CME_PRED_EQ
                    pred_operand = rhs
                elif op == "!=":
                    pred_opcode = CME_PRED_NEQ
                    pred_operand = rhs
                elif op == ">":
                    pred_opcode = CME_PRED_GT
                    pred_operand = rhs
                elif op == "<":
                    pred_opcode = CME_PRED_LT
                    pred_operand = rhs
                elif op == "&":
                    pred_opcode = CME_PRED_BITMASK
                    pred_operand = rhs
                elif op in (">=", "<="):
                    pred_opcode = CME_PRED_RANGE
                    pred_operand = rhs & 0xFFFF
            elif isinstance(guard, Literal):
                guard_flags |= CME_GUARD_ASSUMPTION_EN
                pred_opcode = CME_PRED_NOP

            # Визначення спільного поля operand_val для 16-байтного дескриптора
            if action_opcode in (CME_ACT_ADD, CME_ACT_SUB):
                operand_val = action_operand
            elif pred_opcode != CME_PRED_NOP:
                operand_val = pred_operand
            else:
                operand_val = 0

        # Інваріанти та небезпеки (Requirements)
        for req in module.requirements:
            r_kind = req.kind.lower()
            targets_this = (
                (req.target == st.name)
                or (matching_rules and any(r.event == req.event for r in matching_rules))
                or (req.target is None and st.name in str(req.expression))
            )
            if targets_this:
                if r_kind == "invariant":
                    guard_flags |= CME_GUARD_INVARIANT_EN
                elif r_kind == "hazard":
                    guard_flags |= CME_GUARD_HAZARD_EN
                    if isinstance(req.expression, Binary) and req.expression.operator in (">", ">="):
                        hazard_limit = _eval_int(req.expression.right) & 0xFF
                    elif isinstance(req.expression, Literal) and isinstance(req.expression.value, (int, Decimal)):
                        hazard_limit = int(req.expression.value) & 0xFF

        # Каскадна підписка (Cascade / Rendezvous)
        if cascade_map:
            tgt = cascade_map.get(st.name, cascade_map.get(cid, None))
            if tgt is not None:
                if isinstance(tgt, int):
                    subscriber_cid = tgt
                elif isinstance(tgt, str) and tgt in state_index:
                    subscriber_cid = state_index[tgt]

        desc = ConceptMicroDescriptor(
            cid=cid,
            name=st.name,
            current_state=init_val,
            operand_val=operand_val,
            pred_opcode=pred_opcode,
            guard_flags=guard_flags,
            hazard_limit=hazard_limit,
            action_opcode=action_opcode,
            subscriber_cid=subscriber_cid,
        )
        descriptors.append(desc)

    # Заповнення вільних слотів до 64
    for cid in range(len(descriptors), 64):
        descriptors.append(ConceptMicroDescriptor(cid=cid, name=f"Empty_{cid}"))

    return b"".join(d.pack() for d in descriptors)



def compile_c_header(module: Module) -> str:
    """Generates a self-contained C99 header for MCU/STM32 firmware."""
    guard_name = f"KM_KPOL_{module.name.upper()}_H"
    lines = [
        f"/* Generated by KPOL Compiler v0.5 for module: {module.name} */",
        f"#ifndef {guard_name}",
        f"#define {guard_name}",
        "",
        "#include <stdint.h>",
        "#include <stdbool.h>",
        "",
        f"#define {module.name.upper()}_NUM_CONCEPTS {len(module.states)}u",
        f"#define {module.name.upper()}_BRAM_WORDS 256u",
        "",
        "/* --- Concept ID Enumeration --- */",
        "typedef enum {",
    ]
    for cid, state in enumerate(module.states):
        lines.append(f"    CID_{state.name} = {cid},")
    lines.append(f"    {module.name.upper()}_TOTAL_CIDS = {len(module.states)}")
    lines.append("} km_concept_id_t;\n")

    lines.append("/* --- Initial BRAM Image (1024 bytes / 256 words) --- */")
    lines.append(f"static const uint32_t {module.name.upper()}_BRAM_INIT[256] = {{")

    bram_bytes = compile_bram_image(module)
    words = struct.unpack("<256I", bram_bytes)
    for i in range(0, 256, 4):
        chunk = words[i:i+4]
        cid = i // 4
        comment = f"/* CID {cid:02d} ({module.states[cid].name}) */" if cid < len(module.states) else f"/* CID {cid:02d} (empty) */"
        lines.append(f"    0x{chunk[0]:08X}u, 0x{chunk[1]:08X}u, 0x{chunk[2]:08X}u, 0x{chunk[3]:08X}u, {comment}")

    lines.append("};\n")
    lines.append(f"#endif /* {guard_name} */\n")
    return "\n".join(lines)


def compile_verilog_interconnect(module: Module) -> str:
    """Synthesizes an interconnect Verilog module wiring kpol_txn_gate_v2 instances."""
    _reject_unsupported_u32_codegen(module)
    mod_lower = module.name.lower()
    state_regs = "\n".join(f"    logic [31:0] state_{state.name}_q;" for state in module.states)

    return f"""// Generated by KPOL Compiler v0.5 for module: {module.name}
`timescale 1ns / 1ps

module km_{mod_lower}_interconnect (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        event_strobe_i,
    input  logic        hazard_active_i,
    input  logic        alert_active_i,
    output logic        committed_o,
    output logic        rejected_o,
    output logic        hazard_blocked_o,
    output logic        alert_observed_o
);

    // Hardware concept registers
{state_regs}

    // Instantiation of fail-closed transaction gate v2
    kpol_txn_gate_v2 #(
        .FAIL_CLOSED_HAZARDS(1'b1)
    ) u_txn_gate (
        .clk_i(clk),
        .rst_ni(rst_n),
        .event_valid_i(event_strobe_i),
        .candidate_known_i(1'b1),
        .candidate_value_i(32'h00000000),
        .assumption_known_i(1'b1),
        .assumption_true_i(1'b1),
        .invariant_known_i(1'b1),
        .invariant_true_i(1'b1),
        .hazard_known_i(1'b1),
        .hazard_true_i(hazard_active_i),
        .alert_known_i(1'b1),
        .alert_true_i(alert_active_i),
        .state_o(),
        .committed_o(committed_o),
        .rejected_o(rejected_o),
        .rejected_input_o(),
        .rejected_invariant_o(),
        .rejected_hazard_o(),
        .changed_o(),
        .hazard_observed_o(),
        .hazard_blocked_o(hazard_blocked_o),
        .unknown_hazard_o(),
        .alert_observed_o(alert_observed_o)
    );

endmodule // km_{mod_lower}_interconnect
"""


def compile_compliance_rtm(module: Module) -> str:
    """Generates a Bidirectional Requirements Traceability Matrix (RTM) for ISO 26262 / DO-178C."""
    lines = [
        f"# Requirements Traceability Matrix (RTM): {module.name}",
        "",
        "| Req Kind | Requirement ID | Target Event / Concept | Implementation Rule | Verification Proof Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for req in module.requirements:
        rule_name = "-"
        for rule in module.rules:
            if rule.covers == req.name or (rule.event == req.event and req.kind == "Invariant"):
                rule_name = f"`{rule.name}`"
                break
        proof_name = "-"
        for proof in module.proofs:
            if isinstance(proof, AssertPropertyDecl) and proof.event == req.event:
                proof_name = f"`assert {proof.name}`"
                break
            elif isinstance(proof, ScenarioDecl):
                if req.event and any(isinstance(s, StepAction) and s.event_name == req.event for s in proof.steps):
                    proof_name = f"`scenario {proof.name}`"
                    break
        lines.append(f"| **{req.kind}** | `{req.name}` | `{req.event or req.target or '-'}` | {rule_name} | {proof_name} |")
    return "\n".join(lines)


# ==============================================================================
# KPOL v0.6: CyberSecurity, Hardware Capabilities (ACL) & Secure Boot
# ==============================================================================

KPOL_SEC_MAGIC = 0x4C4F504B  # "KPOL" ASCII in Little-Endian (<I)
KPOL_SEC_VERSION = 0x0006     # v0.6 format

SEC_FLAG_HMAC_SHA256 = 0x0001
SEC_FLAG_ED25519 = 0x0002
SEC_FLAG_LOCKOUT_ON_TAMPER = 0x0004
SEC_FLAG_ENFORCE_ACL = 0x0008

CAP_READ = 0x01
CAP_WRITE = 0x02
CAP_PIN_OUT = 0x04
CAP_CSP_TX = 0x08
CAP_INTERRUPT = 0x10
CAP_LOCKED = 0x80


def compile_signed_bram_image(
    module: Module | bytes,
    secret_key: bytes,
    key_id: int = 1,
    nonce: int | bytes | None = None,
    flags: int = (SEC_FLAG_HMAC_SHA256 | SEC_FLAG_LOCKOUT_ON_TAMPER | SEC_FLAG_ENFORCE_ACL),
    *,
    payload_format: str = "CME-RAW-1",
) -> bytes:
    """Compiles a 1088-byte cryptographically signed BRAM image (v0.6 Secure Boot).

    Layout:
      +0x00: MAGIC (4 bytes) = 0x4C4F504B ("KPOL" in Little-Endian)
      +0x04: FORMAT_VERSION (2 bytes) = 0x0006
      +0x06: FLAGS (2 bytes)
      +0x08: PAYLOAD_LEN (4 bytes) = 1024
      +0x0C: KEY_ID (4 bytes)
      +0x10: NONCE (16 bytes)
      +0x20: AUTH_TAG (32 bytes HMAC-SHA256 digest of Header[0:32] + Payload[0:1024])
      +0x40: PAYLOAD (1024 bytes BRAM binary, CME-RAW-1 by default)
    """
    if not isinstance(secret_key, (bytes, bytearray)) or len(secret_key) < 16:
        raise KpolError("secret_key must be at least 16 bytes for HMAC-SHA256")
    if not (flags & SEC_FLAG_HMAC_SHA256):
        raise KpolError("flags must specify SEC_FLAG_HMAC_SHA256")

    if isinstance(module, (bytes, bytearray)):
        payload = bytes(module)
    else:
        if payload_format == "CME-RAW-1":
            payload = compile_concept_microcode_bram_image(module)
        elif payload_format == "legacy":
            payload = compile_bram_image(module)
        else:
            raise KpolError(f"Unsupported payload_format: {payload_format!r}")

    if len(payload) != 1024:
        raise KpolError(f"Internal compiler error: invalid payload length {len(payload)}")

    if nonce is None:
        nonce_bytes = secrets.token_bytes(16)
    elif isinstance(nonce, int):
        nonce_bytes = struct.pack("<Q", nonce).ljust(16, b"\x00")
    elif isinstance(nonce, (bytes, bytearray)):
        if len(nonce) != 16:
            raise KpolError(f"Nonce must be exactly 16 bytes, got {len(nonce)}")
        nonce_bytes = bytes(nonce)
    else:
        raise KpolError(f"Unsupported nonce type: {type(nonce)}")

    header_prefix = struct.pack("<IHHI I", KPOL_SEC_MAGIC, KPOL_SEC_VERSION, flags, len(payload), key_id) + nonce_bytes
    auth_tag = hmac.new(secret_key, header_prefix + payload, hashlib.sha256).digest()
    if len(auth_tag) != 32:
        raise KpolError("HMAC-SHA256 tag calculation error")

    signed_image = header_prefix + auth_tag + payload
    if len(signed_image) != 1088:
        raise KpolError(f"Expected 1088 bytes, got {len(signed_image)}")
    return signed_image


def verify_bram_signature(
    signed_image: bytes,
    secret_key: bytes,
    seen_nonces: set[bytes] | None = None,
) -> tuple[bool, str]:
    """Verifies a 1088-byte signed BRAM image against secret_key in constant time."""
    if not isinstance(secret_key, (bytes, bytearray)) or len(secret_key) < 16:
        return False, "secret_key must be at least 16 bytes"
    if not isinstance(signed_image, (bytes, bytearray)):
        return False, "Image must be bytes"
    if len(signed_image) != 1088:
        return False, f"Invalid image length: {len(signed_image)} bytes (expected 1088)"

    header_prefix = signed_image[:32]
    magic, version, flags, payload_len, key_id = struct.unpack("<IHHI I", header_prefix[:16])

    if magic != KPOL_SEC_MAGIC:
        return False, f"Invalid magic header: 0x{magic:08X} (expected 0x{KPOL_SEC_MAGIC:08X} 'KPOL')"
    if version != KPOL_SEC_VERSION:
        return False, f"Unsupported version: 0x{version:04X} (expected 0x{KPOL_SEC_VERSION:04X})"
    if payload_len != 1024:
        return False, f"Invalid payload length in header: {payload_len} (expected 1024)"
    if not (flags & SEC_FLAG_HMAC_SHA256):
        return False, "Image flags missing SEC_FLAG_HMAC_SHA256"

    auth_tag = signed_image[32:64]
    payload = signed_image[64:1088]

    computed_tag = hmac.new(secret_key, header_prefix + payload, hashlib.sha256).digest()
    if not hmac.compare_digest(auth_tag, computed_tag):
        return False, "Signature verification failed: Cryptographic tag mismatch (tampering detected)"

    nonce = header_prefix[16:32]
    if seen_nonces is not None:
        if nonce in seen_nonces:
            return False, "Replay attack detected: Nonce has already been used"
        seen_nonces.add(nonce)

    return True, "OK: Valid signature"


def check_module_security_acl(module: Module, concept_acls: dict[str, int] | None = None) -> list[str]:
    """Audits module rules and states against Hardware Capabilities ACL."""
    violations: list[str] = []
    # By default, concepts without explicit ACL have CAP_READ | CAP_WRITE
    acls = {state.name: (CAP_READ | CAP_WRITE) for state in module.states}
    if concept_acls:
        acls.update(concept_acls)

    # Check Pin<Out> states requirement for CAP_PIN_OUT
    for state in module.states:
        if state.type_ref.name == "Pin":
            unit = state.type_ref.unit or ""
            is_output = "Out" in unit.split(",")
            cap = acls.get(state.name, 0)
            if is_output and not (cap & CAP_PIN_OUT):
                violations.append(
                    f"ACL violation: state '{state.name}' of type Pin<Out> requires CAP_PIN_OUT (0x04) capability"
                )

    # Check rules modifying states
    for rule in module.rules:
        for act in rule.actions:
            if act.name in acls:
                cap = acls[act.name]
                if not (cap & CAP_WRITE):
                    violations.append(
                        f"ACL violation: rule '{rule.name}' writes to state '{act.name}' without CAP_WRITE capability"
                    )
            state_decl = next((s for s in module.states if s.name == act.name), None)
            if state_decl and state_decl.type_ref.name == "Pin":
                unit = state_decl.type_ref.unit or ""
                if "Out" in unit.split(","):
                    cap = acls.get(act.name, 0)
                    if not (cap & CAP_PIN_OUT):
                        violations.append(
                            f"ACL violation: rule '{rule.name}' writes to output pin '{act.name}' without CAP_PIN_OUT capability"
                        )
    return violations


# ==============================================================================
# KPOL v0.7: Popperian Falsification, Mutation Fuzzing & SMT Counterexamples
# ==============================================================================

@dataclass
class FalsificationResult:
    total_mutants: int
    killed_mutants: int
    survived_mutants: list[str]
    mutation_score: float
    corroboration_score: float
    details: list[str] = field(default_factory=list)


def _mutate_expr(expr: Expr) -> list[tuple[str, Expr]]:
    """Generates first-order AST mutants for an expression."""
    mutated: list[tuple[str, Expr]] = []
    if isinstance(expr, Binary):
        orig_op = expr.operator
        relational_alts = {
            ">": [">=", "==", "<"],
            "<": ["<=", "==", ">"],
            ">=": [">", "<"],
            "<=": ["<", ">"],
            "==": ["!="],
            "!=": ["=="],
            "and": ["or"],
            "or": ["and"],
        }
        if orig_op in relational_alts:
            for alt_op in relational_alts[orig_op]:
                mutated.append((f"OP_{orig_op}_to_{alt_op}", Binary(alt_op, expr.left, expr.right)))

        # BSR on right integer literal
        if isinstance(expr.right, Literal) and isinstance(expr.right.value, int):
            val = expr.right.value
            for delta in (+1, -1):
                mutated.append((f"BSR_val_{val}_to_{val+delta}", Binary(orig_op, expr.left, Literal(val + delta))))

        # BSR on left integer literal
        if isinstance(expr.left, Literal) and isinstance(expr.left.value, int):
            val = expr.left.value
            for delta in (+1, -1):
                mutated.append((f"BSR_left_{val}_to_{val+delta}", Binary(orig_op, Literal(val + delta), expr.right)))

        # Recursive mutations on sub-expressions
        for desc, sub in _mutate_expr(expr.left):
            mutated.append((f"left_{desc}", Binary(orig_op, sub, expr.right)))
        for desc, sub in _mutate_expr(expr.right):
            mutated.append((f"right_{desc}", Binary(orig_op, expr.left, sub)))
    return mutated


def generate_mutants(module: Module) -> list[tuple[str, Module]]:
    """Synthesizes first-order mutants of the module's rules."""
    mutants: list[tuple[str, Module]] = []

    for r_idx, rule in enumerate(module.rules):
        # 1. Guard mutations
        for desc, mut_guard in _mutate_expr(rule.guard):
            mut_rule = Rule(
                rule.name, rule.event, rule.reject, rule.watch, mut_guard, rule.covers, rule.actions
            )
            mut_rules = list(module.rules)
            mut_rules[r_idx] = mut_rule
            mut_mod = Module(
                module.name, module.requirements, module.events, module.states, tuple(mut_rules), module.proofs,
                proof_present=module.proof_present,
            )
            mutants.append((f"ROR:{rule.name}:{desc}", mut_mod))

        # 2. Action mutations (State Value Replacement SVR)
        for a_idx, action in enumerate(rule.actions):
            if isinstance(action.expression, Literal):
                val = action.expression.value
                if isinstance(val, bool):
                    mut_act = SetAction(action.name, Literal(not val))
                    mut_actions = list(rule.actions)
                    mut_actions[a_idx] = mut_act
                    mut_rule = Rule(
                        rule.name, rule.event, rule.reject, rule.watch, rule.guard, rule.covers, tuple(mut_actions)
                    )
                    mut_rules = list(module.rules)
                    mut_rules[r_idx] = mut_rule
                    mut_mod = Module(
                        module.name, module.requirements, module.events, module.states, tuple(mut_rules), module.proofs,
                        proof_present=module.proof_present,
                    )
                    mutants.append((f"SVR:{rule.name}:{action.name}_bool_inverted", mut_mod))
                elif isinstance(val, int):
                    for delta in (+1, -1):
                        mut_act = SetAction(action.name, Literal(val + delta))
                        mut_actions = list(rule.actions)
                        mut_actions[a_idx] = mut_act
                        mut_rule = Rule(
                            rule.name, rule.event, rule.reject, rule.watch, rule.guard, rule.covers, tuple(mut_actions)
                        )
                        mut_rules = list(module.rules)
                        mut_rules[r_idx] = mut_rule
                        mut_mod = Module(
                            module.name, module.requirements, module.events, module.states, tuple(mut_rules), module.proofs,
                            proof_present=module.proof_present,
                        )
                        mutants.append((f"SVR:{rule.name}:{action.name}_val_{val}_to_{val+delta}", mut_mod))

    return mutants


def run_falsification_suite(module: Module) -> FalsificationResult:
    """Executes the Popperian falsification suite across all generated mutants."""
    base_result = verify_module(module)
    if not base_result.passed:
        raise KpolError(f"Cannot run falsification on invalid module: {base_result.failures}")

    mutants = generate_mutants(module)
    if not mutants:
        if len(module.rules) > 0:
            raise KpolError("Popperian falsification error: module rules contain no mutable operators (untestable logic gap)")
        return FalsificationResult(
            total_mutants=0,
            killed_mutants=0,
            survived_mutants=[],
            mutation_score=1.0,
            corroboration_score=1.0,
            details=["No mutable operators found in module rules."],
        )

    killed = 0
    survived: list[str] = []
    details: list[str] = []

    for name, mutant in mutants:
        try:
            res = verify_module(mutant)
            if res.passed:
                survived.append(name)
                details.append(f"SURVIVED: {name}")
            else:
                killed += 1
                details.append(f"KILLED: {name}")
        except KpolError:
            killed += 1
            details.append(f"KILLED (Contract violation): {name}")
        except Exception as e:
            survived.append(name)
            details.append(f"SURVIVED (Internal error): {name} -> {e}")

    total = len(mutants)
    mutation_score = killed / total if total > 0 else 1.0
    # Popper corroboration C(h, e)
    corroboration = mutation_score * (1.0 - (1.0 / (2.0 + math.log2(1 + killed)))) if killed > 0 else 0.0

    return FalsificationResult(
        total_mutants=total,
        killed_mutants=killed,
        survived_mutants=survived,
        mutation_score=mutation_score,
        corroboration_score=corroboration,
        details=details,
    )


def enforce_popperian_gate(module: Module) -> FalsificationResult:
    """Enforces that mutation score M == 1.0 (release gate)."""
    result = run_falsification_suite(module)
    if result.total_mutants == 0 and len(module.rules) > 0:
        raise KpolError("Popperian falsification gate failed: no mutants generated for non-empty rules")
    if result.mutation_score < 1.0:
        survived_str = ", ".join(result.survived_mutants)
        raise KpolError(
            f"Popperian falsification gate failed: Mutation Score M = {result.mutation_score:.3f} < 1.0 "
            f"({len(result.survived_mutants)} mutants survived: {survived_str})"
        )
    return result


# ==============================================================================
# KPOL v0.8: Fixed Silicon, Bare-Metal Runtime libkpol & STM32 / AXI4-Lite HIL
# ==============================================================================

def _ast_expr_to_c(
    expr: Expr,
    state_names: set[str],
    param_names: set[str],
    state_prefix: str = "ctx->state_",
) -> str:
    """Recursively compiles a typed KPOL AST expression into standard C99 code."""
    if isinstance(expr, Literal):
        val = expr.value
        if isinstance(val, bool):
            return "true" if val else "false"
        elif isinstance(val, (int, Decimal)):
            return str(int(val))
        return str(val)
    elif isinstance(expr, Name):
        if expr.value in param_names:
            return f"param_{expr.value}"
        elif expr.value in state_names:
            return f"{state_prefix}{expr.value}"
        return expr.value
    elif isinstance(expr, Unary):
        inner = _ast_expr_to_c(expr.operand, state_names, param_names, state_prefix)
        if expr.operator == "not":
            return f"(!({inner}))"
        elif expr.operator == "-":
            return f"(-({inner}))"
        return f"{expr.operator}({inner})"
    elif isinstance(expr, Binary):
        left_c = _ast_expr_to_c(expr.left, state_names, param_names, state_prefix)
        right_c = _ast_expr_to_c(expr.right, state_names, param_names, state_prefix)
        op_map = {
            "and": "&&",
            "or": "||",
            "==": "==",
            "!=": "!=",
            "<": "<",
            "<=": "<=",
            ">": ">",
            ">=": ">=",
            "+": "+",
            "-": "-",
            "*": "*",
            "/": "/",
        }
        c_op = op_map.get(expr.operator, expr.operator)
        return f"({left_c} {c_op} {right_c})"
    elif isinstance(expr, Call):
        args = [_ast_expr_to_c(a, state_names, param_names, state_prefix) for a in expr.arguments]
        if expr.name == "gcd" and len(args) == 2:
            return f"km_gcd({args[0]}, {args[1]})"
        return f"{expr.name}({', '.join(args)})"
    raise KpolError(f"Unsupported AST node in C compiler: {type(expr)}")


def compile_baremetal_runtime(module: Module) -> tuple[str, str]:
    """Generates MISRA-C:2012 compliant bare-metal C99 header and source from AST (no malloc, real code gen)."""
    _reject_unsupported_u32_codegen(module)
    violations = check_module_security_acl(module)
    if violations:
        raise KpolError(f"Hardware ACL violation: {'; '.join(violations)}")

    mod_name = module.name.lower()
    mod_upper = module.name.upper()
    state_names = {s.name for s in module.states}

    # --- Header generation ---
    h_lines = [
        f"/* Generated by KPOL Compiler v0.8 for module: {module.name} */",
        "/* Zero dynamic allocation (MISRA C:2012 Rule 21.3 compliant) */",
        f"#ifndef KM_{mod_upper}_RUNTIME_H",
        f"#define KM_{mod_upper}_RUNTIME_H",
        "",
        "#include <stdint.h>",
        "#include <stdbool.h>",
        "",
        "typedef enum {",
        "    KM_TXN_COMMITTED      = 0,",
        "    KM_TXN_REJECTED       = 1,",
        "    KM_TXN_HAZARD_BLOCKED = 2",
        f"}} km_{mod_name}_status_t;",
        "",
        "typedef enum {",
    ]
    for ev_id, ev in enumerate(module.events):
        h_lines.append(f"    KM_EV_{ev.name.upper()} = {ev_id},")
    h_lines.extend([
        f"}} km_{mod_name}_event_id_t;",
        "",
        f"#define KM_{mod_upper}_NUM_STATES {len(module.states)}",
        f"#define KM_{mod_upper}_NUM_EVENTS {len(module.events)}",
        "",
    ])

    # Event payload structs
    for ev in module.events:
        if ev.parameters:
            h_lines.append(f"typedef struct {{")
            for p_name, _ in ev.parameters:
                h_lines.append(f"    int32_t {p_name};")
            h_lines.append(f"}} km_{mod_name}_payload_{ev.name.lower()}_t;")
            h_lines.append("")

    h_lines.extend([
        "typedef struct {",
        "    uint32_t step_counter;",
        "    uint32_t committed_count;",
        "    uint32_t rejected_count;",
        "    uint32_t hazard_blocked_count;",
    ])
    for state in module.states:
        h_lines.append(f"    int32_t state_{state.name};")
    h_lines.extend([
        f"}} km_{mod_name}_context_t;",
        "",
        f"void km_{mod_name}_init(km_{mod_name}_context_t *ctx);",
        f"km_{mod_name}_status_t km_{mod_name}_dispatch(km_{mod_name}_context_t *ctx, uint32_t event_id, const void *payload);",
        f"km_{mod_name}_status_t km_{mod_name}_dispatch_raw(km_{mod_name}_context_t *ctx, uint32_t event_id, int32_t raw_val);",
        "",
    ])

    for ev in module.events:
        if len(ev.parameters) == 1:
            p_name = ev.parameters[0][0]
            h_lines.append(f"km_{mod_name}_status_t km_{mod_name}_dispatch_{ev.name.lower()}(km_{mod_name}_context_t *ctx, int32_t {p_name});")
        elif len(ev.parameters) == 0:
            h_lines.append(f"km_{mod_name}_status_t km_{mod_name}_dispatch_{ev.name.lower()}(km_{mod_name}_context_t *ctx);")

    h_lines.append(f"\n#endif /* KM_{mod_upper}_RUNTIME_H */\n")
    header_str = "\n".join(h_lines)

    # --- Source generation ---
    c_lines = [
        f"/* Generated by KPOL Compiler v0.8 for module: {module.name} */",
        f'#include "km_{mod_name}_runtime.h"',
        "",
        "static int32_t km_gcd(int32_t a, int32_t b) {",
        "    while (b != 0) {",
        "        int32_t t = b;",
        "        b = a % b;",
        "        a = t;",
        "    }",
        "    return a >= 0 ? a : -a;",
        "}",
        "",
        f"void km_{mod_name}_init(km_{mod_name}_context_t *ctx) {{",
        "    if (ctx == 0) return;",
        "    ctx->step_counter = 0;",
        "    ctx->committed_count = 0;",
        "    ctx->rejected_count = 0;",
        "    ctx->hazard_blocked_count = 0;",
    ]
    for state in module.states:
        init_val = _eval(state.initial, {})
        val_int = 1 if init_val is True else (0 if init_val is False else int(init_val))
        c_lines.append(f"    ctx->state_{state.name} = {val_int};")
    c_lines.append("}\n")

    c_lines.extend([
        f"km_{mod_name}_status_t km_{mod_name}_dispatch(km_{mod_name}_context_t *ctx, uint32_t event_id, const void *payload) {{",
        "    if (ctx == 0) return KM_TXN_REJECTED;",
        "    ctx->step_counter++;",
        "",
        "    switch (event_id) {",
    ])

    for ev_id, ev in enumerate(module.events):
        p_names = {p[0] for p in ev.parameters}
        c_lines.append(f"    case KM_EV_{ev.name.upper()}: {{")

        if ev.parameters:
            c_lines.append(f"        const km_{mod_name}_payload_{ev.name.lower()}_t *p = (const km_{mod_name}_payload_{ev.name.lower()}_t *)payload;")
            for p_name, _ in ev.parameters:
                c_lines.append(f"        int32_t param_{p_name} = p ? p->{p_name} : 0;")

        # 1. Pre-Phase: Check Assumptions
        for req in module.requirements:
            if req.kind == "Assumption" and req.event == ev.name:
                cond_c = _ast_expr_to_c(req.expression, state_names, p_names)
                c_lines.append(f"        /* Assumption: {req.name} */")
                c_lines.append(f"        if (!({cond_c})) {{")
                c_lines.append("            ctx->rejected_count++;")
                c_lines.append("            return KM_TXN_REJECTED;")
                c_lines.append("        }")

        # 2. Pre-Phase: Check Hazards (Fail-Closed)
        for req in module.requirements:
            if req.kind == "Hazard" and req.event == ev.name:
                cond_c = _ast_expr_to_c(req.expression, state_names, p_names)
                c_lines.append(f"        /* Hazard: {req.name} */")
                c_lines.append(f"        if ({cond_c}) {{")
                c_lines.append("            ctx->hazard_blocked_count++;")
                if req.target:
                    c_lines.append(f"            ctx->state_{req.target} = 1;")
                for rule in module.rules:
                    if rule.covers == req.name:
                        for act in rule.actions:
                            act_c = _ast_expr_to_c(act.expression, state_names, p_names)
                            c_lines.append(f"            ctx->state_{act.name} = {act_c};")
                c_lines.append("            return KM_TXN_HAZARD_BLOCKED;")
                c_lines.append("        }")

        # 3. Candidate next states for nominal rules
        for state in module.states:
            c_lines.append(f"        int32_t next_{state.name} = ctx->state_{state.name};")

        for rule in module.rules:
            if rule.event == ev.name and not rule.reject and not rule.covers:
                guard_c = _ast_expr_to_c(rule.guard, state_names, p_names)
                c_lines.append(f"        /* Rule: {rule.name} */")
                c_lines.append(f"        if ({guard_c}) {{")
                for act in rule.actions:
                    act_c = _ast_expr_to_c(act.expression, state_names, p_names)
                    c_lines.append(f"            next_{act.name} = {act_c};")
                c_lines.append("        }")

        # 4. Check Invariants on candidate next state
        for req in module.requirements:
            if req.kind == "Invariant":
                inv_c = _ast_expr_to_c(req.expression, state_names, set(), state_prefix="next_")
                c_lines.append(f"        /* Invariant: {req.name} */")
                c_lines.append(f"        if (!({inv_c})) {{")
                c_lines.append("            ctx->rejected_count++;")
                c_lines.append("            return KM_TXN_REJECTED;")
                c_lines.append("        }")

        # 5. Commit state changes
        for state in module.states:
            c_lines.append(f"        ctx->state_{state.name} = next_{state.name};")

        c_lines.append("        ctx->committed_count++;")
        c_lines.append("        return KM_TXN_COMMITTED;")
        c_lines.append("    }")

    c_lines.extend([
        "    default:",
        "        ctx->rejected_count++;",
        "        return KM_TXN_REJECTED;",
        "    }",
        "}",
        "",
        f"km_{mod_name}_status_t km_{mod_name}_dispatch_raw(km_{mod_name}_context_t *ctx, uint32_t event_id, int32_t raw_val) {{",
        "    int32_t tmp = raw_val;",
        f"    return km_{mod_name}_dispatch(ctx, event_id, (const void *)&tmp);",
        "}\n",
    ])

    for ev in module.events:
        if len(ev.parameters) == 1:
            p_name = ev.parameters[0][0]
            c_lines.extend([
                f"km_{mod_name}_status_t km_{mod_name}_dispatch_{ev.name.lower()}(km_{mod_name}_context_t *ctx, int32_t {p_name}) {{",
                f"    km_{mod_name}_payload_{ev.name.lower()}_t payload;",
                f"    payload.{p_name} = {p_name};",
                f"    return km_{mod_name}_dispatch(ctx, KM_EV_{ev.name.upper()}, &payload);",
                "}\n",
            ])
        elif len(ev.parameters) == 0:
            c_lines.extend([
                f"km_{mod_name}_status_t km_{mod_name}_dispatch_{ev.name.lower()}(km_{mod_name}_context_t *ctx) {{",
                f"    return km_{mod_name}_dispatch(ctx, KM_EV_{ev.name.upper()}, 0);",
                "}\n",
            ])

    source_str = "\n".join(c_lines)
    return header_str, source_str


def compile_axi_lite_wrapper(module: Module) -> str:
    """Generates an AMBA AXI4-Lite compliant slave peripheral FSM (real handshaking & WSTRB)."""
    _reject_unsupported_u32_codegen(module)
    mod_name = module.name.lower()
    return f"""// Generated by KPOL Compiler v0.8 for module: {module.name}
// AMBA AXI4-Lite Compliant Slave Peripheral
`timescale 1ns / 1ps

module km_{mod_name}_axi_lite_slave #(
    parameter int C_S_AXI_DATA_WIDTH = 32,
    parameter int C_S_AXI_ADDR_WIDTH = 6
)(
    input  logic                          s_axi_aclk,
    input  logic                          s_axi_aresetn,

    // Write Address Channel (AW)
    input  logic [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input  logic [2:0]                    s_axi_awprot,
    input  logic                          s_axi_awvalid,
    output logic                          s_axi_awready,

    // Write Data Channel (W)
    input  logic [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
    input  logic [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input  logic                          s_axi_wvalid,
    output logic                          s_axi_wready,

    // Write Response Channel (B)
    output logic [1:0]                    s_axi_bresp,
    output logic                          s_axi_bvalid,
    input  logic                          s_axi_bready,

    // Read Address Channel (AR)
    input  logic [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input  logic [2:0]                    s_axi_arprot,
    input  logic                          s_axi_arvalid,
    output logic                          s_axi_arready,

    // Read Data Channel (R)
    output logic [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
    output logic [1:0]                    s_axi_rresp,
    output logic                          s_axi_rvalid,
    input  logic                          s_axi_rready
);

    // Register map offsets: 0x00=CR_STATUS, 0x04=EVENT_ID, 0x08=PARAM0, 0x10=CYCLE_COUNTER
    logic [31:0] cr_status_reg;
    logic [31:0] event_id_reg;
    logic [31:0] param0_reg;
    logic [31:0] cycle_counter_reg;

    // Independent Write Handshake Latches
    logic aw_latched;
    logic w_latched;
    logic [C_S_AXI_ADDR_WIDTH-1:0] aw_addr_q;
    logic [C_S_AXI_DATA_WIDTH-1:0] w_data_q;
    logic [3:0]                     w_strb_q;

    // Effective write bus signals
    logic [C_S_AXI_ADDR_WIDTH-1:0] eff_addr;
    logic [C_S_AXI_DATA_WIDTH-1:0] eff_data;
    logic [3:0]                     eff_strb;

    assign eff_addr = aw_latched ? aw_addr_q : s_axi_awaddr;
    assign eff_data = w_latched  ? w_data_q  : s_axi_wdata;
    assign eff_strb = w_latched  ? w_strb_q  : s_axi_wstrb[3:0];

    // Response registers
    logic bvalid_q;
    logic rvalid_q;
    logic [31:0] rdata_q;

    // AWREADY & WREADY are asserted only when buffer empty and not blocked by unconsumed BVALID
    assign s_axi_awready = (!aw_latched) && (!bvalid_q || s_axi_bready);
    assign s_axi_wready  = (!w_latched)  && (!bvalid_q || s_axi_bready);
    assign s_axi_bvalid  = bvalid_q;
    assign s_axi_bresp   = 2'b00; // OKAY

    // ARREADY & RVALID
    assign s_axi_arready = (!rvalid_q || s_axi_rready);
    assign s_axi_rvalid  = rvalid_q;
    assign s_axi_rdata   = rdata_q;
    assign s_axi_rresp   = 2'b00; // OKAY

    // Helper function to apply byte strobes
    function automatic [31:0] apply_wstrb(input [31:0] old_val, input [31:0] new_val, input [3:0] strb);
        apply_wstrb[7:0]   = strb[0] ? new_val[7:0]   : old_val[7:0];
        apply_wstrb[15:8]  = strb[1] ? new_val[15:8]  : old_val[15:8];
        apply_wstrb[23:16] = strb[2] ? new_val[23:16] : old_val[23:16];
        apply_wstrb[31:24] = strb[3] ? new_val[31:24] : old_val[31:24];
    endfunction

    // Write Channel Logic
    always_ff @(posedge s_axi_aclk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            aw_latched        <= 1'b0;
            w_latched         <= 1'b0;
            aw_addr_q         <= '0;
            w_data_q          <= '0;
            w_strb_q          <= '0;
            bvalid_q          <= 1'b0;
            cr_status_reg     <= 32'h00000000;
            event_id_reg      <= 32'h00000000;
            param0_reg        <= 32'h00000000;
            cycle_counter_reg <= 32'h00000000;
        end else begin
            cycle_counter_reg <= cycle_counter_reg + 1;

            if (s_axi_bready && bvalid_q) begin
                bvalid_q <= 1'b0;
            end

            // Latch write address independently
            if (s_axi_awvalid && s_axi_awready) begin
                aw_addr_q  <= s_axi_awaddr;
                aw_latched <= 1'b1;
            end

            // Latch write data independently
            if (s_axi_wvalid && s_axi_wready) begin
                w_data_q  <= s_axi_wdata;
                w_strb_q  <= s_axi_wstrb[3:0];
                w_latched <= 1'b1;
            end

            // When both address and data are latched, execute register write
            if ((aw_latched || (s_axi_awvalid && s_axi_awready)) &&
                (w_latched  || (s_axi_wvalid  && s_axi_wready)) &&
                (!bvalid_q || s_axi_bready)) begin

                case (eff_addr[5:2])
                    4'h0: cr_status_reg <= apply_wstrb(cr_status_reg, eff_data, eff_strb);
                    4'h1: event_id_reg  <= apply_wstrb(event_id_reg,  eff_data, eff_strb);
                    4'h2: param0_reg    <= apply_wstrb(param0_reg,    eff_data, eff_strb);
                    default: ;
                endcase

                bvalid_q   <= 1'b1;
                aw_latched <= 1'b0;
                w_latched  <= 1'b0;
            end
        end
    end

    // Read Channel Logic
    always_ff @(posedge s_axi_aclk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            rvalid_q <= 1'b0;
            rdata_q  <= 32'h00000000;
        end else begin
            if (s_axi_rready && rvalid_q) begin
                rvalid_q <= 1'b0;
            end

            if (s_axi_arvalid && s_axi_arready) begin
                rvalid_q <= 1'b1;
                case (s_axi_araddr[5:2])
                    4'h0: rdata_q <= cr_status_reg;
                    4'h1: rdata_q <= event_id_reg;
                    4'h2: rdata_q <= param0_reg;
                    4'h4: rdata_q <= cycle_counter_reg;
                    default: rdata_q <= 32'h00000000;
                endcase
            end
        end
    end

endmodule // km_{mod_name}_axi_lite_slave
"""


# ==============================================================================
# KPOL v0.9: Modular Decomposition, Headers-as-Code & Multi-File Linker kpol-ld
# ==============================================================================

def parse_triad_files(problem_src: str, solution_src: str, proof_src: str | None = None) -> Module:
    """Parses and links independent .kproblem, .ksolution, and .kproof files with cryptographic auditing (DO-178C DAL A)."""
    if not problem_src or not problem_src.strip():
        raise KpolError("DO-178C DAL A violation: problem_src (.kproblem) is mandatory")
    if not solution_src or not solution_src.strip():
        raise KpolError("DO-178C DAL A violation: solution_src (.ksolution) is mandatory")
    if not proof_src or not proof_src.strip():
        raise KpolError("DO-178C DAL A violation: proof_src (.kproof) is mandatory and cannot be empty")

    def sanitize(src: str) -> str:
        lines = []
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("namespace ") or s.startswith("import "):
                continue
            lines.append(line)
        return "\n".join(lines)

    combined = sanitize(problem_src) + "\n" + sanitize(solution_src) + "\n" + sanitize(proof_src)
    parsed = parse_module(combined)
    if len(parsed.proofs) == 0:
        raise KpolError("DO-178C DAL A violation: module must declare at least one assert or scenario in Proof block")

    return Module(
        name=parsed.name,
        requirements=parsed.requirements,
        events=parsed.events,
        states=parsed.states,
        rules=parsed.rules,
        proofs=parsed.proofs,
        problem_hash=hashlib.sha256(problem_src.encode("utf-8")).hexdigest(),
        solution_hash=hashlib.sha256(solution_src.encode("utf-8")).hexdigest(),
        proof_hash=hashlib.sha256(proof_src.encode("utf-8")).hexdigest(),
        proof_present=parsed.proof_present,
    )


def link_modules(modules: list[Module], target_name: str = "SystemComposite") -> Module:
    """Links multiple independently compiled KPOL modules into a composite system (kpol-ld)."""
    if not modules:
        raise KpolError("Cannot link an empty list of modules")

    total_states = sum(len(m.states) for m in modules)
    if total_states > 64:
        raise KpolError(f"Total concepts ({total_states}) exceeds 64-concept BRAM hardware limit")

    all_reqs: list[Requirement] = []
    all_events: list[EventDecl] = []
    all_states: list[StateDecl] = []
    all_rules: list[Rule] = []
    all_proofs: list[ProofItem] = []

    for m in modules:
        all_reqs.extend(m.requirements)
        all_events.extend(m.events)
        all_states.extend(m.states)
        all_rules.extend(m.rules)
        all_proofs.extend(m.proofs)

    composite = Module(
        target_name,
        tuple(all_reqs),
        tuple(all_events),
        tuple(all_states),
        tuple(all_rules),
        tuple(all_proofs),
        proof_present=any(module.proof_present for module in modules),
    )
    check_module(composite)
    return composite
