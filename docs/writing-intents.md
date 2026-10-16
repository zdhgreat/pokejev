# Writing designer intents

[中文](zh-CN/writing-intents.md) · [README](../README.md)

An **intent** is one plain-text instruction for the AI's play style. Jev reads only the text; no code is needed to
*use* an intent:

```bash
python -m pokejev play --decider jev --intent ha02 --battles 5 --out runs/ha02
```

To **add** your own:
1. Put the sentence in `pokejev/data/intents.json` with a new id.
2. To **measure** compliance, also add a checker to `CHECKS` in `pokejev/intents.py`:

```python
"my01": (lambda r: ...,      # applies(request): is the intent relevant to this decision?
         lambda r, c: ...),  # complies(request, chosen_option): does choosing c follow it?
```

`r` is the decision request; `r["options"]` lists every legal option with its `facts`, and `r["state"]` holds the
situation (HP %, turn, speed, Pokémon left, turns since the last switch…). Helpers in `intents.py`:
- `_moves(r)`, `_sw(r)` and `_dmg(r)` list the moves, the switches and the damaging moves;
- `_f(o, "likely_ko")` reads one fact of an option.

## How compliance is measured

- **Conflict turn:** the intent applies, and the plain rule's own pick would break it. Compliance is counted only
  here; otherwise a decider that ignores the intent would look compliant for free.
- **Non-conflict turn:** the intent applies, and the rule's pick already complies. Here we count how often the pick
  breaks the intent anyway (should be about 0).

```bash
python -m pokejev eval runs/ha02
# "conflict_turns": 3, "conflict_compliance": 1.0, "nonconflict_breaks_intent": 0.0
```

## Tips (from our experiments)

- **Write the condition the way it reads in the facts:** HP %, effectiveness, "likely to knock out", priority,
  recoil, "lowers own stats", times in a row. Jev reads literally.
- **Exact conditions work best.** Thresholds, "unless it KOs" and comparisons between options are followed reliably
  (97% live).
- **Vague style intents also work for picking moves.** For example "play cautiously", "show off" or "be merciful
  when far ahead": 92% of Jev's picks were accepted by two independent labelers. They have no exact checker, so
  judge them by watching the viewer.
- **Chinese intents work as well as English.**
- **Avoid two-step references** ("the Pokémon that last hit the one we switched out"). Compute such things in code
  and add them as facts.
