# vtk-pipelines-knowledge

The corpus behind [pipelines-watch](https://github.com/vicentebolea/gitlab-pipelines-watch):
past `vtk/vtk` CI failures, each as a markdown entry saying whether a retry of
that job passed or failed. CI embeds them into Chroma and publishes a data-only
image, `ghcr.io/vicentebolea/vtk-pipelines-knowledge`, which the watcher mounts.

```
GitLab --scrape--> raw/*.jsonl --convert--> knowledge/entries/*.md --load--> knowledge/chroma + manifest.json --CI--> image
```

- `raw/<project>.jsonl`: what `scrape` fetched. Committed, not in the image.
- `knowledge/entries/<project>/<job_id>.md`: the entries, committed. Plain
  markdown you can read and edit.
- `knowledge/chroma/`, `knowledge/manifest.json`: built by `load`, rebuilt by CI.
- `explorations/`: notebooks that look at the corpus.
- `scripts/query.py`: what retrieval returns for an error text.

The entry format, the extraction and the `Corpus` class come from the
`pipelines-watch` package (pinned in `pyproject.toml`), so entries are written
and read the way the watcher expects.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,explore]"
```

Settings are the watcher's `PW_*` variables. Stage 1 needs `PW_GITLAB_TOKEN`,
stage 2 `ANTHROPIC_API_KEY`, stage 3 an ollama server with `nomic-embed-text`.

## Build

```sh
.venv/bin/pipelines-knowledge scrape vtk/vtk --pipelines 200   # 1
.venv/bin/pipelines-knowledge convert vtk/vtk                  # 2
.venv/bin/pipelines-knowledge load                             # 3
```

1. **scrape** appends one JSON line per `script_failure` job that was run
   again: ref, runner, log tail and `outcome`, what the next attempt of the job
   did (`retry_passed` or `retry_failed`). Never-retried failures are skipped.
   Re-running skips known jobs. `--limit N` stops at N jobs.
2. **convert** has the LLM (through `instructor`, which validates and retries)
   extract the snippet, platform and error type, and writes one entry per raw
   job. Failed extractions are logged and skipped, existing entries are kept.
   It then writes `similar` and `success_rate` into every entry: how many
   retries of the same error exist and the share that passed. Errors match on
   the first snippet line with hashes, numbers and paths blanked.
3. **load** embeds the snippets into Chroma (the whole markdown is stored with
   each one) and writes `manifest.json` with the embedding model, extraction
   version and entry count, which the watcher checks at startup. After editing
   a loaded entry, `rm -rf knowledge/chroma` first.

Review the entries, fix or delete bad ones, then commit `raw/` and `knowledge/entries/`.

## Query and test

```sh
.venv/bin/python scripts/query.py "fatal: index file corrupt" -k 5
.venv/bin/pytest
```

`query.py` prints distance, outcome, success rate, error type, platform and job
of the nearest entries, with no LLM. The tests use the real corpus and embedding
model (they skip without ollama and fail in CI): manifest, indexing, and
retrieval quality, with leave-one-out error-type precision of 0.85 against 0.20
by chance.

## CI

`.github/workflows/ci.yml` starts ollama, rebuilds Chroma, runs the tests, and
only then builds and pushes the image (sha and `latest`), so a corpus with
broken retrieval is never published. The package must allow this repo to write
to it (package settings, "Manage Actions access").

## When the extraction changes

In `gitlab-pipelines-watch`: edit the code, bump `EXTRACTION_VERSION`, tag a
release. Here: bump the pin in `pyproject.toml`, delete the affected entries,
rerun `convert` and `load`, commit and push. The watcher refuses to start on a
corpus whose manifest does not match.
