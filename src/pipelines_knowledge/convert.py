import json
import logging
import re
from collections import defaultdict

import instructor

from pipelines_watch import entries
from pipelines_watch.extract import PROMPT, Extraction, scrub, terminal_errors

from .scrape import raw_file

log = logging.getLogger(__name__)


def convert(cfg, project_path, raw_dir):
    """Stage 2: ask the LLM for the snippet, platform and error type of each raw job, write one entry file each."""
    client = instructor.from_provider(cfg.extract_model.replace(":", "/", 1))
    done = failed = 0
    for line in raw_file(raw_dir, project_path).open():
        r = json.loads(line)
        if entries.exists(cfg.knowledge_dir, project_path, r["job_id"]):
            continue
        messages = [{"role": "system" if m.type == "system" else "user", "content": m.content}
                    for m in PROMPT.format_messages(job_name=r["job_name"], runner=r["runner"],
                                                    hint=terminal_errors(r["log"]), log=r["log"])]
        try:
            x = client.chat.completions.create(response_model=Extraction, messages=messages, max_retries=3)
        except Exception:
            log.exception("extraction failed for job %d, skipped", r["job_id"])
            failed += 1
            continue
        entries.save(cfg.knowledge_dir, entries.Entry(
            project=project_path, job_id=r["job_id"], pipeline_id=r["pipeline_id"], ref=r["ref"],
            job_name=r["job_name"], platform=x.platform, error_type=x.error_type,
            snippet=scrub(x.snippet), outcome=r["outcome"]))
        done += 1
        if done % 25 == 0:
            log.info("%d new entries", done)
    log.info("wrote %d entries, %d failed", done, failed)
    add_rates(cfg.knowledge_dir)


def _error_key(e):
    """The root-cause line with numbers and paths blanked, so the same error on other jobs and runs matches."""
    line = e.snippet.splitlines()[0].lower()
    return re.sub(r"\s+", " ", re.sub(r"\S*[/\\]\S*|0x[0-9a-f]+|\d+", "#", line)).strip()


def add_rates(knowledge_dir):
    """Write into every entry how many retries of the same error exist and what share of them passed."""
    groups = defaultdict(list)
    for e, _ in entries.load_all(knowledge_dir):
        if e.snippet.strip():  # an empty snippet matches nothing
            groups[_error_key(e)].append(e)
    for group in groups.values():
        rate = sum(e.outcome == "retry_passed" for e in group) / len(group)
        for e in group:
            if (e.similar, e.success_rate) != (len(group), rate):
                entries.save(knowledge_dir, e.model_copy(update={"similar": len(group), "success_rate": rate}))
