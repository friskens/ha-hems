"""Safe declarative presentation derived from the HEMS output contract.

Only this deliberately small grammar is accepted.  The HEMS contract owns the
presentation rules, including its declarative expressions.  Expressions are
therefore evaluated here, but only with a deliberately non-executable AST
grammar: they cannot call code, access attributes, index data or perform a
Home Assistant action.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import operator
from typing import Any, Mapping


@dataclass(frozen=True)
class OutputSpec:
    key: str
    entity: str
    unique_id: str
    source: str
    definition: Mapping[str, Any]


class ExpressionError(ValueError):
    """The contract expression is outside the non-executable presentation DSL."""


_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}


def evaluate_expression(expression: str, values: Mapping[str, Any]) -> Any:
    """Evaluate only literals, names, arithmetic, comparisons and conditionals.

    This intentionally rejects calls, attributes, indexing, comprehensions and
    every other Python construct.  The contract is data, never executable code.
    """
    if not isinstance(expression, str) or len(expression) > 200:
        raise ExpressionError("invalid_expression")
    try:
        root = ast.parse(expression, mode="eval").body
    except SyntaxError as err:
        raise ExpressionError("invalid_expression") from err

    def visit(node, literal_token: bool = False):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in values:
                # The contract uses unquoted tokens for enum-like result
                # values (for example ``connected if ... else warning``).
                # They are data labels only in an if-expression result; an
                # unknown input to arithmetic/comparison remains invalid.
                if literal_token:
                    return node.id
                raise ExpressionError("unknown_name")
            return values[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            return _BINARY[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -visit(node.operand) if isinstance(node.op, ast.USub) else +visit(node.operand)
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1 and type(node.ops[0]) in _COMPARE:
            return _COMPARE[type(node.ops[0])](visit(node.left), visit(node.comparators[0]))
        if isinstance(node, ast.IfExp):
            return (
                visit(node.body, literal_token=True)
                if visit(node.test)
                else visit(node.orelse, literal_token=True)
            )
        raise ExpressionError("unsupported_expression")

    try:
        return visit(root)
    except (ArithmeticError, TypeError, ValueError) as err:
        raise ExpressionError("invalid_expression_value") from err


def _names(value: Any) -> bool:
    return isinstance(value, Mapping) and any(isinstance(name, str) and name.strip() for name in value.values())


def _spec(key: str, value: Any, source: str) -> OutputSpec | None:
    if not isinstance(value, Mapping):
        return None
    entity, unique_id = value.get("entity"), value.get("unique_id")
    if entity not in {"sensor", "binary_sensor"} or not isinstance(unique_id, str) or not unique_id.strip():
        return None
    if not _names(value.get("names")):
        return None
    return OutputSpec(key, entity, unique_id, source, value)


def output_specs(contract) -> tuple[OutputSpec, ...]:
    """Compile the supported, declarative output grammar from the contract."""
    if contract is None:
        return ()
    decision = contract.output("decision")
    if not isinstance(decision, Mapping):
        return ()
    result: list[OutputSpec] = []
    state_from = decision.get("state_from")
    core = _spec("decision", decision, state_from)
    if core is not None and isinstance(state_from, str) and state_from:
        result.append(core)
    attributes = decision.get("attributes")
    extras = decision.get("extra_entities")
    if isinstance(attributes, Mapping) and isinstance(extras, Mapping):
        for key, value in extras.items():
            if not isinstance(key, str) or not isinstance(value, Mapping):
                continue
            source = value.get("from")
            if not isinstance(source, str) or not source.startswith("attributes."):
                continue
            attribute = source.removeprefix("attributes.")
            if attribute not in attributes or "." in attribute:
                continue
            spec = _spec(key, value, source)
            if spec is not None:
                result.append(spec)
    # A local top-level output is entirely contract-defined.  It is allowed
    # only when its state comes from the restricted expression grammar.
    # This is how the current connection sensor is declared, but there is no
    # connection-specific evaluator here.
    for key, definition in contract.outputs.items():
        if key == "decision" or not isinstance(definition, Mapping):
            continue
        if definition.get("local") is not True or not isinstance(definition.get("expression"), str):
            continue
        spec = _spec(key, definition, "expression")
        if spec is not None:
            result.append(spec)
    return tuple(result)


def load_attributes(contract) -> tuple[str, ...]:
    """Return the contract's display-only load fields, never arbitrary JSON."""
    loads = contract.output("loads") if contract else None
    if not isinstance(loads, Mapping):
        return ()
    entry, per_entry = loads.get("entry"), loads.get("entity_per_entry")
    fields = per_entry.get("attributes_from_entry") if isinstance(per_entry, Mapping) else None
    if not isinstance(entry, Mapping) or not isinstance(fields, (list, tuple)):
        return ()
    return tuple(field for field in fields if isinstance(field, str) and field in entry)


def display_name(runtime, spec: OutputSpec) -> str:
    """Choose a contract label without requiring a static translation key."""
    names = spec.definition["names"]
    hass = getattr(runtime, "hass", None)
    config = getattr(hass, "config", None)
    language = getattr(config, "language", "en").split("-", 1)[0]
    return names.get(language) or names.get("en") or next(iter(names.values()))


def decision_attributes(contract, decision, now: float) -> dict[str, Any]:
    """Render declared decision attributes from response data and safe DSL."""
    definition = contract.output("decision") if contract else None
    attributes = definition.get("attributes") if isinstance(definition, Mapping) else None
    if not isinstance(attributes, Mapping) or decision is None:
        return {}
    values = dict(decision.presentation or {})
    values["received_at"] = decision.received_at
    values["now"] = now
    rendered: dict[str, Any] = {}
    # A bounded fixed-point pass lets a derived field use an earlier declared
    # derived field (e.g. power_w from power_kw), without executing code.
    for _ in range(len(attributes)):
        changed = False
        for name, attribute in attributes.items():
            if not isinstance(name, str) or not isinstance(attribute, Mapping) or name in rendered:
                continue
            expression = attribute.get("expression")
            if isinstance(expression, str):
                try:
                    value = evaluate_expression(expression, values | rendered)
                except ExpressionError:
                    continue
            elif name in values:
                value = values[name]
            else:
                continue
            rendered[name] = value
            changed = True
        if not changed:
            break
    return rendered
