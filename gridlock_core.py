# gridlock_core.py
# =============================================================
#  OPERATION GRIDLOCK -- Shared constants and helpers
#  Import in every notebook with:
#      from gridlock_core import *
# =============================================================

import math as _math
import hashlib as _hashlib
import base64 as _base64
import urllib.request as _urlreq
import pandas as pd
import numpy as np
import matplotlib.pyplot as _plt
import matplotlib.patches as _mpa
import matplotlib.lines as _mlines
import matplotlib.patheffects as _pe
import matplotlib.gridspec as _gs
import networkx as nx
import io as _io

# =============================================================
#  BUDGET
# =============================================================
BLUE_BUDGET = 350   # units available to Blue Teams

# =============================================================
#  RELAY NODES
#  Activating relay nodes is FREE — budget is spent only on links.
#  Relay nodes CANNOT be directly attacked -- only links can.
# =============================================================

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
RED_MIN = 40
RED_MAX = 60

# =============================================================
#  INTELLIGENCE / RECONNAISSANCE COSTS
# =============================================================
INTEL_COST_BLUE = 25   # BT pays from design budget to reveal exact RT budget
RECON_COST_RED  = 10   # RT pays from attack budget to reveal BT armor status

# =============================================================
#  NEXTCLOUD PUBLIC SHARE  (WebDAV via stdlib urllib)
# =============================================================
NC_SHARE_URL = "https://nextcloud.centralesupelec.fr/s/iEKCqsGrCXXNp7D"
_NC_TOKEN    = NC_SHARE_URL.rstrip("/").rsplit("/", 1)[-1]
_NC_WEBDAV   = "https://nextcloud.centralesupelec.fr/public.php/webdav/"
_NC_AUTH     = "Basic " + _base64.b64encode(
                   (_NC_TOKEN + ":").encode("ascii")).decode("ascii")


def nc_upload(local_path):
    """Upload *local_path* to the Nextcloud shared folder (WebDAV PUT).

    Returns the remote URL on success.
    """
    import os
    fname = os.path.basename(local_path)
    url   = _NC_WEBDAV + _urlreq.quote(fname)
    with open(local_path, "rb") as fh:
        data = fh.read()
    req = _urlreq.Request(url, data=data, method="PUT",
                          headers={"Authorization": _NC_AUTH,
                                   "Content-Type": "application/octet-stream"})
    with _urlreq.urlopen(req) as resp:
        _ = resp.read()
    print(f"  Uploaded -> {fname}  ({len(data)} bytes)")
    return NC_SHARE_URL + "?path=/" + _urlreq.quote(fname)


def nc_download(remote_name, local_path=None):
    """Download *remote_name* from the Nextcloud shared folder.

    If *local_path* is None the file is saved in the current directory
    with the same name.  Returns the local file path.
    """
    import os
    if local_path is None:
        local_path = remote_name
    url = _NC_WEBDAV + _urlreq.quote(remote_name)
    req = _urlreq.Request(url, method="GET",
                          headers={"Authorization": _NC_AUTH})
    with _urlreq.urlopen(req) as resp:
        data = resp.read()
    with open(local_path, "wb") as fh:
        fh.write(data)
    print(f"  Downloaded -> {local_path}  ({len(data)} bytes)")
    return local_path


def nc_list():
    """List files in the Nextcloud shared folder.  Returns a list of names."""
    body = ('<?xml version="1.0"?>'
            '<d:propfind xmlns:d="DAV:"><d:prop>'
            '<d:displayname/><d:getcontentlength/>'
            '</d:prop></d:propfind>').encode("utf-8")
    req = _urlreq.Request(_NC_WEBDAV, data=body, method="PROPFIND",
                          headers={"Authorization": _NC_AUTH,
                                   "Depth": "1",
                                   "Content-Type": "application/xml"})
    with _urlreq.urlopen(req) as resp:
        xml = resp.read().decode("utf-8")
    # Minimal XML parsing — extract href values after the root collection
    import re
    hrefs = re.findall(r"<d:href>([^<]+)</d:href>", xml)
    names = []
    for h in hrefs:
        part = h.rstrip("/").rsplit("/", 1)[-1]
        if part and part != "webdav":
            names.append(_urlreq.unquote(part))
    return names


