#!/usr/bin/env python3
"""The Xiaomi 12 (cupid) GPU, as its own device tree says it is.

usage: tools/gpu-facts.py --dtb Resources/DTBs/cupid.dtb [--check docs/gpu-facts.txt] [--out FILE]

Why this exists. HakiOS's GPU driver carries the reference phone's addresses and register offsets as
literals (drivers/gpu/hakios.adreno.c: the `struct block` table and the `GPUCC_*`, `GMU_*`, `RSCC_*`,
`SMMU_*` defines). A second phone needs a second set, and the tree is where they come from: this reads
the GPU's blocks, its power levels, its SMMU streams and its firmware's memory out of the phone's own
tree, so that the port cannot drift from the hardware it describes.

Every line is a fact with one source: the device tree. Nothing here is a register value and nothing
here is a measurement -- this file says where the GPU is and what the vendor's own firmware expects,
not what the GPU does.

--check compares the facts with a file made earlier (docs/gpu-facts.txt) and fails if they differ, so
CI can catch a tree that changed under a port.
"""
import argparse
import os
import struct
import sys

# ---------------------------------------------------------------- flattened device tree

def fdt_nodes(blob):
    """The nodes of a flattened device tree, as {path: {property: bytes}}. Minimal, like tools/soc-args.py."""
    if blob[:4] != b"\xd0\x0d\xfe\xed":
        sys.exit("gpu-facts.py: not a flattened device tree")
    off_struct, off_strings = struct.unpack(">II", blob[8:16])
    size_strings, = struct.unpack(">I", blob[32:36])
    strings = blob[off_strings:off_strings + size_strings]
    out, path, at = {}, [], off_struct
    while True:
        token, = struct.unpack(">I", blob[at:at + 4])
        at += 4
        if token == 1:                                     # FDT_BEGIN_NODE
            end = blob.index(b"\0", at)
            path.append(blob[at:end].decode("utf-8", "replace"))
            at = (end + 4) & ~3
            out["/".join(path)] = {}
        elif token == 2:                                   # FDT_END_NODE
            path.pop()
        elif token == 3:                                   # FPROP
            length, name_off = struct.unpack(">II", blob[at:at + 8])
            at += 8
            name = strings[name_off:strings.index(b"\0", name_off)].decode()
            out["/".join(path)][name] = blob[at:at + length]
            at = (at + length + 3) & ~3
        elif token == 9:                                   # FDT_END
            return out
        elif token != 4:
            sys.exit("gpu-facts.py: unexpected token %d in the device tree" % token)


