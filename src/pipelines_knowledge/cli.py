import argparse
import logging

from pipelines_watch.config import Settings

from .backfill import backfill, load


def main():
    parser = argparse.ArgumentParser(prog="pipelines-knowledge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    bf = sub.add_parser("backfill", help="stage 1: write entry files from GitLab history")
    bf.add_argument("project", help="group/project path")
    bf.add_argument("--pipelines", type=int, default=200)
    sub.add_parser("load", help="stage 2: embed entry files into Chroma and write the manifest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Settings()
    if args.cmd == "backfill":
        backfill(cfg, args.project, args.pipelines)
    else:
        load(cfg)
