#!/usr/bin/env python3
"""Audit which boot-arguments each driver reads, and which this device provides.

A HakiOS driver reads its arguments with PE_parse_boot_arg*("name", ...). A device provides them in
soc.args (the SoC addresses), metal.args (the display and its frame rate) and its config fragment.
This reads both sides and reports, per driver:

* the arguments it reads;
* which of them this device provides;
* which it does not -- and, for the modem's SoC addresses, the built-in default it would then keep.

The last group is the point. A driver that falls back to a built-in default silently uses the first
phone's value, which is how a port ships a wrong address. soc.args already had three such values
missing (tools/soc-args-cupid.py fixed them); this checks the rest.

Usage:
  python3 tools/driver-args-check.py
  python3 tools/driver-args-check.py --common ../.. --device .
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

BOOT_ARG = re.compile(r'PE_parse_boot_arg[a-z_]*\(\s*"([a-z0-9_]+)"')
DEFAULT = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(0x[0-9a-fA-F]+|\d+)[uUlL]*\b', re.MULTILINE)


def read_args(device):
    """Every boot-argument this device provides, from soc.args, metal.args and the config fragment."""
    provided = {}
    for name, source in (("soc.args", "the modem's SoC addresses"),
                         ("metal.args", "the display and its frame rate")):
        path = os.path.join(device, name)
        if not os.path.isfile(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.split("#", 1)[0].strip()
            for key, value in re.findall(r"([a-z0-9_]+)=([^\s]+)", line):
                provided[key] = source
    for fragment in ("configs/cupid.config",):
        path = os.path.join(device, fragment)
        if os.path.isfile(path):
            for line in open(path, encoding="utf-8"):
                match = re.match(r"CONFIG_([A-Z0-9_]+)=(y|m|\"[^\"]*\")", line.strip())
                if match:
                    provided["CONFIG_" + match.group(1)] = "the config fragment"
    return provided


def read_drivers(common):
    """Per driver file: the arguments it reads, and the defaults it carries."""
    drivers = {}
    root = os.path.join(common, "drivers")
    if not os.path.isdir(root):
        return drivers
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith((".c", ".cpp")):
                continue
            path = os.path.join(base, name)
            text = open(path, encoding="utf-8", errors="replace").read()
            args = sorted(set(BOOT_ARG.findall(text)))
            if not args:
                continue
            defaults = dict(DEFAULT.findall(text))
            drivers[os.path.relpath(path, common).replace(os.sep, "/")] = {"args": args, "defaults": defaults}
    return drivers


def default_for(arg, defaults):
    """The built-in default for a boot-arg, when the driver names one after the argument.

    The modem driver names its defaults after the argument with the `soc_` dropped and the words
    sometimes spelled out (`soc_mpss_mem` -> `MPSS_MEMORY_DEFAULT`), so an exact match is tried
    first and a prefix match on the remainder second.
    """
    best = None
    for name, value in defaults.items():
        stem = name.lower()[:-8] if name.lower().endswith("_default") else name.lower()
        if not stem:
            continue
        if arg == stem:
            best = (len(stem), value)
        elif arg.startswith("soc_") or arg.startswith("modem_"):
            rest = arg.split("_", 1)[1]
            if len(rest) >= 3 and (stem.startswith(rest) or rest.startswith(stem)):
                if best is None or len(stem) > best[0]:
                    best = (len(stem), value)
    return best[1] if best else None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--common", default=os.path.dirname(os.path.dirname(REPO)))
    parser.add_argument("--device", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            common = os.path.join(tmp, "common", "drivers", "modem")
            os.makedirs(common)
            with open(os.path.join(common, "hakios.mpss.c"), "w", encoding="utf-8") as handle:
                handle.write('#define MPSS_MEMORY_DEFAULT 0x8b800000u\n'
                             '#define PAS_MPSS_DEFAULT 4\n'
                             'static uint32_t x;\n'
                             'PE_parse_boot_argn("soc_mpss_mem", &x, sizeof(x));\n'
                             'PE_parse_boot_argn("soc_pas_mpss", &x, sizeof(x));\n'
                             'PE_parse_boot_argn("modem_step", &x, sizeof(x));\n')
            device = os.path.join(tmp, "device")
            os.makedirs(os.path.join(device, "configs"))
            with open(os.path.join(device, "soc.args"), "w", encoding="utf-8") as handle:
                handle.write("soc_mpss_mem=0x8bc00000  # the modem's memory\n")
            with open(os.path.join(device, "configs", "cupid.config"), "w", encoding="utf-8") as handle:
                handle.write('CONFIG_HAKIOS_MODEM=y\n')
            provided = read_args(device)
            assert provided["soc_mpss_mem"] == "the modem's SoC addresses", provided
            assert "modem_step" not in provided
            drivers = read_drivers(os.path.dirname(os.path.dirname(common)))
            info = drivers["drivers/modem/hakios.mpss.c"]
            assert info["args"] == ["modem_step", "soc_mpss_mem", "soc_pas_mpss"], info["args"]
            assert default_for("soc_mpss_mem", info["defaults"]) == "0x8b800000"
            assert default_for("soc_pas_mpss", info["defaults"]) == "4"
            assert default_for("modem_step", info["defaults"]) is None
        print("driver-args-check: self-test passed")
        return 0

    provided = read_args(args.device)
    drivers = read_drivers(args.common)
    if not drivers:
        print("driver-args-check: no drivers under %s" % args.common)
        return 1

    total = soc_total = soc_missing = 0
    for path in sorted(drivers):
        info = drivers[path]
        total += len(info["args"])
        soc_args = [a for a in info["args"] if a.startswith("soc_")]
        if not soc_args:
            continue
        soc_total += len(soc_args)
        missing = [a for a in soc_args if a not in provided]
        soc_missing += len(missing)
        print("%-44s %d soc_* argument(s), %d not provided" % (path, len(soc_args), len(missing)))
        for arg in soc_args:
            if arg in provided:
                print("    %-28s provided by %s" % (arg, provided[arg]))
            else:
                default = default_for(arg, info["defaults"])
                print("    %-28s NOT provided%s" % (arg, ""
                      if default is None else "; keeps its built-in %s" % default))
    print("driver-args-check: %d driver(s), %d argument(s) read, %d of them soc_*, %d of those not provided"
          % (len(drivers), total, soc_total, soc_missing))
    print("driver-args-check: this is an audit, not a failure: a soc_* argument that is not provided "
          "leaves the modem driver on the first phone's built-in value")
    return 0


if __name__ == "__main__":
    sys.exit(main())
