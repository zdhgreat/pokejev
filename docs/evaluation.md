# Evaluation

[中文](zh-CN/evaluation.md) · [README](../README.md) · full tables: [results/RESULTS.md](../results/RESULTS.md)

## Paired evaluation of versions (v0.2)

- **Teams:** 72 fixed team pairs, made by Pokémon Showdown's own random-battle generator from fixed seeds.
- **Seats:** every pair is played twice, with the teams swapped (144 games per version).
- **Setup:** format `gen9customgame`, against poke-env's `SimpleHeuristicsPlayer`; every version plays the same
  games, so differences are paired.
- **CI:** a 95% bootstrap interval over team pairs.

| Version | Wins / 144 | Change vs v0.1 |
|---|---|---|
| v01 | 80 (56%) | — |
| v1: + Tera + calculator | 93 (65%) | +9.0 [0.0, 18.8] |
| v2: + next-turn facts | 94 (65%) | +9.7 [−1.4, 20.8] |
| v3: + two-stage shortlist | 91 (63%) | +7.6 [−4.2, 18.8] |
| **v4: v2 + memory** | **100 (69%)** | **+13.9 [4.9, 23.6]** |

- **Where the gain came from:** most of it from Tera and the calculator (better facts). The two-stage shortlist did
  not pay for its doubled cost.
- **Pairing limit:** the server's battle RNG is not seeded, so pairing controls the team draw, not luck within a
  battle.

## Steering (live, v0.1 agent)

| Intent | Conflict turns | Followed |
|---|---|---|
| never the same move 3× | 35 | 100% |
| no move 2+ times in a row unless it KOs | 71 | 99% |
| no self-lowering move unless it KOs | 79 | 100% |
| avoid < 85% accuracy when a ≥ 1× alternative exists | 43 | 91% |

Breaks on non-conflict turns: 0.4%. Wins: 104 / 200 (52%), against 54 / 100 (54%) for the unsteered rule.

## Head-to-head with other public Jev agents (v0.1, all sides `jev-1.13.0`)

| Opponent | Result (ours first) | Notes |
|---|---|---|
| NatBrian's agent (gen 9) | 24–12 | its state is about 16k tokens per decision |
| jev-showdown's Jev (Gen 1, their own fixtures) | 18–5 | it is given move descriptions, no damage numbers |
| Porygon-Jev (gen 9) | 11–4 | too few games to show a difference |

## Reproduce

```bash
python -m pokejev play --decider jev --version v4 --battles 50 --out runs/v4
python -m pokejev play --decider rule --battles 50 --out runs/rule
python -m pokejev eval runs/v4
```

The paired fixed-team harness used for the table above is part of the research repository this package came from;
the package's own CLI plays random teams.
