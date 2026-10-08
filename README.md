<!-- FILE MAP
  1-40  Project overview, status, layout, and how to run what exists so far.
-->
# triagebench

An agent that triages a GitHub issue queue the way a maintainer's assistant would (classify, label, find duplicates, extract repro steps, draft small fixes), behind human approval gates, plus a **benchmark backtested on real issue history**: ground truth is what maintainers actually did.

> Status: Week 1 of 10. Dataset builder in progress. Results table, demo video and failure taxonomy land here as they exist.

## Backtest repos

| Repo | Why |
|---|---|
| `astral-sh/ruff` | High volume, strong labels, cheap repro (install the release from issue time) |
| `python-poetry/poetry` | Clean `kind/*` / `area/*` / `status/*` scheme, pure Python tests |
| `pydantic/pydantic-ai` | High volume; AI bots also label here, so only human-applied labels count as truth |

Reasoning and rejected candidates: [docs/decisions.md](docs/decisions.md).

## Layout

```
agent/       Python agent (Pydantic AI) + FastAPI approval queue      (Week 3+)
mcp-server/  TypeScript MCP server: get_issue, search_dup, ...        (Week 2)
evals/       dataset builder, tasks, judges, harness (Inspect AI)
ui/          approval queue + trace viewer (TypeScript, React)        (Week 7)
sandbox/     Docker repro sandbox                                     (Week 6)
docs/        decisions, discovery, solution brief, eval report
```

## Setup

```bash
uv sync                      # Python deps
cp .env.example ~/.config/triagebench/.env   # then add a read-only GitHub token
uv run pytest
```

## Building the dataset (Week 1)

```bash
uv run python -m evals.survey_repos            # label hygiene per candidate repo -> docs/decisions.md
uv run python -m evals.build_dataset build     # ~900 issues, cached under ~/.cache/triagebench
uv run python -m evals.build_dataset verify    # offline rebuild must match every manifest hash
git add evals/data && git commit -m "Freeze dataset v1"
git tag test-split-v1 && git push origin test-split-v1   # seal BEFORE any prompt work
```

What goes in: `t0` is what was visible when the issue was opened (original title, body, issue-form labels, default-branch SHA, open issues). `t1` is what maintainers did afterwards (labels added by humans, duplicate links, closing commit, merged PRs). Bot-applied labels are recorded but never count as truth. The test split only opens with `TRIAGEBENCH_FINAL_EVAL=1`.

## License

MIT. Issue data is public GitHub content; each snapshot links back to its source issue.
