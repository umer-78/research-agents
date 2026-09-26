from research.agents import SubQuestion, planner, researcher
from research.graph import Budget, Store, fingerprint, run
from research.web import Web

PAGES = {f"https://pypi.org/project/{n}/": {"name": n, "facts": {}, "text": t} for n, t in {
    "requests": "requests\nHTTP for humans\nLicense: Apache-2.0\nRequires: urllib3, idna\nAuthor: Kenneth Reitz\n\nSend HTTP requests.",
    "urllib3": "urllib3\nHTTP client\nLicense: MIT\nRequires: none\nAuthor: Andrey Petrov\n\nConnection pools.",
    "idna": "idna\nInternationalized domain names\nLicense: not stated\nRequires: none\nAuthor: Kim Davies\n\nIDNA."}.items()}
KNOWN = ["requests", "urllib3", "idna"]


def test_planner_and_researcher_with_provenance():
    plan = planner("Compare requests and urllib3: licence and author.", KNOWN, 8)
    assert [(s.entity, s.aspect) for s in plan.subquestions] == [("requests", "licence"), ("requests", "author"),
                                                                ("urllib3", "licence"), ("urllib3", "author")]
    a = researcher(SubQuestion("requests", "dependencies"), Web(PAGES, 0), "0", 3)
    assert a.status == "ok" and a.finding.value == "urllib3, idna" and a.finding.snippet == "Requires: urllib3, idna"
    assert researcher(SubQuestion("idna", "licence"), Web(PAGES, 0), "0", 3).status == "not_stated"


def test_failures_become_gaps_not_guesses_and_budgets_hold():
    s = run("r", "Compare requests and urllib3: licence, dependencies and author.", Web(PAGES, 1.0), KNOWN, Store())
    assert s["status"] == "done" and not any(a["finding"] for a in s["attempts"].values())
    assert "Could not establish" in s["report"] and s["pass"] == 1                 # one send-back, then stop
    assert all(a["searches"] <= Budget().max_searches for a in s["attempts"].values())
    tight = run("t", "Compare requests and urllib3: licence.", Web(PAGES, 0), KNOWN, Store(), Budget(max_tokens=100))
    assert tight["status"] == "stopped_budget"


def test_a_killed_run_resumes_to_the_same_report():
    q, web = "Compare requests and idna: licence, dependencies and author.", Web(PAGES, 0.3)
    whole = run("a", q, web, KNOWN, Store())
    store = Store()
    run("b", q, web, KNOWN, store, crash_after=3)
    assert fingerprint(run("b", q, web, KNOWN, store)) == fingerprint(whole)
