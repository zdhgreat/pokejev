"""poke-env player: code builds the facts for every legal option, a decider picks, code executes and logs."""
import asyncio
import random

from poke_env.battle import PokemonType
from poke_env.player import Player

from pokejev import facts as F
from pokejev.features import Features


class DeciderPlayer(Player):
    def __init__(self, decider, seed=0, features=Features(), **kwargs):
        super().__init__(**kwargs)
        self.decider, self.features = decider, features
        self.rng = random.Random(seed)
        self.records, self.hist, self.errors = [], {}, []

    def _history(self, battle):
        h = self.hist.setdefault(battle.battle_tag, {"last_switch_turn": 0, "last_move": None, "consecutive": 0,
                                                     "last_opp": None, "memory": [], "pending": None})
        opp = battle.opponent_active_pokemon.species if battle.opponent_active_pokemon else None
        just = h["last_opp"] is not None and opp != h["last_opp"]
        h["last_opp"] = opp
        return h, {"turns_since_switch": battle.turn - h["last_switch_turn"], "opp_just_switched": just}

    # ------------------------------------------------------------------ memory (features.memory)
    def _snapshot(self, battle, option):
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        return {"turn": battle.turn, "we_used": option["text"], "damaging": option["kind"] == "move"
                and option["facts"].get("est_damage_pct", 0) > 0, "opp_species": opp.species,
                "opp_hp": opp.current_hp_fraction, "our_species": me.species, "our_hp": me.current_hp_fraction,
                "opp_moves": sorted(opp.moves)}

    def _update_memory(self, battle, h):
        p = h["pending"]
        if p is None:
            return
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        same_opp = opp is not None and opp.species == p["opp_species"]
        entry = {"turn": p["turn"], "we_used": p["we_used"], "opponent_switched_out": not same_opp,
                 "opponent_revealed_moves": sorted(set(opp.moves) - set(p["opp_moves"])) if same_opp else [],
                 "opponent_hp_change_pct": round(100 * (opp.current_hp_fraction - p["opp_hp"]), 1) if same_opp else None,
                 "our_hp_change_pct": round(100 * (me.current_hp_fraction - p["our_hp"]), 1)
                 if me is not None and me.species == p["our_species"] else None}
        if p["damaging"] and same_opp and entry["opponent_hp_change_pct"] == 0:
            entry["no_visible_effect"] = True                  # missed, blocked, immune or healed back
        h["memory"] = (h["memory"] + [entry])[-3:]
        h["pending"] = None

    # ------------------------------------------------------------------ request
    def build_request(self, battle):
        fx = self.features
        h, view = self._history(battle)
        if fx.memory:
            self._update_memory(battle, h)
        me, opp = battle.active_pokemon, battle.opponent_active_pokemon
        tera_type = F.own_tera_type(battle) if fx.tera and battle.can_tera else None
        options = []
        for mv in battle.available_moves:
            cons = h["consecutive"] if mv.id == h["last_move"] else 0
            name = mv.entry.get("name", mv.id)
            options.append({"id": "m_" + mv.id, "kind": "move", "text": name,
                            "facts": F.move_facts(battle, mv, cons, use_calc=fx.calc)})
            if tera_type is not None and mv.category.name != "STATUS":       # offensive Tera only
                f = F.move_facts(battle, mv, cons, use_calc=fx.calc, tera=tera_type)
                f.update(terastallize=True, tera_type=tera_type.name.lower())
                options.append({"id": "t_" + mv.id, "kind": "move", "text": name + " (Terastallize)", "facts": f})
        for mon in battle.available_switches:
            options.append({"id": "s_" + mon.species, "kind": "switch", "text": "Switch %s" % mon.species,
                            "facts": F.switch_facts(battle, mon)})
        if fx.exchange:
            self._add_exchange(battle, options, me, opp, branches=fx.two_stage)
        self.rng.shuffle(options)                         # no fixed option order for the model to lean on
        state, text = F.state_facts(battle, view)
        if fx.exchange:
            state["opponent_revealed_moves"] = sorted(m.entry.get("name", m.id) for m in opp.moves.values())
        if fx.memory and h["memory"]:
            state["memory"] = list(h["memory"])
        return {"decision_id": "%s-t%02d-%d" % (battle.battle_tag, battle.turn, len(self.records)),
                "state": state, "state_text": text, "options": options}

    def _add_exchange(self, battle, options, me, opp, branches):
        """One-turn trade facts per option (features.exchange); with branches, also the opponent-switch branch."""
        calc = self.features.calc
        bench = [m for m in battle.opponent_team.values() if m is not opp and not m.fainted]
        for o in options:
            f = o["facts"]
            if o["kind"] == "move":
                mv = next(m for m in battle.available_moves if m.id == o["id"][2:])
                types = [PokemonType.from_name(f["tera_type"])] if f.get("terastallize") else None
                label, mean, low = F.opponent_threat(battle, opp, me, calc, target_types=types)
                first = F.moves_first(battle, mv, opp)
                f["exchange"] = {"we_move_first": first, "opponent_best_reply": label,
                                 "reply_damage_pct_of_our_hp": round(100 * mean, 1),
                                 "reply_likely_ko_us": bool(low > 0 and low >= me.current_hp_fraction),
                                 "we_ko_before_reply": bool(f["likely_ko"] and first)}
                if branches and bench and f.get("est_damage_pct", 0) > 0:
                    hits = [(m.species, 100 * F.damage(me, m, mv)[0]) for m in bench]
                    sp, pct = min(hits, key=lambda x: x[1])
                    f["if_opponent_switches"] = {"to_best_revealed_counter": sp,
                                                 "our_damage_to_it_pct": round(min(pct, 200.0), 1)}
            else:
                mon = next(m for m in battle.available_switches if "s_" + m.species == o["id"])
                label, mean, low = F.opponent_threat(battle, opp, mon, calc)
                f["exchange"] = {"switch_in_takes_reply": label,
                                 "reply_damage_pct_of_switch_in_hp": round(100 * mean, 1),
                                 "reply_likely_ko_switch_in": bool(low > 0 and low >= mon.current_hp_fraction)}

    # ------------------------------------------------------------------ act
    async def choose_move(self, battle):
        if battle.active_pokemon is None or battle.opponent_active_pokemon is None:
            return self.choose_random_move(battle)
        try:
            request = self.build_request(battle)
        except Exception as exc:                             # counted, never silently swallowed
            self.errors.append({"battle": battle.battle_tag, "turn": battle.turn, "error": repr(exc)})
            return self.choose_random_move(battle)
        if not request["options"]:
            return self.choose_random_move(battle)
        # the API call runs in a worker thread so other battles / players on the event loop are not blocked
        chosen, entry = await asyncio.to_thread(self.decider.decide, request)
        self.records.append({"battle": battle.battle_tag, "request": request, "chosen_id": chosen, "decision": entry})
        h = self.hist[battle.battle_tag]
        option = next(o for o in request["options"] if o["id"] == chosen)
        if self.features.memory:
            h["pending"] = self._snapshot(battle, option)
        if chosen.startswith("s_"):
            h.update(last_switch_turn=battle.turn, last_move=None, consecutive=0)
            return self.create_order(next(m for m in battle.available_switches if "s_" + m.species == chosen))
        mid = chosen[2:]
        h["consecutive"] = h["consecutive"] + 1 if h["last_move"] == mid else 1
        h["last_move"] = mid
        move = next(m for m in battle.available_moves if m.id == mid)
        return self.create_order(move, terastallize=chosen.startswith("t_"))
