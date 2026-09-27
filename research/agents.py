"""Planner, researcher, writer: each a function from a typed input to a typed output, with a
deterministic implementation here (an LLM can stand behind the same contracts)."""
import re
import time
from dataclasses import dataclass, field

ASPECTS = {"licence": r"licen[cs]e", "dependencies": r"depend|requires?", "author": r"author|maintain|who (wrote|makes)",
           "summary": r"what (is|does)|purpose|used for"}
LINE = {"licence": r"^License: (.+)$", "dependencies": r"^Requires: (.+)$", "author": r"^Author: (.+)$"}


@dataclass
class SubQuestion:
    entity: str
    aspect: str


@dataclass
class Plan:
    question: str
    subquestions: list


@dataclass
class Finding:
    entity: str
    aspect: str
    value: str
    url: str
    snippet: str
    retrieved_at: int                    # seconds since the epoch


@dataclass
class Attempt:
    subquestion: SubQuestion
    status: str                          # ok, rate_limited, timeout, no_results, not_found, not_stated
    finding: Finding = None
    searches: int = 0
    log: list = field(default_factory=list)


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def planner(question, known, max_subquestions):
    """Packages the question names (longest names first) times the aspects it asks about."""
    text, entities = question.lower(), []
    for name in sorted(known, key=len, reverse=True):
        m = re.search(rf"(?<![\w-]){re.escape(name.lower())}(?![\w-])", text)
        if m and len(name) > 2:
            entities.append((m.start(), name))
            text = text[:m.start()] + " " * len(name) + text[m.end():]
    aspects = [a for a, pattern in ASPECTS.items() if re.search(pattern, question, re.I)] or ["summary"]
    subs = [SubQuestion(e, a) for _, e in sorted(entities) for a in aspects]
    return Plan(question, subs[:max_subquestions])


def researcher(sub, web, attempt_no, max_searches):
    """Search for the entity's page, check the result is that entity, fetch it, extract the aspect with its line."""
    a = Attempt(sub, "no_results")
    for query in (sub.entity, f"{sub.entity} python package"):
        if a.searches >= max_searches:
            break
        a.searches += 1
        res = web.search(query, attempt=f"{attempt_no}:{a.searches}")
        a.log.append(("search", query, res["status"]))
        if res["status"] != "ok":
            a.status = res["status"]
            continue
        hit = next((r for r in res["results"] if norm(r["title"]) == norm(sub.entity)), None)
        if hit is None:
            a.status = "not_found"
            continue
        page = web.fetch(hit["url"], attempt=attempt_no)
        a.log.append(("fetch", hit["url"], page["status"]))
        if page["status"] != "ok":
            a.status = page["status"]
            continue
        lines = page["text"].splitlines()
        if sub.aspect == "summary":
            snippet = lines[1] if len(lines) > 1 else ""
            value = snippet
        else:
            m = next((re.match(LINE[sub.aspect], l) for l in lines if re.match(LINE[sub.aspect], l)), None)
            snippet, value = (m.group(0), m.group(1).strip()) if m else ("", "")
        if not value or value in ("not stated", "none") and sub.aspect != "dependencies":
            a.status = "not_stated"
            return a
        a.status, a.finding = "ok", Finding(sub.entity, sub.aspect, value, hit["url"], snippet, int(time.time()))   # whole seconds: a fixed-length stamp keeps metered tokens reproducible
        return a
    return a


def writer(plan, findings, gaps):
    """A report where every claim carries its citation, and what could not be established is said."""
    refs, lines = {}, [f"# {plan.question}", ""]
    for entity in dict.fromkeys(s.entity for s in plan.subquestions):
        facts = []
        for f in (f for f in findings if f.entity == entity):
            n = refs.setdefault(f.url, len(refs) + 1)
            facts.append(f"{f.aspect}: {f.value} [{n}]")
        lines.append(f"**{entity}** — " + ("; ".join(facts) if facts else "nothing established."))
    if gaps:
        lines += ["", "Could not establish: " + "; ".join(f"{g.subquestion.entity} {g.subquestion.aspect} ({g.status})" for g in gaps) + "."]
    lines += ["", "Sources:"] + [f"[{n}] {u}" for u, n in refs.items()]
    return "\n".join(lines)
