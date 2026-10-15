# Architecture

The offline half of pipelines-watch: it turns CI history into a retrieval
corpus and publishes it as an image. The online half (the watcher) is in
`gitlab-pipelines-watch`, see its `ARCHITECTURE.md`.

```mermaid
flowchart TD
    subgraph S1[Stage 1: pipelines-knowledge backfill]
        H[Recent pipelines<br/>jobs with include_retried] --> G[Group attempts by job name]
        G --> O1{Later attempt exists?}
        O1 -- passed --> R1[retry_passed]
        O1 -- failed --> R2[retry_failed]
        O1 -- none --> X[Skipped]
        R1 --> HINT[Pick last error lines<br/>before Job failed]
        R2 --> HINT
        HINT --> EX[LLM: snippet, platform, error type]
        EX --> SC[Scrub timestamps, tokens, ids]
        SC --> MD[(knowledge/entries/project/job_id.md)]
    end

    subgraph S2[Stage 2: pipelines-knowledge load]
        MD --> EMB[Embed snippet only<br/>local ollama]
        EMB --> V[(Chroma: snippet vector,<br/>full markdown in metadata)]
        V --> MF[manifest.json<br/>embedding model, extraction version, count]
    end

    subgraph CI[CI]
        MD -. committed .-> RB[Rebuild Chroma on the runner]
        RB --> Q[Retrieval-quality tests]
        Q --> IMG[podman build, push to ghcr.io]
    end

    V --> IMG
    MF --> IMG
```

## Decisions

- **Entries are the source of truth.** They are small markdown files in git;
  Chroma is rebuilt from them in CI, so the database always matches the
  embedding model and no binary churns in history.
- **Labels come only from what a retry did.** `retry_passed` is strong evidence
  of a transient failure and `retry_failed` of a real bug. Failures never
  retried are skipped. The platform is part of every entry because the same
  error can be transient on one platform and a bug on another.
- **Only the snippet is embedded,** so similarity depends on the error and not
  on the surrounding text. The whole file is stored with the record and shown
  to the LLM as an example.
- **The root-cause line is chosen by code** (the last `ERROR` or `FATAL` lines
  before "Job failed"), then given to the LLM as a hint, because asking the LLM
  to rank several errors gave inconsistent labels.
- **Quality gates publishing.** The tests run after the rebuild and before the
  image is built.

## Known limits

- Many entries share identical snippets (277 distinct of 425), so the top
  results contain duplicates. They can carry different outcomes, which is useful
  evidence, but it reduces the variety of examples the LLM sees.
- An entry needs a job that was retried within its own pipeline, so projects
  where people restart whole pipelines yield few entries.
- The same error can have both outcomes (for example a corrupt git index on
  Windows runners), probably depending on which runner picks up the retry.
