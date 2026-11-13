#!/usr/bin/env python3
"""Check the UEFI platform's vendor-binary references before the build.

The platform's Include/*.inf files name the vendor DXE drivers it needs, each as
`Binaries/<board>/<path>/<Driver>.inf`. Those binaries are the phone's own and are never committed,
so a build without them fails late -- at the link, with a message about a file it cannot find.

This reads the platform's .inc/.fdf files, lists every vendor-binary reference, and reports:

* how many the platform needs;
* which of them are present on disk (normally none, until the phone's drivers are unpacked);
* optionally, how the list differs from another platform's -- useful because a sibling board on the
  same SoC is the best available reference for what a board's platform should name.

Usage:
  python3 tools/uefi-build-check.py
  python3 tools/uefi-build-check.py --reference ../negroniPkg --reference-name negroni
  python3 tools/uefi-build-check.py --self-test
"""

import argparse
import os
import re
import sys
import tempfile

REFERENCE = re.compile(r"Binaries/([A-Za-z0-9_.-]+)/([A-Za-z0-9_./-]+\.(?:inf|efi|fdf|dec|dsc))")
TEXT_FILES = (".inc", ".fdf", ".dsc", ".dec", ".inf")


def collect(root, board=None):
    """Every `Binaries/<board>/...` reference under a platform directory."""
    found = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(TEXT_FILES):
                continue
            path = os.path.join(base, name)
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for match in REFERENCE.finditer(text):
                reference_board, relative = match.group(1), match.group(2)
                if board is not None and reference_board != board:
                    continue
                found.setdefault("%s/%s" % (reference_board, relative), set()).add(
                    os.path.relpath(path, root))
    return found


def present(reference, binaries_root):
    return os.path.isfile(os.path.join(binaries_root, reference.replace("/", os.sep)))


def self_test():
    with tempfile.TemporaryDirectory() as tmp:
        platform = os.path.join(tmp, "cupidPkg")
        os.makedirs(os.path.join(platform, "Include"))
        with open(os.path.join(platform, "Include", "DXE.inc"), "w", encoding="utf-8") as handle:
            handle.write("  INF Binaries/cupid/QcomPkg/Drivers/ClockDxe/ClockDxe.inf\n"
                         "  INF Binaries/cupid/QcomPkg/Drivers/I2CDxe/I2CDxe.inf\n"
                         "!if $(X) == 1\n"
                         "  INF Binaries/cupid/QcomPkg/Drivers/CPRDxe/CPRDxe.inf\n"
                         "!endif\n")
        with open(os.path.join(platform, "Include", "APRIORI.inc"), "w", encoding="utf-8") as handle:
            handle.write("  INF Binaries/cupid/QcomPkg/Drivers/EnvDxe/EnvDxe.inf\n")
        found = collect(platform)
        assert set(found) == {
            "cupid/QcomPkg/Drivers/ClockDxe/ClockDxe.inf",
            "cupid/QcomPkg/Drivers/I2CDxe/I2CDxe.inf",
            "cupid/QcomPkg/Drivers/CPRDxe/CPRDxe.inf",
            "cupid/QcomPkg/Drivers/EnvDxe/EnvDxe.inf",
        }, sorted(found)
        # a reference inside a conditional is still a reference: the build may take that branch
        assert all(len(sources) == 1 for sources in found.values())

        binaries = os.path.join(tmp, "Binaries", "cupid")
        os.makedirs(os.path.join(binaries, "QcomPkg", "Drivers", "ClockDxe"))
        with open(os.path.join(binaries, "QcomPkg", "Drivers", "ClockDxe", "ClockDxe.inf"), "w") as h:
            h.write("")
        assert present("cupid/QcomPkg/Drivers/ClockDxe/ClockDxe.inf", os.path.join(tmp, "Binaries"))
        assert not present("cupid/QcomPkg/Drivers/I2CDxe/I2CDxe.inf", os.path.join(tmp, "Binaries"))
    print("uefi-build-check: self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", default="uefi/files/Platforms/Xiaomi/cupidPkg",
                        help="the platform directory to read (default: cupidPkg)")
    parser.add_argument("--binaries", default="uefi/files/Binaries",
                        help="where the vendor binaries would be")
    parser.add_argument("--board", default="cupid")
    parser.add_argument("--reference", action="append", default=[],
                        help="another platform directory to compare against (repeatable)")
    parser.add_argument("--reference-name", default="the reference platform")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not os.path.isdir(args.platform):
        print("uefi-build-check: no platform at %s" % args.platform)
        return 1
    found = collect(args.platform, args.board)
    if not found:
        print("uefi-build-check: %s names no Binaries/%s/ references" % (args.platform, args.board))
        return 1

    here = [r for r in sorted(found) if present(r, args.binaries)]
    missing = [r for r in sorted(found) if r not in here]
    print("uefi-build-check: %s names %d vendor binary reference(s), %d present, %d missing"
          % (args.platform, len(found), len(here), len(missing)))
    for reference in here:
        print("  present   %s" % reference)
    for reference in missing:
        print("  missing   %s" % reference)

    status = 0
    for other in args.reference:
        if not os.path.isdir(other):
            print("uefi-build-check: no reference platform at %s" % other)
            status = 1
            continue
        theirs = collect(other)

        def relative(key):
            return key.split("/", 1)[1] if "/" in key else key

        mine_relative = {relative(r) for r in found}
        theirs_relative = {relative(r) for r in theirs}
        only_mine = sorted(r for r in found if relative(r) not in theirs_relative)
        only_theirs = sorted(r for r in theirs if relative(r) not in mine_relative)
        print("uefi-build-check: against %s (%d references): %d only here, %d only there"
              % (args.reference_name, len(theirs), len(only_mine), len(only_theirs)))
        for reference in only_mine:
            print("  only here  %s" % reference)
        for reference in only_theirs:
            print("  only there %s" % reference)
    return status


if __name__ == "__main__":
    sys.exit(main())
