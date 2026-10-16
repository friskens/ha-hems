"""Public integration constants."""

DOMAIN = "hems"
VERSION = "0.2.0a1"
PLATFORMS = ["sensor", "binary_sensor", "switch"]
# Known decision states for translations only. They are not a list of commands
# this integration can execute; HEMS Client never actuates equipment.
COMMANDS = (
    "charge",
    "chargesolar",
    "selfconsumption",
    "sellsolar",
    "pause",
    "export",
    "peakshaving",
    "zeroexport",
    "observe",
)
REQUIRED_FIELDS = ("soc", "grid_power", "solar_power", "battery_power")
PHASE_CURRENT_ENTITY_KEYS = (
    "phase_l1_current_entity",
    "phase_l2_current_entity",
    "phase_l3_current_entity",
)
DECISION_MAX_AGE = 90
DEFAULT_INTERVAL = 20
