"""Minimal client for TypeSafe's System One API (Jev). Docs: https://docs.typesafe.ai

The API key is read from the TYPESAFE_API_KEY environment variable and is never logged. The model is pinned to a
versioned ID (the `jev-latest` alias moves when a new release ships). Calls cost money: about $0.042 per million
input tokens at the time of writing (see https://docs.typesafe.ai/models).
"""
import json
import os
import random
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
PRICE_PER_M_INPUT = 0.042
RETRY_CODES = (429, 500, 502, 503, 504, 529)


class JevClient:
    def __init__(self, model=MODEL, key=None, timeout=60, tries=6):
        self.model, self.timeout, self.tries = model, timeout, tries
        self.key = key or os.environ.get("TYPESAFE_API_KEY")
        if not self.key:
            raise SystemExit("set TYPESAFE_API_KEY (or use --stub for a free dry run)")
        self.input_tokens = 0

    def ask(self, state, questions):
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode("utf-8")
        req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                     headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        last = None
        for t in range(self.tries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read().decode("utf-8"))
                self.input_tokens += (data.get("usage") or {}).get("input_tokens", 0)
                return data
            except urllib.error.HTTPError as e:
                last = "HTTP %d" % e.code
                if e.code not in RETRY_CODES:
                    break
            except Exception as e:
                last = type(e).__name__
            time.sleep(min(60, 2 ** t))
        raise RuntimeError(last)

    def cost_usd(self):
        return self.input_tokens / 1e6 * PRICE_PER_M_INPUT


class StubClient:
    """Random but valid answers, no network: for rehearsing the pipeline for free."""
    model = "stub"

    def __init__(self, seed=0):
        self.rng, self.input_tokens = random.Random(seed), 0

    def ask(self, state, questions):
        ans = {}
        for qid, q in questions.items():
            names = list(q["criteria"])
            ps = [self.rng.random() for _ in names]
            z = sum(ps)
            pr = {n: p / z for n, p in zip(names, ps)}
            ans[qid] = {"type": "choice", "choice": max(pr, key=pr.get), "probabilities": pr, "confidence": 0.5}
        return {"model": "stub", "answers": ans, "usage": {"input_tokens": 0}}

    def cost_usd(self):
        return 0.0
