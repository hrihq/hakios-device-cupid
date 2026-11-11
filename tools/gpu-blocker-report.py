#!/usr/bin/env python3
"""Write the machine-readable blocker report for the Xiaomi 12 (cupid) Adreno 730 port.

The report is `docs/gpu-blockers.json`. It lists, with a status and a resolution, everything that
stops the port moving from the address layer to a working GPU. It is generated from
`gpu/a730_resources.json` (the uncertain values and the recorded disagreements) plus the
dependencies that no configuration can settle -- firmware, TrustZone, a physical phone.

Every entry says what would resolve it, so the list is a work list and not a complaint.

Usage:
  python3 tools/gpu-blocker-report.py --config gpu/a730_resources.json --out docs/gpu-blockers.json
  python3 tools/gpu-blocker-report.py --config ... --check docs/gpu-blockers.json   # CI
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Dependencies that are not facts about the hardware but things only the user or the phone can supply.
# Each is a blocker until it is resolved.
DEPENDENCY_BLOCKERS = [
    {
        "id": "firmware-gmu",
        "what": "the GMU's firmware image",
        "detail": "gmu_gen70000.bin, loaded into the GMU's TCM and its memory",
        "blocks": "phase 3 -- GMU initialization",
        "why": "the GMU will not start without it, and it is not in any repository",
        "resolution": "pull it from the phone's own /vendor/firmware; never commit it",
        "status": "unresolved",
    },
    {
        "id": "firmware-sqe",
        "what": "the 3D core's microcode",
        "detail": "a730_sqe.fw, loaded into the core's instruction ring",
        "blocks": "phase 4 -- the 3D core",
        "why": "the core has no instruction stream without it",
        "resolution": "pull it from the phone's own /vendor/firmware; never commit it",
        "status": "unresolved",
    },
    {
        "id": "firmware-zap",
        "what": "the zap shader image",
        "detail": "a730_zap, authenticated by TrustZone into 0x08b91a000 (the tree's "
                 "gpu_micro_code_region)",
        "blocks": "phase 4 -- the 3D core and secure mode",
        "why": "without a signed image the core stays in secure mode and nothing draws",
        "resolution": "pull it from the phone's own /vendor/firmware; never commit it",
        "status": "unresolved",
    },
    {
        "id": "trustzone",
        "what": "whether this kernel may call TrustZone, and whether the zap image is accepted",
        "detail": "the two calls the A6xx driver already makes, and the zap shader's signature check",
        "blocks": "phase 4 -- secure mode",
        "why": "a refusal here ends the GPU bring-up and no source can predict it",
        "resolution": "a run on the phone, with the zap image present",
        "status": "unresolved",
    },
    {
        "id": "smmu-acceptance",
        "what": "whether the SMMU accepts the streams and contexts the tree describes",
        "detail": "gfx3d_user 0, gfx3d_lpac 1, gfx3d_secure 2, the GMU on stream 5",
        "blocks": "phase 3 and 4",
        "why": "the stream ids are read from the tree; whether the hardware accepts them is not knowable "
               "from a source",
        "resolution": "a run on the phone",
        "status": "unresolved",
    },
    {
        "id": "power-stability",
        "what": "whether the GPU is stable at its top operating point",
        "detail": "12 levels, 220 MHz to 818 MHz, each with a bus and an ACD level",
        "blocks": "phase 6 -- performance",
        "why": "the levels are read from the tree; stability is a measurement",
        "resolution": "a run on the phone, at each level",
        "status": "unresolved",
    },
    {
        "id": "no-physical-device",
        "what": "a Xiaomi 12 (cupid) to run on",
        "detail": "every register write, every sequence, every performance number",
        "blocks": "phases 3 to 6",
        "why": "a wrong register ends the run, often silently, and no source can catch it",
        "resolution": "the user supplies a device and the firmware pulled from it",
        "status": "unresolved",
    },
    {
        "id": "uefi-vendor-drivers",
        "what": "the vendor UEFI drivers needed to link the UEFI firmware volume",
        "detail": "the phone's own xbl drivers, extracted and never committed",
        "blocks": "the UEFI build (a separate work stream from this one)",
        "why": "the FD cannot link without them",
        "resolution": "the user supplies them, or the workflow is run with VENDOR_BINARIES_URL",
        "status": "unresolved",
    },
]


def build(config):
    blockers = []

    for entry in config.get("uncertain", []):
        blockers.append({
            "id": "uncertain-" + entry["what"].lower().replace(" ", "-").replace("'", "")[:48],
            "what": entry["what"],
            "detail": "this tree: %s | Linux sm8450.dtsi: %s"
                      % (entry.get("this tree", ""), entry.get("Linux sm8450.dtsi", "")),
            "blocks": "phase 2 review -- it is a fact the port starts from",
            "why": entry.get("note", ""),
            "resolution": "a run on the phone, or a vendor kernel source that carries the value",
            "status": "unresolved",
        })

    for entry in config.get("disagreements", []):
        blockers.append({
            "id": "disagreement-" + entry["what"].lower().replace(" ", "-")[:48],
            "what": entry["what"],
            "detail": "this configuration says %s; the generated table says %s"
                      % (entry.get("this", entry.get("Linux a6xx.xml", "")), entry.get("generated table", "")),
            "blocks": "nothing -- it is recorded so a later reader does not have to rediscover it",
            "why": entry.get("note", ""),
            "resolution": "resolved: the configuration takes the value that fits the GPU block",
            "status": "resolved",
        })

    blockers.extend(DEPENDENCY_BLOCKERS)

    return {
        "device": config["device"],
        "soc": config["soc"],
        "title": config["title"],
        "generated_by": "tools/gpu-blocker-report.py",
        "source": "gpu/a730_resources.json",
        "tree": config["tree"],
        "summary": {
            "total": len(blockers),
            "unresolved": sum(1 for b in blockers if b["status"] == "unresolved"),
            "resolved": sum(1 for b in blockers if b["status"] == "resolved"),
        },
        "blockers": blockers,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=os.path.join(ROOT, "gpu/a730_resources.json"))
    parser.add_argument("--out", default=os.path.join(ROOT, "docs/gpu-blockers.json"))
    parser.add_argument("--check")
    args = parser.parse_args()

    config = json.load(open(args.config, encoding="utf-8"))
    report = build(config)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = open(args.check, encoding="utf-8").read()
        if current != text:
            print("gpu-blocker-report: %s does not match the configuration; regenerate it with --out"
                  % args.check)
            return 1
    else:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("gpu-blocker-report: wrote %s" % args.out)

    print("gpu-blocker-report: %d blocker(s), %d unresolved, %d resolved"
          % (report["summary"]["total"], report["summary"]["unresolved"], report["summary"]["resolved"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
