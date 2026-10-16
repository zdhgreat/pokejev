"""Evaluate a run directory: win rate, play quality, and (with an intent) compliance on conflict turns."""
import json
import math
from pathlib import Path

from pokejev.intents import INTENTS
from pokejev.rules import rule_pick


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def mean(v):
    v = list(v)
    return sum(v) / len(v) if v else None


def evaluate(run_dir):
    d = Path(run_dir)
    s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    recs = [json.loads(l) for l in (d / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    out = {"decider": s["decider"], "intent": s["intent"], "battles": s["battles"], "wins": s["wins"],
           "win_rate": s["wins"] / s["battles"], "win_ci95": wilson(s["wins"], s["battles"]),
           "decisions": len(recs), "fallbacks": sum(1 for r in recs if r["decision"].get("fallback")),
           "cost_usd": s.get("cost_usd")}
    multi = [r for r in recs if len(r["request"]["options"]) > 1]
    pick = lambda r: next(o for o in r["request"]["options"] if o["id"] == r["chosen_id"])          # noqa: E731
    ko = [pick(r)["kind"] == "move" and pick(r)["facts"]["likely_ko"] for r in multi
          if any(o["kind"] == "move" and o["facts"]["likely_ko"] for o in r["request"]["options"])]
    out.update(agree_with_rule=mean(r["chosen_id"] == rule_pick(r["request"]) for r in multi),
               ko_pick_when_available=mean(ko),
               no_effect_move_picks=mean(pick(r)["kind"] == "move" and pick(r)["facts"]["type_mult"] == 0.0 for r in multi))
    if s["intent"]:
        it = INTENTS[s["intent"]]
        conf, conf_ok, nc, nc_break = 0, 0, 0, 0
        for r in recs:
            req = r["request"]
            if not it["applies"](req):
                continue
            rule_opt = next(o for o in req["options"] if o["id"] == rule_pick(req))
            if not it["complies"](req, rule_opt):
                conf += 1
                conf_ok += bool(it["complies"](req, pick(r)))
            else:
                nc += 1
                nc_break += not it["complies"](req, pick(r))
        out.update(conflict_turns=conf, conflict_compliance=conf_ok / conf if conf else None,
                   nonconflict_turns=nc, nonconflict_breaks_intent=nc_break / nc if nc else None)
    return out
