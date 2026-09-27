"""python -m research.demo   write the live demo's data (docs/data.json): the first 12 of the bench's questions,
run with tools failing 0%, 15% and 40% of the time, each with its trace, every sub-question's attempts and
the report; plus results/summary.json. Runs replay exactly: the 15% runs match the bench's rows."""
import json
from pathlib import Path

from .bench import evaluate, questions
from .graph import Budget, Store, run
from .web import Web, pages

ROOT = Path(__file__).resolve().parent.parent


def build(out=ROOT / "docs", n=12):
    summary = json.loads((ROOT / "results" / "summary.json").read_text())
    pgs = pages()
    known = [p["name"] for p in pgs.values()]
    qs = questions(pgs)[:n]
    if evaluate(pgs, Web(pgs, 0.15), qs, known) != summary["runs"][:n]:
        raise SystemExit("the runs no longer match results/summary.json; rerun the bench first")
    runs = {}
    for rate in (0.0, 0.15, 0.4):
        web, rows = Web(pgs, rate), []
        for i, q in enumerate(qs):
            s = run(f"q{i}", q, web, known, Store())
            attempts = [{"entity": a["subquestion"]["entity"], "aspect": a["subquestion"]["aspect"], "status": a["status"],
                         "searches": a["searches"], "retried": a.get("retried", False), "log": a["log"],
                         "value": a["finding"]["value"] if a["finding"] else None}
                        for _, a in sorted(s["attempts"].items(), key=lambda kv: int(kv[0]))]
            rows.append({"question": q, "status": s["status"], "tokens": s["tokens"], "report": s["report"],
                         "trace": [{k: t[k] for k in ("node", "status", "tokens")} for t in s["trace"]], "attempts": attempts})
        runs[str(rate)] = rows
    out.mkdir(exist_ok=True)
    (out / "data.json").write_text(json.dumps({"summary": {k: v for k, v in summary.items() if k != "runs"}, "bench_runs": summary["runs"],
                                               "budget": Budget().__dict__, "runs": runs}, indent=1))
    print(f"wrote {out / 'data.json'}: {n} questions at three failure rates")


if __name__ == "__main__":
    build()
