# research-agents

A multi-agent research assistant built around the three things a production agent needs and a tutorial agent doesn't:

- **Durable state.** Every step is stored, and a killed run resumes where it stopped.
- **Budgets enforced in the graph.** Sub-questions, searches per sub-question, metered tokens and wall-clock time are all capped, and the reviewer sends work back exactly once.
- **Step-level tracing.**

There are three specialists:

- **The planner** turns a question into sub-questions.
- **The researcher** searches, checks the result is the right entity, fetches the page and extracts one claim. Every finding carries its claim, source URL, the supporting line and a retrieval timestamp.
- **The writer** composes a report in which every claim has a citation, and says what could not be established.

Tool failures (rate limits, timeouts, empty results, pages that don't state the fact) come back as structured statuses the supervisor acts on. They are never exceptions, and never guesses.

The "web" is local and real: the project pages of the 500 most-downloaded Python packages on PyPI, at their real URLs, searched with BM25. Tools fail at a set, seeded rate, so every run can be replayed. The agents are deterministic implementations of typed contracts; an LLM can stand behind the same contracts, but that isn't measured here, since the repository runs without API keys.

## Results

`python -m research bench` (under 10 seconds): 100 questions, each comparing two packages on licence, dependencies and author (600 sub-questions), with tools failing 15% of the time.

- **94.0% of sub-questions answered.** The other 36 are reported in the report as gaps (21 rate-limited, 9 timed out, 6 with no results), not filled in.
- **28 runs used their one send-back,** re-trying 93 sub-questions that hit a failure. 57 of those came back answered.
- **Every claim is cited.** All 564 claims match the PyPI record behind the page, and every citation's snippet contains its claim on the entity's own page.
  - This is by construction: the pages are rendered from those records.
  - It checks the extraction, entity check and citation plumbing, not reading comprehension. With an LLM researcher, this is the number to watch.
- **Budgets held.** The median run metered 4,741 tokens and the largest 8,528, against a 20,000 ceiling; no run needed more than 16 steps.
- **Durable state works:** 20 of 20 runs killed at a random step and resumed from the store ended with the same report and the same path.

| Tool failure rate | Sub-questions answered | Median tokens per run |
|---|---|---|
| 0% | 100.0% | 4,616 |
| 15% | 94.0% | 4,741 |
| 40% | 66.5% | 6,360 |

As tools get worse, coverage falls and cost rises (retries), but runs still end within budget. They report what they don't know instead of inventing it.

An example report:

```
# Compare google-cloud-os-login and execnet: licence, dependencies and author.

**google-cloud-os-login** — licence: Apache-2.0 [1]; dependencies: google-api-core, google-auth, grpcio, proto-plus, protobuf [1]; author: Google LLC [1]
**execnet** — licence: MIT [2]; dependencies: none [2]; author: holger krekel and others [2]

Sources:
[1] https://pypi.org/project/google-cloud-os-login/
[2] https://pypi.org/project/execnet/
```

## How it works

```python
from research.web import Web, pages
from research.graph import Budget, Store, run

pgs = pages()
store = Store("runs.db")
state = run("r1", "Compare httpx and requests: licence and dependencies.", Web(pgs, failure_rate=0.15),
            [p["name"] for p in pgs.values()], store, Budget(max_tokens=20_000, max_seconds=30))
state["report"], state["trace"]            # every step: node, status, tokens, milliseconds
```

- `research/agents.py`: the planner, researcher and writer, with typed findings.
- `research/graph.py`: the supervisor, the budgets, the single send-back, the store and the trace.
- `research/web.py`: the local web, with BM25 search, fetch and seeded failures.

```bash
pip install -e '.[dev]'
pytest -q
python -m research bench
```

The package list and PyPI records are downloaded on first use into `~/.cache/research`; nothing is committed.
