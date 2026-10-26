"""
Serve the HTML coverage report, with live reloading.

Watches the coverage database and rebuilds the report whenever a test
run refreshes it. Intended to be run via the ``cov-dev`` nox
session, which provides the ``coverage`` and ``livereload`` libraries.
"""

import argparse
import sys
from pathlib import Path

# pylint: disable=import-error
import coverage
from coverage.exceptions import CoverageException
from livereload import Server

# pylint: enable=import-error

PLACEHOLDER = """\
<!DOCTYPE html>
<html>
  <head><title>No coverage data</title></head>
  <body>
    <p>
      No coverage data found. Run <code>nox -e test</code> to create it.
      This page reloads automatically once the report is ready.
    </p>
  </body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-file", required=True, type=Path, help="The coverage database to watch"
    )
    parser.add_argument(
        "--report-dir", required=True, type=Path, help="Render the HTML report into this directory"
    )
    parser.add_argument(
        "--include", action="append", help="Restrict the report to these path patterns"
    )
    parser.add_argument(
        "--host", default=None, help="Bind the server to this host instead of localhost"
    )
    parser.add_argument("--port", type=int, default=5500, help="Bind the server to this port")
    args = parser.parse_args()

    def build():
        if not args.data_file.exists():
            print(
                f"Coverage database '{args.data_file}' not found. "
                "Run `nox -e test` to create it.",
                file=sys.stderr,
            )
            return
        try:
            cov = coverage.Coverage(data_file=args.data_file)
            cov.load()
            cov.html_report(directory=str(args.report_dir), include=args.include)
        except CoverageException as err:
            print(f"Failed to render the HTML coverage report: {err}", file=sys.stderr)

    args.report_dir.mkdir(parents=True, exist_ok=True)
    build()
    index = args.report_dir / "index.html"
    if not index.exists():
        # livereload injects its reload script into served HTML, so this
        # placeholder refreshes into the real report after the first test run.
        index.write_text(PLACEHOLDER, encoding="utf-8")

    server = Server()
    server.watch(str(args.data_file), build)
    server.serve(
        host=args.host,
        port=args.port,
        root=str(args.report_dir),
        # If the user is overriding the host, it's likely they are rendering on
        # a remote/headless system and don't want the browser to open.
        open_url_delay=None if args.host else 1,
    )


if __name__ == "__main__":
    main()
