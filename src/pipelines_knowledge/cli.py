import argparse
import logging

from pipelines_watch.config import Settings

from .convert import convert
from .load import load
from .scrape import scrape


def main():
    parser = argparse.ArgumentParser(prog="pipelines-knowledge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scrape", help="stage 1: write retried failures and their logs from GitLab to a JSONL file")
    sc.add_argument("project", help="group/project path")
    sc.add_argument("--pipelines", type=int, default=200, help="how many recent pipelines to scan at most")
    sc.add_argument("--limit", type=int, help="stop once the JSONL file has this many jobs")
    cv = sub.add_parser("convert", help="stage 2: turn the JSONL file into markdown entries with an LLM")
    cv.add_argument("project", help="group/project path")
    for p in (sc, cv):
        p.add_argument("--raw", default="raw", help="directory of the JSONL files")
    sub.add_parser("load", help="stage 3: embed entry files into Chroma and write the manifest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Settings()
    if args.cmd == "scrape":
        scrape(cfg, args.project, args.raw, args.pipelines, args.limit)
    elif args.cmd == "convert":
        convert(cfg, args.project, args.raw)
    else:
        load(cfg)
