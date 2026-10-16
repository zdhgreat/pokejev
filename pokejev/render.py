"""Render a decision request as Jev's input: a structured JSON state with ALL options visible.

This format is the main lesson of the study: with one option per question Jev could not judge comparisons; with every
option's facts in one structured state it can.
"""

EFF = {0.0: "immune (0x)", 0.25: "0.25x", 0.5: "0.5x", 1.0: "1x (neutral)", 2.0: "2x", 4.0: "4x"}
PROPS = [("self_drop", "lowers own stats"), ("recoil", "recoil"), ("inflicts_status", "may inflict status"),
         ("setup", "boosts own stats"), ("heal", "heals user"), ("hazard", "sets entry hazard"),
         ("hazard_already_set", "hazard already set")]

PLAYER_Q = ("Pick the option most likely to win the battle. Knocking out the opponent is best; "
            "otherwise more damage is better; avoid moves with no effect.")
STEER_Q = ("Which option follows `designer_intent`? If several options follow it, choose the one among them that best "
           "helps win the battle.")


def option_names(req):
    """option id -> unique readable name ("Earthquake", "Switch to garchomp")."""
    names, seen = {}, set()
    for o in req["options"]:
        n = o["text"] if o["kind"] == "move" else "Switch to " + o["text"].replace("Switch ", "", 1)
        if n in seen:
            n = "%s (%s)" % (n, o["id"])
        seen.add(n)
        names[o["id"]] = n
    return names


def option_json(o):
    """Numbers always present; yes/no properties listed only when true ("properties": [] = none)."""
    f = o["facts"]
    if o["kind"] == "switch":
        return _with_exchange({"action": "switch", "hp_pct": f["hp_pct"], "matchup": f["matchup"],
                               "faster": f["faster"]}, f)
    d = {"action": "%s move (%s)" % (f["category"], f["type"])}
    if not f["is_status"]:
        d["effectiveness"] = EFF.get(f["type_mult"], "%gx" % f["type_mult"])
        d["damage_pct_of_opponent_hp"] = f["est_damage_pct"]
        d["likely_ko"] = f["likely_ko"]
    d.update({"accuracy_pct": round(100 * f["accuracy"]), "priority": f["priority"],
              "used_in_a_row": f["consecutive_uses"], "properties": [w for k, w in PROPS if f[k]]})
    if f.get("terastallize"):
        d.update(terastallize=True, becomes_type=f["tera_type"])
    return _with_exchange(d, f)


def _with_exchange(d, f):
    if "exchange" in f:
        d["next_turn"] = f["exchange"]
    return d


def structured(req, intent_text=None):
    s = req["state"]
    names = option_names(req)
    out = {"situation": {
        "turn": s["turn"],
        "your_pokemon": {"species": s["our_species"], "hp_pct": s["our_hp_pct"], "faster_than_opponent": s["we_faster"]},
        "opponent_pokemon": {"species": s["opp_species"], "hp_pct": s["opp_hp_pct"]},
        "your_pokemon_left": s["our_left"], "opponent_pokemon_left": s["opp_left"],
        "turns_since_your_last_switch": s["turns_since_switch"], "opponent_just_switched_in": s["opp_just_switched"],
        "forced_switch": s["forced_switch"]},
        "options": {names[o["id"]]: option_json(o) for o in req["options"]}}
    for k in ("opponent_revealed_moves", "memory"):                 # optional features (see features.py)
        if k in s:
            out["situation"][k] = s[k]
    if intent_text is not None:
        out["designer_intent"] = intent_text
    return out


def choice_question(req, intent_text=None):
    """(state, questions, name -> option id) for one Choice per turn."""
    names = option_names(req)
    q = {"pick": {"type": "choice", "instructions": PLAYER_Q if intent_text is None else STEER_Q,
                  "criteria": {names[o["id"]]: None for o in req["options"]}}}
    return structured(req, intent_text), q, {n: oid for oid, n in names.items()}


BRIEF_NOTE = (" `consequence_brief` summarises each shortlisted option's likely next turn: the opponent's best reply,"
              " who moves first, knockouts either way, and what happens if the opponent switches instead.")


def brief_question(req, keep_ids, intent_text=None):
    """Second stage: the shortlisted options only, plus a consequence brief built from the code-computed facts."""
    names = option_names(req)
    kept = [o for o in req["options"] if o["id"] in keep_ids]
    sub = dict(req, options=kept)
    state = structured(sub, intent_text)
    for d in state["options"].values():
        d.pop("next_turn", None)                                    # carried once, in the brief
    brief = {}
    for o in kept:
        f = o["facts"]
        b = dict(f.get("exchange", {}))
        if "if_opponent_switches" in f:
            b["if_opponent_switches"] = f["if_opponent_switches"]
        brief[names[o["id"]]] = b
    state["consequence_brief"] = brief
    ins = (PLAYER_Q if intent_text is None else STEER_Q) + BRIEF_NOTE
    q = {"pick": {"type": "choice", "instructions": ins, "criteria": {names[o["id"]]: None for o in kept}}}
    return state, q, {names[o["id"]]: o["id"] for o in kept}
