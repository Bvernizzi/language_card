"""CLI.

    python -m italiano load aulas/2026-11-06.yaml   # lesson or source files, or a folder
    python -m italiano export [-o output/italiano.apkg]
    python -m italiano dump                         # database -> aulas/*.yaml + aulas/fontes/*.yaml
    python -m italiano remove 2000-01-01            # delete a lesson (e.g. the example)
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

from .db import ROOT, connect, ensure_schema
from .dump import dump_file, fetch_lesson, fetch_source, lesson_dates, source_keys
from .exporter import export_package
from .lesson_file import LessonFileError, parse_lesson
from .loader import load_lesson, remove_lesson


def _lesson_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():  # sources first (lessons may reference them), skipping the example
            files += sorted((p / "fontes").glob("*.yaml"))
            files += sorted(f for f in p.glob("*.yaml") if f.name != "exemplo.yaml")
        else:
            files.append(p)
    return files


def cmd_load(args) -> int:
    files = _lesson_files(args.paths)
    lessons = [parse_lesson(f) for f in files]  # validate everything before touching the DB
    with connect() as conn:
        ensure_schema(conn)
        for f, lesson in zip(files, lessons):
            counts = load_lesson(conn, lesson)
            summary = ", ".join(f"{n} {k}" for k, n in counts.items())
            print(f"loaded {f.name} ({lesson.label}): {summary}")
    return 0


def cmd_export(args) -> int:
    with connect() as conn:
        ensure_schema(conn)
        counts = export_package(conn, args.output)
    for deck, n in sorted(counts.items()):
        print(f"  {deck}: {n} notes")
    print(f"wrote {args.output} ({sum(counts.values())} notes)")
    return 0


def cmd_dump(args) -> int:
    folder = ROOT / "aulas"
    with connect() as conn:
        ensure_schema(conn)
        items = [fetch_lesson(conn, d) for d in lesson_dates(conn)]
        items += [fetch_source(conn, k) for k in source_keys(conn)]
        for item in items:
            print(f"wrote {dump_file(item, folder).relative_to(ROOT)}")
    return 0


def cmd_remove(args) -> int:
    with connect() as conn:
        ensure_schema(conn)
        removed = remove_lesson(conn, args.date)
    print(f"removed lesson {args.date}" if removed else f"no lesson on {args.date}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="italiano", description="Italian lesson memory -> Anki")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("load", help="load lesson YAML files (idempotent)")
    p.add_argument("paths", nargs="+", help="YAML files or folders")
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("export", help="export all cards to an .apkg")
    p.add_argument("-o", "--output", type=Path, default=ROOT / "output" / "italiano.apkg")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("dump", help="rewrite aulas/*.yaml and aulas/fontes/*.yaml from the database")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("remove", help="delete a lesson by date")
    p.add_argument("date", type=dt.date.fromisoformat)
    p.set_defaults(func=cmd_remove)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except LessonFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
