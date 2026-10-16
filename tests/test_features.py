"""v0.2 features: Tera factor, opponent threat, consequence brief, two-stage decider. Offline."""
import unittest

from poke_env.battle import Move, PokemonType

from pokejev import facts as F
from pokejev.decider import JevDecider
from pokejev.features import VERSIONS, Features
from pokejev.render import brief_question, choice_question
from test_core import move, request, switch


class Mon:
    def __init__(self, types=("FIRE",), tera=None, terastallized=False, moves=(), atk=100, spa=100, df=100, spd=100,
                 spe=100, hp=100, level=80, hp_frac=1.0):
        self.level, self.stats, self.boosts, self.current_hp_fraction = level, {}, {}, hp_frac
        self.base_stats = {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": spe}
        self.types = [PokemonType[t] for t in types]
        self.tera_type = PokemonType[tera] if tera else None
        self.is_terastallized = terastallized
        self.moves = {m: Move(m, gen=9) for m in moves}

    def damage_multiplier(self, move):
        return F._type_mult(move.type, self.types)


class Tera(unittest.TestCase):
    def test_stab_gain_and_upgrade(self):
        self.assertEqual(F.tera_multiplier(Mon(types=("FIRE",), tera="WATER"), Move("surf", gen=9)), 1.5)
        self.assertAlmostEqual(F.tera_multiplier(Mon(types=("FIRE",), tera="FIRE"), Move("flamethrower", gen=9)), 2 / 1.5)
        self.assertEqual(F.tera_multiplier(Mon(types=("FIRE",), tera="WATER"), Move("flamethrower", gen=9)), 1.0)
        self.assertEqual(F.tera_multiplier(Mon(tera="WATER", terastallized=True), Move("surf", gen=9)), 1.0)


class Threat(unittest.TestCase):
    def test_revealed_move_beats_estimate_and_tera_changes_types(self):
        opp = Mon(types=("WATER",), moves=("surf", "toxic"))
        me = Mon(types=("FIRE",))
        label, mean, low = F.opponent_threat(None, opp, me, use_calc=False)
        self.assertEqual(label, "Surf")
        self.assertGreater(mean, low)
        _, mean_tera, _ = F.opponent_threat(None, opp, me, use_calc=False, target_types=[PokemonType.WATER])
        self.assertAlmostEqual(mean_tera / mean, 0.5 / 2.0)              # fire -> water: 2x becomes 0.5x

    def test_stab_estimate_when_nothing_revealed(self):
        label, mean, _ = F.opponent_threat(None, Mon(types=("ELECTRIC",)), Mon(types=("WATER",)), use_calc=False)
        self.assertIn("electric", label)
        self.assertGreater(mean, 0)


class Brief(unittest.TestCase):
    def _req(self):
        opts = [move("m_a", "A", 80), move("m_b", "B", 60), move("m_c", "C", 40), move("m_d", "D", 20), switch("x")]
        for o in opts:
            o["facts"]["exchange"] = {"reply_damage_pct_of_our_hp": 30.0}
        opts[0]["facts"]["if_opponent_switches"] = {"to_best_revealed_counter": "y", "our_damage_to_it_pct": 10.0}
        return request(opts)

    def test_stage_one_shows_next_turn_but_not_branches(self):
        state, _, _ = choice_question(self._req())
        self.assertIn("next_turn", state["options"]["A"])
        self.assertNotIn("if_opponent_switches", state["options"]["A"])

    def test_brief_keeps_shortlist_and_moves_facts_into_brief(self):
        state, q, back = brief_question(self._req(), {"m_a", "m_b"})
        self.assertEqual(set(state["options"]), {"A", "B"})
        self.assertNotIn("next_turn", state["options"]["A"])
        self.assertEqual(state["consequence_brief"]["A"]["if_opponent_switches"]["to_best_revealed_counter"], "y")
        self.assertEqual(set(q["pick"]["criteria"]), {"A", "B"})
        self.assertEqual(back["B"], "m_b")


class TwoStage(unittest.TestCase):
    class Client:
        model = "fake"

        def __init__(self):
            self.calls, self.input_tokens = [], 0

        def ask(self, state, questions):
            self.calls.append(questions)
            names = list(questions["pick"]["criteria"])
            pr = {n: (len(names) - i) / sum(range(1, len(names) + 1)) for i, n in enumerate(names)}
            pick = names[-1] if len(self.calls) == 2 else names[0]          # stage 2 picks the last shortlisted
            return {"model": "fake", "answers": {"pick": {"choice": pick, "probabilities": pr}}, "usage": {}}

        def cost_usd(self):
            return 0.0

    def test_second_call_only_with_more_than_shortlist_options(self):
        r = request([move("m_%d" % i, "M%d" % i, 10 * i) for i in range(1, 7)])
        c = self.Client()
        pick, entry = JevDecider(c, two_stage=True).decide(r)
        self.assertEqual(len(c.calls), 2)
        self.assertEqual(len(c.calls[1]["pick"]["criteria"]), 4)
        self.assertEqual(entry["stage1_pick"], entry["shortlist"][0])
        self.assertIn(pick, entry["shortlist"])
        c2 = self.Client()
        JevDecider(c2, two_stage=True).decide(request([move("m_%d" % i, "M%d" % i, 10 * i) for i in range(1, 4)]))
        self.assertEqual(len(c2.calls), 1)


class Versions(unittest.TestCase):
    def test_versions_are_nested_as_documented(self):
        self.assertEqual(VERSIONS["v01"], Features())
        for v in ("v2", "v3", "v4"):
            self.assertTrue(VERSIONS[v].tera and VERSIONS[v].calc and VERSIONS[v].exchange)
        self.assertTrue(VERSIONS["v3"].two_stage and not VERSIONS["v3"].memory)
        self.assertTrue(VERSIONS["v4"].memory and not VERSIONS["v4"].two_stage)


if __name__ == "__main__":
    unittest.main()
