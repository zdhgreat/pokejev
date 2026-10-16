"""Optional decision features and the named versions used in the improvement study.

tera      offer each damaging move also with Terastallize (gen 9), with adjusted damage and the post-Tera type
calc      damage from poke-env's Showdown calculator where it runs (abilities, items, weather, screens)
exchange  one-turn trade facts per option: opponent's best reply, who moves first, KO either way
two_stage Jev shortlists 4 options, then chooses among them with a consequence brief (two calls per turn)
memory    short memory of the last exchanges: HP changes, revealed moves, "no visible effect"
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Features:
    tera: bool = False
    calc: bool = False
    exchange: bool = False
    two_stage: bool = False
    memory: bool = False


VERSIONS = {
    "v01": Features(),
    "v1": Features(tera=True, calc=True),
    "v2": Features(tera=True, calc=True, exchange=True),
    "v3": Features(tera=True, calc=True, exchange=True, two_stage=True),
    "v4": Features(tera=True, calc=True, exchange=True, memory=True),
}
