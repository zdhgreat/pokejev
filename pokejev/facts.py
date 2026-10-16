"""Showdown decision facts. Code computes everything; the model only judges.

Damage is a base-stat estimate (opponent stats are hidden in random battles, so poke-env's calc refuses them):
random-battle spreads (IV 31, EV 85, neutral nature), our own stats when known, stat boosts, STAB, type multiplier,
expected hits, mean roll 0.925 and minimum roll 0.85 for "likely KO".
Known gaps: abilities (e.g. Levitate), items, weather, terrain and tera are not modelled.
"""
import math

from poke_env.battle import MoveCategory, SideCondition

HAZARDS = {SideCondition.STEALTH_ROCK, SideCondition.SPIKES, SideCondition.TOXIC_SPIKES, SideCondition.STICKY_WEB}


def stage(boost):
    return (2 + boost) / 2 if boost >= 0 else 2 / (2 - boost)


def stat(mon, name):
    known = (mon.stats or {}).get(name)
    if isinstance(known, (int, float)) and known:
        return float(known)
    base, lv = mon.base_stats[name], mon.level or 80
    if name == "hp":
        return math.floor((2 * base + 31 + 21) * lv / 100) + lv + 10
    return math.floor((2 * base + 31 + 21) * lv / 100) + 5


def speed(mon):
    return stat(mon, "spe") * stage(mon.boosts.get("spe", 0))


def _tier(x, table, default):
    """First value whose threshold x reaches; table is [(threshold, value), ...] from high to low."""
    return next((v for t, v in table if x >= t), default)


def base_power(attacker, defender, move):
    """Base power, including moves whose power depends on weight, speed, HP or boosts (0 in the move data)."""
    mid, bp = move.id, move.base_power or 0
    if mid in ("lowkick", "grassknot"):
        return _tier(defender.weight or 0, [(200, 120), (100, 100), (50, 80), (25, 60), (10, 40)], 20)
    if mid in ("heavyslam", "heatcrash"):
        return _tier((attacker.weight or 1) / max(defender.weight or 1, 0.1), [(5, 120), (4, 100), (3, 80), (2, 60)], 40)
    if mid == "gyroball":
        return min(150, math.floor(25 * speed(defender) / max(speed(attacker), 1)) + 1)
    if mid == "electroball":
        return _tier(speed(attacker) / max(speed(defender), 1), [(4, 150), (3, 120), (2, 80), (1, 60)], 40)
    if mid in ("flail", "reversal"):
        p = math.floor(48 * attacker.current_hp_fraction)
        return 200 if p <= 1 else 150 if p <= 4 else 100 if p <= 9 else 80 if p <= 16 else 40 if p <= 32 else 20
    if mid in ("crushgrip", "hardpress"):
        return max(1, math.floor((120 if mid == "crushgrip" else 100) * defender.current_hp_fraction))
    if mid in ("eruption", "waterspout", "dragonenergy"):
        return max(1, math.floor(150 * attacker.current_hp_fraction))
    if mid in ("storedpower", "powertrip"):
        return 20 + 20 * sum(v for v in attacker.boosts.values() if v > 0)
    return bp


def fixed_damage(attacker, defender, move):
    """Damage as a fraction of the defender's max HP for moves that ignore the damage formula, else None."""
    mid, hp = move.id, stat(defender, "hp")
    if move.damage == "level":                                    # Seismic Toss, Night Shade
        return float(attacker.level or 80) / hp
    if mid in ("superfang", "ruination"):
        return 0.5 * defender.current_hp_fraction
    if mid == "endeavor":
        return max(0.0, defender.current_hp_fraction - attacker.current_hp_fraction * stat(attacker, "hp") / hp)
    if mid == "finalgambit":
        return attacker.current_hp_fraction * stat(attacker, "hp") / hp
    if move.entry.get("ohko"):                                    # KO if it hits (accuracy is reported separately)
        return defender.current_hp_fraction
    return None


