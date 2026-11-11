#!/usr/bin/env python3
"""Validate the cupid UEFI platform before a build.

usage: uefi/tools/validate.py --device <device repository> --mu <assembled Mu-Silicium tree>
                              [--require-vendor] [--json OUT]

What it checks, and why each is worth checking before a 20-minute build:

  platform   the platform package's files are there, and the DSC includes the SM8450's WaipioPkg
  dtb        the device tree is a flattened tree, says it is an SM8450, and the two copies match
  acpi       every table the ACPI .inf names is present in the Silicium-ACPI submodule
  memory     the FD base in Resources/Configs/cupid.toml is the address the memory map reserves for
             the UEFI FD, and the DSC's stack PCD falls inside the memory map's UEFI Stack
  vendor     which of the vendor DXEs the driver list names are present in Binaries/cupid/

The vendor check is a warning unless --require-vendor: the vendor's drivers are the phone's own and
are never in this repository, so a run without them cannot build the FD, but everything else can still
be validated.

Exits 1 if any check fails. Prints a report; with --json, writes it as JSON too.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys
import tomllib

FAIL = []
WARN = []
PASS = []


def check(ok, label, detail=""):
    (PASS if ok else FAIL).append((label, detail))
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", label, ("  -- " + detail) if detail else ""))
    return ok


def warn(label, detail=""):
    WARN.append((label, detail))
    print("  WARN %s%s" % (label, ("  -- " + detail) if detail else ""))


# ---------------------------------------------------------------- device tree

def fdt_nodes(blob):
    """The nodes of a flattened device tree, as {path: {property: bytes}}. Minimal, like tools/soc-args.py."""
    if blob[:4] != b"\xd0\x0d\xfe\xed":
        return None
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
        elif token == 3:                                   # FDT_PROP
            length, name_off = struct.unpack(">II", blob[at:at + 8])
            at += 8
            name = strings[name_off:strings.index(b"\0", name_off)].decode()
            out["/".join(path)][name] = blob[at:at + length]
            at = (at + length + 3) & ~3
        elif token == 9:                                   # FDT_END
            return out
        elif token != 4:
            return None


def u32(value, index=0):
    return struct.unpack_from(">I", value, index * 4)[0]


# ---------------------------------------------------------------- checks

def check_platform(device, mu):
    print("\nplatform")
    pkg = os.path.join(mu, "Platforms", "Xiaomi", "cupidPkg")
    for rel in ("cupid.dsc", "cupid.fdf", "cupid.dec", "DeviceBuild.py",
                "Include/APRIORI.inc", "Include/DXE.inc", "Include/RAW.inc",
                "Library/MemoryMapLib/MemoryMapLib.c", "Library/MemoryMapLib/MemoryMapLib.inf",
                "Library/ConfigurationMapLib/ConfigurationMapLib.c",
                "Library/ConfigurationMapLib/ConfigurationMapLib.inf"):
        check(os.path.isfile(os.path.join(pkg, rel)), "cupidPkg/%s" % rel)

    dsc = os.path.join(pkg, "cupid.dsc")
    if os.path.isfile(dsc):
        text = open(dsc, encoding="utf-8", errors="replace").read()
        inc = re.search(r"^\s*!include\s+(\S+)", text, re.M)
        check(inc is not None and inc.group(1) == "WaipioPkg/WaipioPkg.dsc.inc",
              "the DSC includes WaipioPkg/WaipioPkg.dsc.inc",
              inc.group(1) if inc else "no !include found")
        check(os.path.isfile(os.path.join(mu, "Silicon", "Qualcomm", "WaipioPkg", "WaipioPkg.dsc.inc")),
              "Silicon/Qualcomm/WaipioPkg/WaipioPkg.dsc.inc is in the tree")
        check(re.search(r"PLATFORM_NAME\s*=\s*cupid\b", text) is not None, "PLATFORM_NAME is cupid")
        fdf = re.search(r"FLASH_DEFINITION\s*=\s*(\S+)", text)
        check(fdf is not None and os.path.isfile(os.path.join(mu, "Platforms", "Xiaomi", fdf.group(1))),
              "FLASH_DEFINITION points at a file in the tree", fdf.group(1) if fdf else "none")
        smbios = re.search(r'PcdSmbiosSystemManufacturer\|"([^"]+)"', text)
        model = re.search(r'PcdSmbiosSystemModel\|"([^"]+)"', text)
        check(smbios is not None and smbios.group(1) == "Xiaomi", 'SMBIOS manufacturer is "Xiaomi"')
        check(model is not None and model.group(1) == "Xiaomi 12", 'SMBIOS model is "Xiaomi 12"')
        for name, want in (("PcdFrameBufferWidth", "1080"), ("PcdFrameBufferHeight", "2400")):
            got = re.search(r"%s\|(\d+)" % name, text)
            check(got is not None and got.group(1) == want, "%s is %s" % (name, want),
                  got.group(1) if got else "none")

    toml = os.path.join(mu, "Resources", "Configs", "cupid.toml")
    check(os.path.isfile(toml), "Resources/Configs/cupid.toml")
    fd = None
    if os.path.isfile(toml):
        try:
            with open(toml, "rb") as f:
                cfg = tomllib.load(f)
            fd = cfg.get("uefi_fd")
            check(isinstance(fd, dict) and fd.get("base") and fd.get("size"),
                  "cupid.toml has uefi_fd.base and uefi_fd.size",
                  "base=%s size=%s" % (fd.get("base"), fd.get("size")) if fd else "no uefi_fd")
            check("boot_shim" in cfg and "boot_image" in cfg,
                  "cupid.toml has the boot image sections build_uefi.py reads")
        except Exception as e:                              # noqa: BLE001
            check(False, "cupid.toml parses", str(e))
    return fd


def check_dtb(mu):
    print("\ndevice tree")
    res = os.path.join(mu, "Resources", "DTBs", "cupid.dtb")
    fdt = os.path.join(mu, "Platforms", "Xiaomi", "cupidPkg", "FdtBlob", "sm8450-xiaomi-cupid.dtb")
    check(os.path.isfile(res), "Resources/DTBs/cupid.dtb")
    check(os.path.isfile(fdt), "cupidPkg/FdtBlob/sm8450-xiaomi-cupid.dtb")
    if not (os.path.isfile(res) and os.path.isfile(fdt)):
        return
    a = open(res, "rb").read()
    b = open(fdt, "rb").read()
    check(hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest(),
          "the two copies of the device tree are the same")
    nodes = fdt_nodes(a)
    check(nodes is not None, "the device tree is a flattened tree")
    if nodes is None:
        return
    root = nodes.get("", {})
    model = root.get("model", b"").split(b"\0")[0].decode("utf-8", "replace")
    check("SM8450" in model.upper(), "the tree says it is an SM8450", model)
    msm = root.get("qcom,msm-id")
    check(msm is not None and any(u32(msm, i) == 457 for i in range(0, len(msm) // 4)),
          "the tree's qcom,msm-id names SoC 457 (SM8450)")
    compatible = root.get("compatible", b"").split(b"\0")[0].decode("utf-8", "replace")
    check("waipio" in compatible, "the tree is compatible with qcom,waipio", compatible)


def check_acpi(mu):
    print("\nACPI")
    inf = os.path.join(mu, "Silicium-ACPI", "Platforms", "Xiaomi", "cupid", "AcpiTables.inf")
    check(os.path.isfile(inf), "Silicium-ACPI/Platforms/Xiaomi/cupid/AcpiTables.inf")
    if not os.path.isfile(inf):
        return
    text = open(inf, encoding="utf-8", errors="replace").read()
    refs = re.findall(r"^\s*ASL\|(\S+)", text, re.M)
    check(bool(refs), "the ACPI .inf names at least one table")
    # An `ASL|` path is relative to an entry of DeviceBuild.py's PackagesPath, not to the .inf's own
    # directory: "Waipio/DSDT.aml" is Silicium-ACPI/Silicon/Qualcomm/Waipio/DSDT.aml, and a device's
    # own "DSDT.aml" is Silicium-ACPI/Platforms/<Vendor>/<device>/DSDT.aml.
    roots = [os.path.join(mu, "Silicium-ACPI"),
             os.path.join(mu, "Silicium-ACPI", "Silicon", "Qualcomm"),
             os.path.join(mu, "Silicium-ACPI", "Platforms", "Xiaomi"),
             mu]
    missing = [r for r in refs if not any(os.path.isfile(os.path.join(root, r)) for root in roots)]
    check(not missing, "every ACPI table it names is in the tree",
          "missing: %s" % ", ".join(missing) if missing else "%d tables" % len(refs))


def check_memory(mu, fd):
    print("\nmemory map")
    src = os.path.join(mu, "Platforms", "Xiaomi", "cupidPkg", "Library", "MemoryMapLib", "MemoryMapLib.c")
    dsc = os.path.join(mu, "Platforms", "Xiaomi", "cupidPkg", "cupid.dsc")
    if not (os.path.isfile(src) and os.path.isfile(dsc)):
        check(False, "the memory map and the DSC are both there")
        return
    text = open(src, encoding="utf-8", errors="replace").read()
    regions = re.findall(r'\{"([^"]+)",\s*(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+),', text)
    check(bool(regions), "the memory map has regions", "%d regions" % len(regions))
    by_name = {name: (int(addr, 16), int(size, 16)) for name, addr, size in regions}
    if fd and "UEFI FD" in by_name:
        check(by_name["UEFI FD"][0] == fd["base"],
              "the memory map's UEFI FD is at the toml's uefi_fd.base",
              "map=%#x toml=%#x" % (by_name["UEFI FD"][0], fd["base"]))
    else:
        check(False, "the memory map has a UEFI FD region")
    stack = re.search(r"PcdCPUCoresStackBase\|(0x[0-9a-fA-F]+)",
                      open(dsc, encoding="utf-8", errors="replace").read())
    if stack and "UEFI Stack" in by_name:
        base = int(stack.group(1), 16)
        start, size = by_name["UEFI Stack"]
        check(start <= base < start + size, "the DSC's stack PCD is inside the memory map's UEFI Stack",
              "%#x in [%#x, %#x)" % (base, start, start + size))
    else:
        check(False, "the DSC's stack PCD and the memory map's UEFI Stack are both there")


def check_vendor(mu):
    print("\nvendor drivers")
    dxe = os.path.join(mu, "Platforms", "Xiaomi", "cupidPkg", "Include", "DXE.inc")
    ap = os.path.join(mu, "Platforms", "Xiaomi", "cupidPkg", "Include", "APRIORI.inc")
    refs = []
    for f in (dxe, ap):
        if os.path.isfile(f):
            refs += re.findall(r"INF\s+Binaries/cupid/(\S+\.inf)", open(f, encoding="utf-8", errors="replace").read())
    refs = sorted(set(refs))
    check(bool(refs), "the driver list names vendor DXEs", "%d of them" % len(refs))
    present = [r for r in refs if os.path.isfile(os.path.join(mu, "Binaries", "cupid", r))]
    missing = [r for r in refs if r not in present]
    if missing:
        warn("Binaries/cupid/ is missing %d of %d vendor DXEs the driver list names"
             % (len(missing), len(refs)),
             "the FD cannot be built without them; they come from the phone's own xbl")
    else:
        check(True, "every vendor DXE the driver list names is present", "%d of them" % len(refs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True, help="the device repository (its uefi/files/ is the platform)")
    ap.add_argument("--mu", required=True, help="the assembled Mu-Silicium tree")
    ap.add_argument("--require-vendor", action="store_true",
                    help="fail when the vendor's UEFI drivers are absent")
    ap.add_argument("--json", help="write the report as JSON here as well")
    a = ap.parse_args()

    print("validating the cupid UEFI platform")
    print("  device repository: %s" % a.device)
    print("  Mu-Silicium tree:  %s" % a.mu)

    platform_dir = os.path.join(a.device, "uefi", "files")
    check(os.path.isdir(platform_dir), "the device repository carries uefi/files/",
          platform_dir if not os.path.isdir(platform_dir) else "")

    fd = check_platform(a.device, a.mu)
    check_dtb(a.mu)
    check_acpi(a.mu)
    check_memory(a.mu, fd)
    check_vendor(a.mu)

    if a.require_vendor and WARN:
        for label, detail in WARN:
            FAIL.append((label, detail))

    print("\n%d passed, %d failed, %d warnings" % (len(PASS), len(FAIL), len(WARN)))
    if FAIL:
        print("\nFAILED:")
        for label, detail in FAIL:
            print("  - %s%s" % (label, ("  -- " + detail) if detail else ""))
        print("\nThe platform is not ready to build. Fix the above, then run again.")
    else:
        print("\nThe platform's own configuration holds together. This says nothing about booting on a phone:")
        print("a build that succeeds is not a boot that works.")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"pass": [x[0] for x in PASS], "fail": FAIL, "warn": WARN}, f, indent=2)
        print("report: %s" % a.json)

    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
