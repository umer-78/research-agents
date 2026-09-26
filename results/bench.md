100 questions, 600 sub-questions, tools failing 15% of the time.

- Answered: 564 (94.0%); unanswered, and said so in the report: 36 (no_results 6, rate_limited 21, timeout 9).
- Claims matching the PyPI record behind the page: 564 of 564 (100.0%). Citations whose snippet contains the claim, on the entity's own page: 564 of 564.
- Tool failures met: 96; sub-questions retried after the one send-back: 93; runs that used the send-back: 28; runs stopped by a budget: 0.
- Metered tokens per run: median 4,741, max 8,528 (ceiling 20,000); steps per run: max 16.
- Runs killed at a random step and resumed from the store: 20 of 20 ended with the same report and path.

| Tool failure rate | Sub-questions answered | Median tokens per run |
|---|---|---|
| 0% | 100.0% | 4,616 |
| 15% | 94.0% | 4,741 |
| 40% | 66.5% | 6,360 |

An example report (tools failing 15% of the time):

```
# Compare google-cloud-os-login and execnet: licence, dependencies and author.

**google-cloud-os-login** — licence: Apache-2.0 [1]; dependencies: google-api-core, google-auth, grpcio, proto-plus, protobuf [1]; author: Google LLC [1]
**execnet** — licence: MIT [2]; dependencies: none [2]; author: holger krekel and others [2]

Sources:
[1] https://pypi.org/project/google-cloud-os-login/
[2] https://pypi.org/project/execnet/
```
