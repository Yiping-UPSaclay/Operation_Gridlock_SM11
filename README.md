# Operation GRIDLOCK

A serious game for 3GS3110 **Resilience of Critical Infrastructures**.

## Overview

Students are divided into **Blue Teams** (defenders) and **Red Teams** (attackers).

- **Blue Teams** design a supply network under a budget constraint (350u) by building links with chosen capacities and armoring. Relay nodes activate automatically when used.
- **Red Teams** receive the Blue Team designs and plan an attack sequence under a budget (range: 40–60u).
- Both sides operate under **information asymmetry** with optional intelligence purchases.
- The **Instructor** runs the live simulation and scores each design.

## Files

| File | Role |
|------|------|
| `BT_design.ipynb` | Blue Team notebook — design the network |
| `RT_attack.ipynb` | Red Team notebook — plan the attack |
| `instructor_sim.ipynb` | Instructor notebook — run simulation & debrief |
| `gridlock_core.py` | Shared constants and helpers (do not edit) |
| `gridlock_config.py` | Shared constants (lightweight, for quick reference) |
| `BT_design_template.csv` | Template for Blue Team network submission |
| `RT_attack_template.csv` | Template for Red Team attack submission |

## Setup

```bash
pip install -r requirements.txt
```

Open any notebook in Jupyter after installing dependencies.

## Game Rules (summary)

- Blue Team budget: **350 units** (spent entirely on links)
- Red Team budget: range **40–60 units** (exact value revealed in class)
- Relay node activation: **free** (auto-activated when used in a link)
- Link build cost scales with distance and capacity (×2.5 if armored)
- Attack costs are **flat** (independent of link length)

| Action  | Cost (flat) |
|---------|-------------|
| sever   | 10u         |
| degrade | 5u          |

## Information Asymmetry & Intelligence Market

| Side | What they know | What they DON'T know | Intel option |
|------|---------------|---------------------|--------------|
| Blue Team | Own full design, RT budget range (40–60u) | RT exact budget | Pay **25u** to learn exact RT budget |
| Red Team | Network topology + link capacities | Which links are **armored** | Pay **10u** to reveal armor status |

- **Blue intel (25u):** Reveals exact RT budget → enables adaptive redesign in-class
- **Red recon (10u):** Reveals armor status → otherwise attacks on armored links **waste budget** (cost spent, no effect)

## In-Class Schedule

| Phase | Time | Blue Teams | Red Teams |
|-------|------|------------|-----------|
| Intelligence Market | 5 min | Buy intel? (25u) | Buy recon? (10u) |
| Adjustment + Initial Planning | 25 min | Adapt design (if intel bought) | Study + plan attacks |
| Attack Finalization + Self-Assessment | 25 min | Self-assess own vulnerabilities | Finalize attack plans |
| Live Simulation | 40 min | Watch matchups | Watch matchups |
| Debrief | 30 min | VOI analysis | VOI analysis |

## Scoring

`Score = 0.6 × R1 + 0.4 × R2`

- **R1** = average demand fraction served across all attack steps (absorption)
- **R2** = minimum demand fraction served at any step (worst-case floor)
