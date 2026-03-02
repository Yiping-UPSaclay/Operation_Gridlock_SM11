# gridlock_core.py
# =============================================================
#  OPERATION GRIDLOCK -- Shared constants and helpers
#  Import in every notebook with:
#      from gridlock_core import *
# =============================================================

import math as _math
import pandas as pd
import numpy as np
import matplotlib.pyplot as _plt
import matplotlib.patches as _mpa
import matplotlib.lines as _mlines
import matplotlib.patheffects as _pe
import matplotlib.ticker as _tk
import networkx as nx

# =============================================================
#  BUDGET
# =============================================================
BLUE_BUDGET = 500   # units available to Blue Teams

# =============================================================
#  RELAY NODES
#  All relay candidates are identical: 12u each to activate.
#  Relay nodes CANNOT be directly attacked -- only links can.
# =============================================================
RELAY_NODE_COST = 12

# =============================================================
#  LINK COSTS
#  CAPACITY 1|2|3: build = max(MIN, round(dist * RATE))
#  ARMORED True|False: armored cost = base * 2.5 (rounded)
# =============================================================
LINK_BUILD_RATE = {1: 2, 2: 4, 3: 6}
LINK_BUILD_MIN  = {1: 3, 2: 6, 3: 10}
ARMOR_MULT      = 2.5

# =============================================================
#  ATTACK COSTS (flat -- independent of link length)
# =============================================================
ATK_SEVER   = 10   # flat -- independent of link capacity
ATK_DEGRADE = 5    # flat -- independent of link capacity

# =============================================================
#  ATTACK BUDGET RANGE (revealed in class)
# =============================================================
RED_MIN = 55
RED_MAX = 100

# =============================================================
#  NETWORK TOPOLOGY  (fixed -- same for all Blue Teams)
#
#  DESIGN RULES
#  1. Sources connect ONLY to relay nodes (never to sinks).
#  2. Sinks  connect ONLY from relay nodes (never from sources).
#  3. No direct source->sink links.
#
#  Total supply (21) > total demand (14).
# =============================================================
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

# Position lookup (all node types)
_POSITIONS = {}
_POSITIONS.update({k: (v["x"], v["y"]) for k, v in SOURCES.items()})
_POSITIONS.update({k: (v["x"], v["y"]) for k, v in SINKS.items()})
_POSITIONS.update({k: (v["x"], v["y"]) for k, v in RELAY_CANDIDATES.items()})


# =============================================================
#  COST FUNCTIONS
# =============================================================
def _dist(n1, n2):
    x1, y1 = _POSITIONS[n1]
    x2, y2 = _POSITIONS[n2]
    return _math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def link_build_cost(n1, n2, cap, armored):
    """Build cost: scales with distance and capacity; armored x2.5."""
    d    = _dist(n1, n2)
    base = max(LINK_BUILD_MIN[cap], round(d * LINK_BUILD_RATE[cap]))
    return round(base * ARMOR_MULT) if armored else base


# =============================================================
#  VISUAL PALETTE
# =============================================================
PAL = {
    "panel":        "#f8f9fa",
    "grid":         "#e9ecef",
    "border":       "#adb5bd",
    "text":         "#212529",
    "muted":        "#6c757d",
    "source":       "#2b8a3e",
    "sink":         "#1864ab",
    "relay":        "#e67700",
    "candidate":    "#ced4da",
    "relay_fill":   "#a5d8ff",
    "unprotected":  "#868e96",
    "armored":      "#2f9e44",
    "dead":         "#c92a2a",
    "degraded":     "#f59f00",
    "ok":           "#2b8a3e",
    "warn":         "#e67700",
}
EDGE_W = {1: 1.4, 2: 2.8, 3: 4.5}