def damage(attacker, defender, move):
    """(mean, minimum) damage as a fraction of the defender's max HP; (0, 0) for non-damaging moves.

    Still 0: moves that depend on damage taken this turn or on hidden items / stockpiles (Counter, Mirror Coat,
    Metal Burst, Comeuppance, Beat Up, Fling, Present, Spit Up).
    """
    if move.category == MoveCategory.STATUS:
        return 0.0, 0.0
    lv = attacker.level or 80
    fixed = fixed_damage(attacker, defender, move)
    if fixed is not None:
        if defender.damage_multiplier(move) == 0:                 # type immunity still applies
            return 0.0, 0.0
        return fixed, fixed
    bp = base_power(attacker, defender, move)
    if bp <= 0:
        return 0.0, 0.0
    phys = move.category == MoveCategory.PHYSICAL
    off_mon = defender if move.id == "foulplay" else attacker               # Foul Play uses the target's Attack
    off = "def" if move.id == "bodypress" else ("atk" if phys else "spa")   # Body Press uses the user's Defense
    a = stat(off_mon, off) * stage(off_mon.boosts.get(off, 0))
    d = stat(defender, "def" if phys else "spd") * stage(defender.boosts.get("def" if phys else "spd", 0))
    base = math.floor(math.floor(math.floor(2 * lv / 5 + 2) * bp * a / d) / 50) + 2
    mult = (1.5 if move.type in attacker.types else 1.0) * defender.damage_multiplier(move) * (move.expected_hits or 1)
    hp = stat(defender, "hp")
    return base * mult * 0.925 / hp, base * mult * 0.85 / hp


def matchup(mon, opp):
    """poke-env SimpleHeuristicsPlayer._estimate_matchup, reproduced so the facts don't depend on a private method."""
    score = max(opp.damage_multiplier(t) for t in mon.types if t is not None)
    score -= max(mon.damage_multiplier(t) for t in opp.types if t is not None)
    if mon.base_stats["spe"] > opp.base_stats["spe"]:
        score += 0.1
    elif opp.base_stats["spe"] > mon.base_stats["spe"]:
        score -= 0.1
    return score + 0.4 * mon.current_hp_fraction - 0.4 * opp.current_hp_fraction


def move_facts(battle, move, consecutive, use_calc=False, tera=None):
    """Facts for one move. use_calc: Showdown calculator when it runs; tera: a PokemonType to Terastallize into."""
    me, opp = battle.active_pokemon, battle.opponent_active_pokemon
    mean, low = best_damage(battle, me, opp, move, use_calc) if use_calc else damage(me, opp, move)
    if tera is not None:
        k = tera_multiplier(me, move, tera)
        mean, low = mean * k, low * k
    remaining = opp.current_hp_fraction
    self_drop = bool(move.self_boost and any(v < 0 for v in move.self_boost.values()))
    setup = bool((move.boosts and getattr(move.target, "name", "") == "SELF" and sum(move.boosts.values()) > 0)
                 or (move.category == MoveCategory.STATUS and move.self_boost
                     and sum(move.self_boost.values()) > 0))
    inflicts = bool(move.status) or any(s.get("status") for s in (move.secondary or []))
    hazard = move.side_condition in HAZARDS
    acc = 1.0 if move.accuracy is True else float(move.accuracy)
    return {"type": move.type.name.lower(), "category": move.category.name.lower(),
            "type_mult": float(opp.damage_multiplier(move)) if move.category != MoveCategory.STATUS else None,
            "est_damage_pct": round(100 * min(mean, 2.0), 1), "likely_ko": bool(low > 0 and low >= remaining),
            "accuracy": round(acc, 2), "priority": int(move.entry.get("priority", 0)), "self_drop": self_drop,
            "recoil": bool(move.recoil and move.recoil > 0), "inflicts_status": inflicts, "setup": setup,
            "heal": bool(move.heal and move.heal > 0), "hazard": hazard,
            "hazard_already_set": bool(hazard and move.side_condition in battle.opponent_side_conditions),
            "is_status": move.category == MoveCategory.STATUS, "consecutive_uses": int(consecutive)}


