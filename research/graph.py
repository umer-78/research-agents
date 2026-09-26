"""The supervisor: plan, research every sub-question, review, send the unanswered back once,
write. Budgets live here, not in prompts: sub-questions, searches per sub-question, metered
tokens and a wall-clock ceiling. The whole state is stored after every step, so a run that
dies resumes where it stopped and ends the same way; every step is traced."""
import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass

from .agents import Attempt, Finding, Plan, SubQuestion, planner, researcher, writer

RETRYABLE = ("rate_limited", "timeout", "no_results")
SYSTEM_TOKENS = 300


@dataclass
class Budget:
    max_subquestions: int = 8
    max_searches: int = 3                # per sub-question, across the first pass and the send-back
    max_tokens: int = 20_000
    max_seconds: float = 30.0
    send_backs: int = 1


def tokens(obj):
    return max(1, len(json.dumps(obj, default=str)) // 4)


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS steps (run TEXT, step INTEGER, state TEXT, PRIMARY KEY (run, step))")

    def save(self, state):
        self.db.execute("INSERT OR REPLACE INTO steps VALUES (?, ?, ?)", (state["run"], state["step"], json.dumps(state)))
        self.db.commit()

    def latest(self, run):
        row = self.db.execute("SELECT state FROM steps WHERE run = ? ORDER BY step DESC LIMIT 1", (run,)).fetchone()
        return json.loads(row[0]) if row else None


def trace(state, node, status, t_in, t_out, started):
    state["tokens"] += t_in + t_out
    state["trace"].append({"step": state["step"], "node": node, "status": status, "tokens": t_in + t_out,
                           "ms": round(1000 * (time.perf_counter() - started), 2)})
    state["step"] += 1


def run(run_id, question, web, known, store, budget=Budget(), crash_after=None):
    """Run (or resume) to the end; `crash_after` stops after that many steps, as a killed process would."""
    state = store.latest(run_id) or {"run": run_id, "question": question, "step": 0, "stage": "plan", "tokens": 0,
                                     "plan": None, "attempts": {}, "pass": 0, "report": None, "status": "running",
                                     "trace": [], "elapsed": 0.0}
    clock = time.perf_counter() - state["elapsed"]
    while state["status"] == "running":
        if crash_after is not None and state["step"] >= crash_after:
            return state
        if state["tokens"] > budget.max_tokens or time.perf_counter() - clock > budget.max_seconds:
            state["status"] = "stopped_budget"
            break
        started = time.perf_counter()
        if state["stage"] == "plan":
            plan = planner(question, known, budget.max_subquestions)
            state["plan"] = asdict(plan)
            state["stage"] = "research"
            trace(state, "planner", f"{len(plan.subquestions)} sub-questions", SYSTEM_TOKENS + tokens(question), tokens(state["plan"]), started)
        elif state["stage"] == "research":
            pending = [i for i, s in enumerate(state["plan"]["subquestions"])
                       if str(i) not in state["attempts"] or (state["attempts"][str(i)]["status"] in RETRYABLE and state["pass"] > 0
                                                              and not state["attempts"][str(i)].get("retried"))]
            if not pending:
                state["stage"] = "review"
                continue
            i = pending[0]
            prev = state["attempts"].get(str(i))
            left = budget.max_searches - (prev["searches"] if prev else 0)
            a = researcher(SubQuestion(**state["plan"]["subquestions"][i]), web, f"{state['pass']}", left) if left > 0 else \
                Attempt(SubQuestion(**state["plan"]["subquestions"][i]), prev["status"])
            rec = asdict(a)
            rec["searches"] += prev["searches"] if prev else 0
            rec["retried"] = prev is not None
            state["attempts"][str(i)] = rec
            trace(state, "researcher", a.status, SYSTEM_TOKENS + tokens(asdict(a.subquestion)), tokens(rec), started)
        elif state["stage"] == "review":
            retry = [k for k, a in state["attempts"].items() if a["status"] in RETRYABLE and not a.get("retried")]
            if retry and state["pass"] < budget.send_backs:
                state["pass"] += 1
                state["stage"] = "research"
                verdict = f"sent back {len(retry)}"
            else:
                state["stage"] = "write"
                verdict = "complete" if not retry else f"{len(retry)} unanswered, no send-backs left"
            trace(state, "supervisor", verdict, SYSTEM_TOKENS + tokens(state["attempts"]), 20, started)
        else:
            attempts = [state["attempts"][str(i)] for i in range(len(state["plan"]["subquestions"]))]
            found = [Finding(**a["finding"]) for a in attempts if a["finding"]]
            gaps = [Attempt(SubQuestion(**a["subquestion"]), a["status"]) for a in attempts if not a["finding"]]
            state["report"] = writer(Plan(state["plan"]["question"], [SubQuestion(**s) for s in state["plan"]["subquestions"]]),
                                     found, gaps)
            state["status"] = "done"
            trace(state, "writer", "done", SYSTEM_TOKENS + tokens([asdict(f) for f in found]), tokens(state["report"]), started)
        state["elapsed"] = time.perf_counter() - clock
        store.save(state)
    store.save(state)
    return state


def fingerprint(state):
    """What must match after a resume: the report and the path taken (timestamps and timings aside)."""
    import re
    report = re.sub(r"\d{10}\.\d+", "", state["report"] or "")
    return hashlib.sha256(json.dumps([report, [(t["node"], t["status"]) for t in state["trace"]]]).encode()).hexdigest()[:16]
