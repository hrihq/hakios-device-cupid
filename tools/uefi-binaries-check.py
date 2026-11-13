#!/usr/bin/env python3
"""List and check the vendor UEFI binaries a platform needs.

Mu-Silicium uses Qualcomm's own DXE drivers -- ClockDxe, UFSDxe, SPMI, TLMM, USB, the TrustZone
drivers and the rest. They are proprietary and are not in any repository: they come from the phone's
own `uefi.img`. A platform's .inc and .fdf files name them as `INF Binaries/<board>/<path>/<Driver>.inf`.

This tool does two things:

  --reference DIR   scan a platform's .inc/.fdf files and print the vendor INF list as JSON
  --check DIR       check a Binaries/<board> tree against a manifest and report what is missing

It does not extract anything. The extraction tool is tools/uefi-fv-unpack.py.

Usage:
  python3 tools/uefi-binaries-check.py --reference <platform dir> --board negroni
  python3 tools/uefi-binaries-check.py --manifest uefi/firmware/vendor-binaries.json \
      --check uefi/files/Binaries/cupid
"""

import argparse
import json
import os
import re
import sys
import tempfile

# Roles, from what the driver names say and from the reference platform's own documentation. This is a
# reading of the names, not a claim about what each driver does.
ROLES = {
    "ClockDxe": "clocks and PLLs",
    "PmicDxe": "the PMIC",
    "SPMIDxe": "the SPMI bus (PMIC, haptics, regulators)",
    "TLMMDxe": "the GPIO/pin-mux controller",
    "I2CDxe": "I2C controllers",
    "UFSDxe": "UFS storage",
    "CmdDbDxe": "the bus command database",
    "RpmhDxe": "RPMh power resources",
    "PwrUtilsDxe": "power helpers",
    "NpaDxe": "the NPA resource graph",
    "VcsDxe": "voltage scaling",
    "TsensDxe": "the thermal sensors",
    "DDRInfoDxe": "DDR information",
    "SmemDxe": "shared-memory transport",
    "GLinkDxe": "the GLINK inter-processor link",
    "IPCCDxe": "inter-processor communication",
    "ShmBridgeDxe": "the shared-memory bridge",
    "TzDxeLA": "TrustZone",
    "ScmDxeLA": "the secure-channel manager (TrustZone calls)",
    "ICBDxe": "interconnect bus",
    "GpiDxe": "the GPI DMA engine",
    "SPIDxe": "SPI controllers",
    "SdcDxe": "SD card (present on some boards)",
    "SdccDxe": "SD card (present on some boards)",
    "XhciDxe": "USB 3 xHCI",
    "XhciPciEmulationDxe": "PCI emulation for xHCI",
    "UsbfnDwc3Dxe": "the USB device controller",
    "UsbConfigDxe": "USB configuration",
    "UsbDeviceDxe": "USB device support",
    "UsbInitDxe": "USB initialisation",
    "UsbMsdDxe": "USB mass storage",
    "UsbPwrCtrlDxe": "USB power control",
    "UCDxe": "the USB composite driver",
    "RNGDxe": "the random number generator",
    "PILDxe": "the peripheral image loader",
    "PILProxyDxe": "the PIL proxy",
    "SPSSDxe": "SPSS",
    "ULogDxe": "the micro-logger",
    "DALSYSDxe": "the device-access layer",
    "HALIOMMUDxe": "the IOMMU HAL",
    "HWIODxe": "the hardware IO layer",
    "ChipInfoDxe": "the chip identification",
    "PlatformInfoDxe": "platform information",
    "EnvDxe": "the UEFI environment",
    "DisplayDxe": "the display driver",
    "CPRDxe": "the display colour pipeline",
    "DiskIoDxe": "disk IO",
    "PartitionDxe": "partition tables",
}

INF_REFERENCE = re.compile(r"^\s*INF\s+(Binaries/[^/\s]+/\S+\.inf)\s*$", re.MULTILINE)


