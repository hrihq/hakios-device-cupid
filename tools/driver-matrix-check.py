#!/usr/bin/env python3
"""Check the driver compatibility matrix against the drivers in the common repository.

docs/driver-compatibility.md names every driver HakiOS has. This reads the `driver <NAME>` entries
out of drivers/*/conf in the common repository and reports:

* a driver the matrix does not cover -- the matrix has drifted behind the code;
* a driver the matrix names that is no longer in the code -- the matrix is stale.

The matrix is a document; the conf files are the code. CI keeps them together.

Usage:
  python3 tools/driver-matrix-check.py
  python3 tools/driver-matrix-check.py --common ../.. --matrix docs/driver-compatibility.md
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def read_matrix(path):
    text = open(path, encoding="utf-8").read()
    # the matrix names a driver as **NAME** in the first column of a table row
    names = set()
    for line in text.splitlines():
        match = re.match(r"\|\s*\*\*([A-Z0-9_]+)\*\*", line)
        if match:
            names.add(match.group(1))
    return names


def read_confs(root):
    drivers = {}
    conf_dir = os.path.join(root, "drivers")
    if not os.path.isdir(conf_dir):
        return drivers
    for subsystem in sorted(os.listdir(conf_dir)):
        conf = os.path.join(conf_dir, subsystem, "conf")
        if not os.path.isfile(conf):
            continue
        for line in open(conf, encoding="utf-8"):
            match = re.match(r"driver\s+([A-Z0-9_]+)", line.strip())
            if match:
                drivers.setdefault(match.group(1), []).append(subsystem)
    return drivers


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--common", default=os.path.dirname(os.path.dirname(REPO)),
                        help="the common repository (default: the grandparent of this tool, i.e. the "
                             "device repository's parent's parent)")
    parser.add_argument("--matrix", default="docs/driver-compatibility.md")
    args = parser.parse_args()

    matrix = read_matrix(args.matrix)
    confs = read_confs(args.common)
    if not confs:
        print("driver-matrix: no drivers/*/conf under %s" % args.common)
        return 1

    missing = sorted(set(confs) - matrix)
    stale = sorted(matrix - set(confs))
    print("driver-matrix: %d driver(s) in %s, %d named in %s"
          % (len(confs), os.path.join(os.path.basename(args.common.rstrip(os.sep)), "drivers"),
             len(matrix), args.matrix))
    for name in missing:
        print("  NOT COVERED  %-12s in %s" % (name, ", ".join(confs[name])))
    for name in stale:
        print("  STALE        %-12s named in the matrix but not in any conf" % name)
    if missing or stale:
        return 1
    print("driver-matrix: every driver is covered and every name is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
