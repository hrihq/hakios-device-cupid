#!/usr/bin/env python3
"""Write devices/cupid/soc.args from the phone's own device tree.

The common repository's tools/soc-args.py reads a phone's device tree and prints the soc_* boot-args
the modem and IPA drivers take. It matches the reserved-memory nodes by the first phone's names
(`cmd_db`, `mpss`, `ipa_gsi`); this phone names them `aop_cmd_db_region`, `mpss_region` and
`ipa_gsi_region`, so three of the values are not found and the file is short.

This does the same job for this phone: it reads the tree, takes the values the common tool finds, and
adds the ones whose node names differ here. It also reports the one value the tree does not carry at
all, so the gap is said rather than silently kept.

Usage:
  python3 tools/soc-args-cupid.py --dtb uefi/files/Resources/DTBs/cupid.dtb --out soc.args
  python3 tools/soc-args-cupid.py --dtb uefi/files/Resources/DTBs/cupid.dtb --check soc.args
"""

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _facts():
    spec = importlib.util.spec_from_file_location("gpu_facts", os.path.join(HERE, "gpu-facts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FACTS = _facts()

# The values the common tool cannot find here, and where this phone keeps them.
CUPID_NODES = (
    ("soc_cmd_db", "aop_cmd_db_region", "the command DB"),
    ("soc_mpss_mem", "mpss_region", "the modem's memory"),
    ("modem_ipa_fw_at", "ipa_gsi_region", "where the IPA's firmware is loaded"),
)

# Read by the driver, carried by the first phone's tree, and absent from this one.
NOT_IN_TREE = (
    ("soc_pas_mpss", "the modem's PAS id (qcom,pas-id); the driver's built-in value is the first "
                     "phone's 4", "the vendor kernel's modem configuration"),
)


def build(nodes):
    args = {}

    def put(name, value, source):
        if value is None:
            return
        args[name] = (value, source)

    # the register blocks, read the same way the common tool reads them
    def reg(node, index=0):
        pairs = FACTS.reg_pairs(nodes, node)
        return pairs[index][0] if pairs and index < len(pairs) else None

    ipa = "/soc/qcom,ipa@3e00000"
    put("soc_ipa_base", (reg(ipa) or 0) + 0x40000 if reg(ipa) else None, ipa + " + 0x40000")
    put("soc_gsi_base", reg(ipa, 1), ipa + " (second range)")
    for node, name, index in (
        ("/soc/qcom,ipcc@ed18000", "soc_ipcc", 0),
        ("/soc/rsc@17a00000", "soc_rsc", 2),
        ("/soc/apps-smmu@15000000", "soc_apps_smmu", 0),
        ("/soc/qcom,msm-imem@146aa000", "soc_imem", 0),
    ):
        value = reg(node, index)
        if name == "soc_imem" and value is not None:
            value &= ~0x1FFFFF  # the 2 MB block that holds it, as the IPA's table maps
        put(name, value, node + ((" (drv-%d)" % index) if index else ""))

    # the AOSS mailbox: the qcom,*_aoss-qmp node, or the qcom,qmp-aop node
    for node, props in nodes.items():
        if b"qcom," in props.get("compatible", b"") and b"-aoss-qmp" in props.get("compatible", b""):
            put("soc_aoss", reg(node), node)
            break
    else:
        for node, props in nodes.items():
            if props.get("compatible", b"").startswith(b"qcom,qmp-aop"):
                put("soc_aoss", reg(node), node)
                break

    # shared memory: the reserved-memory the /soc/qcom,smem node points at
    by_phandle = {}
    for path, props in nodes.items():
        if "phandle" in props:
            by_phandle[FACTS.cells(props["phandle"])[0]] = path
    smem = nodes.get("/soc/qcom,smem")
    if smem and "memory-region" in smem:
        target = by_phandle.get(FACTS.cells(smem["memory-region"])[0])
        if target:
            put("soc_smem", reg(target), target)

    # the IPA's stream ids, from the iommus of the IPA's SMMU contexts
    for compatible, name in (("qcom,ipa-smmu-ap-cb", "soc_ipa_stream"),
                             ("qcom,ipa-smmu-uc-cb", "soc_ipa_stream_uc")):
        for path, props in nodes.items():
            if props.get("compatible", b"").split(b"\0")[0].decode() == compatible:
                if "iommus" in props and len(props["iommus"]) >= 8:
                    put(name, FACTS.cells(props["iommus"])[1], path + " (iommus)")
                break

    # the IPA's PAS id and firmware name
    ipa_fws = nodes.get("/soc/qcom,ipa_fws")
    if ipa_fws:
        if "qcom,pas-id" in ipa_fws:
            put("soc_pas_ipa", FACTS.cells(ipa_fws["qcom,pas-id"])[0], "/soc/qcom,ipa_fws (qcom,pas-id)")
        if "qcom,firmware-name" in ipa_fws:
            name = ipa_fws["qcom,firmware-name"].split(b"\0")[0].decode()
            args["soc_ipa_fw"] = (name, "/soc/qcom,ipa_fws (qcom,firmware-name)")

    # the values the common tool cannot find here
    for name, leaf, role in CUPID_NODES:
        for path, props in nodes.items():
            if path.rsplit("/", 1)[-1].split("@", 1)[0] == leaf:
                put(name, reg(path), "%s (%s)" % (path, role))
                break

    return args


def render(args):
    lines = ["# soc.args: the modem and IPA SoC addresses of the Xiaomi 12 (cupid), from its own device tree.",
             "# Generated by tools/soc-args-cupid.py; do not edit by hand. The common repository's tools/soc-args.py",
             "# finds most of these but matches the reserved-memory nodes by the first phone's names, so it misses",
             "# aop_cmd_db_region, mpss_region and ipa_gsi_region here.",
             "#"]
    for name in sorted(args):
        value = args[name][0]
        lines.append("%s=%s" % (name, value if isinstance(value, str) else "%#x" % value))
    lines.append("#")
    lines.append("# where each value came from:")
    for name in sorted(args):
        lines.append("#   %-18s %s" % (name, args[name][1]))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dtb", default="uefi/files/Resources/DTBs/cupid.dtb")
    parser.add_argument("--out", default="soc.args")
    parser.add_argument("--check")
    args = parser.parse_args()

    nodes = FACTS.fdt_nodes(open(args.dtb, "rb").read())
    built = build(nodes)
    text = render(built)
    if args.check:
        current = open(args.check, encoding="utf-8").read()
        if current != text:
            print("soc-args-cupid: %s does not match %s; regenerate it with --out" % (args.check, args.dtb))
            return 1
        print("soc-args-cupid: %s matches %s" % (args.check, os.path.basename(args.dtb)))
        return 0
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    for name, detail, resolution in NOT_IN_TREE:
        print("soc-args-cupid: %s is not in the tree -- %s; it needs %s"
              % (name, detail, resolution))
    print("soc-args-cupid: wrote %s (%d value(s))" % (args.out, len(built)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
