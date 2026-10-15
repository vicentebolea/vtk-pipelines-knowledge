"""Show what the corpus returns for an error text: the retrieval step, without any LLM.

    .venv/bin/python scripts/query.py "fatal: index file corrupt"
    some-command | .venv/bin/python scripts/query.py -k 8
"""
import argparse
import sys

from pipelines_watch.config import Settings
from pipelines_watch.corpus import Corpus
from pipelines_watch.entries import Entry

parser = argparse.ArgumentParser()
parser.add_argument("text", nargs="?", help="error text, default stdin")
parser.add_argument("-k", type=int, default=5)
args = parser.parse_args()

cfg = Settings()
text = args.text or sys.stdin.read()
for doc, distance in Corpus(cfg.knowledge_dir, cfg.embedding_model).store.similarity_search_with_score(text, k=args.k):
    e = Entry.from_markdown(doc.metadata["markdown"])
    rate = f"{e.success_rate:.0%} of {e.similar}" if e.success_rate is not None else "n/a"
    print(f"{distance:.3f}  {e.outcome:<12} rate {rate:<9} {e.error_type:<14} {e.platform:<20} {e.job_name}")
    print(f"       {e.snippet.splitlines()[0][:110] if e.snippet else '(empty)'}")
