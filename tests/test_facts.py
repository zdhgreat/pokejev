"""Damage estimates, including variable-power moves. Uses poke-env move data and small fake Pokemon objects."""
import unittest

from poke_env.battle import Move

from pokejev import facts as F


class Mon:
    def __init__(self, atk=100, df=100, spa=100, spd=100, spe=100, hp=100, weight=50.0, hp_frac=1.0, mult=1.0,
                 boosts=None, level=80):
        self.level, self.stats, self.types, self.weight = level, {}, (), weight
        self.base_stats = {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": spe}
        self.boosts = boosts or {}
        self.current_hp_fraction, self._mult = hp_frac, mult

    def damage_multiplier(self, move):
        return self._mult


def mv(name):
    return Move(name, gen=9)


class VariablePower(unittest.TestCase):
    def test_weight_moves(self):
        self.assertEqual(F.base_power(Mon(weight=400), Mon(weight=50), mv("heavyslam")), 120)
        self.assertEqual(F.base_power(Mon(weight=60), Mon(weight=50), mv("heatcrash")), 40)
        self.assertEqual(F.base_power(Mon(), Mon(weight=5), mv("lowkick")), 20)
        self.assertEqual(F.base_power(Mon(), Mon(weight=250), mv("grassknot")), 120)
        self.assertGreater(F.damage(Mon(weight=400), Mon(weight=50), mv("heavyslam"))[0], 0)

    def test_speed_moves(self):
        self.assertEqual(F.base_power(Mon(spe=50), Mon(spe=150), mv("gyroball")), min(150, int(25 * F.speed(Mon(spe=150)) / F.speed(Mon(spe=50))) + 1))
        self.assertEqual(F.base_power(Mon(spe=255), Mon(spe=20), mv("electroball")), 150)   # speed ratio ~5.8

    def test_hp_and_boost_moves(self):
        self.assertEqual(F.base_power(Mon(hp_frac=0.5), Mon(), mv("eruption")), 75)
        self.assertEqual(F.base_power(Mon(hp_frac=0.02), Mon(), mv("flail")), 200)
        self.assertEqual(F.base_power(Mon(), Mon(hp_frac=0.5), mv("crushgrip")), 60)
        self.assertEqual(F.base_power(Mon(boosts={"atk": 2, "spe": 1, "def": -1}), Mon(), mv("storedpower")), 80)

    def test_stat_swaps(self):
        weak_def, strong_def = Mon(df=50), Mon(df=200)
        self.assertGreater(F.damage(strong_def, Mon(), mv("bodypress"))[0], F.damage(weak_def, Mon(), mv("bodypress"))[0])
        self.assertGreater(F.damage(Mon(atk=10), Mon(atk=200), mv("foulplay"))[0],
                           F.damage(Mon(atk=10), Mon(atk=50), mv("foulplay"))[0])


class FixedDamage(unittest.TestCase):
    def test_super_fang_halves_current_hp_and_respects_immunity(self):
        self.assertAlmostEqual(F.damage(Mon(), Mon(hp_frac=0.8), mv("superfang"))[0], 0.4)
        self.assertEqual(F.damage(Mon(), Mon(hp_frac=0.8, mult=0.0), mv("superfang")), (0.0, 0.0))

    def test_level_and_ohko(self):
        self.assertAlmostEqual(F.damage(Mon(level=80), Mon(), mv("seismictoss"))[0], 80 / F.stat(Mon(), "hp"))
        self.assertEqual(F.damage(Mon(), Mon(hp_frac=0.6), mv("sheercold")), (0.6, 0.6))

    def test_ordinary_move_unchanged(self):
        self.assertEqual(F.base_power(Mon(), Mon(), mv("flamethrower")), 90)
        self.assertGreater(F.damage(Mon(), Mon(), mv("flamethrower"))[0], 0)
        self.assertEqual(F.damage(Mon(), Mon(), mv("counter")), (0.0, 0.0))     # documented: still unknown


if __name__ == "__main__":
    unittest.main()
