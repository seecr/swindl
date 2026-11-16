## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Swindl"
#
# "Swindl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

"""Run the example:
python -m swindl_collection [--port 8000] [--data-dir ./collection-data]"""

import argparse

import uvicorn

from .app import DEMO_PASSWORD, DEMO_USER, create_app


def main():
    parser = argparse.ArgumentParser(description="swindl example: your collections")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--data-dir", default="collection-data", help="where everything is stored"
    )
    args = parser.parse_args()
    print(
        f"Collection on http://{args.host}:{args.port}/"
        f" - log in as {DEMO_USER} / {DEMO_PASSWORD}"
    )
    uvicorn.run(
        create_app(args.data_dir), host=args.host, port=args.port, log_level="warning"
    )


if __name__ == "__main__":
    main()