def move_words(f):
    """Compact, shared by every model (Laya's option budget is ~192 tokens for up to 9 options)."""
    if f["is_status"]:
        parts = ["status"]
        for k, w in (("setup", "boosts self"), ("heal", "heals"), ("hazard", "hazard"), ("inflicts_status", "inflicts status")):
            if f[k]:
                parts.append(w)
    else:
        mult = f["type_mult"]
        eff = {0.0: "immune", 0.25: "0.25x", 0.5: "0.5x", 1.0: "1x", 2.0: "2x", 4.0: "4x"}.get(mult, "%gx" % mult)
        parts = ["%s %s" % (f["type"], "phys" if f["category"] == "physical" else "spec"), eff,
                 "~%d%%" % round(f["est_damage_pct"])]
        for k, w in (("likely_ko", "KO"), ("self_drop", "self-drop"), ("recoil", "recoil"),
                     ("inflicts_status", "may status")):
            if f[k]:
                parts.append(w)
    if f["accuracy"] < 1:
        parts.append("acc %d" % round(100 * f["accuracy"]))
    if f["priority"] > 0:
        parts.append("priority")
    if f["consecutive_uses"] >= 1:
        parts.append("used %dx in a row" % f["consecutive_uses"])
    return " ".join(parts)


def switch_facts(battle, mon):
    opp = battle.opponent_active_pokemon
    return {"hp_pct": round(100 * mon.current_hp_fraction, 1), "matchup": round(matchup(mon, opp), 2),
            "faster": speed(mon) > speed(opp)}


def switch_words(f):
    return "%d%% HP, matchup %+.1f, %s" % (round(f["hp_pct"]), f["matchup"], "faster" if f["faster"] else "slower")


def state_facts(battle, hist):
    me, opp = battle.active_pokemon, battle.opponent_active_pokemon
    ours = len([m for m in battle.team.values() if not m.fainted])
    theirs = 6 - len([m for m in battle.opponent_team.values() if m.fainted])
    s = {"turn": battle.turn, "our_species": me.species, "opp_species": opp.species,
         "our_hp_pct": round(100 * me.current_hp_fraction, 1), "opp_hp_pct": round(100 * opp.current_hp_fraction, 1),
         "we_faster": speed(me) > speed(opp), "our_left": ours, "opp_left": theirs,
         "turns_since_switch": hist["turns_since_switch"], "opp_just_switched": hist["opp_just_switched"],
         "active_matchup": round(matchup(me, opp), 2), "forced_switch": bool(battle.force_switch),
         # display only (the battle viewer); not part of the model input rendered by render.structured
         "our_types": [t.name.lower() for t in me.types if t is not None],
         "opp_types": [t.name.lower() for t in opp.types if t is not None],
         "our_status": me.status.name.lower() if me.status else None,
         "opp_status": opp.status.name.lower() if opp.status else None}
    text = ("Turn %d. Your %s has %d%% HP; opponent %s has %d%% HP; you are %s. You have %d Pokemon left, the "
            "opponent %d. Turns since your last switch: %d.%s" % (
                s["turn"], s["our_species"], round(s["our_hp_pct"]), s["opp_species"], round(s["opp_hp_pct"]),
                "faster" if s["we_faster"] else "slower", ours, theirs, min(s["turns_since_switch"], 9),
                " The opponent just switched in." if s["opp_just_switched"] else ""))
    return s, text


def rerender(request):
    """Rebuild option text/words from stored facts with the current shared template (bank requests predate it)."""
    for o in request["options"]:
        if o["kind"] == "move":
            o["text"] = o["text"][4:] if o["text"].startswith("Use ") else o["text"]
            o["words"] = move_words(o["facts"])
        else:
            o["text"] = "Switch " + o["text"][10:] if o["text"].startswith("Switch to ") else o["text"]
            o["words"] = switch_words(o["facts"])
    return request


# ================================================================== v0.2: calculator, Tera, one-turn exchange
def ensure_stats(mon):
    """Fill unknown stats (opponents in random battles) with the random-battle estimate used by `stat`."""
    st = getattr(mon, "_stats", None)
    if isinstance(st, dict) and any(v is None for v in st.values()):
        for k in ("hp", "atk", "def", "spa", "spd", "spe"):
            if st.get(k) is None:
                st[k] = int(stat(mon, k))