# =============================================================
#  DRAWING FUNCTIONS
# =============================================================
def draw_network(nodes_df, edges_df, ax=None, title="",
                 dead_edges=None, degraded_edges=None,
                 show_candidates=True):
    """
    Draw the network.
    Edge colour: grey = unprotected, green = armored.
    Edge width:  thin=cap1, medium=cap2, thick=cap3.
    """
    dead_edges     = set(dead_edges    or [])
    degraded_edges = set(degraded_edges or [])
    standalone = ax is None
    if standalone:
        fig, ax = _plt.subplots(figsize=(11, 10), facecolor="white")

    ax.set_facecolor(PAL["panel"])
    ax.set_xlim(0.2, 10.8); ax.set_ylim(0.2, 10.8)
    ax.set_aspect("equal")
    ax.set_title(title, color=PAL["text"], fontsize=12,
                 fontweight="bold", pad=10, fontfamily="monospace")
    ax.tick_params(which="both", left=False, bottom=False,
                   labelleft=False, labelbottom=False)
    for sp in ax.spines.values():
        sp.set_color(PAL["border"]); sp.set_linewidth(0.7)

    for v in range(1, 11):
        ax.axvline(v, color=PAL["grid"], lw=0.5, zorder=0)
        ax.axhline(v, color=PAL["grid"], lw=0.5, zorder=0)
        ax.text(v, 0.12, str(v), ha="center", fontsize=5.5, color=PAL["muted"])
        ax.text(0.12, v, str(v), va="center", fontsize=5.5, color=PAL["muted"])

    if show_candidates:
        for cid, cv in RELAY_CANDIDATES.items():
            ax.scatter(cv["x"], cv["y"], s=50, color=PAL["candidate"],
                       marker="s", zorder=1, alpha=0.55)
            ax.text(cv["x"] + 0.13, cv["y"] + 0.13, cid,
                    fontsize=5.5, color=PAL["candidate"], zorder=2)

    pos = {}
    for r in nodes_df.itertuples():
        pos[r.id] = (r.x, r.y)
    for nid, nd in SOURCES.items():
        pos[nid] = (nd["x"], nd["y"])
    for nid, nd in SINKS.items():
        pos[nid] = (nd["x"], nd["y"])

    for r in edges_df.itertuples():
        s, t = r.source, r.target
        if s not in pos or t not in pos:
            continue
        xs = [pos[s][0], pos[t][0]]
        ys = [pos[s][1], pos[t][1]]
        cap     = int(r.cap)
        armored = bool(r.armored)
        lw  = EDGE_W[cap]
        col = PAL["armored"] if armored else PAL["unprotected"]

        if r.id in dead_edges:
            ax.plot(xs, ys, color=PAL["dead"], lw=1.0, ls="--", alpha=0.28, zorder=2)
        elif r.id in degraded_edges:
            ax.plot(xs, ys, color=PAL["degraded"], lw=lw, ls=(0,(3,2)), alpha=0.75, zorder=2)
        else:
            ls = "-" if armored else (0, (5, 2))
            ax.plot(xs, ys, color=col, lw=lw, ls=ls, alpha=0.80, zorder=2)
            mx = (pos[s][0] + pos[t][0]) / 2
            my = (pos[s][1] + pos[t][1]) / 2
            try:
                bc = link_build_cost(s, t, cap, armored)
                ax.text(mx, my, str(bc) + "u",
                        ha="center", va="center",
                        fontsize=4.5, color=col, alpha=0.80,
                        bbox=dict(fc="white", ec="none", pad=0.5), zorder=3)
            except Exception:
                pass

    for nid, nd in SOURCES.items():
        ax.scatter(nd["x"], nd["y"], s=360, color=PAL["source"],
                   marker="^", edgecolors="white", linewidths=2.0, zorder=6)
        ax.annotate(nid + " (" + str(nd["supply"]) + ")",
                    (nd["x"], nd["y"]),
                    textcoords="offset points", xytext=(7, 6),
                    fontsize=7.5, fontweight="bold", color=PAL["source"], zorder=7,
                    path_effects=[_pe.withStroke(linewidth=2, foreground="white")])

    for nid, nd in SINKS.items():
        sz = 120 + nd["demand"] * 55
        ax.scatter(nd["x"], nd["y"], s=sz, color=PAL["sink"],
                   marker="o", edgecolors="white", linewidths=1.5, zorder=5)
        ax.annotate(nid + " (" + str(nd["demand"]) + ")",
                    (nd["x"], nd["y"]),
                    textcoords="offset points", xytext=(5, 5),
                    fontsize=6.5, fontweight="bold", color=PAL["sink"], zorder=6,
                    path_effects=[_pe.withStroke(linewidth=1.5, foreground="white")])

    for r in nodes_df.itertuples():
        if r.role != "relay":
            continue
        ax.scatter(r.x, r.y, s=220, color=PAL["relay_fill"],
                   marker="s", edgecolors=PAL["relay"],
                   linewidths=2.0, zorder=4)
        ax.annotate(r.id, (r.x, r.y),
                    textcoords="offset points", xytext=(5, 6),
                    fontsize=7, fontweight="bold", color=PAL["text"], zorder=5,
                    path_effects=[_pe.withStroke(linewidth=2, foreground="white")])

    items = [
        _mpa.Patch(color=PAL["source"],     label="Source  (supply in brackets)"),
        _mpa.Patch(color=PAL["sink"],       label="Sink  (demand in brackets)"),
        _mpa.Patch(color=PAL["relay_fill"], label="Relay node  (12u each)"),
        _mlines.Line2D([], [], color=PAL["unprotected"], lw=2.4, ls=(0,(5,2)),
                       label="Unprotected link  (attackable)"),
        _mlines.Line2D([], [], color=PAL["armored"],     lw=2.4, ls="-",
                       label="Armored link  (immune, ×2.5 cost)"),
        _mlines.Line2D([], [], color=PAL["unprotected"], lw=EDGE_W[1], ls="-",
                       label="Cap=1  (sever 10u / degrade 5u)"),
        _mlines.Line2D([], [], color=PAL["unprotected"], lw=EDGE_W[2], ls="-",
                       label="Cap=2  (sever 10u / degrade 5u)"),
        _mlines.Line2D([], [], color=PAL["unprotected"], lw=EDGE_W[3], ls="-",
                       label="Cap=3  (sever 10u / degrade 5u)"),
    ]
    ax.legend(handles=items, loc="upper right",
              framealpha=0.95, facecolor="white",
              edgecolor=PAL["border"], labelcolor=PAL["text"], fontsize=7.5)

    if standalone:
        _plt.tight_layout()
        _plt.show()