def scan_reference(platform_dir, board):
    """Every vendor INF a platform's .inc/.fdf files name. This is the only source; nothing is copied
    from another board."""
    references = set()
    for root, _, files in os.walk(platform_dir):
        for name in files:
            if not name.endswith((".inc", ".fdf", ".dsc")):
                continue
            text = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
            for match in INF_REFERENCE.finditer(text):
                path = match.group(1)
                if path.split("/")[1] == board:
                    references.add(path)
    return sorted(references)


def role_of(inf_path):
    name = os.path.basename(inf_path)[:-4]
    return ROLES.get(name, "role not recorded")


def build_manifest(references, board, source):
    return {
        "board": board,
        "source": source,
        "description": "The vendor DXE drivers a platform names. These binaries are proprietary and are "
                       "not in any repository; they come from the phone's own uefi.img. The list is "
                       "read out of the platform's own .inc/.fdf files, never copied from another "
                       "board.",
        "files": [{"path": path, "role": role_of(path)} for path in references],
    }


def check(manifest_path, binaries_dir):
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    board = manifest["board"]
    missing = []
    present = []
    for entry in manifest["files"]:
        path = entry["path"]
        # the manifest is stored relative to Binaries/<board>
        relative = "/".join(path.split("/")[2:])
        full = os.path.join(binaries_dir, relative)
        if os.path.exists(full):
            present.append(path)
        else:
            missing.append((path, entry["role"]))
    print("uefi-binaries-check: %s, %d driver(s) referenced" % (board, len(manifest["files"])))
    print("  source: %s" % manifest["source"])
    for path in present:
        print("  present  %s" % path)
    for path, role in missing:
        print("  MISSING  %-60s %s" % (path, role))
    if missing:
        print("uefi-binaries-check: %d of %d missing. These are proprietary: pull them from the "
              "phone's uefi.img with tools/uefi-fv-unpack.py." % (len(missing), len(manifest["files"])))
        return 1
    print("uefi-binaries-check: all %d present" % len(present))
    return 0


def self_test(manifest_path):
    """The checker must accept a complete tree and reject one with a file missing."""
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for entry in manifest["files"]:
            relative = "/".join(entry["path"].split("/")[2:])
            full = os.path.join(tmp, relative)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w", encoding="utf-8").write("# fixture\n")
        if check(manifest_path, tmp) != 0:
            failures += 1
            print("FAIL a complete tree passes")
        else:
            print("ok   a complete tree passes")

        first = manifest["files"][0]["path"]
        os.remove(os.path.join(tmp, "/".join(first.split("/")[2:])))
        if check(manifest_path, tmp) == 0:
            failures += 1
            print("FAIL a tree with a missing file fails")
        else:
            print("ok   a tree with a missing file fails")
    print("uefi-binaries-check: self-test %d failure(s)" % failures)
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", help="a platform directory to scan")
    parser.add_argument("--board", help="the board name used in Binaries/<board>/")
    parser.add_argument("--source", help="where the reference came from, recorded in the manifest")
    parser.add_argument("--manifest")
    parser.add_argument("--check", help="a Binaries/<board> directory to check")
    parser.add_argument("--out", help="where to write the manifest from --reference")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        if not args.manifest:
            parser.error("--manifest is required with --self-test")
        return self_test(args.manifest)

    if args.reference:
        if not args.board:
            parser.error("--board is required with --reference")
        references = scan_reference(args.reference, args.board)
        manifest = build_manifest(references, args.board,
                                  args.source or "scanned from %s" % args.reference)
        text = json.dumps(manifest, indent=2) + "\n"
        if args.out:
            open(args.out, "w", encoding="utf-8", newline="\n").write(text)
            print("uefi-binaries-check: wrote %s (%d drivers)" % (args.out, len(references)))
        else:
            print(text)
        return 0

    if args.check:
        if not args.manifest:
            parser.error("--manifest is required with --check")
        return check(args.manifest, args.check)

    parser.error("either --reference or --check is required")


if __name__ == "__main__":
    sys.exit(main())
