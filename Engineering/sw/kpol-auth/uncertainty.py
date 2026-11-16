"""Central registry and fail-closed configuration for KPOL-AUTH open questions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class Span:
    """1-based source location in Unicode codepoints and exact UTF-8 byte offsets."""

    line: int
    column: int
    offset: int
    length: int
    end_line: int = 0
    end_column: int = 0
    byte_offset: int = 0
    byte_end: int = 0

    @property
    def col(self) -> int:
        return self.column

    @property
    def end_col(self) -> int:
        return self.end_column


@dataclass(frozen=True)
class UncertaintyPoint:
    """One unresolved language question with a single diagnostic code."""

    code: str
    rfc: str
    topic: str
    source_status: str
    default_policy: str = "fail-closed"


@dataclass(frozen=True)
class Diagnostic:
    """Explicit diagnostic emitted by the KPOL-AUTH frontend."""

    code: str
    severity: str
    message: str
    span: Span | None = None
    uncertainty_code: str | None = None
    source_ref: str | None = None


class KpolAuthError(Exception):
    """Frontend error raised in fail-closed mode or on syntax violation."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(f"{diagnostic.code}: {diagnostic.message}")


UNCERTAINTY_REGISTRY: dict[str, UncertaintyPoint] = {
    "KPOL-AUTH-U01": UncertaintyPoint(
        code="KPOL-AUTH-U01",
        rfc="RFC-009 п. 2",
        topic="Зв'язок семантичного И (Collection) / ИЛИ (Array) з межами Min/Max",
        source_status="Тимчасова репліка про запуски та И/ИЛИ без правила зв'язку з Min/Max; атрибуція до RFC-009 не підтверджена остаточно",
    ),
    "KPOL-AUTH-U02": UncertaintyPoint(
        code="KPOL-AUTH-U02",
        rfc="RFC-009 п. 3",
        topic="Не-Token індекси Min/Max та поведінка при виході за межі",
        source_status="Поза межами джерела (відповідь не отримана)",
    ),
    "KPOL-AUTH-U03": UncertaintyPoint(
        code="KPOL-AUTH-U03",
        rfc="RFC-015",
        topic="Канонічне написання закривального концепту: CloseBracket проти CloseBracked",
        source_status="Слайд 5 містить CloseBracket, повідомлення Автора — CloseBracked; остаточне написання не узгоджено",
    ),
    "KPOL-AUTH-U04": UncertaintyPoint(
        code="KPOL-AUTH-U04",
        rfc="RFC-015",
        topic="Момент виконання OpenBracket і CloseBracket (транслятор vs рантайм)",
        source_status="Автор позначив заглушками («не придумал», у трансляторі двома функціями)",
    ),
    "KPOL-AUTH-U05": UncertaintyPoint(
        code="KPOL-AUTH-U05",
        rfc="RFC-016 п. 1",
        topic="Нова пара роздільників замість # та призначення звільненого #",
        source_status="Поза межами джерела (відповідь на RFC-016 не отримана)",
    ),
    "KPOL-AUTH-U06": UncertaintyPoint(
        code="KPOL-AUTH-U06",
        rfc="RFC-016 п. 2",
        topic="Запис (екранування/вкладення) закривального знака всередині Text або Help",
        source_status="Поза межами джерела (відповідь на RFC-016 не отримана)",
    ),
    "KPOL-AUTH-U07": UncertaintyPoint(
        code="KPOL-AUTH-U07",
        rfc="RFC-016 п. 3",
        topic="Одиниця вимірювання довжини Name (максимум 16) та полів First/Length",
        source_status="Поза межами джерела (відповідь на RFC-016 не отримана)",
    ),
    "KPOL-AUTH-U08": UncertaintyPoint(
        code="KPOL-AUTH-U08",
        rfc="RFC-017 п. 2",
        topic="Зміст булевого значення • (успіх звернення vs результат підписки B)",
        source_status="Поза межами джерела (відповідь на п. 2 RFC-017 не отримана)",
    ),
    "KPOL-AUTH-U09": UncertaintyPoint(
        code="KPOL-AUTH-U09",
        rfc="RFC-017 п. 1",
        topic="Стан busy концепту A у проміжку між читанням і записом в A • B",
        source_status="Не визначено: у відповіді 3 описано послідовність читання -> підписка -> запис, але не статус busy у проміжку",
    ),
    "KPOL-AUTH-U10": UncertaintyPoint(
        code="KPOL-AUTH-U10",
        rfc="RFC-017 п. 3",
        topic="Читання неініціалізованого стану _ у виразах (напр. C := A + B при A = _)",
        source_status="Поза межами джерела (відповідь на п. 3 RFC-017 не отримана)",
    ),
    "KPOL-AUTH-U11": UncertaintyPoint(
        code="KPOL-AUTH-U11",
        rfc="RFC-018",
        topic="Статус елемента Child та кількість бітів байта Def (7 vs 8)",
        source_status="Автор зазначив «один лишний. Child», але остаточна кількість бітів не визначена («При разработке уточним»)",
    ),
    "KPOL-AUTH-U12": UncertaintyPoint(
        code="KPOL-AUTH-U12",
        rfc="RFC-018 / RFC-010 п. 3",
        topic="Розмежування відсутнього елемента (Def[i]=0) і присутнього елемента зі станом _",
        source_status="Поза межами джерела (відповідь не торкнулася цього питання)",
    ),
}

