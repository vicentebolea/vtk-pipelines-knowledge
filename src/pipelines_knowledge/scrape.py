import json
import logging
from itertools import groupby
from pathlib import Path

import gitlab

from pipelines_watch.gitlab import ANSI, LOG_TAIL_CHARS

log = logging.getLogger(__name__)


def raw_file(raw_dir, project_path):
    return Path(raw_dir) / f"{project_path.replace('/', '__')}.jsonl"


def scrape(cfg, project_path, raw_dir, pipelines=200, limit=None):
    """Stage 1: append one JSON line per failed job that was retried, labelled by what the retry did."""
    path = raw_file(raw_dir, project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = {json.loads(line)["job_id"] for line in path.open()} if path.exists() else set()
    gl = gitlab.Gitlab(cfg.gitlab_url, private_token=cfg.gitlab_token, retry_transient_errors=True)
    project = gl.projects.get(project_path, lazy=True)
    done = 0
    with path.open("a") as out:
        for n, pipe in enumerate(_take(project.pipelines.list(per_page=100, iterator=True), pipelines), 1):
            if limit and len(seen) >= limit:
                break
            jobs = sorted(pipe.jobs.list(include_retried=True, get_all=True), key=lambda j: (j.name, j.id))
            for name, attempts in groupby(jobs, key=lambda j: j.name):
                attempts = list(attempts)
                for i, j in enumerate(attempts[:-1]):  # the last attempt was never retried
                    if j.status != "failed" or j.failure_reason != "script_failure" or j.id in seen:
                        continue
                    text = ANSI.sub("", project.jobs.get(j.id, lazy=True).trace().decode(errors="replace"))
                    out.write(json.dumps(dict(
                        project=project_path, job_id=j.id, pipeline_id=pipe.id, ref=pipe.ref, job_name=name,
                        runner=(getattr(j, "runner", None) or {}).get("description", ""),
                        outcome="retry_passed" if attempts[i + 1].status == "success" else "retry_failed",
                        log=text[-LOG_TAIL_CHARS:])) + "\n")
                    out.flush()
                    seen.add(j.id)
                    done += 1
                    if done % 25 == 0:
                        log.info("%d new jobs (%d in total), pipeline %d scanned", done, len(seen), n)
    log.info("wrote %d jobs to %s", done, path)


def _take(it, n):
    for i, x in enumerate(it):
        if i >= n:
            return
        yield x
