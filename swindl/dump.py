## begin license ##
#
# "Recordstore" is a JSON store enhanced with a Lucene Index.
#
# All rights reserved.
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) http://seecr.nl
#
# This file is part of "Recordstore"
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