def cells(prop):
    return list(struct.unpack(">%dI" % (len(prop) // 4), prop[:len(prop) // 4 * 4]))


def text(prop):
    return prop.split(b"\0")[0].decode("utf-8", "replace")


def reg_pairs(nodes, path):
    """(address, size) pairs of a node's reg, using its parent's #address-cells/#size-cells.

    A decompiled tree stores a 2-cell address as two dwords, high first; the address is the pair,
    not the first cell alone.
    """
    props = nodes.get(path, {})
    if "reg" not in props:
        return []
    parent = nodes.get(path.rsplit("/", 1)[0], {})
    ac = cells(parent["#address-cells"])[0] if "#address-cells" in parent else 2
    sc = cells(parent["#size-cells"])[0] if "#size-cells" in parent else 1
    values = cells(props["reg"])
    out = []
    for i in range(0, len(values) - ac - sc + 1, ac + sc):
        address = 0
        for j in range(ac):
            address = (address << 32) | values[i + j]
        size = 0
        for j in range(sc):
            size = (size << 32) | values[i + ac + j]
        out.append((address, size))
    return out


def find(nodes, needle):
    """The first node whose compatible names `needle`; (None, {}) when there is none."""
    for path, props in sorted(nodes.items()):
        for name in text(props.get("compatible", b"")).split("\0"):
            if needle in name:
                return path, props
    return None, {}


# ---------------------------------------------------------------- the facts

def facts(nodes):
    out = []
    add = out.append

    path, props = find(nodes, "qcom,adreno-gpu-gen7")
    if path is None:
        path, props = find(nodes, "qcom,kgsl-3d0")
    if path is None:
        sys.exit("gpu-facts.py: no GPU node in the tree")
    add("gpu.node              %s" % path)
    add("gpu.compatible        %s" % text(props.get("compatible", b"")).replace("\0", " "))
    add("gpu.model             %s" % text(props.get("qcom,gpu-model", b"?")))
    add("gpu.initial-pwrlevel  %d" % (cells(props["qcom,initial-pwrlevel"])[0]
                                      if "qcom,initial-pwrlevel" in props else -1))
    for name, key in (("qcom,gpu-speed-bin", "gpu.speed-bin"),
                      ("qcom,chipid", "gpu.chipid"),
                      ("qcom,ubwc-mode", "gpu.ubwc-mode"),
                      ("qcom,min-access-length", "gpu.min-access-length")):
        if name in props:
            values = cells(props[name])
            add("%-22s %s" % (key, " ".join("0x%x" % v for v in values)))
    if "qcom,tzone-names" in props:
        # a decompiled tree may hold the separators as the literal text "\x00", not as NULs
        raw = props["qcom,tzone-names"].replace(b"\\x00", b"\0")
        names = [t for t in raw.split(b"\0") if t.strip()]
        add("gpu.thermal-zones     %s" % " ".join(t.decode("utf-8", "replace") for t in names))
    for label, key in (("kgsl_3d0_reg_memory", "gpu.reg.gpu"),
                       ("cx_dbgc", "gpu.reg.cx_dbgc"),
                       ("rscc", "gpu.reg.rscc"),
                       ("isense_cntl", "gpu.reg.isense"),
                       ("cx_misc", "gpu.reg.cx_misc"),
                       ("qdss_gfx", "gpu.reg.qdss"),
                       ("rdpm_cx", "gpu.reg.rdpm")):
        names = (text(props["reg-names"]).split("\0") if "reg-names" in props else [])
        pairs = reg_pairs(nodes, path)
        if label in names:
            i = names.index(label)
            if i < len(pairs):
                add("%-22s 0x%x 0x%x" % (key, pairs[i][0], pairs[i][1]))

    gmu, _ = find(nodes, "qcom,gen7-gmu")
    if gmu:
        pairs = reg_pairs(nodes, gmu)
        for label, key in (("gmu", "gmu.reg.gmu"), ("gmu_pdc", "gmu.reg.pdc"),
                           ("gmu_ao_blk_dec0", "gmu.reg.ao")):
            names = text(nodes[gmu]["reg-names"]).split("\0")
            if label in names:
                i = names.index(label)
                if i < len(pairs):
                    add("%-22s 0x%x 0x%x" % (key, pairs[i][0], pairs[i][1]))

    gpucc, _ = find(nodes, "gpucc")
    if gpucc:
        pair = reg_pairs(nodes, gpucc)[0]
        add("%-22s 0x%x 0x%x" % ("gpucc.reg.cc_base", pair[0], pair[1]))

    gcc, _ = find(nodes, "qcom,waipio-gcc")
    if gcc:
        pair = reg_pairs(nodes, gcc)[0]
        add("%-22s 0x%x 0x%x" % ("gcc.reg.cc_base", pair[0], pair[1]))

    smmu, _ = find(nodes, "qcom,kgsl-smmu")
    if smmu:
        pair = reg_pairs(nodes, smmu)[0]
        add("%-22s 0x%x 0x%x" % ("smmu.reg.base", pair[0], pair[1]))
        for child, props in sorted(nodes.items()):
            if not child.startswith(smmu + "/"):
                continue
            if "iommus" in props:
                values = cells(props["iommus"])
                add("%-22s stream %d (iommus %s)" % ("smmu." + child.rsplit("/", 1)[-1],
                                                     values[-2], " ".join(str(v) for v in values)))
        for child, props in sorted(nodes.items()):
            if child.startswith(smmu + "/") and "reg" in props:
                pair = reg_pairs(nodes, child)[0]
                add("%-22s 0x%x 0x%x" % ("smmu." + child.rsplit("/", 1)[-1] + ".reg",
                                         pair[0], pair[1]))

    # the power levels, in the vendor's own order
    pwr = None
    for path2, props2 in sorted(nodes.items()):
        if path2.rsplit("/", 1)[-1].startswith("qcom,gpu-pwrlevels"):
            pwr = path2
            break
    if pwr:
        levels = []
        for path2, props2 in sorted(nodes.items()):
            if not path2.startswith(pwr + "/"):
                continue
            freq = cells(props2["qcom,gpu-freq"])[0] if "qcom,gpu-freq" in props2 else 0
            bus = cells(props2["qcom,bus-freq"])[0] if "qcom,bus-freq" in props2 else -1
            acd = cells(props2["qcom,acd-level"])[0] if "qcom,acd-level" in props2 else 0
            levels.append((freq, bus, acd))
        levels.sort()
        add("gpu.pwrlevels         %d" % len(levels))
        for i, (freq, bus, acd) in enumerate(levels):
            add("  level %-2d            %d Hz  bus %d  acd 0x%08x" % (i, freq, bus, acd))

    # the firmware's memory, which the vendor's own tree reserves for it. The zap-shader node's
    # memory-region is a phandle to a reserved-memory node; resolve it to the address and size.
    phandles = {}
    for path2, props2 in nodes.items():
        if "phandle" in props2:
            phandles[cells(props2["phandle"])[0]] = path2
    for path2, props2 in sorted(nodes.items()):
        if "memory-region" in props2 and "zap" in path2.rsplit("/", 1)[-1]:
            wanted = cells(props2["memory-region"])[0]
            region = phandles.get(wanted)
            if region and "reg" in nodes[region]:
                pair = reg_pairs(nodes, region)[0]
                add("%-22s %s 0x%x 0x%x" % ("gpu.zap.memory-region", region, pair[0], pair[1]))
            else:
                add("%-22s phandle %d (unresolved)" % ("gpu.zap.memory-region", wanted))

    for path2, props2 in sorted(nodes.items()):
        if (path2.rsplit("/", 1)[-1].startswith("qcom,gpu-mempool@")
                and "qcom,mempool-page-size" in props2):
            size = cells(props2["qcom,mempool-page-size"])[0]
            add("%-22s page-size 0x%x" % ("gpu.mempool." + path2.rsplit("@", 1)[-1], size))

    # the GPU's own power/clock controls, which the tree names by node; the alias section of the
    # tree says which node is which (gpu_cc_cx_gdsc = "/soc/qcom,gdsc@3d99108", and so on)
    controls = (("gpu_cc_cx_gdsc", "qcom,gdsc@3d99108"),
                ("gpu_cc_gx_gdsc", "qcom,gdsc@3d9905c"),
                ("gpu_cc_cx_hw_ctrl", "syscon@3d9953c"),
                ("gpu_cc_gx_sw_reset", "syscon@3d99058"),
                ("gpu_cc_gx_acd_reset", "syscon@3d99358"),
                ("gpu_cc_gx_acd_iroot_reset", "syscon@3d9958c"),
                ("gpu_cc_gx_domain_addr", "syscon@3d99504"))
    for label, leaf in controls:
        for path2, props2 in sorted(nodes.items()):
            if path2.rsplit("/", 1)[-1] == leaf and "reg" in props2:
                add("%-22s 0x%x" % ("gpu." + label, reg_pairs(nodes, path2)[0][0]))
                break

    # the two temperature-sensor blocks, in the tree's own order
    for i, (path2, props2) in enumerate(
            sorted((p, q) for p, q in nodes.items()
                   if p.rsplit("/", 1)[-1].startswith("thermal-sensor@"))):
        pair = reg_pairs(nodes, path2)[0]
        add("%-22s 0x%x 0x%x" % ("tsens%d.reg" % i, pair[0], pair[1]))

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtb", required=True, help="the phone's own device tree")
    ap.add_argument("--check", help="compare with a file made earlier; fail when they differ")
    ap.add_argument("--out", help="write the facts here")
    a = ap.parse_args()

    with open(a.dtb, "rb") as f:
        blob = f.read()
    lines = facts(fdt_nodes(blob))
    made = "# gpu-facts.txt: the Xiaomi 12 (cupid) GPU, read out of its own device tree by tools/gpu-facts.py.\n"
    made += "# Do not edit by hand; change the tree and make it again.\n"
    made += "\n".join(lines) + "\n"

    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(made)
        print("gpu-facts.py: wrote %s (%d facts)" % (a.out, len(lines)))

    if a.check:
        with open(a.check, encoding="utf-8") as f:
            was = f.read()
        if was == made:
            print("gpu-facts.py: %s matches %s (%d facts)" % (a.check, a.dtb, len(lines)))
            return 0
        import difflib
        sys.stderr.write("".join(difflib.unified_diff(
            was.splitlines(True), made.splitlines(True), "was", "now")))
        sys.exit("gpu-facts.py: %s does not match %s; run tools/gpu-facts.py --dtb %s --out %s"
                 % (a.check, a.dtb, a.dtb, a.check))

    if not a.out:
        sys.stdout.write(made)
    return 0


if __name__ == "__main__":
    sys.exit(main())
