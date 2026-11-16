"""KPOL-AUTH native dialect frontend prototype (lexer, CST, uncertainty registry, corpus)."""

if __package__:
    from .corpus import AUTHOR_CORPUS, CorpusExample
    from .cst import (
        AssignmentCST,
        BinaryExprCST,
        BracketGroupCST,
        CSTNode,
        CallOrConstructCST,
        DefLayoutCST,
        GroupBoundsCST,
        IdentifierCST,
        LiteralCST,
        ParamCST,
        ProgramCST,
        SubscriptionSeqCST,
        UninitCST,
        parse_kpol_auth,
    )
    from .lexer import Token, tokenize
    from .lowering import (
        KpolAuthLoweringError,
        LoweredArtifact,
        LoweredConcept,
        LoweredSubscription,
        km_pack_instr,
        lower_kpol_auth,
    )
    from .uncertainty import (
        UNCERTAINTY_REGISTRY,
        AuthFrontendConfig,
        Diagnostic,
        KpolAuthError,
        Span,
        UncertaintyPoint,
    )

__all__ = [
    "AUTHOR_CORPUS",
    "AssignmentCST",
    "AuthFrontendConfig",
    "BinaryExprCST",
    "BracketGroupCST",
    "CSTNode",
    "CallOrConstructCST",
    "CorpusExample",
    "DefLayoutCST",
    "Diagnostic",
    "GroupBoundsCST",
    "IdentifierCST",
    "KpolAuthError",
    "KpolAuthLoweringError",
    "LiteralCST",
    "LoweredArtifact",
    "LoweredConcept",
    "LoweredSubscription",
    "ParamCST",
    "ProgramCST",
    "Span",
    "SubscriptionSeqCST",
    "Token",
    "UNCERTAINTY_REGISTRY",
    "UncertaintyPoint",
    "UninitCST",
    "km_pack_instr",
    "lower_kpol_auth",
    "parse_kpol_auth",
    "tokenize",
]
