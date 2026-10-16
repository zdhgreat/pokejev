"""Offline checks: no server, no network.  Run: python -m unittest discover -s tests -v"""
import json
import tempfile
import unittest
from pathlib import Path

from pokejev.decider import JevDecider, RuleDecider
from pokejev.evaluate import evaluate, wilson
from pokejev.intents import INTENTS, TEXTS
from pokejev.jev import StubClient
from pokejev.render import PLAYER_Q, STEER_Q, choice_question, option_json
from pokejev.rules import rule_pick


def move(i, name, dmg=50.0, **kw):
    f = {"type": "fire", "category": "special", "type_mult": 1.0, "est_damage_pct": dmg, "likely_ko": False,
         "accuracy": 1.0, "priority": 0, "self_drop": False, "recoil": False, "inflicts_status": False, "setup": False,
         "heal": False, "hazard": False, "hazard_already_set": False, "is_status": False, "consecutive_uses": 0}
    f.update(kw)
    return {"id": i, "kind": "move", "text": name, "facts": f}


def switch(species, matchup=0.0, hp=100.0):
    return {"id": "s_" + species, "kind": "switch", "text": "Switch " + species,
            "facts": {"hp_pct": hp, "matchup": matchup, "faster": True}}


def request(options, **state):
    s = {"turn": 6, "our_species": "charizard", "opp_species": "blastoise", "our_hp_pct": 100.0, "opp_hp_pct": 100.0,
         "we_faster": True, "our_left": 6, "opp_left": 6, "turns_since_switch": 5, "opp_just_switched": False,
         "active_matchup": 0.0, "forced_switch": False}
    s.update(state)
    return {"decision_id": "b-t06-0", "state": s, "state_text": "", "options": options}


class FakeClient:
    model = "fake"

    def __init__(self, pick=None, fail=False):
        self.pick, self.fail, self.calls, self.input_tokens = pick, fail, [], 0

    def ask(self, state, questions):
        self.calls.append((state, questions))
        if self.fail:
            raise RuntimeError("HTTP 500")
        names = list(questions["pick"]["criteria"])
        c = self.pick or names[0]
        return {"model": "fake", "answers": {"pick": {"type": "choice", "choice": c,
                                                     "probabilities": {n: float(n == c) for n in names}}},
                "usage": {"input_tokens": 1000}}

    def cost_usd(self):
        return 0.0


class Render(unittest.TestCase):
    def test_all_options_visible_with_facts(self):
        r = request([move("m_flamethrower", "Flamethrower", 60, type_mult=2.0, likely_ko=True), switch("pikachu", 1.2)])
        state, q, back = choice_question(r)
        self.assertEqual(set(state["options"]), {"Flamethrower", "Switch to pikachu"})
        self.assertEqual(state["options"]["Flamethrower"]["effectiveness"], "2x")
        self.assertTrue(state["options"]["Flamethrower"]["likely_ko"])
        self.assertEqual(q["pick"]["instructions"], PLAYER_Q)
        self.assertEqual(back["Switch to pikachu"], "s_pikachu")
        self.assertNotIn("designer_intent", state)

    def test_intent_goes_into_state_and_question(self):
        state, q, _ = choice_question(request([move("m_a", "A"), move("m_b", "B")]), "Never repeat a move.")
        self.assertEqual(state["designer_intent"], "Never repeat a move.")
        self.assertEqual(q["pick"]["instructions"], STEER_Q)

    def test_properties_only_when_true(self):
        self.assertEqual(option_json(move("m_a", "A", recoil=True))["properties"], ["recoil"])
        self.assertEqual(option_json(move("m_a", "A"))["properties"], [])


class Rule(unittest.TestCase):
    def test_prefers_accurate_ko_then_damage(self):
        r = request([move("m_a", "A", 150, likely_ko=True, accuracy=0.8), move("m_b", "B", 110, likely_ko=True),
                     move("m_c", "C", 60)])
        self.assertEqual(rule_pick(r), "m_b")

    def test_switches_only_on_bad_matchup(self):
        self.assertEqual(rule_pick(request([move("m_a", "A", 20), switch("x", 1.0)], active_matchup=-2.5)), "s_x")
        self.assertEqual(rule_pick(request([move("m_a", "A", 20), switch("x", 1.0)])), "m_a")


class Decider(unittest.TestCase):
    def test_jev_pick_mapped_back(self):
        c = FakeClient(pick="Switch to pikachu")
        pick, entry = JevDecider(c).decide(request([move("m_a", "A"), switch("pikachu")]))
        self.assertEqual(pick, "s_pikachu")
        self.assertEqual(entry["rule_pick"], "m_a")

    def test_single_option_skips_api_and_errors_fall_back(self):
        c = FakeClient()
        self.assertEqual(JevDecider(c).decide(request([move("m_a", "A")]))[0], "m_a")
        self.assertEqual(c.calls, [])
        d = JevDecider(FakeClient(fail=True))
        pick, entry = d.decide(request([move("m_a", "A", 20), move("m_b", "B", 80)]))
        self.assertEqual((pick, d.fallbacks), ("m_b", 1))

    def test_stub_client_answers_every_question(self):
        r = request([move("m_a", "A"), move("m_b", "B"), switch("x")])
        pick, _ = JevDecider(StubClient(1)).decide(r)
        self.assertIn(pick, {"m_a", "m_b", "s_x"})
        self.assertEqual(RuleDecider().decide(r)[0], rule_pick(r))


class Intents(unittest.TestCase):
    def test_every_text_has_a_checker(self):
        self.assertEqual(set(TEXTS), set(INTENTS))
        self.assertEqual(len(INTENTS), 20)

    def test_ha05_conflict(self):
        r = request([move("m_rep", "Rep", 90, consecutive_uses=2), move("m_alt", "Alt", 40)])
        it = INTENTS["ha05"]
        self.assertTrue(it["applies"](r))
        rep, alt = r["options"]
        self.assertFalse(it["complies"](r, rep))       # the rule's pick (more damage) breaks the intent: a conflict
        self.assertTrue(it["complies"](r, alt))
        self.assertEqual(rule_pick(r), "m_rep")


class Evaluate(unittest.TestCase):
    def test_conflict_compliance_from_a_run_dir(self):
        r = request([move("m_rep", "Rep", 90, consecutive_uses=2), move("m_alt", "Alt", 40)])
        with tempfile.TemporaryDirectory() as d:
            Path(d, "summary.json").write_text(json.dumps({"decider": "jev_steer_ha05", "intent": "ha05", "battles": 2,
                                                           "wins": 1, "cost_usd": 0.0}))
            recs = [{"battle": "b", "request": r, "chosen_id": "m_alt", "decision": {}},
                    {"battle": "b", "request": r, "chosen_id": "m_rep", "decision": {"fallback": "HTTP 500"}}]
            Path(d, "decisions.jsonl").write_text("\n".join(json.dumps(x) for x in recs))
            e = evaluate(d)
        self.assertEqual((e["conflict_turns"], e["conflict_compliance"], e["fallbacks"]), (2, 0.5, 1))
        self.assertEqual(e["win_rate"], 0.5)
        lo, hi = wilson(54, 100)
        self.assertAlmostEqual(lo, 0.4426, places=3)


if __name__ == "__main__":
    unittest.main()
