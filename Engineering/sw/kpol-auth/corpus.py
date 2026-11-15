"""Corpus of KPOL-AUTH examples grounded in Author sources and open-question boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusExample:
    """One KPOL-AUTH example with explicit source attribution and expected CST/diagnostic."""

    id: str
    title: str
    source_text: str
    source_refs: tuple[str, ...]
    expected_status: str  # "ok" | "fail-closed"
    expected_cst_kind: str | None
    expected_diagnostics: tuple[str, ...]
    source_boundary_note: str
    in_source_scope: bool = True
    show_to_author: bool = False


AUTHOR_CORPUS: tuple[CorpusExample, ...] = (
    CorpusExample(
        id="EX-01",
        title="Межі виконання групи Min=1, Max=15 (на 1 більше -> 1..16)",
        source_text="Collection(Letter)[Min=1, Max=15]",
        source_refs=(
            "Research/sources/author/introduction-2026-11-13.md (слайд 5)",
            "Research/sources/author/group-execution-2026-11-13.md",
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-009-group-execution-bounds.md",
        ),
        expected_status="ok",
        expected_cst_kind="GroupBoundsCST",
        expected_diagnostics=(),
        source_boundary_note=(
            "Підтверджено дослівно: «min=1 -одно обязательное выполнение max=15 максимум 16 раз. На 1 больше». "
            "Зв'язок И/ИЛИ з Min/Max та не-Token індекси — поза межами джерела."
        ),
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-02",
        title="Типове виконання групи Min=1, Max=0 (один запуск)",
        source_text="{ Item }[Min=1, Max=0]",
        source_refs=(
            "Research/sources/author/introduction-2026-11-13.md (слайд 3)",
            "Research/sources/author/group-execution-2026-11-13.md",
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-009-group-execution-bounds.md",
        ),
        expected_status="ok",
        expected_cst_kind="GroupBoundsCST",
        expected_diagnostics=(),
        source_boundary_note=(
            "За правилом «на 1 больше» Max=0 дає max_effective=1 (одне виконання). "
            "Алгоритм вибірки та підрахунку елементів — поза межами джерела."
        ),
        show_to_author=False,
    ),
    CorpusExample(
        id="EX-03",
        title="Порядок бітів байта Def: зліва молодший, справа старший (7 елементів без Child)",
        source_text="Def(1, 0, 1, 0, 0, 0, 0)",
        source_refs=(
            "Research/sources/author/introduction-2026-11-13.md (слайд 2)",
            "Research/sources/author/clarifications-2026-11-13.md (RFC-010)",
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-018-def-bitmask-order-and-empty-vs-uninit.md",
        ),
        expected_status="ok",
        expected_cst_kind="DefLayoutCST",
        expected_diagnostics=(),
        source_boundary_note=(
            "Підтверджено дослівно: «слева младший-справа старший». "
            "Статус 8-го біта Child і розрізнення Def[i]=0 проти '_' — поза межами джерела."
        ),
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-04",
        title="OpenBracket і CloseBracket як структурні заглушки у Static",
        source_text="Static(OpenBracket, ItemA, CloseBracket)",
        source_refs=(
            "Research/sources/author/clarifications-2026-11-13.md",
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-015-executable-brackets-in-static.md",
        ),
        expected_status="ok",
        expected_cst_kind="CallOrConstructCST",
        expected_diagnostics=(),
        source_boundary_note=(
            "Підтверджено дослівно: «Считай пока заглушками обозначающими открывающую и соответствующую закрывающую. "
            "В трансляторе реализовано двумя функциями.» Момент виконання та написання CloseBracket/CloseBracked — поза межами джерела."
        ),
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-05",
        title="A • B — подія/послідовність запуску підписки (крок Евкліда, НЕ not)",
        source_text="(A, B) • Do(A, B)",
        source_refs=(
            "Research/sources/author/introduction-2026-11-13.md (слайд 3)",
            "Research/sources/author/clarifications-2026-11-13.md (RFC-013)",
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md",
        ),
        expected_status="ok",
        expected_cst_kind="SubscriptionSeqCST",
        expected_diagnostics=(),
        source_boundary_note=(
            "Підтверджено дослівно: підписка B стартує після читання поточного значення, результат записується в A. "
            "Булеве значення '•' і статус busy між читанням та записом — поза межами джерела."
        ),
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-06",
        title="Відхилення похідного унарного '• Flag' (не є not у native-діалекті)",
        source_text="• Flag",
        source_refs=(
            "Research/sources/author/introduction-2026-11-13.md (слайд 3)",
            "Research/studies/author-semantics/kpol-syntax-155-report.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-SYNTAX-03",),
        source_boundary_note="У native-діалекті '•' є послідовністю підписки, а не унарним запереченням 'not'.",
        show_to_author=False,
    ),
    CorpusExample(
        id="EX-07",
        title="RFC-009 п. 2: зв'язок И/ИЛИ з Min/Max",
        source_text="Collection(A, B, C)[Min=1, Max=2, Logic=AND]",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-009-group-execution-bounds.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U01",),
        source_boundary_note="Поза межами джерела: тимчасова репліка Автора про И/ИЛИ не пояснює зв'язок із Min/Max.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-08",
        title="RFC-009 п. 3: не-Token індекс для Min",
        source_text="Array(A, B)[Min=Byte(1), Max=2]",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-009-group-execution-bounds.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U02",),
        source_boundary_note="Поза межами джерела: не-Token індекси та вихід за межі не визначені.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-09",
        title="RFC-015: конфлікт написання CloseBracked проти CloseBracket",
        source_text="Static(OpenBracket, A, CloseBracked)",
        source_refs=(
            "Research/sources/author/clarifications-2026-11-13.md (§3)",
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-015-executable-brackets-in-static.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U03",),
        source_boundary_note="Поза межами джерела: остаточне написання CloseBracket vs CloseBracked не підтверджено.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-10",
        title="RFC-015: невизначений момент виконання дужок (@runtime)",
        source_text="Static(@runtime, OpenBracket, A, CloseBracket)",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-015-executable-brackets-in-static.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U04",),
        source_boundary_note="Поза межами джерела: Автор позначив момент виконання дужок як не визначений («не придумал»).",
        in_source_scope=False,
        show_to_author=False,
    ),
    CorpusExample(
        id="EX-11",
        title="RFC-016 п. 1: використання звільненого '#' без нової пари роздільників",
        source_text="#legacy_comment",
        source_refs=(
            "Research/sources/author/clarifications-2026-11-13.md (RFC-011)",
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-016-updated-delimiters-after-hash.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U05",),
        source_boundary_note="Поза межами джерела: нова пара знаків замість '#' не повідомлена.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-12",
        title="RFC-016 п. 2: екранування закривального знака всередині Text/Help",
        source_text='"text \\" quote"',
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-016-updated-delimiters-after-hash.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U06",),
        source_boundary_note="Поза межами джерела: спосіб запису закривального знака всередині тексту не визначений.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-13",
        title="RFC-016 п. 3: одиниця вимірювання довжини Name (не-ASCII на межі 16)",
        source_text='Name("ПривітСвітДовгеІм")',
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-016-updated-delimiters-after-hash.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U07",),
        source_boundary_note="Поза межами джерела: не визначено, чи межа 16 рахується у буквах, байтах чи 4-бітних Token.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-14",
        title="RFC-017 п. 2: використання '•' як булевого значення",
        source_text="Flag := (A • B)",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U08",),
        source_boundary_note="Поза межами джерела: зміст булевого значення '•' не визначений.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-15",
        title="RFC-017 п. 1: перевірка busy між читанням і записом в A • B",
        source_text="A • busy(A)",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U09",),
        source_boundary_note="Поза межами джерела: стан busy у проміжку між читанням і записом прямо не визначений.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-16",
        title="RFC-017 п. 3: читання стану '_' в арифметичному виразі",
        source_text="C := _ + B",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-017-busy-release-and-uninitialized-ops.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U10",),
        source_boundary_note="Поза межами джерела: поведінка обчислення при читанні '_' не визначена.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-17",
        title="RFC-018: 8-бітний Def із елементом Child",
        source_text="Def(1, 0, 0, 0, 0, 0, 0, 1)",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-018-def-bitmask-order-and-empty-vs-uninit.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U11",),
        source_boundary_note="Поза межами джерела: Автор назвав Child «лишним», остаточна ширина Def не визначена.",
        in_source_scope=False,
        show_to_author=True,
    ),
    CorpusExample(
        id="EX-18",
        title="RFC-018 / RFC-010 п. 3: розрізнення Def[i]=0 і значення '_'",
        source_text="Property(DefBit=1, Value=_)",
        source_refs=(
            "drafts@84812f6:KuzminMachine/RFC/details/RFC-018-def-bitmask-order-and-empty-vs-uninit.md",
        ),
        expected_status="fail-closed",
        expected_cst_kind=None,
        expected_diagnostics=("KPOL-AUTH-U12",),
        source_boundary_note="Поза межами джерела: розрізнення відсутнього елемента і присутнього зі станом '_' не визначене.",
        in_source_scope=False,
        show_to_author=True,
    ),
)
