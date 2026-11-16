## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Swindl"
#
# "Swindl" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "Swindl" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "Swindl"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
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