def calc_damage(battle, attacker, defender, move):
    """(mean, minimum) fraction of the defender's max HP from poke-env's gen 9 Showdown calculator, else None.

    Covers abilities, items, weather, terrain and screens that `damage` ignores. Opponent stats are estimated.
    """
    if battle.gen != 9 or move.category == MoveCategory.STATUS:
        return None
    try:
        from poke_env.calc.damage_calc_gen9 import calculate_damage
        ensure_stats(attacker)
        ensure_stats(defender)
        role = lambda m: battle.player_role if m in battle.team.values() else battle.opponent_role   # noqa: E731
        lo, hi = calculate_damage(attacker.identifier(role(attacker)), defender.identifier(role(defender)), move, battle)
        hp = defender.stats["hp"] or stat(defender, "hp")
        hits = move.expected_hits or 1
        return (lo + hi) / 2 * hits / hp, lo * hits / hp
    except Exception:
        return None


def best_damage(battle, attacker, defender, move, use_calc):
    """Calculator when enabled and it runs, else the base-stat estimate."""
    if use_calc:
        c = calc_damage(battle, attacker, defender, move)
        if c is not None:
            return c
    return damage(attacker, defender, move)


def own_tera_type(battle):
    """Our active Pokemon's Tera type from the server request (poke-env only sets tera_type after Terastallizing)."""
    from poke_env.battle import PokemonType
    for mon in ((getattr(battle, "last_request", None) or {}).get("side") or {}).get("pokemon", []):
        if mon.get("active") and mon.get("teraType"):
            try:
                return PokemonType.from_name(mon["teraType"])
            except Exception:
                return None
    return None


def tera_multiplier(attacker, move, tera=None):
    """Damage factor from terastallizing before this move (STAB gain or upgrade); 1.0 when nothing changes."""
    tera = tera if tera is not None else attacker.tera_type
    if tera is None or attacker.is_terastallized or move.category == MoveCategory.STATUS or move.type != tera:
        return 1.0
    return 2.0 / 1.5 if move.type in attacker.types else 1.5


def _single(attack_type, defend_type):
    """Gen 9 type chart lookup (indexed [defending type][attacking type])."""
    from poke_env.data import GenData
    return GenData.from_gen(9).type_chart.get(defend_type.name.upper(), {}).get(attack_type.name.upper(), 1.0)


def _type_mult(attack_type, defender_types):
    m = 1.0
    for t in defender_types:
        if t is not None:
            m *= _single(attack_type, t)
    return m


def opponent_threat(battle, opp, target, use_calc, target_types=None):
    """Opponent's best one-move reply against `target`: (label, mean fraction, min fraction of target's max HP).

    Uses the opponent's revealed damaging moves; if none are revealed, a STAB estimate (power 80 per type, the higher
    of its attacking stats). `target_types` overrides the target's types (e.g. after Terastallizing)."""
    best = ("unknown move (STAB estimate)", 0.0, 0.0)
    moves = [m for m in opp.moves.values() if m.category != MoveCategory.STATUS]
    for m in moves:
        mean, low = best_damage(battle, opp, target, m, use_calc)
        if target_types is not None:
            before = _type_mult(m.type, target.types) or 1.0
            ratio = _type_mult(m.type, target_types) / before if before else 0.0
            mean, low = mean * ratio, low * ratio
        if mean > best[1] or best[0].startswith("unknown move"):          # name the move even if nothing hits
            best = (m.entry.get("name", m.id), mean, low)
    if moves:
        return best
    lv = opp.level or 80
    phys = stat(opp, "atk") * stage(opp.boosts.get("atk", 0)) >= stat(opp, "spa") * stage(opp.boosts.get("spa", 0))
    a = stat(opp, "atk" if phys else "spa") * stage(opp.boosts.get("atk" if phys else "spa", 0))
    d = stat(target, "def" if phys else "spd") * stage(target.boosts.get("def" if phys else "spd", 0))
    types = target_types if target_types is not None else target.types
    for t in opp.types:
        if t is None:
            continue
        base = math.floor(math.floor(math.floor(2 * lv / 5 + 2) * 80 * a / d) / 50) + 2
        frac = base * 1.5 * _type_mult(t, types) / stat(target, "hp")
        if frac * 0.925 > best[1] or best[0].startswith("unknown move"):     # keep the type even when it can't hit
            best = ("unknown %s move (STAB estimate)" % t.name.lower(), frac * 0.925, frac * 0.85)
    return best


def moves_first(battle, move, opp):
    """True if our move acts before an ordinary opponent move (priority, then speed)."""
    pr = int(move.entry.get("priority", 0))
    if pr != 0:
        return pr > 0
    return speed(battle.active_pokemon) > speed(opp)
