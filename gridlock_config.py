# gridlock_config.py
# =============================================================
#  OPERATION GRIDLOCK -- Shared constants
#  Import this module in every notebook:
#      from gridlock_config import *
# =============================================================
import math as _math

BLUE_BUDGET = 500        # units available to Blue Teams

# ---- Relay nodes -----------------------------------------------
RELAY_NODE_COST = 12     # cost per activated relay node

# ---- Link build costs ------------------------------------------
LINK_BUILD_RATE = {1: 2, 2: 4, 3: 6}   # cost per distance unit
LINK_BUILD_MIN  = {1: 3, 2: 6, 3: 10}  # minimum build cost
ARMOR_MULT      = 2.5                   # armored-link cost multiplier

# ---- Attack costs (flat, independent of link length) -----------
ATK_SEVER   = {1:  6, 2: 12, 3: 20}
ATK_DEGRADE = {1:  3, 2:  6, 3: 10}

# ---- Red-Team budget uncertainty shown to Blue Teams -----------
RED_MIN = 55
RED_MAX = 100

# ---- Network topology (fixed for all Blue Teams) ---------------
SOURCES = {
    "S1": {"x": 1, "y": 9, "supply": 8, "label": "NW Plant"},
    "S2": {"x": 9, "y": 9, "supply": 4, "label": "NE Plant"},
    "S3": {"x": 1, "y": 1, "supply": 5, "label": "SW Plant"},
    "S4": {"x": 9, "y": 1, "supply": 4, "label": "SE Plant"},
}

SINKS = {
    "D1": {"x": 2, "y": 8, "demand": 2, "label": "N-West"},
    "D2": {"x": 5, "y": 9, "demand": 1, "label": "N-Mid"},
    "D3": {"x": 8, "y": 8, "demand": 2, "label": "N-East"},
    "D4": {"x": 1, "y": 5, "demand": 1, "label": "W-Mid"},
    "D5": {"x": 5, "y": 5, "demand": 3, "label": "Downtown"},
    "D6": {"x": 9, "y": 5, "demand": 1, "label": "E-Mid"},
    "D7": {"x": 2, "y": 2, "demand": 1, "label": "S-West"},
    "D8": {"x": 5, "y": 1, "demand": 2, "label": "S-Mid"},
    "D9": {"x": 8, "y": 2, "demand": 1, "label": "S-East"},
}
TOTAL_DEMAND = sum(v["demand"] for v in SINKS.values())   # = 14

RELAY_CANDIDATES = {
    "RC1":  {"x": 3, "y": 8},
    "RC2":  {"x": 7, "y": 8},
    "RC3":  {"x": 2, "y": 6},
    "RC4":  {"x": 4, "y": 7},
    "RC5":  {"x": 6, "y": 7},
    "RC6":  {"x": 8, "y": 6},
    "RC7":  {"x": 3, "y": 5},
    "RC8":  {"x": 7, "y": 5},
    "RC9":  {"x": 2, "y": 3},
    "RC10": {"x": 5, "y": 3},
    "RC11": {"x": 4, "y": 5},
    "RC12": {"x": 7, "y": 3},
}

# ---- Position lookup (all node types) --------------------------
_POSITIONS = {}
_POSITIONS.update({k: (v["x"], v["y"]) for k, v in SOURCES.items()})
_POSITIONS.update({k: (v["x"], v["y"]) for k, v in SINKS.items()})
_POSITIONS.update({k: (v["x"], v["y"]) for k, v in RELAY_CANDIDATES.items()})


# ---- Helper functions ------------------------------------------
def _dist(n1, n2):
    x1, y1 = _POSITIONS[n1]
    x2, y2 = _POSITIONS[n2]
    return _math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def link_build_cost(n1, n2, cap, armored):
    """Return the build cost of a link given its endpoints, capacity, and armor status."""
    d    = _dist(n1, n2)
    base = max(LINK_BUILD_MIN[cap], round(d * LINK_BUILD_RATE[cap]))
    return round(base * ARMOR_MULT) if armored else base
