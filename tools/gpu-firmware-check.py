#!/usr/bin/env python3
"""Check the Xiaomi 12 (cupid) Adreno 730's firmware images against gpu/firmware/manifest.json.

The manifest says what each image is for and what format the public sources describe. This tool
checks what a public source can check: that the file is there, that it is not empty, that its size is
plausible, and that its structure matches the format a public source documents.

It does NOT check whether the firmware works. Nothing here has been loaded, and no claim is made that
the GMU will start, that TrustZone will accept the zap shader, or that the 3D core will leave secure
mode. The report says so.

Usage:
  python3 tools/gpu-firmware-check.py --dir <path with the three images>
  python3 tools/gpu-firmware-check.py --manifest gpu/firmware/manifest.json --dir <path>
  python3 tools/gpu-firmware-check.py --self-test
"""

import argparse
import json
import os
import struct
import sys
import tempfile

# Linux's a6xx_gmu_fw_load() windows. A block outside both is reported, not failed: the GMU's own
# buffer objects (icache, dcache, dummy) are matched separately and their layout is not public.
GMU_ITCM_BASE = 0x00000000
GMU_ITCM_SIZE = 0x00004000
GMU_DTCM_BASE = 0x10004000
GMU_DTCM_SIZE = 0x00004000
GMU_BLOCK_MAGIC = 0xEFBEADDE   # the bytes de ad be ef, read as a little-endian dword

# The zap shader's reserved memory, from the phone's own device tree.
ZAP_REGION_PHYS = 0x08B91A000
ZAP_REGION_SIZE = 0x00002000

# Linux's mdt_loader.c: QCOM_MDT_TYPE_MASK / QCOM_MDT_TYPE_HASH
QCOM_MDT_TYPE_MASK = 7 << 24
QCOM_MDT_TYPE_HASH = 3 << 24
PT_LOAD = 1

ELF_MAGIC = b"\x7fELF"
ELFCLASS32 = 1
ELFDATA2LSB = 1
ELF32_EHSIZE = 52
ELF32_PHENTSIZE = 32
ELF32_PHNUM_OFFSET = 44   # e_phnum sits at offset 0x2c
SZ_4K = 4096


def align(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


# -------------------------------------------------------------------------------------------
# Format checks, each modelled on a public source
# -------------------------------------------------------------------------------------------

def check_gmu(data):
    """Linux a6xx_gmu.c: struct block_header { u32 addr, size, type, value; u32 data[]; }.

    The table must consume the file exactly. Entries with size == 0 carry a length in value and are
    skipped by Linux; entries with data are written to ITCM, DTCM or a GMU buffer.
    """
    notes = []
    offset = 0
    blocks = []
    while offset < len(data):
        if offset + 16 > len(data):
            return False, ["a block header at offset 0x%x is truncated" % offset], blocks
        addr, size, kind, value = struct.unpack_from("<IIII", data, offset)
        if offset + 16 + size > len(data):
            return False, ["the block at offset 0x%x claims %d bytes of data but only %d remain"
                           % (offset, size, len(data) - offset - 16)], blocks
        blocks.append((addr, size, kind, value))
        offset += 16 + size
    if offset != len(data):
        return False, ["the table ends at 0x%x but the file is %d bytes" % (offset, len(data))], blocks

    data_blocks = [b for b in blocks if b[1] > 0]
    if not data_blocks:
        return False, ["the table carries no data blocks"], blocks

    for addr, size, _, _ in data_blocks:
        in_itcm = GMU_ITCM_BASE <= addr < GMU_ITCM_BASE + GMU_ITCM_SIZE
        in_dtcm = GMU_DTCM_BASE <= addr < GMU_DTCM_BASE + GMU_DTCM_SIZE
        if not (in_itcm or in_dtcm):
            notes.append("a data block at 0x%08x (%d bytes) is outside Linux's ITCM and DTCM "
                         "windows; it would have to go to a GMU buffer, whose layout is not public"
                         % (addr, size))

    descriptors = [b for b in blocks if b[1] == 0]
    notes.append("%d descriptor entries, %d data blocks, table consumes the file exactly"
                 % (len(descriptors), len(data_blocks)))
    return True, notes, blocks


def check_zap(data):
    """Linux mdt_loader.c: the image is a 32-bit little-endian ELF; the loadable, non-hash segments
    must fit the reserved region."""
    notes = []
    if len(data) < ELF32_EHSIZE:
        return False, ["the file is smaller than an ELF32 header"], None
    if data[:4] != ELF_MAGIC:
        return False, ["no ELF magic; the zap shader must be a Qualcomm MDT"], None
    if data[4] != ELFCLASS32 or data[5] != ELFDATA2LSB:
        return False, ["not a 32-bit little-endian ELF"], None

    (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags,
     e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum,
     e_shstrndx) = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)

    if e_phentsize != ELF32_PHENTSIZE:
        return False, ["e_phentsize is %d, mdt_loader requires %d" % (e_phentsize, ELF32_PHENTSIZE)], None
    if e_phoff + e_phentsize * e_phnum > len(data):
        return False, ["the program header table does not fit in the file"], None

    segments = []
    min_addr = None
    max_addr = 0
    for i in range(e_phnum):
        (p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz,
         p_flags, p_align) = struct.unpack_from("<IIIIIIII", data, e_phoff + i * e_phentsize)
        segments.append((p_type, p_offset, p_paddr, p_filesz, p_memsz, p_flags))
        loadable = (p_type == PT_LOAD
                    and (p_flags & QCOM_MDT_TYPE_MASK) != QCOM_MDT_TYPE_HASH
                    and p_memsz != 0)
        if not loadable:
            continue
        if min_addr is None or p_paddr < min_addr:
            min_addr = p_paddr
        end = align(p_paddr + p_memsz, SZ_4K)
        if end > max_addr:
            max_addr = end

    if min_addr is None:
        return False, ["no loadable segment"], None

    span = max_addr - min_addr
    notes.append("ELF32 machine 0x%04x, %d program headers, %d loadable, span 0x%x bytes at 0x%x"
                 % (e_machine, e_phnum, sum(1 for s in segments if s[0] == PT_LOAD), span, min_addr))
    if span > ZAP_REGION_SIZE:
        return False, ["the loadable span 0x%x exceeds the reserved region 0x%x"
                       % (span, ZAP_REGION_SIZE)], segments
    notes.append("fits the reserved region at 0x%x (0x%x bytes)" % (ZAP_REGION_PHYS, ZAP_REGION_SIZE))
    return True, notes, segments


