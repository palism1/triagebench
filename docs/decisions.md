<!-- FILE MAP
  1-60  Decision log: what was decided, when, why, and what would change it.
-->
# Decisions

## D1. Backtest repos (2026-10-08)

**Decided:** `astral-sh/ruff`, `python-poetry/poetry`, `pydantic/pydantic-ai`. Alternate: `promptfoo/promptfoo` (TypeScript).
Provisional until `evals/survey_repos.py` measures label coverage and human-vs-bot labeling with a real token.

**Rejected:** `fastapi/fastapi` (only the maintainer may open issues; everything else is Discussions), `langfuse/langfuse` (features and support live in Discussions, so issues are almost all bugs), `unslothai/unsloth` (bugs need CUDA), `streamlit/streamlit` (AI triage bot; kept as backup).

## D2. Label task predicts human labels added after t0 (2026-10-08)

Issue forms apply `bug`, `question`, `kind/bug` at creation. Those are visible at t0, so they are **inputs**, not targets. The target is the set of labels a **human** added after the creation window and did not later remove. Bot actors (`[bot]` accounts, `type: Bot`, plus per-repo lists in `evals/config.py`) are excluded from ground truth.

## D3. Hardware: Apple Silicon, free cloud only (2026-10-08)

Local model via Ollama or MLX (vLLM does not run on macOS). Default Qwen3-8B Q4; 14B only with 24 GB+ unified memory. Bulk eval runs may use a free Kaggle GPU with vLLM; the eval report states which hardware produced each number.

## D4. Frontier comparison: Gemini free tier (2026-10-08)

Default chosen without objection; OpenRouter free models are the fallback. Every response is cached so rate limits only slow runs down.

## D5. Snapshots stored as canonical JSONL, not parquet (2026-10-08)

Byte-identical rebuilds are easier to test on sorted-key JSON lines than on parquet, whose bytes depend on the writer version. Parquet export can be added for analysis without becoming the source of truth.

## D6. Edited issue bodies are excluded by default (2026-10-08)

The REST API returns the latest body, which can contain post-t0 text ("fixed in 0.6.3"). Issues whose body was edited more than `EDIT_GRACE` after creation are skipped by the sampler (count reported). Titles are restored from the first `renamed` event.
