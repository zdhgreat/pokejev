# How it works

[中文](zh-CN/how-it-works.md) · [README](../README.md)

## One turn

1. **poke-env** receives the battle request from the Showdown server: the legal moves and switches.
2. **`facts.py`** computes, for every option:

   | Option | Facts |
   |---|---|
   | **Move** | estimated damage as % of the opponent's HP; *likely KO*; type effectiveness; accuracy; priority; recoil, self-drop, status, setup, heal, hazard; times used in a row |
   | **Tera variant** (v1+) | the same move with Terastallize, damage adjusted for the new STAB, and the type it becomes |
   | **Switch** | the benched Pokémon's HP, a matchup score, whether it is faster |
   | **Next turn** (v2+) | the opponent's best reply (revealed moves, else a STAB estimate) and its damage to us or the switch-in; who moves first; KO either way |

   - **Damage** comes from **poke-env's Showdown calculator**, with estimated opponent stats; when the calculator
     can't run, from our own estimate. Our estimate also handles variable-power moves (Heavy Slam, Low Kick, Gyro
     Ball, Super Fang, Body Press, Foul Play, Eruption, Stored Power, one-hit KOs).
   - **Memory** (v4) adds the last three exchanges: HP changes, newly revealed opponent moves, whether the opponent
     switched, and "no visible effect".
3. **`render.py`** turns this into one structured JSON state, `situation` plus all `options`, plus the designer
   intent if there is one. It asks **one Choice question**, "Pick the option most likely to win…", or, with an
   intent, "Which option follows `designer_intent`? If several do, the one that best helps win."
4. **Jev** returns a probability for every option. **`decider.py`** takes its choice. If the API fails or the budget
   is reached, it falls back to the rule (counted as a fallback). Single-option turns don't call the API.
5. **`player.py`** executes the order (with `terastallize=True` for a Tera option), logs the request and the
   decision, and poke-env saves the replay for the viewer.

## Why this split

Jev ("System One") returns calibrated choices, not text. Our controlled probes found:

| Task | Result |
|---|---|
| Thresholds, comparisons, best-of-N, AND / OR / NOT / UNLESS over numbers that are **stated** | **100%** |
| Two-step references ("the member who last healed the boss's target") | chance level |
| Counting long lists | off by one |
| Judging comparison intents ("weakest KO move") when each question showed **one option only** | poor |
| The same intents with **all options visible** | good |

So the design rule is: **compute in code, show every option, ask one direct question.** Jev's own documentation
says the same ("Jev is not a calculator"; avoid indirection; avoid large irrelevant state).

## The rule baseline

`rules.py` is deliberately simple: if a move is likely to KO, it picks the most accurate KO move; otherwise the
highest damage × accuracy. It switches only when forced, or when the current matchup is very bad and a good switch
exists. The rule is the fallback, and it defines conflict turns for intents.

## Files

| File | Role |
|---|---|
| `facts.py` | all numbers, including the calculator, Tera, opponent threat and speed |
| `render.py` | the model input and the second-stage brief (v3) |
| `decider.py` | `JevDecider` (with an optional `two_stage`) and `RuleDecider` |
| `player.py` | poke-env player: history counters, memory, Tera orders, replays |
| `features.py` | named versions `v01` … `v4` |
| `jev.py` | the API client (pinned `jev-1.13.0`, retries, cost) and a free stub |
