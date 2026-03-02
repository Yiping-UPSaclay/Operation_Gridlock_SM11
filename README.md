# Operation GRIDLOCK

A serious game for courses on **infrastructure resilience**.

## Overview

Students are divided into **Blue Teams** (defenders) and **Red Teams** (attackers).

- **Blue Teams** design a supply network under a budget constraint (500u), choosing relay nodes, link capacities, and armoring decisions.
- **Red Teams** receive the Blue Team designs and plan an attack sequence under a revealed budget (range: 55–100u).
- The **Instructor** runs the live simulation and scores each design.

## Files

| File | Role |
|------|------|
| `BT_design.ipynb` | Blue Team notebook — design the network |
| `RT_attack.ipynb` | Red Team notebook — plan the attack |
| `instructor_sim.ipynb` | Instructor notebook — run simulation & debrief |
| `gridlock_core.py` | Shared constants and helpers (do not edit) |
| `BT_design_template.csv` | Template for Blue Team network submission |
| `RT_attack_template.csv` | Template for Red Team attack submission |

## Setup

```bash
pip install -r requirements.txt
```

Open any notebook in Jupyter after installing dependencies.

## Game Rules (summary)

- Blue Team budget: **500 units**
- Red Team budget: revealed in class (range: 55–100 units)
- Relay node cost: **12u each**
- Link build cost scales with distance and capacity (×2.5 if armored)
- Attack costs are **flat** (independent of link length)

| Action  | Cost (flat) |
|---------|-------------|
| sever   | 10u         |
| degrade | 5u          |

## Scoring

`Score = 0.6 × R1 + 0.4 × R2`

- **R1** = average demand fraction served across all attack steps (absorption)
- **R2** = minimum demand fraction served at any step (worst-case floor)