# =============================================================
#  ARMOR ENCRYPTION HELPERS  (stdlib only: hashlib + base64)
# =============================================================
def _armor_keystream(key: str, length: int) -> bytes:
    """Produce a deterministic keystream from *key* using iterated SHA-256."""
    stream = bytearray()
    block = key.encode("utf-8")
    while len(stream) < length:
        block = _hashlib.sha256(block).digest()
        stream.extend(block)
    return bytes(stream[:length])


def _encrypt_armor(edge_ids, armor_values, key: str) -> str:
    """Encrypt a list of (edge_id, bool) pairs into a base-64 token.

    Format before encryption: ``id1:T,id2:F,...``
    """
    plain = ",".join(
        f"{eid}:{'T' if arm else 'F'}" for eid, arm in zip(edge_ids, armor_values)
    )
    plainb = plain.encode("utf-8")
    ks = _armor_keystream(key, len(plainb))
    cipher = bytes(a ^ b for a, b in zip(plainb, ks))
    return _base64.urlsafe_b64encode(cipher).decode("ascii")


def _decrypt_armor(token: str, key: str) -> dict:
    """Decrypt a base-64 token back to ``{edge_id: bool}``."""
    cipher = _base64.urlsafe_b64decode(token.encode("ascii"))
    ks = _armor_keystream(key, len(cipher))
    plainb = bytes(a ^ b for a, b in zip(cipher, ks))
    plain = plainb.decode("utf-8")
    result = {}
    for pair in plain.split(","):
        eid, flag = pair.split(":")
        result[eid] = (flag == "T")
    return result


# =============================================================
#  FOG-OF-WAR HELPERS
# =============================================================
def mask_armor(edges_df):
    """Return a copy of edges_df with armored column hidden (all set to 'unknown').
    Used by Red Teams who have NOT purchased recon."""
    masked = edges_df.copy()
    masked["armored"] = False      # RT sees all links as 'unprotected'
    masked["_fog"]    = True       # flag: armor status is hidden
    return masked


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
    "D9": {"x": 7, "y": 3, "demand": 1, "label": "S-East"},
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
    "RC12": {"x": 8, "y": 2},
}

# Position lookup (all node types)
POSITIONS = {}
POSITIONS.update({k: (v["x"], v["y"]) for k, v in SOURCES.items()})
POSITIONS.update({k: (v["x"], v["y"]) for k, v in SINKS.items()})
POSITIONS.update({k: (v["x"], v["y"]) for k, v in RELAY_CANDIDATES.items()})


# =============================================================
#  COST FUNCTIONS
# =============================================================
def _dist(n1, n2):
    x1, y1 = POSITIONS[n1]
    x2, y2 = POSITIONS[n2]
    return _math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def link_build_cost(n1, n2, cap, armored):
    """Build cost: scales with distance and capacity; armored x2.5."""
    d    = _dist(n1, n2)
    base = max(LINK_BUILD_MIN[cap], round(d * LINK_BUILD_RATE[cap],1))
    return round(base * ARMOR_MULT, 1) if armored else base


def link_cost_catalog(from_node=None):
    """Return a DataFrame of all valid candidate links with build costs.

    Valid links: Source\u2192Relay, Relay\u2192Relay, Relay\u2192Sink.
    If from_node is given, only links involving that node.

    Columns: source, target, dist, cap1, cap2, cap3, arm1, arm2, arm3
    """
    src_ids = set(SOURCES)
    rc_ids  = set(RELAY_CANDIDATES)
    snk_ids = set(SINKS)
    pairs = []
    for s in sorted(src_ids):
        for r in sorted(rc_ids):
            pairs.append((s, r))
    rc_sorted = sorted(rc_ids)
    for i, a in enumerate(rc_sorted):
        for b in rc_sorted[i+1:]:
            pairs.append((a, b))
    for r in sorted(rc_ids):
        for d in sorted(snk_ids):
            pairs.append((r, d))
    if from_node:
        pairs = [(a, b) for a, b in pairs
                 if a == from_node or b == from_node]
    rows = []
    for a, b in pairs:
        d = round(_dist(a, b), 2)
        rows.append({
            "source": a, "target": b, "dist": d,
            "cap1": link_build_cost(a, b, 1, False),
            "cap2": link_build_cost(a, b, 2, False),
            "cap3": link_build_cost(a, b, 3, False),
            "arm1": link_build_cost(a, b, 1, True),
            "arm2": link_build_cost(a, b, 2, True),
            "arm3": link_build_cost(a, b, 3, True),
        })
    return pd.DataFrame(rows)