def draw_budget_bar(spent, budget, breakdown, ax=None):
    standalone = ax is None
    if standalone:
        fig, ax = _plt.subplots(figsize=(11, 1.4), facecolor="white")
    ax.set_facecolor(PAL["panel"])
    ax.set_xlim(0, budget); ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("Build units", color=PAL["muted"], fontsize=8)
    ax.set_title("Budget", color=PAL["text"], fontsize=10,
                 fontweight="bold", fontfamily="monospace")
    for sp in ax.spines.values():
        sp.set_color(PAL["border"]); sp.set_linewidth(0.7)
    ax.tick_params(colors=PAL["muted"])
    x = 0
    for lbl, val, col in breakdown:
        if val <= 0:
            continue
        ax.barh(0.5, val, left=x, height=0.48, color=col, alpha=0.88)
        if val > 15:
            ax.text(x + val / 2, 0.5, lbl + "  " + str(val) + "u",
                    ha="center", va="center",
                    color="white", fontsize=6.5, fontweight="bold")
        x += val
    remaining = budget - spent
    if remaining > 0:
        ax.barh(0.5, remaining, left=x, height=0.48,
                color=PAL["grid"], alpha=0.7)
    ax.axvline(budget, color=PAL["dead"], lw=1.5, ls="--")
    col = PAL["dead"] if remaining < 0 else PAL["ok"]
    ax.text(budget - 2, 0.88,
            str(spent) + "/" + str(budget) + "u  ("
            + str(remaining) + " remaining)",
            ha="right", color=col, fontsize=9, fontweight="bold")
    if standalone:
        _plt.tight_layout()


