"""Core tests run without importing Home Assistant's integration entrypoint."""

from pathlib import Path
import sys
import types

root = Path(__file__).resolve().parents[1]
package = types.ModuleType("custom_components.hems")
package.__path__ = [str(root / "custom_components" / "hems")]
sys.modules["custom_components.hems"] = package
