"""Deciders: decide(request) -> (option id, log entry).

RuleDecider: the baseline rule.
JevDecider:  Jev picks the move with ONE Choice question per turn over all options (structured state). With an
             intent, the question asks for the option that follows the designer intent and, among those, best helps
             win. Single-option turns skip the API; an API error or the budget falls back to the rule (counted).
             two_stage: when there are more than `shortlist` options, the top ones from the first answer are asked
             again with a consequence brief (render.brief_question); a failed second call keeps the first pick.
"""
import time

from pokejev.render import brief_question, choice_question
from pokejev.rules import rule_pick


class RuleDecider:
    name = "rule"

    def decide(self, request):
        rid = rule_pick(request)
        return rid, {"decision_id": request["decision_id"], "rule_pick": rid, "pick": rid}


class JevDecider:
    def __init__(self, client, intent=None, budget_usd=0.20, two_stage=False, shortlist=4):
        self.client, self.intent, self.budget = client, intent, budget_usd
        self.two_stage, self.shortlist = two_stage, shortlist
        self.name = "jev" if intent is None else "jev_steer_" + intent["id"]
        self.fallbacks = 0

    def decide(self, request):
        rid = rule_pick(request)
        entry = {"decision_id": request["decision_id"], "rule_pick": rid}
        if len(request["options"]) < 2:
            entry.update(pick=rid, skipped="single_option")
            return rid, entry
        if self.client.cost_usd() >= self.budget:
            self.fallbacks += 1
            entry.update(pick=rid, fallback="budget")
            return rid, entry
        state, q, back = choice_question(request, None if self.intent is None else self.intent["text"])
        t0 = time.perf_counter()
        try:
            data = self.client.ask(state, q)
            ans = data["answers"]["pick"]
            pick = back[ans["choice"]]
        except Exception as e:
            self.fallbacks += 1
            entry.update(pick=rid, fallback=str(e)[:120])
            return rid, entry
        probs = {back[n]: float(p) for n, p in ans["probabilities"].items()}
        entry.update(pick=pick, probs=probs, latency_ms=1000 * (time.perf_counter() - t0), model=data.get("model"),
                     usage=data.get("usage"))
        if self.two_stage and len(request["options"]) > self.shortlist:
            keep = sorted(probs, key=probs.get, reverse=True)[:self.shortlist]
            try:
                state, q, back2 = brief_question(request, set(keep), None if self.intent is None else self.intent["text"])
                data2 = self.client.ask(state, q)
                pick = back2[data2["answers"]["pick"]["choice"]]
                entry.update(stage1_pick=entry["pick"], shortlist=keep, pick=pick, usage2=data2.get("usage"),
                             probs2={back2[n]: float(p) for n, p in data2["answers"]["pick"]["probabilities"].items()})
            except Exception as e:                                  # keep the stage-1 pick (counted, not a fallback)
                entry.update(stage2_error=str(e)[:120])
        return pick, entry
