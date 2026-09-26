"""The web the researcher searches: the project pages of the 500 most-downloaded Python
packages on PyPI, each rendered as text (summary, licence, dependencies, author, description)
at its real URL. Search is BM25 over the pages. Tools fail the way real ones do (rate limits,
timeouts, empty results), seeded so every run can be replayed. Downloaded on first use into
RESEARCH_DATA (default ~/.cache/research)."""
import json
import math
import os
import random
import re
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOP = "https://raw.githubusercontent.com/hugovk/top-pypi-packages/main/top-pypi-packages.min.json"
PYPI = "https://pypi.org/pypi/{}/json"


def cache_dir():
    path = Path(os.environ.get("RESEARCH_DATA", Path.home() / ".cache" / "research"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch_json(url, path, tries=4):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    body = r.read()
                break
            except OSError:
                if attempt == tries - 1:
                    raise
                time.sleep(2 ** attempt)
        path.write_bytes(body)
    return json.loads(path.read_text())


def runtime_deps(info):
    out = []
    for req in info.get("requires_dist") or []:
        if "extra" not in req.split(";", 1)[-1] or ";" not in req:
            m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req)
            if m:
                out.append(m.group(1))
    return list(dict.fromkeys(out))          # a requirement listed twice (under different markers) is one dependency


def licence(info):
    raw = info.get("license_expression") or (info.get("license") if info.get("license") and len(info["license"]) < 60 else "")
    return (raw or next((c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")), "")).strip()


def pages(n=500):
    """{url: {"name", "text", "facts"}}: the page as the researcher reads it, and the structured record it came from."""
    top = fetch_json(TOP, cache_dir() / "top.json")["rows"][:n]
    def one(name):
        try:
            return fetch_json(PYPI.format(name), cache_dir() / "pypi" / f"{name}.json")["info"]
        except (OSError, ValueError):
            return None
    with ThreadPoolExecutor(8) as pool:
        infos = [i for i in pool.map(one, [r["project"] for r in top]) if i]
    out = {}
    for info in infos:
        facts = {"licence": licence(info), "dependencies": runtime_deps(info),
                 "author": (info.get("author") or info.get("maintainer") or "").strip(), "summary": (info.get("summary") or "").strip()}
        text = (f"{info['name']}\n{facts['summary']}\nLicense: {facts['licence'] or 'not stated'}\n"
                f"Requires: {', '.join(facts['dependencies']) or 'none'}\nAuthor: {facts['author'] or 'not stated'}\n\n"
                + (info.get("description") or "")[:4000])
        out[f"https://pypi.org/project/{info['name']}/"] = {"name": info["name"], "text": text, "facts": facts}
    return out


class Web:
    """search(query) and fetch(url), each returning {"status": ...}; failures are data, not exceptions."""

    def __init__(self, pages, failure_rate=0.15, seed=0):
        self.pages, self.failure_rate, self.seed = pages, failure_rate, seed
        self.docs = {u: Counter(re.findall(r"[a-z0-9]+", p["text"].lower())) for u, p in pages.items()}
        self.df = Counter(w for c in self.docs.values() for w in c)
        self.avg = sum(sum(c.values()) for c in self.docs.values()) / len(self.docs)

    def _fails(self, what, key, attempt):
        r = random.Random(f"{self.seed}:{what}:{key}:{attempt}").random()
        return None if r >= self.failure_rate else ("rate_limited" if r < self.failure_rate / 3 else
                                                     "timeout" if r < 2 * self.failure_rate / 3 else "no_results")

    def search(self, query, attempt=0, k=5):
        status = self._fails("search", query, attempt)
        if status:
            return {"status": status, "results": []}
        q = re.findall(r"[a-z0-9]+", query.lower())
        n = len(self.docs)
        def bm25(c):
            size = sum(c.values())
            return sum(math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5)) * c[w] * 2.2 / (c[w] + 1.2 * (0.25 + 0.75 * size / self.avg))
                       for w in q if w in c)
        ranked = sorted(self.docs, key=lambda u: -bm25(self.docs[u]))[:k]
        return {"status": "ok" if ranked else "no_results", "results": [{"url": u, "title": self.pages[u]["name"]} for u in ranked]}

    def fetch(self, url, attempt=0):
        status = self._fails("fetch", url, attempt)
        if status or url not in self.pages:
            return {"status": status or "not_found", "text": ""}
        return {"status": "ok", "text": self.pages[url]["text"]}
