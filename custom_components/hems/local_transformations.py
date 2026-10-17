"""Small, declarative evaluator for contract-local transformations.

The HEMS contract is authoritative for how an existing Home Assistant state is
normalised before it is sent.  Expressions are *not* Python, Jinja, or a
template language: this module accepts a deliberately tiny arithmetic grammar
and evaluates its parsed AST without names, imports, attribute lookup, or
calls outside the two explicitly supported numeric functions.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class TransformationError(ValueError):
    """A contract rule is not part of the safe local transformation grammar."""


@dataclass(frozen=True)
class LocalOptions:
    """Only explicitly declared input options are visible to an expression."""

    values: Mapping[str, bool]

    def get(self, name: str) -> bool:
        if name not in self.values:
            raise TransformationError("unknown_option")
        return self.values[name]


def expression_uses_values(expression: str) -> bool:
    """Whether a rule consumes the selected-source collection, not one value."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as err:
        raise TransformationError("invalid_expression") from err
    return any(isinstance(node, ast.Name) and node.id == "values" for node in ast.walk(tree))


def evaluate(expression: str, *, value: float | None = None, values: list[float] | None = None,
             unit: str | None = None, options: Mapping[str, bool] | None = None) -> float:
    """Evaluate one bounded numeric contract expression.

    The only available values are ``value``, ``values``, ``unit`` and declared
    ``option.<name>`` flags.  This keeps a downloaded contract data-only while
    still allowing its declared, portable unit/sign/aggregation transforms.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as err:
        raise TransformationError("invalid_expression") from err
    context: dict[str, Any] = {
        "value": value,
        "values": values,
        "unit": unit,
        "option": LocalOptions(options or {}),
    }
    result = _evaluate(tree.body, context)
    if isinstance(result, bool):
        raise TransformationError("non_numeric_result")
    try:
        numeric = float(result)
    except (TypeError, ValueError) as err:
        raise TransformationError("non_numeric_result") from err
    if not math.isfinite(numeric):
        raise TransformationError("non_finite_result")
    return numeric


def _evaluate(node: ast.AST, context: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool)) and not isinstance(node.value, complex):
            return node.value
        raise TransformationError("invalid_literal")
    if isinstance(node, ast.Name):
        if node.id in context:
            return context[node.id]
        raise TransformationError("unknown_name")
    if isinstance(node, ast.IfExp):
        return _evaluate(node.body if _truth(_evaluate(node.test, context)) else node.orelse, context)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _number(_evaluate(node.operand, context))
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left, right = _number(_evaluate(node.left, context)), _number(_evaluate(node.right, context))
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise TransformationError("division_by_zero")
            return left / right
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left, right = _evaluate(node.left, context), _evaluate(node.comparators[0], context)
        if isinstance(node.ops[0], ast.Eq):
            return left == right
        if isinstance(node.ops[0], ast.NotEq):
            return left != right
        if isinstance(node.ops[0], ast.Lt):
            return _number(left) < _number(right)
        if isinstance(node.ops[0], ast.LtE):
            return _number(left) <= _number(right)
        if isinstance(node.ops[0], ast.Gt):
            return _number(left) > _number(right)
        if isinstance(node.ops[0], ast.GtE):
            return _number(left) >= _number(right)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "option":
        return context["option"].get(node.attr)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords and len(node.args) == 1:
        argument = _evaluate(node.args[0], context)
        if node.func.id == "abs":
            return abs(_number(argument))
        if node.func.id == "sum" and isinstance(argument, list):
            return sum(_number(item) for item in argument)
    raise TransformationError("unsupported_expression")


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise TransformationError("non_numeric_operand")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as err:
        raise TransformationError("non_numeric_operand") from err
    if not math.isfinite(numeric):
        raise TransformationError("non_finite_operand")
    return numeric


def _truth(value: Any) -> bool:
    if not isinstance(value, bool):
        raise TransformationError("non_boolean_condition")
    return value
