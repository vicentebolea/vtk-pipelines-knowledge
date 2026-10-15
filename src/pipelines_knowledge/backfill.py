import logging
from itertools import groupby

import gitlab

from pipelines_watch import entries, manifest
from pipelines_watch.corpus import Corpus
from pipelines_watch.extract import build_extractor, scrub, terminal_errors
from pipelines_watch.gitlab import ANSI, LOG_TAIL_CHARS

log = logging.getLogger(__name__)


def backfill(cfg, project_path, pipelines=200, target=None):
    """Stage 1: write one entry file per failure that was retried, labelled by what the retry did."""
    gl = gitlab.Gitlab(cfg.gitlab_url, private_token=cfg.gitlab_token, retry_transient_errors=True)
    project = gl.projects.get(project_path, lazy=True)
    extractor = build_extractor(cfg.extract_model)
    done = 0
    total = sum(1 for _ in entries.load_all(cfg.knowledge_dir))
    for n, pipe in enumerate(_take(project.pipelines.list(per_page=100, iterator=True), pipelines), 1):
        if target and total >= target:
            break
        jobs = sorted(pipe.jobs.list(include_retried=True, get_all=True), key=lambda j: (j.name, j.id))
        for name, attempts in groupby(jobs, key=lambda j: j.name):
            attempts = list(attempts)
            for i, j in enumerate(attempts[:-1]):  # the last attempt was never retried
                if j.status != "failed" or j.failure_reason != "script_failure":
                    continue
                if entries.exists(cfg.knowledge_dir, project_path, j.id):
                    continue
                outcome = "retry_passed" if attempts[i + 1].status == "success" else "retry_failed"
                text = ANSI.sub("", project.jobs.get(j.id, lazy=True).trace().decode(errors="replace"))
                runner = (getattr(j, "runner", None) or {}).get("description", "")
                x = extractor.invoke({"job_name": name, "runner": runner,
                                           "hint": terminal_errors(text), "log": text[-LOG_TAIL_CHARS:]})
                entries.save(cfg.knowledge_dir, entries.Entry(
                    project=project_path, job_id=j.id, pipeline_id=pipe.id, ref=pipe.ref, job_name=name,
                    platform=x.platform, error_type=x.error_type, snippet=scrub(x.snippet), outcome=outcome))
                done += 1
                total += 1
                if done % 25 == 0:
                    log.info("%d new entries (%d in total), pipeline %d scanned", done, total, n)
    log.info("wrote %d entries for %s", done, project_path)


def load(cfg):
    """Stage 2: embed the entry files into Chroma (skips ones already there)."""
    corpus = Corpus(cfg.knowledge_dir, cfg.embedding_model)
    done = 0
    for e, md in entries.load_all(cfg.knowledge_dir):
        if not corpus.has(e.id):
            corpus.add(e, md)
            done += 1
    total = sum(1 for _ in entries.load_all(cfg.knowledge_dir))
    manifest.write(cfg.knowledge_dir, cfg.embedding_model, total)
    log.info("loaded %d new entries into Chroma, %d in total", done, total)


def _take(it, n):
    for i, x in enumerate(it):
        if i >= n:
            return
        yield x
