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

import argparse
import pathlib
import json


def main():
    parser = argparse.ArgumentParser(
        prog="Dump Import", description="Import SDBL Dump files"
    )
    parser.add_argument(
        "--import-directory",
        required=True,
        type=pathlib.Path,
        help="Path with SDBL dumped files",
    )
    parser.add_argument(
        "--target-directory",
        required=True,
        type=pathlib.Path,
        help="Path to store converted files",
    )

    args = parser.parse_args()
    convert_dump(**vars(args))


def convert_dump(import_directory, target_directory):
    if target_directory.exists():
        print("Target directory already exists")
        return

    for f in import_directory.glob("*.json"):
        cls, identifier = f.stem.split(":", 1)
        cls_directory = target_directory / cls
        cls_directory.mkdir(parents=True, exist_ok=True)

        data = json.loads(f.read_text())

        (cls_directory / f"{identifier}.json").write_text(
            json.dumps(
                dict(
                    meta=dict(
                        __id__=data.get("id"),
                        __rev__=data.get("__rev__"),
                        __archived__=data.get("archived"),
                    ),
                    data={
                        k: v
                        for k, v in data.items()
                        if k not in ["id", "__rev__", "archived"]
                    },
                )
            )
        )
