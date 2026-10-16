# Results

Model: TypeSafe Jev, pinned `jev-1.13.0`. Opponent: poke-env `SimpleHeuristicsPlayer`. Format: `gen9randombattle`.
Measured 2026-10-14/15.

**Provenance.** These numbers were produced by the research harness this package was extracted from. They used the
same structured rendering, Choice question text and pinned model, but the fact layer **before** the v0.1 fix for
variable-power moves (Heavy Slam, Gyro Ball, Super Fang, Body Press and others were then estimated at 0 or
mis-estimated). The rule and Jev saw the same facts, so the comparisons are fair; absolute numbers with v0.1 facts
may differ. Every formal run was frozen by hash before running and checked by an independent recompute script. A
small verification run of this package with real Jev is reported at the end.

## Live battles

**Jev as player (no intent), 100 battles:**

| | Wins | 95% CI |
|---|---|---|
| Rule baseline | 54 / 100 | 0.44–0.63 |
| **Jev** | **55 / 100** | 0.45–0.64 |

Over 2,192 decisions Jev:
- took the KO when one was available 100% of the time;
- never picked a no-effect move (0%) or a status move (0%);
- agreed with the rule on 85% of turns;
- fell back once on an API error.

**Jev steered by a designer intent, 50 battles each:**

| Intent | Jev compliance on conflict turns | Breaks intent on other applicable turns | Jev wins | Rule + perfect intent filter: wins |
|---|---|---|---|---|
| ha05: never the same move three turns in a row | 1.00 (n=35) | 0.00 | 23 | 25 |
| hb09: no move used 2+ times in a row unless it KOs | 0.99 (n=71) | 0.00 | 29 | 18 |
| ha02: no self-lowering move unless it KOs | 1.00 (n=79) | 0.00 | 29 | 22 |
| ha01: avoid < 85% accuracy when a ≥ 1× damaging alternative exists | 0.91 (n=43) | 0.01 | 23 | 24 |
| **Total** | **0.97 macro** | **0.4% pooled** | **104 / 200** | 89 / 200 |

- A *conflict turn* is one where the intent applies and the rule's own pick would break it.
- "Rule + perfect intent filter" applies the exact checker and then takes the rule's best compliant move.
- Battles are not paired (random teams), so per-intent win differences are within noise (about ±14 points).

## Offline (3,923 recorded states, 20 blind-written intents, wrong-intent controls)

**Format comparison** (compliance on conflict turns):

| Question format | Dev intents | Held-out intents | False vetoes |
|---|---|---|---|
| One yes/no per option, other options hidden, P(yes) > 0.5 | 0.72 | 0.90 | 0.18–0.26 |
| One yes/no per option, **all options visible** (structured JSON) | 0.95 | 0.99 | 0.00–0.03 |
| **One Choice per turn, all options visible** (this package) | 0.98 | 0.99 | — |

- Intents that compare options ("the weakest KO move", "your most accurate move") went from 0.36 to 0.90 compliance
  once all options were visible.
- With an unrelated intent's text, Choice still picks complying moves 25–40% of the time, against a random-pick
  baseline of 31–52%. Strong moves often comply anyway.
- Chinese intent text: held-out compliance 0.985 vs 0.986 in English.

**Jev as player, offline** (1,000 states): agrees with the rule 84%, KO taken 100%, no-effect moves 0%. For
comparison, two small local Jev-style models scored 15% / 26% agreement and 20% / 26% KO.

## Controlled probes (what Jev can and cannot do)

On 3,080 generated questions with code-computed answers:
- **100%** on numeric thresholds (including 1–3 points from the line), two-number comparisons, best-of-2/4/6, and
  AND / OR / NOT / UNLESS / 3-part logic. Equally in Chinese, in plain text vs JSON, with 50 irrelevant fields, in 3
  wordings, and in any option order (no first-option bias).
- **Fails** on two-hop references (0.43, chance).
- **Counting** a 12-item list: 0.90, off by one.

So: compute and resolve references in code; let Jev compare and judge.

## Verification run of this package (v0.1 facts, real Jev), 2026-10-15

A small end-to-end check of this repository's own code with the real API: `jev-1.13.0`, 0 API fallbacks in 446
decisions, $0.017 total.

| Run | Wins | Notes |
|---|---|---|
| `--decider jev`, 10 battles | 7 / 10 | KO taken 100% when available; 0 no-effect moves; agrees with the rule on 83% of turns |
| `--decider jev --intent ha05`, 10 battles | 5 / 10 | follows the intent on 10 / 10 conflict turns; 0 breaks on other applicable turns |

Ten battles only confirm that the pipeline works; they are not a strength estimate.

## v0.2 paired evaluation (2026-10-15)

72 fixed seeded gen 9 random-battle team pairs (Showdown's own generator), each played in both seat orientations
(144 games per version), `gen9customgame`, against poke-env's `SimpleHeuristicsPlayer`. `jev-1.13.0` throughout;
0 fallbacks, 0 errors, 0 unfinished games; total cost $0.89.

| Version | Wins | Win rate [95% CI] | Paired change vs v01 [95% CI] | Tokens per decision |
|---|---|---|---|---|
| v01 | 80 | 0.56 [0.47, 0.63] | — | 892 |
| v1 (Tera + calculator) | 93 | 0.65 [0.57, 0.72] | +0.090 [0.000, 0.188] | 951 |
| v2 (+ trade facts) | 94 | 0.65 [0.57, 0.73] | +0.097 [−0.014, 0.208] | 1,387 |
| v3 (v2 + two-stage) | 91 | 0.63 [0.55, 0.71] | +0.076 [−0.042, 0.188] | 2,368 |
| **v4 (v2 + memory)** | **100** | **0.69 [0.62, 0.76]** | **+0.139 [+0.049, +0.236]** | 1,594 |

**Step by step** (exploratory, paired):

| Step | Change [95% CI] |
|---|---|
| Tera + calculator | +0.090 [0.000, 0.188] |
| Trade facts | +0.007 [−0.104, 0.111] |
| Two-stage | −0.021 [−0.132, 0.090] |
| Memory | +0.042 [−0.069, 0.146] |

**Notes:**
- In v3, the second stage changed the first-stage pick on 19% of turns, and v3 switched more (32% vs 25%).
- The server's battle RNG is not seeded, so pairing controls the team draw, not luck within a battle.
- Four comparisons were made with no multiplicity correction.
