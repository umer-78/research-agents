"""100 research questions, each comparing two packages on licence, dependencies and author (six
sub-questions), against the local web with tools failing 15% of the time. Measured: whether
each claim matches the structured PyPI record behind the page, whether its citation supports
it, how many sub-questions end answered, what the retries and the one send-back recover, the
metered cost, and whether runs killed mid-way resume to the same report. Then the same
questions with tools failing 0% and 40% of the time."""
import json
import random
import statistics
from pathlib import Path

from .agents import norm
from .graph import Budget, Store, fingerprint, run
from .web import Web, pages

RESULTS = Path(__file__).resolve().parent.parent / "results"


def questions(pgs, n=100, seed=0):
    ok = [p["name"] for p in pgs.values() if p["facts"]["licence"] and p["facts"]["author"]]
    rng = random.Random(seed)
    return [f"Compare {a} and {b}: licence, dependencies and author." for a, b in (rng.sample(ok, 2) for _ in range(n))]


def correct(f, facts):
    if f["aspect"] == "dependencies":
        got = set() if f["value"] == "none" else {norm(x.strip()) for x in f["value"].split(",")}
        return got == {norm(d) for d in facts["dependencies"]}
    return f["value"] == facts[f["aspect"]]


def evaluate(pgs, web, qs, known, budget=Budget()):
    by_name = {norm(p["name"]): (u, p) for u, p in pgs.items()}
    rows = []
    for i, q in enumerate(qs):
        s = run(f"q{i}", q, web, known, Store(), budget)
        attempts = list(s["attempts"].values())
        found = [a["finding"] for a in attempts if a["finding"]]
        rows.append({"status": s["status"], "subquestions": len(attempts), "answered": len(found),
                     "correct": sum(correct(f, by_name[norm(f["entity"])][1]["facts"]) for f in found),
                     "supported": sum(f["value"] in f["snippet"] and f["url"] == by_name[norm(f["entity"])][0] for f in found),
                     "failures_seen": sum(1 for a in attempts for e in a["log"] if e[2] != "ok"),
                     "retried": sum(bool(a.get("retried")) for a in attempts), "sent_back": s["pass"],
                     "gaps": [a["status"] for a in attempts if not a["finding"]], "tokens": s["tokens"], "steps": s["step"]})
    return rows


def bench():
    pgs = pages()
    known = [p["name"] for p in pgs.values()]
    qs = questions(pgs)
    rows = evaluate(pgs, Web(pgs, 0.15), qs, known)
    total = lambda k: sum(r[k] for r in rows)
    # kill runs part-way and resume them from the store
    web, same = Web(pgs, 0.15), 0
    for i, q in enumerate(qs[:20]):
        whole = run(f"w{i}", q, web, known, Store())
        store = Store()
        run(f"c{i}", q, web, known, store, crash_after=random.Random(i).randint(1, whole["step"] - 1))
        same += fingerprint(run(f"c{i}", q, web, known, store)) == fingerprint(whole)
    sweep = {}
    for rate in (0.0, 0.15, 0.4):
        rs = rows if rate == 0.15 else evaluate(pgs, Web(pgs, rate), qs, known)
        sweep[rate] = {"answered": sum(r["answered"] for r in rs) / sum(r["subquestions"] for r in rs),
                       "tokens": statistics.median(r["tokens"] for r in rs)}
    gaps = {}
    for r in rows:
        for g in r["gaps"]:
            gaps[g] = gaps.get(g, 0) + 1
    pct = lambda a, b: f"{100 * a / b:.1f}%"
    lines = [f"{len(rows)} questions, {total('subquestions')} sub-questions, tools failing 15% of the time.", "",
             f"- Answered: {total('answered')} ({pct(total('answered'), total('subquestions'))}); unanswered, and said so "
             f"in the report: {sum(gaps.values())} ({', '.join(f'{k} {v}' for k, v in sorted(gaps.items()))}).",
             f"- Claims matching the PyPI record behind the page: {total('correct')} of {total('answered')} "
             f"({pct(total('correct'), total('answered'))}). Citations whose snippet contains the claim, on the entity's own page: "
             f"{total('supported')} of {total('answered')}.",
             f"- Tool failures met: {total('failures_seen')}; sub-questions retried after the one send-back: {total('retried')}; "
             f"runs that used the send-back: {sum(r['sent_back'] > 0 for r in rows)}; runs stopped by a budget: "
             f"{sum(r['status'] != 'done' for r in rows)}.",
             f"- Metered tokens per run: median {statistics.median(r['tokens'] for r in rows):,.0f}, max "
             f"{max(r['tokens'] for r in rows):,} (ceiling {Budget().max_tokens:,}); steps per run: max {max(r['steps'] for r in rows)}.",
             f"- Runs killed at a random step and resumed from the store: {same} of 20 ended with the same report and path.", "",
             "| Tool failure rate | Sub-questions answered | Median tokens per run |", "|---|---|---|"]
    lines += [f"| {int(100 * k)}% | {100 * v['answered']:.1f}% | {v['tokens']:,.0f} |" for k, v in sweep.items()]
    example = run("example", qs[0], Web(pgs, 0.15), known, Store())
    lines += ["", "An example report (tools failing 15% of the time):", "", "```", example["report"], "```"]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "bench.md").write_text("\n".join(lines) + "\n")
    (RESULTS / "summary.json").write_text(json.dumps({"runs": rows, "sweep": sweep, "resumed_same": same}, indent=1))
    return "\n".join(lines)
