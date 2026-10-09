<!-- FILE MAP
  1-40  Project overview, status, layout, and how to run what exists so far.
-->
# triagebench

An agent that triages a GitHub issue queue the way a maintainer's assistant would (classify, label, find duplicates, extract repro steps, draft small fixes), behind human approval gates, plus a **benchmark backtested on real issue history**: ground truth is what maintainers actually did.

> Status: dataset builder, MCP server, the zero-shot agent and the eval harness are in place; first numbers come from the frozen dataset. Results table, demo video and failure taxonomy land here as they exist.

## Backtest repos

| Repo | Why |
|---|---|
| `astral-sh/ruff` | High volume, strong labels, cheap repro (install the release from issue time) |
| `python-poetry/poetry` | Clean `kind/*` / `area/*` / `status/*` scheme, pure Python tests |
| `pydantic/pydantic-ai` | High volume; AI bots also label here, so only human-applied labels count as truth |

Reasoning and rejected candidates: [docs/decisions.md](docs/decisions.md).

## Layout

```
agent/       Python agent (Pydantic AI); FastAPI approval queue           (queue planned)
mcp-server/  TypeScript MCP server over replay fixtures (get_issue, list_labels, search_dup, get_file, propose_*)
evals/       dataset builder, task scorers, eval harness
ui/          approval queue + trace viewer (TypeScript, React)        (planned)
sandbox/     Docker repro sandbox                                     (planned)
docs/        decisions, discovery, solution brief, eval report
```

## Setup

```bash
uv sync                      # Python deps
cp .env.example ~/.config/triagebench/.env   # then add a read-only GitHub token
uv run pytest
```

## Building the dataset

```bash
uv run python -m evals.survey_repos            # label hygiene per candidate repo -> docs/decisions.md
uv run python -m evals.build_dataset build     # ~900 issues, cached under ~/.cache/triagebench
uv run python -m evals.build_dataset verify    # offline rebuild must match every manifest hash
git add evals/data && git commit -m "Freeze dataset v1"
git tag test-split-v1 && git push origin test-split-v1   # seal BEFORE any prompt work
```

What goes in: `t0` is what was visible when the issue was opened (original title, body, issue-form labels, default-branch SHA, open issues). `t1` is what maintainers did afterwards (labels added by humans, duplicate links, closing commit, merged PRs). Bot-applied labels are recorded but never count as truth. The test split only opens with `TRIAGEBENCH_FINAL_EVAL=1`.

## MCP server

```bash
uv run python -m evals.export_replay               # dev split -> ~/.cache/triagebench/replay
cd mcp-server && npm ci && npm run build && npm test
node dist/index.js --replay-dir ~/.cache/triagebench/replay   # stdio MCP server, replay + dry-run
uv run --group agent python -m agent.triage.smoke_mcp --replay-dir ~/.cache/triagebench/replay --repo astral-sh/ruff --number <issue>
```

Every read is the issue's t0 view: `search_dup` only searches issues that were open when it was filed, and `get_file` reads at its t0 commit. `propose_label` and `propose_pr` return proposals for human approval; live mode needs both `--allow-repo owner/name` and `--approve`.

## License

MIT. Issue data is public GitHub content; each snapshot links back to its source issue.

## Running the eval

```bash
uv run python -m evals.export_replay                   # dev split -> ~/.cache/triagebench/replay
(cd mcp-server && npm ci && npm run build)
ollama pull qwen3:8b
uv run --group agent python -m evals.harness run --model ollama:qwen3:8b --limit 20
GOOGLE_API_KEY=... uv run --group agent python -m evals.harness run --model google:gemini-2.5-flash --limit 20
```

Each run writes `predictions.jsonl`, `report.json` and `report.md` under `~/.cache/triagebench/runs/<model>`. Interrupted runs resume where they stopped, and `--limit` picks the same seeded issues for every model, so runs compare issue for issue. `--model` takes `ollama:<tag>` or any Pydantic AI model string.

The agent is zero-shot with read-only tools and no guardrails, so later changes are measured against it. Tasks and their metrics:

| Task | Truth | Headline | Also reported |
|---|---|---|---|
| `label` | labels a human added after t0, net of issue-form labels | micro F1 | precision, recall, exact match, rate of labels that don't exist in the repo |
| `dup` | `duplicate_of`, or none | accuracy | duplicate precision and recall, recall when the true target was open at t0 |

Headline numbers carry a 95% bootstrap interval over issues. Model or tool failures count as an empty answer and are reported by error type.

