import logging

from pipelines_watch import entries, manifest
from pipelines_watch.corpus import Corpus

log = logging.getLogger(__name__)


def load(cfg):
    """Stage 3: embed the entry files into Chroma (skips ones already there) and write the manifest."""
    corpus = Corpus(cfg.knowledge_dir, cfg.embedding_model)
    done = 0
    for e, md in entries.load_all(cfg.knowledge_dir):
        if not corpus.has(e.id):
            corpus.add(e, md)
            done += 1
    total = sum(1 for _ in entries.load_all(cfg.knowledge_dir))
    manifest.write(cfg.knowledge_dir, cfg.embedding_model, total)
    log.info("loaded %d new entries into Chroma, %d in total", done, total)
