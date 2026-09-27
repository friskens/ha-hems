"""Dependency-free packaging and translation consistency checks."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "hems"


def leaves(value, prefix=()):
    result = {}
    for key, child in value.items():
        path = prefix + (key,)
        if isinstance(child, dict):
            result.update(leaves(child, path))
        else:
            result[path] = child
    return result


def check():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
    const = ast.parse((INTEGRATION / "const.py").read_text(encoding="utf-8"))
    values = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in const.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert manifest["domain"] == "hems"
    assert manifest["version"] == values["VERSION"], "Manifest and runtime versions differ"
    assert manifest["config_flow"] is True
    assert manifest["codeowners"] and manifest["documentation"]
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert hacs["homeassistant"] and hacs["name"]
    base = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    flat = leaves(base)
    for language in ("en", "sv"):
        translated = json.loads(
            (INTEGRATION / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        actual = leaves(translated)
        assert flat.keys() == actual.keys(), f"{language}: missing or unexpected translation keys"
        assert all(isinstance(value, str) and value.strip() for value in actual.values()), language
        if language == "en":
            assert base == translated, "English source and translation differ"
    assert set(base["entity"]["sensor"]["decision"]["state"]) == set(values["COMMANDS"])
    assert (ROOT / "LICENSE").is_file()
    assert (INTEGRATION / "__init__.py").is_file()
    print(f"Packaging and en/sv translations validated for {manifest['version']} ({len(flat)} strings).")


if __name__ == "__main__":
    check()
