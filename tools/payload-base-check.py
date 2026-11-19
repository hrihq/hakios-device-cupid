#!/usr/bin/env python3
"""Check that every layer that carries the cupid XNUP payload base agrees.

The waipio payload base is a device fact: 0xF0000000 is inside the TZ apps
carve-out (0xEA000000-0xF1400000). Four independent places must carry the
same value, and a mismatch on any one of them silently produces a boot that
is accepted by ABL but never reaches the loader.

  python3 tools/payload-base-check.py
  python3 tools/payload-base-check.py --self-test
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPECT = 0xB0000000

PACKER = ROOT / "tools/mkxnuimg-cupid.py"
KERNEL_WF = ROOT / ".github/workflows/build-kernel.yml"
DSC = ROOT / "uefi/files/Platforms/Xiaomi/cupidPkg/cupid.dsc"
HEADER = ROOT / "uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h"
MEMMAP = ROOT / "uefi/files/Platforms/Xiaomi/cupidPkg/Library/MemoryMapLib/MemoryMapLib.c"


def read(p):
    return p.read_text(encoding="utf-8", errors="replace")


def hexval(s):
    # Values in the workflows and DSC carry a C-style ULL suffix.
    return int(re.sub(r'(?i)ull$', '', s), 16)


def from_packer(text):
    m = re.search(r"['\"]cupid['\"]\s*:\s*dict\([^)]*?payload_base=(0x[0-9a-fA-F]+)", text)
    return hexval(m.group(1)) if m else None


def from_kernel_wf(text):
    d = re.search(r'default:\s*"(0x[0-9A-Fa-f]+)ULL"', text)
    f = re.search(r"inputs\.payload_base\s*\|\|\s*'(0x[0-9A-Fa-f]+)ULL'", text)
    if not d or not f:
        return None
    return hexval(d.group(1)) if d.group(1).lower() == f.group(1).lower() else -1


def from_dsc(text):
    m = re.search(r'-DXNU_PAYLOAD_BASE=(0x[0-9A-Fa-f]+)ULL', text)
    return hexval(m.group(1)) if m else None


def from_header(text):
    # The header's 0xF0000000 default is safe only if a device can override it
    # from its DSC; the override value itself is checked in from_dsc().
    if re.search(r'#ifndef\s+XNU_PAYLOAD_BASE\s*[\r\n]+\s*#define\s+XNU_PAYLOAD_BASE', text):
        return EXPECT
    return None


def from_memmap(text):
    # The old 0xF0000000 reservation must be gone; the payload must sit inside a
    # region marked reserved so UEFI does not hand it to the OS as free memory.
    if re.search(r'\{\s*"XNU Payload"\s*,\s*0xF0000000', text, re.I):
        return None
    m = re.search(r'\{\s*"Kernel"\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)', text)
    if not m:
        return None
    base, size = hexval(m.group(1)), hexval(m.group(2))
    return EXPECT if base <= EXPECT < base + size else None


CHECKS = [
    ("mkxnuimg-cupid.py payload_base", PACKER, from_packer),
    ("build-kernel.yml default", KERNEL_WF, from_kernel_wf),
    ("cupid.dsc BuildOptions", DSC, from_dsc),
    ("XnuLoader.h is overridable", HEADER, from_header),
    ("MemoryMapLib Kernel region", MEMMAP, from_memmap),
]


def check():
    failures = []
    for label, path, parse in CHECKS:
        if not path.is_file():
            failures.append(f"{label}: missing {path.relative_to(ROOT)}")
            continue
        val = parse(read(path))
        if val is None:
            failures.append(f"{label}: value not found")
        elif val != EXPECT:
            failures.append(f"{label}: {val:#x}, expected {EXPECT:#x}")
        else:
            print(f"ok  {label}: {val:#x}")
    return failures


def selftest():
    good = '#ifndef XNU_PAYLOAD_BASE\n#define XNU_PAYLOAD_BASE 0xF0000000ULL\n#endif'
    bad = '#define XNU_PAYLOAD_BASE 0xF0000000ULL'
    assert from_header(good) == EXPECT
    assert from_header(bad) is None
    assert from_packer("'cupid': dict(fd_base=0xA7000000, payload_base=0xB0000000, header=4)") == EXPECT
    assert from_dsc('[BuildOptions]\n  *_*_*_CC_FLAGS = -DXNU_PAYLOAD_BASE=0xB0000000ULL') == EXPECT
    assert from_kernel_wf('payload_base:\n  default: "0xB0000000ULL"\nLOADER_CFLAGS="${{ inputs.payload_base || \'0xB0000000ULL\' }}"') == EXPECT
    assert from_memmap('{"Kernel", 0xA8000000, 0x10000000, AddMem, SYS_MEM}') == EXPECT
    assert from_memmap('{"XNU Payload", 0xF0000000, 0x04000000, AddMem, SYS_MEM}') is None
    print("self-test: ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        selftest()
        return 0
    failures = check()
    if failures:
        for f in failures:
            print("FAIL " + f, file=sys.stderr)
        return 1
    print("cupid payload base consistent:", hex(EXPECT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
