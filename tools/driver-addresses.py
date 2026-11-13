#!/usr/bin/env python3
"""Audit the physical addresses a driver carries against this phone's device tree.

The HakiOS drivers were written for the first phone and carry its addresses as #defines. A port has
to check each one: an address the driver carries that this phone does not have is a silent wrong
register, and an address this phone has that the driver does not is a block the driver never touches.

This reads every `#define NAME 0x...` in the common repository's drivers, keeps the ones that look
like physical addresses, and looks each up in the phone's own tree. It does not say the driver is
wrong -- only where its constants point.

Usage:
  python3 tools/driver-addresses.py
  python3 tools/driver-addresses.py --dtb uefi/files/Resources/DTBs/cupid.dtb --self-test
"""

import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

DEFINE = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(0x[0-9a-fA-F]{4,}|[0-9]{5,})[uUlL]*\b', re.MULTILINE)
# a physical address on these SoCs: 0x100000 and up, and not a size or a shift
MIN_PHYS = 0x100000


def _facts():
    spec = importlib.util.spec_from_file_location("gpu_facts", os.path.join(HERE, "gpu-facts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FACTS = _facts()


def read_defines(common):
    """Per driver file: the physical-looking #defines it carries."""
    out = {}
    root = os.path.join(common, "drivers")
    if not os.path.isdir(root):
        return out
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith((".c", ".cpp", ".h")):
                continue
            path = os.path.join(base, name)
            text = open(path, encoding="utf-8", errors="replace").read()
            found = {}
            for constant, value in DEFINE.findall(text):
                number = int(value, 0)
                if number >= MIN_PHYS:
                    found[constant] = number
            if found:
                out[os.path.relpath(path, common).replace(os.sep, "/")] = found
    return out


def read_tree_addresses(nodes):
    """Every address the phone's tree gives, with the node that holds it."""
    addresses = {}
    for path, props in nodes.items():
        if "reg" not in props:
            continue
        for index, (address, size) in enumerate(FACTS.reg_pairs(nodes, path)):
            addresses.setdefault(address, []).append("%s (reg[%d], 0x%x)" % (path, index, size))
    return addresses


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--common", default=os.path.dirname(os.path.dirname(REPO)))
    parser.add_argument("--dtb", default="uefi/files/Resources/DTBs/cupid.dtb")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            common = os.path.join(tmp, "common", "drivers", "power")
            os.makedirs(common)
            with open(os.path.join(common, "hakios.pmic.c"), "w", encoding="utf-8") as handle:
                handle.write('#define ARB_CORE_PHYS 0x0c440000UL\n'
                             '#define CHANNELS 16\n'
                             '#define ARB_VERSION 0x50020000\n')
            found = read_defines(os.path.dirname(os.path.dirname(common)))
            info = found["drivers/power/hakios.pmic.c"]
            assert info["ARB_CORE_PHYS"] == 0x0C440000, info
            assert info["ARB_VERSION"] == 0x50020000, info
            assert "CHANNELS" not in info, info      # too small to be an address
        print("driver-addresses: self-test passed")
        return 0

    defines = read_defines(args.common)
    if not defines:
        print("driver-addresses: no drivers under %s" % args.common)
        return 1
    nodes = FACTS.fdt_nodes(open(args.dtb, "rb").read())
    tree = read_tree_addresses(nodes)

    total = found = 0
    for path in sorted(defines):
        hits = [(name, value, tree[value]) for name, value in sorted(defines[path].items())
                if value in tree]
        misses = [(name, value) for name, value in sorted(defines[path].items())
                  if value not in tree]
        total += len(defines[path])
        found += len(hits)
        print("%-42s %d address define(s), %d in the tree, %d not"
              % (path, len(defines[path]), len(hits), len(misses)))
        for name, value, where in hits:
            print("    %-28s 0x%08x  %s" % (name, value, where[0]))
        for name, value in misses:
            print("    %-28s 0x%08x  not in this phone's tree" % (name, value))
    print("driver-addresses: %d driver file(s), %d address define(s), %d found in the tree, %d not"
          % (len(defines), total, found, total - found))
    print("driver-addresses: an address the driver carries and the tree does not have is not proof of "
          "a bug -- the driver may compute it, or the block may be outside the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