def compute_design_cost(edges_df):
    """Return the total build cost of all links in edges_df."""
    return sum(link_build_cost(r.source, r.target, int(r.cap), bool(r.armored))
               for r in edges_df.itertuples())


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
    "fog":          "#5c7cfa",   # fog-of-war: unknown protection status
}
EDGE_W = {1: 1.4, 2: 2.8, 3: 4.5}


# =============================================================
#  DRAWING FUNCTIONS
# =============================================================
def draw_network(nodes_df, edges_df, ax=None, title="",
                 dead_edges=None, degraded_edges=None,
                 show_candidates=True, fog_of_war=False):
    """
    Draw the network.
    Edge colour: grey = unprotected, green = armored, blue = fog-of-war (unknown).
    Edge width:  thin=cap1, medium=cap2, thick=cap3.
    If fog_of_war=True, all links are drawn in 'unknown' style (blue solid).
    """
    dead_edges     = set(dead_edges    or [])
    degraded_edges = set(degraded_edges or [])
    standalone = ax is None
    if standalone:
        fig, ax = _plt.subplots(figsize=(11, 10), facecolor="white")

    ax.set_facecolor(PAL["panel"])
    ax.set_xlim(0.2, 10.8); ax.set_ylim(0.2, 12.6)
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

        if fog_of_war and r.id not in dead_edges and r.id not in degraded_edges:
            # Fog-of-war: all links drawn identically (blue solid, no cost label)
            ax.plot(xs, ys, color=PAL["fog"], lw=lw, ls="-", alpha=0.65, zorder=2)
            mx = (pos[s][0] + pos[t][0]) / 2
            my = (pos[s][1] + pos[t][1]) / 2
            ax.text(mx, my, "cap=" + str(cap),
                    ha="center", va="center",
                    fontsize=4.5, color=PAL["fog"], alpha=0.70,
                    bbox=dict(fc="white", ec="none", pad=0.5), zorder=3)
        elif r.id in dead_edges:
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

    if fog_of_war:
        items = [
            _mpa.Patch(color=PAL["source"],     label="Source  (supply in brackets)"),
            _mpa.Patch(color=PAL["sink"],       label="Sink  (demand in brackets)"),
            _mpa.Patch(color=PAL["relay_fill"], label="Relay node  (free)"),
            _mlines.Line2D([], [], color=PAL["fog"], lw=2.4, ls="-",
                           label="Link  (protection UNKNOWN)"),
            _mlines.Line2D([], [], color=PAL["fog"], lw=EDGE_W[1], ls="-",
                           label="Cap=1"),
            _mlines.Line2D([], [], color=PAL["fog"], lw=EDGE_W[2], ls="-",
                           label="Cap=2"),
            _mlines.Line2D([], [], color=PAL["fog"], lw=EDGE_W[3], ls="-",
                           label="Cap=3"),
        ]
    else:
        items = [
            _mpa.Patch(color=PAL["source"],     label="Source  (supply in brackets)"),
            _mpa.Patch(color=PAL["sink"],       label="Sink  (demand in brackets)"),
            _mpa.Patch(color=PAL["relay_fill"], label="Relay node  (free)"),
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
    if dead_edges:
        items.append(_mlines.Line2D([], [], color=PAL["dead"], lw=1.0, ls="--",
                                    alpha=0.5, label="Severed  (link destroyed)"))
    if degraded_edges:
        items.append(_mlines.Line2D([], [], color=PAL["degraded"], lw=2.4,
                                    ls=(0,(3,2)), alpha=0.75,
                                    label="Degraded  (capacity halved)"))
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


# =============================================================
#  COMPOSITE DRAWING FUNCTIONS
# =============================================================
def draw_design_sheet(nodes_df, edges_df, team_id, team_name, strategy,
                      budget=None, save=None):
    """Draw network map with budget bar below. Optionally save to file."""
    if budget is None:
        budget = BLUE_BUDGET
    cost = compute_design_cost(edges_df)
    breakdown = [
        ("armored links",
         sum(link_build_cost(r.source, r.target, int(r.cap), True)
             for r in edges_df[edges_df["armored"]==True].itertuples()),
         PAL["armored"]),
        ("unprotected links",
         sum(link_build_cost(r.source, r.target, int(r.cap), False)
             for r in edges_df[edges_df["armored"]==False].itertuples()),
         PAL["unprotected"]),
    ]
    fig = _plt.figure(figsize=(14, 11), facecolor="white")
    gs = _gs.GridSpec(2, 1, figure=fig, height_ratios=[9, 1], hspace=0.06)
    ax_map = fig.add_subplot(gs[0])
    ax_bgt = fig.add_subplot(gs[1])
    draw_network(nodes_df, edges_df, ax=ax_map,
                 title=team_id + " -- " + team_name + "  |  " + strategy,
                 show_candidates=False)
    draw_budget_bar(cost, budget, breakdown, ax=ax_bgt)
    if save:
        _plt.savefig(save, dpi=130, bbox_inches="tight", facecolor="white")
    _plt.show()


def draw_designs_gallery(network_files, save=None, recon_key=None):
    """Draw a gallery of all Blue Team designs."""
    n = len(network_files)
    if n == 0:
        print("No network files found.")
        return
    cols_n = min(n, 3)
    rows_n = (n + cols_n - 1) // cols_n
    fig, axes = _plt.subplots(rows_n, cols_n,
                               figsize=(11 * cols_n, 10 * rows_n),
                               facecolor="white")
    ax_list = list(axes.flat) if hasattr(axes, "flat") else [axes]
    for i, fpath in enumerate(network_files):
        nd, ed, mt = load_network_csv(fpath, recon_key=recon_key)
        ec = compute_design_cost(ed)
        n_arm = ed["armored"].sum()
        intel = mt.get("intel_purchased", "False")
        title = (mt.get("team_id", "?") + " -- " + mt.get("team_name", "?")
                 + "  |  " + str(ec) + "/" + str(BLUE_BUDGET) + "u"
                 + "  " + str(n_arm) + " armored  " + mt.get("strategy", "?")
                 + ("  [INTEL]" if str(intel).lower() == "true" else ""))
        draw_network(nd, ed, ax=ax_list[i], title=title, show_candidates=False)
    for j in range(n, rows_n * cols_n):
        ax_list[j].set_visible(False)
    _plt.suptitle("OPERATION GRIDLOCK -- All Blue Team Designs",
                  color=PAL["text"], fontsize=15, fontweight="bold", y=1.01)
    _plt.tight_layout()
    if save:
        _plt.savefig(save, dpi=120, bbox_inches="tight", facecolor="white")
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


def run_attacks(nodes_df, edges_df, atk_df, recon_purchased=False):
    """
    Execute the Red Team attack sequence.

    If recon_purchased=False, the Red Team does NOT know which links are
    armored. Attacks on armored links still consume budget but have no
    effect (simulating wasted resources / failed operation).

    If recon_purchased=True (default, legacy behaviour), attacks on
    armored links are flagged INVALID and cost nothing.
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

        elif bool(emap[tid].armored) and recon_purchased:
            # RT knew it was armored -- free INVALID (they should not target it)
            ev["summary"] = ("INVALID: " + tid
                             + " is armored and cannot be attacked.")

        elif bool(emap[tid].armored) and not recon_purchased:
            # RT did NOT know it was armored -- budget wasted!
            cost = ATK_SEVER if action == "sever" else ATK_DEGRADE
            ev["cost"]    = cost
            ev["summary"] = ("WASTED: " + tid + " is armored (unknown to RT)"
                             + " -- " + action + " failed, "
                             + str(cost) + "u lost!")

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


def attack_plan_cost(steps):
    """Return total cost (in units) of an attack plan.
    Each step is (target_type, target_id, action, rationale).
    """
    return sum(ATK_DEGRADE if act == "degrade" else ATK_SEVER
               for _, _, act, _ in steps)


def check_attack_budget(plan_name, steps, budget):
    """Print budget summary for an attack plan. Returns (cost, remaining, ok)."""
    cost = attack_plan_cost(steps)
    remaining = budget - cost
    ok = remaining >= 0
    print("Plan:      " + plan_name)
    print("Steps:     " + str(len(steps)))
    print("Cost:      " + str(cost) + "u")
    print("Budget:    " + str(budget) + "u")
    print("Remaining: " + str(remaining) + "u")
    print("Status:    " + ("OK" if ok else "OVER BUDGET!"))
    return cost, remaining, ok


def compute_attack_result(nodes_df, edges_df, atk_df, recon_purchased=False):
    """Run attacks and return a summary dict (final performance only)."""
    curve, events, dead_e, deg_e = run_attacks(
        nodes_df, edges_df, atk_df, recon_purchased=recon_purchased)
    total_spent = sum(ev["cost"] for ev in events)
    wasted = sum(ev["cost"] for ev in events
                 if "WASTED" in ev.get("summary", ""))
    return {
        "final_frac": curve[-1],
        "intact_frac": curve[0],
        "events": events,
        "dead_e": dead_e,
        "deg_e": deg_e,
        "total_spent": total_spent,
        "wasted": wasted,
    }


def build_resilience_table(network_files, attack_files, recon_key=None):
    """Build a cross-table: rows = BT designs, columns = RT attack plans.

    Each cell = final demand fraction served (0-1) when the attack plan
    is run against the design.  Rows are sorted by Mean (descending).

    Returns a pandas DataFrame.
    """
    designs = []
    for net_f in sorted(network_files):
        nd, ed, nm = load_network_csv(net_f, recon_key=recon_key)
        designs.append((nm.get("team_id", "?"), nm.get("team_name", "?"),
                        nd, ed, nm))

    attacks = []
    for atk_f in sorted(attack_files):
        adf, am = load_attack_csv(atk_f)
        rt_id = am.get("red_team_id", "?")
        rt_recon = str(am.get("recon_purchased", "False")).lower() == "true"
        attacks.append((rt_id, adf, rt_recon))

    rows = []
    for bt_id, bt_name, nd, ed, nm in designs:
        row = {"BT Design": bt_id, "BT Team": bt_name}
        for rt_id, adf, rt_recon in attacks:
            res = compute_attack_result(nd, ed, adf, recon_purchased=rt_recon)
            row[rt_id] = round(res["final_frac"] * 100, 1)
        rows.append(row)

    df = pd.DataFrame(rows)
    atk_cols = [rt_id for rt_id, *_ in attacks]
    if atk_cols:
        df["Mean(%)"] = df[atk_cols].mean(axis=1).round(1)
        df = df.sort_values("Mean(%)", ascending=False).reset_index(drop=True)
    return df


# =============================================================
#  CSV LOADERS
# =============================================================
def load_network_csv(path, recon_key=None):
    """Load a Blue Team network CSV. Returns nodes_df, edges_df, meta dict.

    If the CSV contains encrypted armor (META row ``armor_enc``) and
    *recon_key* is provided, the true armored status is restored.
    Without the key (or with a wrong key) all edges show armored=False.
    """
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

    # --- Armor decryption logic ---
    armor_enc = meta.get("armor_enc", "")
    if armor_enc and recon_key:
        # Attempt decryption; fall back to masked on failure
        try:
            armor_map = _decrypt_armor(armor_enc, recon_key)
            armor_series = edges["id"].map(
                lambda eid: armor_map.get(eid, False)
            )
        except Exception:
            armor_series = pd.Series([False] * len(edges), dtype=bool)
    elif armor_enc:
        # Encrypted but no key → masked
        armor_series = pd.Series([False] * len(edges), dtype=bool)
    else:
        # Plain-text CSV (legacy / instructor export without key)
        armor_series = edges["armored"].map(
            lambda v: str(v).strip().lower() in ("true", "1", "yes")
        )

    edges_df = pd.DataFrame({
        "id":      edges["id"].values,
        "source":  edges["source"].values,
        "target":  edges["target"].values,
        "cap":     edges["cap"].astype(int).values,
        "armored": armor_series.values,
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


# =============================================================
#  CSV EXPORTERS
# =============================================================
def export_network_csv(team_id, team_name, strategy, rationale,
                       nodes_df, edges_df, intel_purchased=False,
                       recon_key=None):
    """Export Blue Team network design to CSV.

    If *recon_key* is provided the armored column is encrypted:
    EDGE rows show ``hidden`` and a META row ``armor_enc`` holds the
    encrypted token.  Only readers who supply the same key can recover
    true armor status.  Returns filename.
    """
    cols = ["record", "id", "value", "role", "x", "y", "label",
            "source", "target", "cap", "armored"]
    def _m(k, v):
        row = {c: "" for c in cols}
        row.update({"record": "META", "id": k, "value": str(v)})
        return row
    def _n(r):
        row = {c: "" for c in cols}
        row.update({"record": "NODE", "id": r.id, "role": r.role,
                     "x": r.x, "y": r.y, "label": r.label})
        return row
    def _e(r, armor_display):
        row = {c: "" for c in cols}
        row.update({"record": "EDGE", "id": r.id, "source": r.source,
                     "target": r.target, "cap": int(r.cap),
                     "armored": armor_display})
        return row

    meta_rows = [_m("team_id", team_id), _m("team_name", team_name),
                 _m("strategy", strategy),
                 _m("intel_purchased", intel_purchased),
                 _m("rationale", rationale.strip().replace("\n", " "))]

    if recon_key:
        # Encrypt armor into a META row; hide per-edge values
        edge_ids = [r.id for r in edges_df.itertuples()]
        armor_vals = [bool(r.armored) for r in edges_df.itertuples()]
        token = _encrypt_armor(edge_ids, armor_vals, recon_key)
        meta_rows.append(_m("armor_enc", token))
        edge_rows = [_e(r, "hidden") for r in edges_df.itertuples()]
    else:
        edge_rows = [_e(r, bool(r.armored)) for r in edges_df.itertuples()]

    rows = (meta_rows
            + [_n(r) for r in nodes_df.itertuples()]
            + edge_rows)
    fname = team_id + "_network.csv"
    pd.DataFrame(rows)[cols].to_csv(fname, index=False)
    return fname


def export_attack_csv(rt_id, bt_id, plan_name, vuln, atk_df,
                      recon_purchased=False):
    """Export Red Team attack plan to CSV. Returns filename.

    *atk_df* is a DataFrame with columns:
        step, target_type, target_id, action, rationale
    """
    cols = ["record", "step", "id", "value", "target_type",
            "target_id", "action", "rationale"]
    def _m(k, v):
        row = {c: "" for c in cols}
        row.update({"record": "META", "id": k, "value": str(v)})
        return row
    def _a(r):
        row = {c: "" for c in cols}
        row.update({"record": "ATTACK", "step": r.step,
                     "target_type": r.target_type, "target_id": r.target_id,
                     "action": r.action, "rationale": r.rationale})
        return row
    rows = ([_m("red_team_id", rt_id), _m("target_team_id", bt_id),
             _m("chosen_plan", plan_name),
             _m("recon_purchased", recon_purchased),
             _m("vuln_analysis", vuln.strip().replace("\n", " "))]
            + [_a(r) for r in atk_df.itertuples()])
    fname = rt_id + "_vs_" + bt_id + "_attacks.csv"
    pd.DataFrame(rows)[cols].to_csv(fname, index=False)
    return fname


# =============================================================
#  STUDENT HELPERS  (called from BT_design.ipynb)
# =============================================================

def check_cost(source, target, cap=2):
    """Print unprotected & armored build cost for a single candidate link.

    Usage:
        check_cost("RC11", "D5", cap=2)
    """
    d = round(_dist(source, target), 2)
    cost_u = link_build_cost(source, target, cap, armored=False)
    cost_a = link_build_cost(source, target, cap, armored=True)
    print(f"  {source} -> {target}  dist={d}  cap={cap}")
    print(f"    unprotected = {cost_u}u    armored = {cost_a}u")


def build_design(edge_list):
    """Convert MY_EDGES into (nodes_df, edges_df).

    Relay nodes are automatically activated based on link endpoints —
    any endpoint that is a relay candidate (RC1-RC12) is included.

    Usage:
        nodes_df, edges_df = build_design(MY_EDGES)
    """
    edges_df = pd.DataFrame(
        [(eid, s, t, int(c), bool(a)) for eid, s, t, c, a in edge_list],
        columns=["id", "source", "target", "cap", "armored"])
    # auto-detect relay nodes from link endpoints
    used = set(edges_df["source"]) | set(edges_df["target"])
    relay_ids = sorted(used & set(RELAY_CANDIDATES))
    rows = []
    for cid in relay_ids:
        cv = RELAY_CANDIDATES[cid]
        rows.append({"id": cid, "role": "relay",
                     "x": cv["x"], "y": cv["y"], "label": cid})
    nodes_df = pd.DataFrame(rows)
    return nodes_df, edges_df


def validate(nodes_df, edges_df, team_id, team_name, rationale,
             budget=None):
    """Run all design checks and print a summary. Returns True if valid.

    Usage:
        nodes_df, edges_df = build_design(MY_EDGES)
        ok = validate(nodes_df, edges_df, TEAM_ID, TEAM_NAME, DESIGN_RATIONALE)
    """
    if budget is None:
        budget = BLUE_BUDGET

    errors = []
    relay_ids = set(nodes_df["id"])
    all_ids   = relay_ids | set(SOURCES) | set(SINKS)

    # duplicates
    if nodes_df.duplicated("id").any():
        dups = nodes_df[nodes_df.duplicated("id")]["id"].tolist()
        errors.append(f"Duplicate relay IDs: {dups}")
    if edges_df.duplicated("id").any():
        dups = edges_df[edges_df.duplicated("id")]["id"].tolist()
        errors.append(f"Duplicate edge IDs: {dups}")

    # per-edge checks
    for r in edges_df.itertuples():
        if r.source not in all_ids:
            errors.append(f"Unknown source node in '{r.id}': '{r.source}'")
        if r.target not in all_ids:
            errors.append(f"Unknown target node in '{r.id}': '{r.target}'")
        if r.cap not in (1, 2, 3):
            errors.append(f"Invalid cap in '{r.id}' (must be 1, 2, or 3)")
        if ((r.source in SOURCES and r.target in SINKS) or
                (r.source in SINKS and r.target in SOURCES)):
            errors.append(f"Direct source-sink link not allowed: '{r.id}'")

    # budget (links only -- relay activation is free)
    edge_cost = sum(
        link_build_cost(r.source, r.target, int(r.cap), bool(r.armored))
        for r in edges_df.itertuples()
        if r.source in all_ids and r.target in all_ids)
    total     = edge_cost
    remaining = budget - total
    if total > budget:
        errors.append(f"Over budget: {total}u > {budget}u")

    # connectivity
    G = nx.Graph()
    G.add_nodes_from(all_ids)
    for r in edges_df.itertuples():
        G.add_edge(r.source, r.target)
    unreachable = [s for s in SINKS
                   if not any(nx.has_path(G, src, s) for src in SOURCES)]
    if unreachable:
        errors.append(f"Sinks unreachable from any source: {unreachable}")

    # rationale
    if len(rationale.strip()) < 60:
        errors.append(
            f"DESIGN_RATIONALE too short ({len(rationale.strip())} chars, need 60)")

    # summary
    n_arm = int(edges_df["armored"].sum())
    n_unp = len(edges_df) - n_arm
    cap_counts = edges_df["cap"].value_counts().to_dict()

    print("=" * 56)
    print(f"  Team: {team_id} -- {team_name}")
    print(f"  Relays:   {len(nodes_df)} (free)")
    print(f"  Links:    {len(edges_df)}  "
          f"({n_arm} armored, {n_unp} unprotected)")
    print(f"  Caps:     "
          + "  ".join(f"cap{c}x{cap_counts.get(c, 0)}" for c in [1, 2, 3]))
    print(f"  Budget:   {edge_cost:.2f}u links"
          f" = {total:.2f}/{budget:.2f}u  ({remaining:.2f}u remaining)")
    print("=" * 56)

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        return False

    p0  = compute_perf(nodes_df, edges_df, set(), set())
    pct = round(p0["fraction"] * 100)
    warn = "" if pct == 100 else "  WARNING: not 100%!"
    print(f"  All checks passed!")
    print(f"  Intact max-flow: {p0['flow']}/{TOTAL_DEMAND} = {pct}%{warn}")
    print(f"  Attack surface:  {n_unp} unprotected links")
    return True


def cost_breakdown(nodes_df, edges_df):
    """Print a per-link cost table showing where the budget goes.

    Usage:
        cost_breakdown(nodes_df, edges_df)
    """
    print(f"  {'Link ID':<16} {'Route':<14} {'Cap':>3} {'Arm':>4} "
          f"{'Dist':>5} {'Cost':>7}")
    print("  " + "-" * 54)
    total_edge = 0.0
    for r in edges_df.itertuples():
        d = round(_dist(r.source, r.target), 2)
        cost = link_build_cost(r.source, r.target, int(r.cap), bool(r.armored))
        total_edge += cost
        arm = "Y" if r.armored else ""
        route = r.source + "->" + r.target
        print(f"  {r.id:<16} {route:<14} {r.cap:>3} {arm:>4} "
              f"{d:>5} {cost:>6.1f}u")
    print("  " + "-" * 54)
    print(f"  {'TOTAL':<40} {total_edge:>6.1f}u")
