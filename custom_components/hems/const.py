"""Public integration constants."""

DOMAIN = "hems"
VERSION = "0.1.0a9"
PLATFORMS = ["sensor", "binary_sensor", "switch"]
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
MAX_AGE = 120
DECISION_MAX_AGE = 90
COMMUNICATION_TIMEOUT = 180
WRITE_TIMEOUT = 120
FAULT_RETRY_SECONDS = 300
DEFAULT_INTERVAL = 20