def draw_curve(curve, ax=None, label="", pred=None):
    standalone = ax is None
    if standalone:
        fig, ax = _plt.subplots(figsize=(8, 5), facecolor="white")
    ax.set_facecolor(PAL["panel"])
    for sp in ax.spines.values():
        sp.set_color(PAL["border"]); sp.set_linewidth(0.8)
    ax.tick_params(colors=PAL["muted"])
    ax.yaxis.set_major_formatter(
        _tk.FuncFormatter(lambda v, _: str(round(v * 100)) + "%"))
    ax.axhline(0.8, ls="--", color=PAL["warn"], lw=1.0, alpha=0.6)
    ax.text(0.01, 0.82, "80% target",
            transform=ax.get_yaxis_transform(), color=PAL["warn"], fontsize=8)
    steps = list(range(len(curve)))
    ax.fill_between(steps, curve, alpha=0.12, color=PAL["relay"])
    ax.plot(steps, curve, color=PAL["relay"], lw=2.2,
            marker="o", markersize=6,
            markerfacecolor="white", markeredgecolor=PAL["relay"],
            markeredgewidth=1.8, label=label)
    if pred is not None:
        ax.axhline(pred, ls=":", color=PAL["dead"], lw=1.2, alpha=0.7,
                   label="RT prediction " + str(round(pred * 100)) + "%")
    ax.set_ylim(-0.06, 1.15)
    ax.set_xlim(-0.3, max(len(curve) - 0.5, 1))
    ax.set_xlabel("Attack step", color=PAL["muted"])
    ax.set_ylabel("Demand fraction served", color=PAL["muted"])
    sc = score_resilience(curve)
    ax.set_title("Resilience Curve  |  R1=" + str(sc["R1"])
                 + "  R2=" + str(sc["R2"])
                 + "  Score=" + str(sc["total"]),
                 color=PAL["text"], fontsize=10,
                 fontweight="bold", fontfamily="monospace")
    ax.legend(framealpha=0.9, facecolor="white",
              edgecolor=PAL["border"], labelcolor=PAL["text"], fontsize=9)
    if standalone:
        _plt.tight_layout()
        _plt.show()


# =============================================================
#  FLOW SIMULATION
# =============================================================
def _build_flow_graph(nodes_df, edges_df, dead_e, deg_e):
    relay_ids = set(nodes_df["id"])
    all_nodes = relay_ids | set(SOURCES) | set(SINKS)

    DG = nx.DiGraph()
    DG.add_nodes_from(all_nodes)

    for r in edges_df.itertuples():
        if r.id in dead_e:
            continue
        s, t = r.source, r.target
        if s not in all_nodes or t not in all_nodes:
            continue
        cap = r.cap * (0.5 if r.id in deg_e else 1.0)
        DG.add_edge(s, t, capacity=cap)
        DG.add_edge(t, s, capacity=cap)

    DG.add_node("__SRC__")
    DG.add_node("__SNK__")
    for nid, nd in SOURCES.items():
        DG.add_edge("__SRC__", nid, capacity=nd["supply"])
    for nid, nd in SINKS.items():
        DG.add_edge(nid, "__SNK__", capacity=nd["demand"])

    return DG


def compute_perf(nodes_df, edges_df, dead_e, deg_e):
    """Return max-flow performance metrics."""
    DG = _build_flow_graph(nodes_df, edges_df, dead_e, deg_e)
    try:
        flow_val, _ = nx.maximum_flow(DG, "__SRC__", "__SNK__")
    except Exception:
        flow_val = 0.0
    fraction = round(min(flow_val / TOTAL_DEMAND, 1.0), 4)
    isolated = [nid for nid in SINKS
                if not nx.has_path(DG, "__SRC__", nid)]
    return {"fraction": fraction, "isolated": isolated,
            "flow": round(flow_val, 2)}


