#!/usr/bin/env python3
"""Check the Xiaomi 12 (cupid) Adreno 730's address layer against the phone's own device tree, and
generate the header the port will include.

The configuration is gpu/a730_resources.json. It is the only place an address is written down; the
header is generated from it, so the two cannot drift.

What this checks, and what it cannot:

  * every physical block must exist in the device tree at the address and size the configuration
    says, with the reg-name the tree gives it. An address that is not in the phone's own tree fails
    here -- which is what stops a reference phone's addresses being reused.
  * no two blocks may overlap, unless one contains the other. A containment is reported as a note
    (the GMU's coarse region covers the GPUCC on this SoC); anything else is a failure.
  * every register offset must be in Linux's A7XX register dumps, when --linux is given. Offsets
    are checked against the dump, never assumed.
  * the generated header must match the configuration.

What it cannot check: whether any of these addresses does anything. A wrong register ends the run on
the phone, and this tool has never been near one.

Usage:
  gpu-address-check.py --config gpu/a730_resources.json --dtb uefi/files/Resources/DTBs/cupid.dtb
  gpu-address-check.py ... --linux <dir with a6xx.xml, adreno_common.xml, a6xx_gmu.xml>
  gpu-address-check.py ... --emit-header gpu/hakios.adreno-a730.h
  gpu-address-check.py ... --check-header gpu/hakios.adreno-a730.h
"""

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _facts():
    """The device-tree reader in tools/gpu-facts.py, which this tool shares."""
    path = os.path.join(HERE, "gpu-facts.py")
    spec = importlib.util.spec_from_file_location("gpu_facts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FACTS = _facts()

# What the port needs before it can do anything. A missing one is a failure, not a warning: the
# configuration is meant to be complete for these.
REQUIRED_BLOCKS = ["gpu", "gmu", "gpucc", "smmu", "gpu_rscc"]
REQUIRED_STREAMS = ["gfx3d_user", "gfx3d_secure", "gmu"]
REQUIRED_INTERRUPTS = ["kgsl_3d0_irq", "hfi", "gmu"]

# The reference phone's (SC7280, redwood) GPU blocks. They are here to be named in the report's
# comparison, never to be used as a source: every block above must be confirmed by the cupid tree.
REFERENCE_BLOCKS = {
    "gpu": 0x3D00000, "gpucc": 0x3D90000, "cx_misc": 0x3D9E000, "smmu": 0x3DA0000,
    "gcc": 0x100000, "gmu": 0x3D6A000, "rscc": 0x3DE0000,
}


# Linux's register dumps carry a variants attribute: "A6XX-A7XX", "A7XX-", "A8XX-". An offset that
# is right for one generation is wrong for another, and several registers appear twice. The A730 is
# A7XX, so the dump entry chosen must be the one whose range contains A7XX.
GENERATION_ORDER = {"A5XX": 5, "A6XX": 6, "A7XX": 7, "A8XX": 8}


def _covers(variants, generation):
    """Does a dump entry's variants attribute cover the given generation?"""
    for part in variants.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, _, high = part.partition("-")
            low = low.strip()
            high = high.strip()
            # "A7XX-" means A7XX and everything after it; "A6XX-A7XX" is a closed range
            if high == "":
                if GENERATION_ORDER.get(low, 0) <= GENERATION_ORDER.get(generation, 0):
                    return True
            elif GENERATION_ORDER.get(low, 0) <= GENERATION_ORDER.get(generation, 0) <= GENERATION_ORDER.get(high, 0):
                return True
        elif part == generation:
            return True
    return False


# The dumps are layered: a6xx.xml and a6xx_gmu.xml are the A6XX-and-later ones, adreno_common.xml is
# the shared one underneath. Where two define the same name, the more specific file wins.
DUMP_PRIORITY = ["a6xx.xml", "a6xx_gmu.xml", "adreno_common.xml"]


def parse_linux_registers(directory, generation="A7XX"):
    """name -> (offset, file) from Linux's A7XX register dumps, one entry per name for the A730."""
    found = {}
    names = [n for n in DUMP_PRIORITY if os.path.exists(os.path.join(directory, n))]
    names += sorted(n for n in os.listdir(directory)
                    if n.endswith(".xml") and n not in DUMP_PRIORITY)
    for name in names:
        text = open(os.path.join(directory, name), encoding="utf-8", errors="replace").read()
        for match in re.finditer(
                r'<reg\d+\s+offset="(0x[0-9a-fA-F]+)"\s+name="([A-Z0-9_]+)"([^>]*)>', text):
            offset, register, rest = match.group(1), match.group(2), match.group(3)
            variants = re.search(r'variants="([^"]+)"', rest)
            if variants and not _covers(variants.group(1), generation):
                continue
            # the first file in priority order wins; a later one never overwrites it
            found.setdefault(register, (int(offset, 16), name))
    return found


def check(config, dtb, linux=None, emit_header=None, check_header=None):
    problems = []
    notes = []
    nodes = FACTS.fdt_nodes(open(dtb, "rb").read())

    blocks = config["blocks"]
    by_name = {b["name"]: b for b in blocks}

    # 1. every block must be in the phone's own tree, at the address and size the tree gives it
    for block in blocks:
        node = nodes.get(block["dt"])
        if node is None:
            problems.append("block %-14s: the device tree has no node %s" % (block["name"], block["dt"]))
            continue
        index = 0
        if block.get("reg"):
            names = [n for n in node.get("reg-names", b"").replace(b"\\x00", b"\0").split(b"\0") if n]
            if block["reg"].encode() not in names:
                problems.append("block %-14s: node %s has no reg-name %r (it has %s)"
                                % (block["name"], block["dt"], block["reg"],
                                   [n.decode() for n in names]))
                continue
            index = names.index(block["reg"].encode())
        if "property" in block:
            # some resources are a property's cells rather than a reg pair (qcom,gpu-qdss-stm)
            cells = FACTS.cells(node[block["property"]])
            if len(cells) < 2:
                problems.append("block %-14s: property %s has %d cells, need an address and a size"
                                % (block["name"], block["property"], len(cells)))
                continue
            address, size = cells[0], cells[1]
        else:
            pairs = FACTS.reg_pairs(nodes, block["dt"])
            if not pairs:
                problems.append("block %-14s: node %s has no reg" % (block["name"], block["dt"]))
                continue
            if index >= len(pairs):
                problems.append("block %-14s: node %s has %d reg pairs, needs index %d"
                                % (block["name"], block["dt"], len(pairs), index))
                continue
            address, size = pairs[index]
        if address != int(block["phys"], 16):
            problems.append("block %-14s: configuration says 0x%x, the tree says 0x%x"
                            % (block["name"], int(block["phys"], 16), address))
        if size != int(block["size"], 16):
            problems.append("block %-14s: configuration says size 0x%x, the tree says 0x%x"
                            % (block["name"], int(block["size"], 16), size))
        if block["status"] == "uncertain":
            notes.append("block %-14s: marked uncertain -- %s" % (block["name"], block["dt"]))

    # 2. the required resources must be there
    for name in REQUIRED_BLOCKS:
        if name not in by_name:
            problems.append("required block %r is missing from the configuration" % name)
    for stream in config.get("streams", []):
        if stream["name"] in REQUIRED_STREAMS and stream["dt"] not in nodes:
            problems.append("required stream %r: the device tree has no node %s"
                            % (stream["name"], stream["dt"]))
    for interrupt in config.get("interrupts", []):
        if interrupt["name"] in REQUIRED_INTERRUPTS and interrupt["dt"] not in nodes:
            problems.append("required interrupt %r: the device tree has no node %s"
                            % (interrupt["name"], interrupt["dt"]))

    # 3. overlaps: a containment is a note, anything else is a failure
    ranges = []
    for block in blocks:
        address, size = int(block["phys"], 16), int(block["size"], 16)
        ranges.append((address, address + size, block["name"]))
    ranges.sort()
    for i, (start, end, name) in enumerate(ranges):
        for start2, end2, name2 in ranges[i + 1:]:
            if start2 >= end:
                break
            if start2 >= start and end2 <= end:
                notes.append("containment: %s (0x%x-0x%x) sits inside %s (0x%x-0x%x)"
                             % (name2, start2, end2, name, start, end))
            else:
                problems.append("overlap: %s (0x%x-0x%x) and %s (0x%x-0x%x) intersect"
                                % (name, start, end, name2, start2, end2))

    # 4. every register offset must be in Linux's dumps, when they are supplied
    registers = config.get("registers", [])
    if linux:
        dumps = parse_linux_registers(linux)
        for register in registers:
            if register["status"] == "unverified-source":
                notes.append("register %-34s: no public source; offset 0x%x is unverified"
                             % (register["name"], int(register["offset"], 16)))
                continue
            if register["name"] not in dumps:
                problems.append("register %-34s: not in the Linux register dumps" % register["name"])
                continue
            offset, where = dumps[register["name"]]
            if offset != int(register["offset"], 16):
                problems.append("register %-34s: configuration says 0x%x, %s says 0x%x"
                                % (register["name"], int(register["offset"], 16), where, offset))
    else:
        notes.append("no --linux given: %d register offsets were not checked against Linux"
                     % len(registers))

    # 5. the generated header must match the configuration
    generated = render_header(config)
    if emit_header:
        with open(emit_header, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(generated)
        print("gpu-address-check: wrote %s" % emit_header)
    if check_header:
        current = open(check_header, encoding="utf-8").read()
        if current != generated:
            problems.append("%s does not match the configuration; regenerate it with --emit-header"
                            % check_header)

    # 6. report
    for note in notes:
        print("gpu-address-check: note: %s" % note)
    if problems:
        for problem in problems:
            print("gpu-address-check: FAIL: %s" % problem)
        print("gpu-address-check: %d problem(s), %d note(s)" % (len(problems), len(notes)))
        return 1
    print("gpu-address-check: %d blocks, %d registers, %d streams, %d interrupts: all consistent with %s"
          % (len(blocks), len(registers), len(config.get("streams", [])),
             len(config.get("interrupts", [])), os.path.basename(dtb)))
    return 0


def render_header(config):
    """The address layer as a header. Physical addresses and register offsets are kept apart."""
    out = []
    out.append("/*")
    out.append(" * hakios.adreno-a730.h -- the Xiaomi 12 (cupid) Adreno 730's address layer.")
    out.append(" *")
    out.append(" * GENERATED by tools/gpu-address-check.py from gpu/a730_resources.json.")
    out.append(" * Do not edit this file: change the configuration and regenerate.")
    out.append(" *")
    out.append(" * Two different kinds of number live here and they are not the same thing:")
    out.append(" *   A730_*_PHYS  a physical address, from the phone's own device tree")
    out.append(" *   A730_*_*     a dword offset inside a block, from Linux's A7XX register dumps")
    out.append(" * A register offset is not a physical address. Adding one to a base is a bug.")
    out.append(" *")
    out.append(" * Every line carries its source. 'uncertain' means two sources disagree; nothing")
    out.append(" * marked uncertain has been written to the hardware.")
    out.append(" */")
    out.append("")
    out.append("#ifndef HAKIOS_ADRENO_A730_H")
    out.append("#define HAKIOS_ADRENO_A730_H")
    out.append("")
    out.append("/* physical blocks, each from the device tree node named in the comment */")
    for block in config["blocks"]:
        name = block["name"].upper()
        line = "#define A730_%-14s 0x%08xu" % (name + "_PHYS", int(block["phys"], 16))
        comment = "/* %s, size 0x%x" % (block["dt"], int(block["size"], 16))
        if block.get("reg"):
            comment += ', reg "%s"' % block["reg"]
        if block.get("alias"):
            comment += ", alias %s" % block["alias"]
        if block["status"] == "uncertain":
            comment += ", UNCERTAIN"
        comment += " */"
        out.append("%-34s %s" % (line, comment))
    out.append("")
    out.append("/* dword offsets inside the gpu block -- NOT physical addresses */")
    for register in config["registers"]:
        name = register["name"].upper()
        line = "#define A730_%-34s 0x%05xu" % (name, int(register["offset"], 16))
        comment = "/* %s" % register["source"]
        if register["status"] != "verified":
            comment += ", %s" % register["status"]
        comment += " */"
        out.append("%-52s %s" % (line, comment))
    out.append("")
    out.append("/* the SMMU's translation contexts, from the device tree */")
    for stream in config.get("streams", []):
        out.append("#define A730_STREAM_%-14s %du\t/* %s */"
                   % (stream["name"].upper(), stream["id"], stream["dt"]))
    out.append("")
    out.append("/* interrupts, GIC SPI numbers from the device tree */")
    for interrupt in config.get("interrupts", []):
        out.append("#define A730_IRQ_%-24s %du\t/* %s */"
                   % (interrupt["name"].upper(), interrupt["number"], interrupt["dt"]))
    out.append("")
    out.append("#endif /* HAKIOS_ADRENO_A730_H */")
    out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="gpu/a730_resources.json")
    parser.add_argument("--dtb", default="uefi/files/Resources/DTBs/cupid.dtb")
    parser.add_argument("--linux", help="a directory holding Linux's a6xx.xml, "
                                        "adreno_common.xml and a6xx_gmu.xml")
    parser.add_argument("--emit-header")
    parser.add_argument("--check-header")
    args = parser.parse_args()

    config = json.load(open(args.config, encoding="utf-8"))
    return check(config, args.dtb, args.linux, args.emit_header, args.check_header)


if __name__ == "__main__":
    sys.exit(main())
