"""The baseline rule: highest value among candidate options (ties: first in option order)."""


def value(option, request):
    f = option["facts"]
    if option["kind"] == "switch":
        return f["matchup"]
    if f["likely_ko"]:
        return 1000.0 + 100.0 * f["accuracy"]
    return f["est_damage_pct"] * f["accuracy"]


def candidates(request):
    """Moves; switches only when forced, or when the active matchup < -2 and a positive-matchup switch exists."""
    moves = [o for o in request["options"] if o["kind"] == "move"]
    switches = [o for o in request["options"] if o["kind"] == "switch"]
    if not moves:
        return switches
    good = [o for o in switches if o["facts"]["matchup"] > 0]
    if request["state"]["active_matchup"] < -2 and good:
        return good
    return moves


def rule_pick(request):
    cand = candidates(request)
    return max(cand, key=lambda o: value(o, request))["id"]