ALLOWED_POLICIES = frozenset({"fail-closed", "record-diagnostic"})
ALLOWED_NAME_LENGTH_UNITS = frozenset({"utf8_bytes", "codepoints"})


@dataclass(frozen=True)
class AuthFrontendConfig:
    """Single configuration point for all KPOL-AUTH uncertainty policies.

    By default, every registered uncertainty point is `fail-closed`.
    `name_length_unit` controls U07 (`Name` length <= 16) measurement unit:
    - `utf8_bytes` (default, conservative): measure in UTF-8 encoded bytes;
    - `codepoints`: measure in Unicode codepoints.
    """

    policies: Mapping[str, str] = field(
        default_factory=lambda: {code: "fail-closed" for code in UNCERTAINTY_REGISTRY}
    )
    name_length_unit: str = "utf8_bytes"

    def __post_init__(self) -> None:
        if self.name_length_unit not in ALLOWED_NAME_LENGTH_UNITS:
            raise ValueError(
                f"Unsupported name_length_unit '{self.name_length_unit}'"
            )
        merged = {code: "fail-closed" for code in UNCERTAINTY_REGISTRY}
        for code, policy in self.policies.items():
            if code not in UNCERTAINTY_REGISTRY:
                raise ValueError(f"Unknown uncertainty code: {code}")
            if policy not in ALLOWED_POLICIES:
                raise ValueError(f"Unsupported policy '{policy}' for {code}")
            merged[code] = policy
        object.__setattr__(self, "policies", merged)

    def policy_for(self, code: str) -> str:
        if code not in UNCERTAINTY_REGISTRY:
            raise ValueError(f"Unknown uncertainty code: {code}")
        return self.policies[code]


def emit_uncertainty(
    code: str,
    message: str,
    config: AuthFrontendConfig,
    span: Span | None = None,
    diagnostics: list[Diagnostic] | None = None,
) -> Diagnostic:
    """Emit an uncertainty diagnostic and raise KpolAuthError if fail-closed."""
    point = UNCERTAINTY_REGISTRY[code]
    diag = Diagnostic(
        code=code,
        severity="error" if config.policy_for(code) == "fail-closed" else "warning",
        message=message,
        span=span,
        uncertainty_code=code,
        source_ref=point.rfc,
    )
    if diagnostics is not None:
        diagnostics.append(diag)
    if config.policy_for(code) == "fail-closed":
        raise KpolAuthError(diag)
    return diag