def check_sqe(data):
    """No public source documents this image. Only word alignment and non-emptiness are checked, and
    what is seen is reported without being interpreted."""
    notes = []
    if len(data) % 4 != 0:
        return False, ["the size %d is not a multiple of 4" % len(data)], None
    words = struct.unpack("<%dI" % (len(data) // 4), data)
    magic = [i for i, w in enumerate(words) if w == 0xFBADC0DE]
    notes.append("%d words; the word 0xfbadc0de appears at offset(s) %s"
                 % (len(words), ", ".join("0x%x" % (i * 4) for i in magic) if magic else "none"))
    tail = data[-16:]
    printable = sum(1 for byte in tail if 0x20 <= byte < 0x7F)
    notes.append("the last 16 bytes are %d%% printable ASCII (not interpreted)" % (printable * 100 // 16))
    notes.append("no public source documents this format; nothing here is a structural claim")
    return True, notes, None


CHECKS = {
    "gmu_gen70000.bin": check_gmu,
    "a730_sqe.fw": check_sqe,
    "a730_zap.mbn": check_zap,
}


# -------------------------------------------------------------------------------------------
# Directory check
# -------------------------------------------------------------------------------------------

def check_directory(manifest_path, directory):
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    failures = 0
    print("gpu-firmware-check: %s (%s, %s)" % (manifest["title"], manifest["device"], manifest["soc"]))
    print("  source of the sizes: %s" % manifest["source"])
    for entry in manifest["files"]:
        name = entry["name"]
        path = os.path.join(directory, name)
        print("  %-18s %s" % (name, entry["role"]))
        if not os.path.exists(path):
            print("      MISSING  -- expected a file of %d bytes (accepted %d..%d)"
                  % (entry["size_bytes"], entry["size_min"], entry["size_max"]))
            failures += 1
            continue
        data = open(path, "rb").read()
        if len(data) < entry["size_min"] or len(data) > entry["size_max"]:
            print("      SIZE     -- %d bytes, outside the accepted range %d..%d"
                  % (len(data), entry["size_min"], entry["size_max"]))
            failures += 1
            continue
        check = CHECKS.get(name)
        if check is None:
            print("      NO CHECK -- no public source describes this format")
            continue
        ok, notes, _ = check(data)
        for note in notes:
            print("      %s" % note)
        if ok:
            print("      OK       -- %d bytes" % len(data))
        else:
            print("      INVALID  -- %s" % "; ".join(notes))
            failures += 1
    print("  unverified, by design:")
    for item in manifest["unverified"]:
        print("      - %s" % item)
    if failures:
        print("gpu-firmware-check: %d file(s) missing or invalid" % failures)
        return 1
    print("gpu-firmware-check: all %d file(s) present and structurally valid. "
          "This says nothing about whether they work." % len(manifest["files"]))
    return 0


# -------------------------------------------------------------------------------------------
# Self-test: the tool must accept a valid fixture and reject a broken one
# -------------------------------------------------------------------------------------------

def build_gmu_block(addr, size, kind, value, data=b""):
    return struct.pack("<IIII", addr, size, kind, value) + data


def build_zap(span, paddr=0x1000):
    """A minimal ELF32 with one PT_LOAD covering `span` bytes at `paddr`."""
    ehsize = ELF32_EHSIZE
    phoff = ehsize
    data = b"\x00" * 0x100
    ehdr = (b"\x7fELF" + bytes([ELFCLASS32, ELFDATA2LSB, 1]) + b"\x00" * 9
            + struct.pack("<HHIIIIIHHHHHH", 2, 164, 1, paddr, phoff, 0, 0,
                          ehsize, ELF32_PHENTSIZE, 1, 0, 0, 0))
    phdr = struct.pack("<IIIIIIII", PT_LOAD, 0x100, paddr, paddr, span, span, 7, SZ_4K)
    return ehdr + phdr + data


def self_test():
    failures = 0

    def expect(name, condition):
        nonlocal failures
        if condition:
            print("ok   %s" % name)
        else:
            failures += 1
            print("FAIL %s" % name)

    with tempfile.TemporaryDirectory() as tmp:
        # a valid GMU table: one descriptor, one data block, exact fit
        valid = build_gmu_block(0x0, 0, 1, 4) + build_gmu_block(0x0, 4, GMU_BLOCK_MAGIC, GMU_BLOCK_MAGIC, b"abcd")
        ok, notes, _ = check_gmu(valid)
        expect("a well-formed GMU table passes", ok)

        # a truncated GMU table must fail
        ok, notes, _ = check_gmu(valid[:-1])
        expect("a truncated GMU table fails", not ok)

        # a GMU table whose data block lies outside ITCM and DTCM is reported, not failed
        outside = build_gmu_block(0x4000, 4, GMU_BLOCK_MAGIC, GMU_BLOCK_MAGIC, b"abcd")
        ok, notes, _ = check_gmu(outside)
        expect("a data block outside ITCM/DTCM is reported", ok and any("outside" in n for n in notes))

        # a valid zap image passes and its span is computed the way mdt_loader computes it
        ok, notes, _ = check_zap(build_zap(0x8bc))
        expect("a well-formed zap image passes", ok)

        # a zap image whose span exceeds the reserved region must fail
        ok, notes, _ = check_zap(build_zap(0x3000))
        expect("an oversized zap image fails", not ok)

        # a file without the ELF magic must fail
        ok, notes, _ = check_zap(b"not an elf" * 8)
        expect("a zap image without ELF magic fails", not ok)

        # the SQE image: word-aligned and non-empty passes, a ragged size fails
        ok, notes, _ = check_sqe(b"\x00" * 64)
        expect("a word-aligned SQE image passes", ok)
        ok, notes, _ = check_sqe(b"\x00" * 63)
        expect("a ragged SQE image fails", not ok)

        # end to end: a directory with all three valid fixtures passes, and a missing one fails
        # The fixtures are padded to the manifest's accepted size range, because the range check is
        # part of what the directory check does.
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "gpu", "firmware", "manifest.json")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        padded_gmu = (build_gmu_block(0x0, 0, 1, 4096)
                      + build_gmu_block(0x0, 4096, GMU_BLOCK_MAGIC, GMU_BLOCK_MAGIC, b"a" * 4096))
        fixtures = {"gmu_gen70000.bin": padded_gmu,
                    "a730_sqe.fw": b"\x00" * 4096,
                    # padded to the manifest's minimum: the size range is part of the check
                    "a730_zap.mbn": build_zap(0x800) + b"\x00" * 1800}
        for entry in manifest["files"]:
            open(os.path.join(tmp, entry["name"]), "wb").write(fixtures[entry["name"]])
        if check_directory(manifest_path, tmp) != 0:
            failures += 1
            print("FAIL a directory of valid fixtures passes")
        else:
            print("ok   a directory of valid fixtures passes")

        os.remove(os.path.join(tmp, "a730_sqe.fw"))
        if check_directory(manifest_path, tmp) == 0:
            failures += 1
            print("FAIL a directory with a missing file fails")
        else:
            print("ok   a directory with a missing file fails")

    print("gpu-firmware-check: self-test %d failure(s)" % failures)
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "gpu", "firmware", "manifest.json"))
    parser.add_argument("--dir", help="a directory holding the firmware images")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.dir:
        parser.error("--dir is required unless --self-test is given")
    return check_directory(args.manifest, args.dir)


if __name__ == "__main__":
    sys.exit(main())
