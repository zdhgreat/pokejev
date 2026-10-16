"""Command line.

    python -m pokejev play --decider jev --battles 10 --out runs/jev-player
    python -m pokejev play --decider jev --intent ha05 --battles 10 --out runs/jev-ha05
    python -m pokejev play --decider rule --battles 10 --out runs/rule
    python -m pokejev play --decider jev --battles 2 --out runs/dry --stub      # free rehearsal, random answers
    python -m pokejev eval runs/jev-ha05
    python -m pokejev view runs/jev-ha05                                         # battle viewer (HTML)
    python -m pokejev demo [--real] [--intent ha05]                              # one battle, then the viewer
    python -m pokejev intents                                                    # list the designer intents

Needs a local Pokemon Showdown server on 127.0.0.1:8000 (see README).
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from pokejev.decider import JevDecider, RuleDecider
from pokejev.evaluate import evaluate
from pokejev.features import VERSIONS
from pokejev.intents import INTENTS
from pokejev import viewer
from pokejev.jev import JevClient, StubClient

FORMAT = "gen9randombattle"


async def play(decider_name, intent_id, n, out, seed, budget, stub, version="v4"):
    from poke_env import AccountConfiguration, LocalhostServerConfiguration
    from poke_env.player import SimpleHeuristicsPlayer
    from pokejev.player import DeciderPlayer
    intent = INTENTS[intent_id] if intent_id else None
    client = None
    if decider_name == "rule":
        decider = RuleDecider()
    else:
        client = StubClient(seed) if stub else JevClient()
        decider = JevDecider(client, intent, budget_usd=budget, two_stage=VERSIONS[version].two_stage)
    tag = "%d%03d" % (int(time.time()) % 100000, seed % 1000)       # unique account names per run
    me = DeciderPlayer(decider, seed=seed, features=VERSIONS[version], battle_format=FORMAT, max_concurrent_battles=1,
                       save_replays=str(out / "replays"),               # Showdown battle logs for the viewer
                       account_configuration=AccountConfiguration("pj%s" % tag, None),
                       server_configuration=LocalhostServerConfiguration)
    opp = SimpleHeuristicsPlayer(battle_format=FORMAT, max_concurrent_battles=1,
                                 account_configuration=AccountConfiguration("pjop%s" % tag, None),
                                 server_configuration=LocalhostServerConfiguration)
    t0 = time.time()
    await me.battle_against(opp, n_battles=n)
    out.mkdir(parents=True, exist_ok=True)              # replays/ already exists
    with (out / "decisions.jsonl").open("w", encoding="utf-8") as f:
        for r in me.records:
            b = me.battles.get(r["battle"])
            f.write(json.dumps(dict(r, won=None if b is None else b.won)) + "\n")
    s = {"decider": decider.name, "version": version, "intent": intent_id, "battles": n, "wins": me.n_won_battles,
         "losses": opp.n_won_battles, "decisions": len(me.records), "facts_errors": len(me.errors),
         "seconds": round(time.time() - t0, 1), "seed": seed, "stub": stub,
         "model": None if client is None else client.model,
         "input_tokens": None if client is None else client.input_tokens,
         "cost_usd": None if client is None else round(client.cost_usd(), 5)}
    (out / "summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    return s


def main():
    ap = argparse.ArgumentParser(prog="pokejev")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("play")
    p.add_argument("--decider", choices=["jev", "rule"], required=True)
    p.add_argument("--intent", choices=sorted(INTENTS), help="designer intent id (see `intents`)")
    p.add_argument("--battles", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--budget", type=float, default=0.20, help="stop calling Jev after this spend (USD)")
    p.add_argument("--stub", action="store_true", help="random answers, no API key, no cost")
    p.add_argument("--version", choices=sorted(VERSIONS), default="v4", help="feature set (see pokejev/features.py)")
    p.add_argument("--out", required=True)
    e = sub.add_parser("eval")
    e.add_argument("run_dir")
    v = sub.add_parser("view")
    v.add_argument("run_dir")
    v.add_argument("--no-open", action="store_true")
    dm = sub.add_parser("demo")
    dm.add_argument("--real", action="store_true", help="use the real Jev API (needs TYPESAFE_API_KEY, ~$0.001)")
    dm.add_argument("--intent", choices=sorted(INTENTS))
    dm.add_argument("--battles", type=int, default=1)
    sub.add_parser("intents")
    a = ap.parse_args()
    if a.cmd == "intents":
        for k, it in INTENTS.items():
            print("%s  %s" % (k, it["text"]))
    elif a.cmd == "eval":
        print(json.dumps(evaluate(a.run_dir), indent=1))
    elif a.cmd == "view":
        print("viewer:", viewer.write(a.run_dir, open_browser=not a.no_open))
    elif a.cmd == "demo":
        out = Path("runs") / ("demo-%s%s-%d" % ("real" if a.real else "stub", "-" + a.intent if a.intent else "",
                                               int(time.time())))
        s = asyncio.run(play("jev", a.intent, a.battles, out, 0, 0.05, not a.real))
        print("won %d of %d battle(s); %s" % (s["wins"], s["battles"], "real Jev" if a.real else
                                             "stub answers (random) - use --real for Jev"))
        print("viewer:", viewer.write(out))
    else:
        if a.decider == "rule" and a.intent:
            raise SystemExit("the rule ignores intents; use --decider jev with --intent")
        out = Path(a.out)
        if out.exists():
            raise SystemExit("refusing to overwrite %s" % out)
        print(json.dumps(asyncio.run(play(a.decider, a.intent, a.battles, out, a.seed, a.budget, a.stub, a.version)), indent=1))


if __name__ == "__main__":
    main()
