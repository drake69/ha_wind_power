"""Consistency guard: every ``translation_key`` used by a SelectSelector in
``config_flow.py`` must have matching entries in the base translation file
(``strings.json``).

Home Assistant lets a SelectSelector replace inline option labels with a
``translation_key`` that resolves human-readable text from the translation
files (``selector.<key>.options.<value>``). If the key is referenced but the
translation file lacks the corresponding ``selector`` entries, the dropdown
silently shows the raw option values (e.g. ``influxdb``) instead of a label —
a UX regression that no other test catches.

This test parses ``config_flow.py`` statically (via ``ast``, no HA import) and
fails when a referenced ``translation_key`` is missing options in the base
file. It is intentionally a no-op while the config flow uses inline labels; it
activates the moment someone migrates a selector to ``translation_key``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from custom_components.wind_power import const

_COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "wind_power"
_CONFIG_FLOW = _COMPONENT / "config_flow.py"
_BASE_JSON = _COMPONENT / "strings.json"


def _resolve_options(
    node: ast.AST, assignments: dict[str, ast.AST] | None = None
) -> set[str] | None:
    """Resolve a SelectSelectorConfig ``options=`` argument to its string values.

    Accepts the options written either **inline** (``options=[...]``,
    ``options=list(DICT.keys())``) or **via a local variable**
    (``opts = [...]`` then ``options=opts``). In the variable case the name is
    looked up in ``assignments`` (name -> assigned value node, collected from
    the module) and resolved recursively.

    Returns ``None`` when the expression cannot be resolved statically, so the
    caller can fail loudly rather than pass a false negative.
    """
    assignments = assignments or {}
    # options=opts -> follow the variable assignment and resolve its value.
    if isinstance(node, ast.Name):
        # A bare name may be a constant from const (e.g. a list/dict)...
        if hasattr(const, node.id):
            resolved = getattr(const, node.id)
            if isinstance(resolved, dict):
                return set(resolved.keys())
            if isinstance(resolved, (list, tuple, set)):
                return set(resolved)
        # ...or a local/module variable assigned an inline expression.
        target = assignments.get(node.id)
        return _resolve_options(target, assignments) if target is not None else None
    # options=[CONST_A, CONST_B] or [SelectOptionDict(value=CONST, ...), ...]
    if isinstance(node, ast.List):
        values: set[str] = set()
        for elt in node.elts:
            if isinstance(elt, ast.Name):
                values.add(getattr(const, elt.id))
            elif isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.add(elt.value)
            elif isinstance(elt, ast.Call):
                # SelectOptionDict(value=..., label=...)
                value_kw = next((kw for kw in elt.keywords if kw.arg == "value"), None)
                if value_kw is None:
                    return None
                if isinstance(value_kw.value, ast.Name):
                    values.add(getattr(const, value_kw.value.id))
                elif isinstance(value_kw.value, ast.Constant):
                    values.add(value_kw.value.value)
                else:
                    return None
            else:
                return None
        return values
    # options=list(SOME_DICT.keys()) / list(SOME_DICT) etc.
    if isinstance(node, ast.Call):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and hasattr(const, sub.id):
                resolved = getattr(const, sub.id)
                if isinstance(resolved, dict):
                    return set(resolved.keys())
    # options=[SelectOptionDict(value=k, ...) for k, v in SOME_DICT.items()]
    if isinstance(node, ast.ListComp):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and hasattr(const, sub.id):
                resolved = getattr(const, sub.id)
                if isinstance(resolved, dict):
                    return set(resolved.keys())
    return None


def _collect_assignments(tree: ast.AST) -> dict[str, ast.AST]:
    """Map ``name -> assigned value node`` for simple ``name = <expr>`` statements.

    Lets ``_resolve_options`` follow ``options=opts`` back to ``opts = [...]``.
    Module-wide, last assignment wins — enough for the option-list variables the
    config flow uses (each assigned once inside its step).
    """
    assignments: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            assignments[node.targets[0].id] = node.value
    return assignments


def _collect_translation_keyed_selectors() -> list[tuple[str, set[str] | None]]:
    tree = ast.parse(_CONFIG_FLOW.read_text())
    assignments = _collect_assignments(tree)
    out: list[tuple[str, set[str] | None]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "SelectSelectorConfig"
        ):
            continue
        tk_kw = next((kw for kw in node.keywords if kw.arg == "translation_key"), None)
        if tk_kw is None or not isinstance(tk_kw.value, ast.Constant):
            continue
        opt_kw = next((kw for kw in node.keywords if kw.arg == "options"), None)
        options = _resolve_options(opt_kw.value, assignments) if opt_kw is not None else None
        out.append((tk_kw.value.value, options))
    return out


def test_translation_keys_have_matching_options_in_base_json():
    """Each translation_key selector must have all its options translated."""
    selectors = _collect_translation_keyed_selectors()
    if not selectors:
        # Config flow uses inline labels — nothing to validate (guard is dormant).
        return

    base = json.loads(_BASE_JSON.read_text())
    selector_section = base.get("selector", {})

    errors: list[str] = []
    for translation_key, options in selectors:
        entry = selector_section.get(translation_key)
        if entry is None:
            errors.append(
                f"translation_key '{translation_key}' missing from base 'selector' section"
            )
            continue
        translated = set(entry.get("options", {}).keys())
        if options is None:
            errors.append(
                f"translation_key '{translation_key}': options could not be resolved statically — "
                "extend _resolve_options() in this test"
            )
            continue
        missing = options - translated
        if missing:
            errors.append(
                f"translation_key '{translation_key}' missing option labels in base json: {sorted(missing)}"
            )

    assert not errors, "Selector translation inconsistencies:\n  " + "\n  ".join(errors)


def _options_of(src: str) -> set[str] | None:
    """Resolve the ``options=`` of the first SelectSelectorConfig in a snippet."""
    tree = ast.parse(src)
    assignments = _collect_assignments(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "SelectSelectorConfig"
        ):
            opt = next((kw for kw in node.keywords if kw.arg == "options"), None)
            return _resolve_options(opt.value, assignments) if opt is not None else None
    return None


class TestResolveOptionsFromVariable:
    """_resolve_options must follow options passed via a local variable."""

    def test_variable_holding_const_list(self):
        src = (
            "opts = [SOURCE_INFLUX, SOURCE_NONE]\n"
            "selector.SelectSelectorConfig(options=opts, translation_key='backfill_source')\n"
        )
        assert _options_of(src) == {const.SOURCE_INFLUX, const.SOURCE_NONE}

    def test_inline_list_still_resolves(self):
        src = "selector.SelectSelectorConfig(options=[UNIT_KN], translation_key='x')\n"
        assert _options_of(src) == {const.UNIT_KN}

    def test_select_option_dict_resolves(self):
        src = (
            "selector.SelectSelectorConfig(options=["
            "selector.SelectOptionDict(value=SOURCE_INFLUX, label='x'),"
            "selector.SelectOptionDict(value=SOURCE_NONE, label='y')],"
            " translation_key='backfill_source')\n"
        )
        assert _options_of(src) == {const.SOURCE_INFLUX, const.SOURCE_NONE}

    def test_unknown_variable_returns_none(self):
        src = "selector.SelectSelectorConfig(options=mystery, translation_key='x')\n"
        assert _options_of(src) is None
