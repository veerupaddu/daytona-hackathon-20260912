# Nosana GPU jobs return 503 until a host is actually serving

## Status

Open. The studio retries a few times and surfaces a queued/503 health pill, but it cannot finish Step 2 until Ollama on the rented GPU answers `/v1/chat/completions`.

## Summary

GPT-OSS 20B on Nosana is not an always-on API. You post (or start) a container job. The public `*.node.k8s.prd.nos.ci` URL exists immediately, but it returns **HTTP 503 Service Initializing** while:

- the job is **queued** (no idle host in that market), or
- the host is assigned but still **pulling the Ollama image / 20B weights**.

A stopped deployment also 503s. Idle time on a running job still burns credits.

There is no official Nosana Python SDK. `@nosana/cli` posts jobs; the studio only HTTP-calls the live endpoint.

## What we saw in this hack

1. An older URL stayed 503 because deployment `gpt-oss-20b-add-test` was **STOPPED**.
2. Restarting it on **nvidia-5080** left the job **queued** (0 idle hosts). Chat kept failing with 503.
3. Stopping that job and starting **gpt-oss-20b-studio** on a **ready 4090** host brought `/api/tags` to 200 and chat to a working `gpt-oss:20b`.
4. After changing `NOSANA_LLM_URL`, the studio must be restarted or it keeps calling the dead URL.
5. Retrying the same prompt while Nosana was down wrote several identical Neo4j paths (Session → Prompt → Nosana fail → Daytona skipped). The insights graph now shows one row per prompt with a repeat count.

## Expected vs actual

| Check | Healthy | Broken |
|---|---|---|
| `GET {NOSANA_LLM_URL}/api/tags` | 200, model `gpt-oss:20b` | 503 or connection error |
| Studio health pill | `Nosana ready` | `Nosana queued / starting` |
| Step 2 | Python source in the Nosana card | `Nosana GPU is not serving yet (HTTP 503)` |
| Step 3 | Daytona stdout | Skipped — no runnable Python |

## Workaround

1. On [deploy.nosana.com](https://deploy.nosana.com), pick a GPU that is **ready now**, not `fits_but_queued`, unless you accept waiting.
2. Use at least a 60-minute timeout (Nosana minimum).
3. Wait until `/api/tags` is 200 before running the studio pipeline.
4. Put that host URL in `NOSANA_LLM_URL` (and update deployment/job links). Restart `./run.sh`.
5. Stop the deployment when you are done. Credits keep draining while it sits idle.

Do not keep posting new 5080 jobs on top of a queued one. Stop or wait.

## Studio behavior (already shipped)

- `ask_nosana_llm` retries 503 a few times, then raises a clear queued/starting error.
- Health treats 503 as `queued`, not a generic unknown failure.
- Insights dedupe repeated prompts and load the latest stored Nosana code / Daytona output on page load.

## Remaining gaps

- No automatic market failover from a queued 5080 to an idle 4090.
- No webhook when a queued job becomes ready; the operator still polls Deploy or `/api/tags`.
- Nosana has no pause — you stop the job or keep paying.
- Local unittest does not post paid jobs; live LLM tests skip if `NOSANA_LLM_URL` is empty.
