# vtk-pipelines-knowledge

The corpus behind [pipelines-watch](https://github.com/vicentebolea/gitlab-pipelines-watch):
past `vtk/vtk` CI failures, each as a markdown entry saying whether a retry of
that job on that platform passed or failed. CI embeds them into Chroma and
publishes a data-only image, `ghcr.io/vicentebolea/vtk-pipelines-knowledge`,
which the watcher mounts.

```
GitLab history --scrape--> raw/*.jsonl --convert--> knowledge/entries/*.md --load--> knowledge/chroma + manifest.json --CI--> image
```

## Layout

- `knowledge/entries/<project>/<job_id>.md`: the entries, committed. This is
  the source of truth, plain markdown you can read and edit.
- `knowledge/chroma/`, `knowledge/manifest.json`: built by `load`, not
  committed (CI rebuilds them).
- `raw/<project>.jsonl`: what `scrape` fetched (failed job, log tail, outcome).
  Not committed, it can hold large logs; `convert` can be rerun from it.
- `src/pipelines_knowledge/`: the three build stages.
- `tests/`: retrieval-quality tests on the real corpus.

The entry format, the LLM extraction and the `Corpus` class come from the
`pipelines-watch` package (pinned in `pyproject.toml`), so the entries are
written and indexed exactly the way the watcher reads them.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e ../gitlab-pipelines-watch pytest   # or the pinned git version
.venv/bin/pip install --no-deps -e .
```

Settings are the same `PW_*` variables as the watcher (see its README). You
need a GitLab token (`PW_GITLAB_TOKEN`) for stage 1, `ANTHROPIC_API_KEY` for stage 2,
and an ollama server with `nomic-embed-text` for stage 3.

## Stage 1: scrape

```sh
.venv/bin/pipelines-knowledge scrape group/project --pipelines 200
```

It reads the last 200 pipelines, including retried attempts, and appends one
JSON line to `raw/<project>.jsonl` for every `script_failure` job that was run
again: job, ref, runner, log tail and `outcome`, which is what the next attempt
of the same job did: `retry_passed` (transient) or `retry_failed` (a real bug).
Failures that were never retried are skipped. Jobs already in the file are
skipped, so re-running is safe. `--limit N` stops once the file has N jobs
(checked between pipelines).

## Stage 2: convert

```sh
.venv/bin/pipelines-knowledge convert group/project
```

For each raw job without an entry, the LLM (through `instructor`, which
validates the answer and retries it) extracts the error snippet, the platform
and the error type, and one markdown entry is written. Timestamps, tokens and
ids are scrubbed. A job whose extraction keeps failing is logged and skipped.
Existing entries are skipped, so a run resumes where it stopped.

At the end every entry gets `similar` and `success_rate`: how many retries of
the same error the corpus holds and the share that passed. Errors are matched
on the first snippet line with numbers and paths blanked. They are rewritten
on each run, since new entries change them; `similar` tells how much to trust a
rate (1 retry gives 0% or 100%).

Review the entries (read them, fix a wrong platform or outcome, delete bad
ones), then commit `knowledge/entries/`.

## Stage 3: load into Chroma

```sh
.venv/bin/pipelines-knowledge load
```

Each entry becomes one Chroma record. Only the snippet is embedded; the whole
markdown file is stored with it and shown to the LLM at inference time. `load`
also writes `knowledge/manifest.json` (embedding model, extraction version,
entry count), which the watcher checks at startup. Entries already in Chroma
are skipped: after editing a loaded file, `rm -rf knowledge/chroma` and load
again.

## Query the corpus

```sh
.venv/bin/python scripts/query.py "fatal: index file corrupt" -k 5
```

Shows what retrieval returns for an error text, without any LLM: distance
(lower is closer), outcome, success rate of that error, error type, platform
and job. Needs the loaded Chroma and the ollama server.

## Test

```sh
.venv/bin/pytest
```

Checks on the real corpus with the real embedding model: the manifest matches
what the watcher expects, every entry is indexed, an entry's nearest neighbours
mostly share its error type (leave-one-out, measured 0.85 against 0.20 by
chance), and known errors retrieve their category. They skip when ollama is
unreachable, and fail in CI.

## CI and publishing

`.github/workflows/ci.yml` starts ollama on the runner, rebuilds Chroma from
the committed entries, runs the tests, and only then builds and pushes the
image (sha and `latest` tags). A corpus with broken retrieval is not published.

One-time setup: the package `vtk-pipelines-knowledge` must allow this repo to
write to it (package settings, "Manage Actions access"), because it was first
published by the app repo's CI.

## Use the image

```sh
podman run -d --env-file .env \
  --mount type=image,source=ghcr.io/vicentebolea/vtk-pipelines-knowledge,destination=/kb,rw=true \
  -e PW_KNOWLEDGE_DIR=/kb/knowledge \
  ghcr.io/vicentebolea/gitlab-pipelines-watch
```

## When the extraction changes

Edit the code in `gitlab-pipelines-watch`, bump `EXTRACTION_VERSION`, tag a
release. Here: bump the pinned version in `pyproject.toml`, delete the affected
entries and re-run stage 2 (stage 1 need not be repeated) if the extraction output changes, `load`, commit, push.
The watcher refuses to start on a corpus whose manifest does not match.