def run_attacks(nodes_df, edges_df, atk_df):
    """
    Execute the Red Team attack sequence.

    BUG FIX: 'was_degraded' is now captured BEFORE deg_e.discard(tid),
    so the [was degraded] flag in the summary is correct.
    """
    emap = {r.id: r for r in edges_df.itertuples()}

    dead_e = set()
    deg_e  = set()

    p0    = compute_perf(nodes_df, edges_df, dead_e, deg_e)
    curve = [p0["fraction"]]
    events = []

    for row in atk_df.sort_values("step").itertuples():
        tid    = str(row.target_id)
        action = str(row.action)
        ev     = {"step": row.step, "summary": "", "cost": 0}

        if str(getattr(row, "target_type", "edge")) == "node":
            ev["summary"] = "INVALID: relay nodes cannot be attacked. Target links."

        elif tid not in emap:
            ev["summary"] = "INVALID: unknown link id '" + tid + "'"

        elif bool(emap[tid].armored):
            ev["summary"] = ("INVALID: " + tid
                             + " is armored and cannot be attacked.")

        elif tid in dead_e:
            ev["summary"] = "INVALID: " + tid + " is already severed."

        elif action == "sever":
            cap          = int(emap[tid].cap)
            cost         = ATK_SEVER
            was_degraded = tid in deg_e        # check BEFORE discard (bug fix)
            dead_e.add(tid)
            deg_e.discard(tid)
            ev["cost"]    = cost
            ev["summary"] = ("Severed " + tid
                             + " (cap=" + str(cap) + ")"
                             + (" [was degraded]" if was_degraded else "")
                             + " -- " + str(cost) + "u")

        elif action == "degrade":
            if tid in deg_e:
                ev["summary"] = ("INVALID: " + tid
                                 + " already degraded. Use 'sever' to finish.")
            else:
                cap  = int(emap[tid].cap)
                cost = ATK_DEGRADE
                deg_e.add(tid)
                ev["cost"]    = cost
                ev["summary"] = ("Degraded " + tid
                                 + " (cap " + str(cap)
                                 + " → " + str(cap * 0.5) + ")"
                                 + " -- " + str(cost) + "u")
        else:
            ev["summary"] = ("INVALID action '" + action
                             + "'. Use 'sever' or 'degrade'.")

        p = compute_perf(nodes_df, edges_df, dead_e, deg_e)
        ev["frac"]     = p["fraction"]
        ev["isolated"] = p["isolated"]
        curve.append(p["fraction"])
        events.append(ev)

    return curve, events, dead_e, deg_e


def score_resilience(curve):
    R1 = round(sum(curve) / len(curve) * 100, 1)
    R2 = round(min(curve) * 100, 1)
    return {"R1": R1, "R2": R2, "total": round(0.6 * R1 + 0.4 * R2, 1)}


# =============================================================
#  CSV LOADERS
# =============================================================
def load_network_csv(path):
    """Load a Blue Team network CSV. Returns nodes_df, edges_df, meta dict."""
    df = pd.read_csv(path, dtype=str).fillna("")
    meta = {r["id"]: r["value"]
            for _, r in df[df["record"] == "META"].iterrows()}
    nodes = df[df["record"] == "NODE"].copy()
    edges = df[df["record"] == "EDGE"].copy()
    nodes_df = pd.DataFrame({
        "id":    nodes["id"].values,
        "role":  nodes["role"].values,
        "x":     nodes["x"].astype(float).values,
        "y":     nodes["y"].astype(float).values,
        "label": nodes["label"].values,
    })
    edges_df = pd.DataFrame({
        "id":      edges["id"].values,
        "source":  edges["source"].values,
        "target":  edges["target"].values,
        "cap":     edges["cap"].astype(int).values,
        "armored": edges["armored"].map(
                       lambda v: str(v).strip().lower() in ("true","1","yes")
                   ).values,
    })
    return nodes_df, edges_df, meta


def load_attack_csv(path):
    """Load a Red Team attack CSV. Returns atk_df, meta dict."""
    df = pd.read_csv(path, dtype=str).fillna("")
    meta = {r["id"]: r["value"]
            for _, r in df[df["record"] == "META"].iterrows()}
    atk = df[df["record"] == "ATTACK"].copy()
    atk_df = pd.DataFrame({
        "step":        atk["step"].astype(int).values,
        "target_type": atk["target_type"].values,
        "target_id":   atk["target_id"].values,
        "action":      atk["action"].values,
        "rationale":   atk["rationale"].values,
    })
    return atk_df, meta
