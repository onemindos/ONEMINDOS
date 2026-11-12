# SPDX-License-Identifier: Apache-2.0
"""Property tests: the Market licence classifier (contract §9.4 check 2, sdk/tools/applib/licence.py).

classify() maps an SPDX expression to L1 (permissive) < L2 (copyleft) < blocked. OR means the user
may pick a term, so it takes the best class; AND means every term applies, so it takes the worst.
Over the order L1 < L2 < blocked that is a distributive lattice (OR = min, AND = max), so:

- classify() agrees with a reference evaluator on every generated expression, written fully
  parenthesised or with the fewest parentheses SPDX precedence allows (WITH > AND > OR);
- commutative, associative, idempotent, absorption and distributive laws hold for OR and AND;
- adding a term with OR never makes the class worse, with AND never better;
- anything that is not a well-formed expression is blocked (fail closed), and no input raises;
- gate(): without a research-matrix row, GitHub's one confirmed term caps the class, so
  "MIT OR <GitHub's licence>" can never lift a copyleft or blocked licence (§9.4);
- normalise(), which drops notes such as "MIT (test data)" before a matrix row is compared, keeps
  the class of an expression written the usual way.

Known gap, a strict xfail (docs/testing/PROPERTY-AND-FUZZ.md, finding F-LIC-1): normalise() also
drops a parenthesised single id, "(MIT)", so a matrix row confirms a different expression.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "tools"))
from applib import licence  # noqa: E402
from props import budget  # noqa: E402

RANK = {"L1": 0, "L2": 1, "blocked": 2}
OPS = {"AND", "OR", "WITH"}


def best(a: str, b: str) -> str:
    return a if RANK[a] <= RANK[b] else b


def worst(a: str, b: str) -> str:
    return a if RANK[a] >= RANK[b] else b


# ---- expressions and their reference value ----------------------------------------------------

unknown_ids = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,15}", fullmatch=True).filter(
    lambda t: t.upper() not in OPS and t not in licence.L1 and t not in licence.L2
)
ids = (
    st.sampled_from(sorted(licence.L1))
    | st.sampled_from(sorted(licence.L2))
    | st.sampled_from(["BUSL-1.1", "SSPL-1.0", "Elastic-2.0", "PolyForm-Noncommercial-1.0.0", "CC-BY-NC-4.0",
                       "LicenseRef-proprietary", "NOASSERTION", "NONE"])
    | unknown_ids
)
exceptions = st.sampled_from(sorted(licence.KNOWN_EXCEPTIONS)) | unknown_ids


def tree(leaves=ids):
    """("id", x) | ("with", x, exception) | ("and"|"or", left, right)"""
    atom = leaves.map(lambda x: ("id", x)) | st.tuples(st.just("with"), leaves, exceptions)
    return st.recursive(
        atom, lambda sub: st.tuples(st.sampled_from(["and", "or"]), sub, sub), max_leaves=8
    )


def value(t) -> str:
    """The reference: the class from the sets alone, min for OR, max for AND."""
    if t[0] in ("id", "with"):
        cls = "L1" if t[1] in licence.L1 else "L2" if t[1] in licence.L2 else "blocked"
        return cls if t[0] == "id" or t[2] in licence.KNOWN_EXCEPTIONS else "blocked"
    a, b = value(t[1]), value(t[2])
    return best(a, b) if t[0] == "or" else worst(a, b)


def full(t) -> str:
    if t[0] == "id":
        return t[1]
    if t[0] == "with":
        return f"{t[1]} WITH {t[2]}"
    return f"({full(t[1])}) {t[0].upper()} ({full(t[2])})"


def minimal(t, parent: str | None = None) -> str:
    """Parentheses only where SPDX precedence needs them: an OR inside an AND."""
    if t[0] in ("id", "with"):
        return full(t)
    s = f"{minimal(t[1], t[0])} {t[0].upper()} {minimal(t[2], t[0])}"
    return f"({s})" if parent == "and" and t[0] == "or" else s


@budget(300)
@given(t=tree())
def test_classify_agrees_with_the_reference(t):
    assert licence.classify(full(t)) == value(t), full(t)
    assert licence.classify(minimal(t)) == value(t), minimal(t)


# ---- lattice laws ------------------------------------------------------------------------------

exprs = tree().map(full)


def c(*parts: str) -> str:
    """classify() of the parts, each wrapped in parentheses: c("a", "OR", "b") = classify("(a) OR (b)")."""
    return licence.classify(" ".join(p if p in OPS else f"({p})" for p in parts))


@budget(200)
@given(a=exprs, b=exprs, k=exprs)
def test_or_and_and_are_lattice_operations(a, b, k):
    for op in ("OR", "AND"):
        assert c(a, op, b) == c(b, op, a), "commutative"
        assert licence.classify(f"(({a}) {op} ({b})) {op} ({k})") == licence.classify(f"({a}) {op} (({b}) {op} ({k}))"), "associative"
        assert c(a, op, a) == licence.classify(a), "idempotent"
    assert licence.classify(f"({a}) OR (({a}) AND ({b}))") == licence.classify(a), "absorption"
    assert licence.classify(f"({a}) AND (({a}) OR ({b}))") == licence.classify(a), "absorption"
    assert licence.classify(f"({a}) AND (({b}) OR ({k}))") == licence.classify(f"(({a}) AND ({b})) OR (({a}) AND ({k}))"), "distributive"
    assert licence.classify(f"({a}) OR (({b}) AND ({k}))") == licence.classify(f"(({a}) OR ({b})) AND (({a}) OR ({k}))"), "distributive"


@budget(200)
@given(a=exprs, b=exprs)
def test_or_never_worsens_and_never_improves(a, b):
    assert RANK[c(a, "OR", b)] <= RANK[licence.classify(a)]
    assert RANK[c(a, "AND", b)] >= RANK[licence.classify(a)]
    assert c(a, "OR", b) == best(licence.classify(a), licence.classify(b))
    assert c(a, "AND", b) == worst(licence.classify(a), licence.classify(b))


# ---- fail closed -------------------------------------------------------------------------------

def well_formed(tokens: list[str]) -> bool:
    """SPDX grammar (Annex D), plus the one leniency classify() documents by behaviour: a WITH after a
    parenthesised group (the exception must still be on the known list, so it cannot lift a class).

        expr := term (("AND" | "OR") term)*
        term := id ["WITH" id] | "(" expr ")" ["WITH" id]
    """
    pos = 0

    def tok() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def is_id(t: str | None) -> bool:
        return t is not None and t not in ("(", ")") and t.upper() not in OPS

    def term() -> bool:
        nonlocal pos
        if tok() == "(":
            pos += 1
            if not expr() or tok() != ")":
                return False
            pos += 1
        elif is_id(tok()):
            pos += 1
        else:
            return False
        if tok() is not None and tok().upper() == "WITH":
            pos += 1
            if not is_id(tok()):
                return False
            pos += 1
        return True

    def expr() -> bool:
        nonlocal pos
        if not term():
            return False
        while tok() is not None and tok().upper() in ("AND", "OR"):
            pos += 1
            if not term():
                return False
        return True

    return expr() and pos == len(tokens)


token_soup = st.lists(
    st.sampled_from(["(", ")", "AND", "OR", "WITH", "and", "or", "MIT", "Apache-2.0", "GPL-3.0", "SSPL-1.0",
                     "LLVM-exception"]) | ids,
    min_size=0, max_size=10,
)


@budget(300)
@given(tokens=token_soup)
def test_anything_malformed_is_blocked(tokens):
    got = licence.classify(" ".join(tokens))
    assert got in RANK
    if not well_formed(tokens):
        assert got == "blocked", tokens


@budget(300)
@given(text=st.text())
def test_any_text_gets_a_class_and_never_raises(text):
    assert licence.classify(text) in RANK


# ---- the gate (§9.4): GitHub's one term caps the class --------------------------------------------

@budget(200)
@given(t=tree(), data=st.data())
def test_github_alone_never_lifts_the_class(t, data):
    manifest = full(t)
    terms = sorted(licence.ids_in(manifest))
    github = data.draw(st.sampled_from(terms) | ids, label="github spdx")
    assume(github not in ("NOASSERTION", "NONE"))
    cls, notes = licence.gate(manifest, github, [])
    if github in terms:
        assert cls == worst(licence.classify(manifest), licence.classify(github)), notes
    else:
        assert cls == "blocked", notes
    # a research-matrix row for the whole expression is the only way to the expression's own class
    row = {"SPDX": manifest, "component": "x", "version": "1"}
    assert licence.gate(manifest, None, [row])[0] == licence.classify(manifest)


@budget(200)
@given(t=tree())
def test_normalise_keeps_the_class(t):
    assert licence.classify(licence.normalise(minimal(t))) == licence.classify(minimal(t)), minimal(t)


@pytest.mark.xfail(strict=True, reason="finding F-LIC-1: normalise() drops '(MIT)' as if it were a note")
def test_a_matrix_row_confirms_only_its_own_expression():
    """The repo's matrix row says AGPL or a commercial licence; the manifest claims MIT or Apache.
    Both normalise to "OR", so the row 'confirms' the manifest and the gate answers L1."""
    row = {"SPDX": "(AGPL-3.0) OR (LicenseRef-commercial)", "component": "example", "version": "1.0"}
    assert licence.gate("(MIT) OR (Apache-2.0)", None, [row])[0] == "blocked"
