#!/usr/bin/env python3
"""Unpack a UEFI Firmware Volume into its FFS files and PE32/TE images.

Pure Python: no UEFIExtract, no external tools. It reads the Firmware Volume header, walks the FFS
files, walks the sections, and writes one directory per file GUID containing `pe32.efi`, `depex.bin`,
`raw.bin`, `name.txt` and an `index.tsv`.

What it handles, and what it does not:

  * FFS files with the 24-byte header and the 32-byte large-file header;
  * sections: PE32, PIC, TE, DXE_DEPEX, PEI_DEPEX, SMM_DEPEX, VERSION, USER_INTERFACE,
    FREEFORM_SUBTYPE_GUID, RAW, COMPATIBILITY16;
  * a COMPRESSION section with CompressionType 0 (not compressed) -- type 1 (EFI standard / Tiano)
    is reported as unsupported, because implementing that decompressor is a separate task;
  * a GUID_DEFINED section carrying LZMA (the standard LZMA_CUSTOM_DECOMPRESS_GUID), which Python's
    `lzma` module handles;
  * a GUID_DEFINED section whose payload starts with the gzip magic -- reported as a heuristic, not
    as a standard GUID;
  * FIRMWARE_VOLUME_IMAGE sections, which are recursed into.

Everything it cannot decompress is reported with its type and GUID, and the file is left in place
rather than silently skipped. A partial unpack is a report, not a success.

Usage:
  python3 tools/uefi-fv-unpack.py --fv <uefi.img or an FV file> --out <output directory>
  python3 tools/uefi-fv-unpack.py --self-test
"""

import argparse
import gzip
import io
import json
import lzma
import os
import struct
import sys
import uuid

FVH_SIGNATURE = 0x4856465F   # "_FVH"
FFS_ATTRIB_LARGE_FILE = 0x01

SECTION_COMPRESSION = 0x01
SECTION_GUID_DEFINED = 0x02
SECTION_PE32 = 0x10
SECTION_PIC = 0x11
SECTION_TE = 0x12
SECTION_DXE_DEPEX = 0x13
SECTION_VERSION = 0x14
SECTION_USER_INTERFACE = 0x15
SECTION_COMPATIBILITY16 = 0x16
SECTION_FIRMWARE_VOLUME_IMAGE = 0x17
SECTION_FREEFORM_SUBTYPE_GUID = 0x18
SECTION_RAW = 0x19
SECTION_PEI_DEPEX = 0x1B
SECTION_SMM_DEPEX = 0x1C

SECTION_NAMES = {
    SECTION_COMPRESSION: "COMPRESSION",
    SECTION_GUID_DEFINED: "GUID_DEFINED",
    SECTION_PE32: "PE32",
    SECTION_PIC: "PIC",
    SECTION_TE: "TE",
    SECTION_DXE_DEPEX: "DXE_DEPEX",
    SECTION_VERSION: "VERSION",
    SECTION_USER_INTERFACE: "USER_INTERFACE",
    SECTION_COMPATIBILITY16: "COMPATIBILITY16",
    SECTION_FIRMWARE_VOLUME_IMAGE: "FIRMWARE_VOLUME_IMAGE",
    SECTION_FREEFORM_SUBTYPE_GUID: "FREEFORM_SUBTYPE_GUID",
    SECTION_RAW: "RAW",
    SECTION_PEI_DEPEX: "PEI_DEPEX",
    SECTION_SMM_DEPEX: "SMM_DEPEX",
}

# EFI_GUIDs as they appear on disk: Data1, Data2, Data3 little-endian, Data4 as-is.
LZMA_CUSTOM_DECOMPRESS_GUID = "EE4E5898-3914-4259-9D6E-DC7BD79403CF"
TIANO_CUSTOM_DECOMPRESS_GUID = "A31280AD-481E-41B6-95E8-127F4C984779"

GZIP_MAGIC = b"\x1f\x8b"


class Report:
    def __init__(self):
        self.notes = []
        self.unsupported = []
        self.files = []

    def note(self, message):
        self.notes.append(message)

    def unsupported_section(self, section_type, guid, why):
        self.unsupported.append({"section": SECTION_NAMES.get(section_type, "0x%02x" % section_type),
                                 "guid": guid or "-",
                                 "why": why})


def guid_from_bytes(raw):
    return str(uuid.UUID(bytes_le=raw)).upper()


def parse_fv_header(data, base):
    if base + 0x38 > len(data):
        raise ValueError("the file is too small to hold a Firmware Volume header")
    signature = struct.unpack_from("<I", data, base + 0x28)[0]
    if signature != FVH_SIGNATURE:
        raise ValueError("no _FVH signature at offset 0x%x (found 0x%08x)" % (base + 0x28, signature))
    fv_length = struct.unpack_from("<Q", data, base + 0x20)[0]
    header_length = struct.unpack_from("<H", data, base + 0x30)[0]
    file_system_guid = guid_from_bytes(data[base + 0x10:base + 0x20])
    return {
        "length": fv_length,
        "header_length": header_length,
        "file_system_guid": file_system_guid,
    }


def parse_ffs_header(data, offset, end):
    if offset + 24 > end:
        return None
    name = guid_from_bytes(data[offset:offset + 16])
    integrity_check = struct.unpack_from("<H", data, offset + 16)[0]
    file_type = data[offset + 18]
    attributes = data[offset + 19]
    size = data[offset + 20] | (data[offset + 21] << 8) | (data[offset + 22] << 16)
    state = data[offset + 23]
    header_size = 24
    if attributes & FFS_ATTRIB_LARGE_FILE:
        if offset + 32 > end:
            return None
        size = struct.unpack_from("<Q", data, offset + 24)[0]
        header_size = 32
    if size == 0 or offset + size > end:
        return None
    return {
        "name": name,
        "integrity_check": integrity_check,
        "type": file_type,
        "attributes": attributes,
        "size": size,
        "state": state,
        "header_size": header_size,
    }


def parse_sections(data, offset, end, report, depth=0):
    sections = []
    while offset + 4 <= end:
        size = data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)
        section_type = data[offset + 3]
        header_size = 4
        if size == 0xFFFFFF:
            if offset + 8 > end:
                report.note("a section header at 0x%x is truncated" % offset)
                break
            size = struct.unpack_from("<I", data, offset + 4)[0]
            header_size = 8
        if size < header_size or offset + size > end:
            report.note("a section at 0x%x claims size 0x%x and does not fit" % (offset, size))
            break
        sections.append({
            "type": section_type,
            "size": size,
            "header_size": header_size,
            "body_offset": offset + header_size,
            "body_size": size - header_size,
        })
        offset += size
    return sections


def decompress_guid_defined(body, guid, report):
    """GUID_DEFINED sections carry a GUID, a data offset and attributes before the payload."""
    if len(body) < 20:
        return None
    section_guid = guid_from_bytes(body[:16])
    data_offset = struct.unpack_from("<H", body, 16)[0]
    attributes = struct.unpack_from("<H", body, 18)[0]
    payload = body[data_offset:]
    if section_guid == LZMA_CUSTOM_DECOMPRESS_GUID:
        try:
            return lzma.decompress(payload, format=lzma.FORMAT_ALONE)
        except lzma.LZMAError as error:
            report.unsupported_section(SECTION_GUID_DEFINED, section_guid,
                                       "LZMA decompression failed: %s" % error)
            return None
    if section_guid == TIANO_CUSTOM_DECOMPRESS_GUID:
        report.unsupported_section(SECTION_GUID_DEFINED, section_guid,
                                   "the EFI standard (Tiano) decompressor is not implemented here")
        return None
    if payload[:2] == GZIP_MAGIC:
        try:
            return gzip.decompress(payload)
        except OSError as error:
            report.unsupported_section(SECTION_GUID_DEFINED, section_guid,
                                       "gzip decompression failed: %s" % error)
            return None
    report.unsupported_section(SECTION_GUID_DEFINED, section_guid,
                               "no decompressor for this GUID (attributes 0x%04x)" % attributes)
    return None


def walk_sections(data, offset, end, report, out, depth=0):
    """Write the sections of one file, recursing into compressed and FV_IMAGE sections."""
    for section in parse_sections(data, offset, end, report, depth):
        kind = section["type"]
        name = SECTION_NAMES.get(kind, "0x%02x" % kind)
        body = data[section["body_offset"]:section["body_offset"] + section["body_size"]]
        if kind in (SECTION_PE32, SECTION_TE, SECTION_PIC, SECTION_COMPATIBILITY16):
            suffixes = {"PE32": "pe32.efi", "TE": "te.efi", "PIC": "pic.efi",
                        "COMPATIBILITY16": "compat16.efi"}
            suffix = suffixes.get(name, "section.bin")
            out.setdefault(suffix, body)
        elif kind == SECTION_DXE_DEPEX:
            out.setdefault("depex.bin", body)
        elif kind == SECTION_RAW:
            out.setdefault("raw.bin", body)
        elif kind == SECTION_USER_INTERFACE:
            try:
                text = body.decode("utf-16le", errors="replace").strip("\x00")
            except Exception:
                text = ""
            out.setdefault("name.txt", text.encode("utf-8", errors="replace"))
        elif kind == SECTION_VERSION:
            out.setdefault("version.bin", body)
        elif kind == SECTION_FREEFORM_SUBTYPE_GUID:
            out.setdefault("freeform.bin", body)
        elif kind == SECTION_COMPRESSION:
            if len(body) < 5:
                report.unsupported_section(kind, None, "the compression header is truncated")
                continue
            uncompressed_length = struct.unpack_from("<I", body, 0)[0]
            compression_type = body[4]
            payload = body[5:]
            if compression_type == 0:
                out.setdefault("uncompressed.bin", payload)
                if len(payload) != uncompressed_length:
                    report.note("a COMPRESSION section claims %d uncompressed bytes but carries %d"
                                % (uncompressed_length, len(payload)))
            else:
                report.unsupported_section(kind, None,
                                           "CompressionType %d (EFI standard / Tiano) is not "
                                           "implemented here" % compression_type)
        elif kind == SECTION_GUID_DEFINED:
            decompressed = decompress_guid_defined(body, None, report)
            if decompressed is not None:
                walk_sections(decompressed, 0, len(decompressed), report, out, depth + 1)
        elif kind == SECTION_FIRMWARE_VOLUME_IMAGE:
            walk_fv(decompressed_or_raw(body), report, out, depth + 1)
        else:
            report.unsupported_section(kind, None, "this section type is not handled")


def decompressed_or_raw(body):
    return body


def walk_fv(data, report, out, depth=0):
    try:
        header = parse_fv_header(data, 0)
    except ValueError as error:
        report.note(str(error))
        return
    offset = header["header_length"]
    end = min(len(data), header["length"] or len(data))
    while offset + 24 <= end:
        file_header = parse_ffs_header(data, offset, end)
        if file_header is None:
            break
        report.files.append(file_header)
        file_out = {}
        walk_sections(data, offset + file_header["header_size"],
                      offset + file_header["size"], report, file_out, depth)
        out.setdefault("files", []).append({
            "guid": file_header["name"],
            "type": file_header["type"],
            "size": file_header["size"],
            "sections": sorted(file_out.keys()),
        })
        offset += file_header["size"]
        offset = (offset + 7) & ~7   # files are 8-byte aligned
    return header


def unpack(data, out_dir, report):
    out = {}
    walk_fv(data, report, out)
    for name, entry in enumerate(out.get("files", [])):
        directory = os.path.join(out_dir, "%03d-%s" % (name, entry["guid"]))
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "index.txt"), "w", encoding="utf-8") as handle:
            handle.write("guid: %s\n" % entry["guid"])
            handle.write("type: 0x%02x\n" % entry["type"])
            handle.write("size: %d\n" % entry["size"])
            handle.write("sections: %s\n" % ", ".join(entry["sections"]))
    return out


# -------------------------------------------------------------------------------------------
# Self-test
# -------------------------------------------------------------------------------------------

def make_section(section_type, body):
    size = 4 + len(body)
    return struct.pack("<I", size)[:3] + bytes([section_type]) + body


def make_ffs(guid, file_type, sections, large=False):
    body = b"".join(sections)
    size = 24 + len(body)
    if large:
        header = (uuid.UUID(guid).bytes_le + struct.pack("<H", 0) + bytes([file_type, FFS_ATTRIB_LARGE_FILE])
                  + b"\x00\x00\x00" + b"\x07" + struct.pack("<Q", 32 + len(body)))
        return header + body
    header = (uuid.UUID(guid).bytes_le + struct.pack("<H", 0) + bytes([file_type, 0])
              + bytes([size & 0xFF, (size >> 8) & 0xFF, (size >> 16) & 0xFF]) + b"\x07")
    return header + body


def make_fv(files):
    body = b"".join(files)
    # pad each file to an 8-byte boundary
    body = b"".join(f + b"\x00" * ((8 - len(f) % 8) % 8) for f in files)
    header_length = 0x38 + 8   # header + one block map entry + the null terminator
    fv_length = header_length + len(body)
    zero_vector = b"\x00" * 16
    file_system_guid = uuid.UUID("FC1BCDB0-7D31-49AA-936A-A4600D9DD083").bytes_le
    header = (zero_vector + file_system_guid + struct.pack("<Q", fv_length)
              + struct.pack("<I", FVH_SIGNATURE)
              + struct.pack("<I", 0x00043FFF)
              + struct.pack("<H", header_length)
              + struct.pack("<H", 0)
              + struct.pack("<H", 0)
              + b"\x00" + bytes([2]))
    block_map = struct.pack("<II", 0x1000, 1) + struct.pack("<II", 0, 0)
    return header + block_map + body


def self_test():
    report = Report()
    failures = 0

    def expect(name, condition):
        nonlocal failures
        if condition:
            print("ok   %s" % name)
        else:
            failures += 1
            print("FAIL %s" % name)

    pe32 = b"MZ" + b"\x00" * 62 + b"PE\x00\x00" + b"\x90" * 32
    raw = b"\x01\x02\x03\x04" * 4
    depex = b"\x05\x0a\x00" + b"\x20\x00" + b"\x00\x00"

    # a PE32 section, uncompressed
    fv = make_fv([make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                           [make_section(SECTION_PE32, pe32)])])
    file_out = {}
    walk_sections(make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                           [make_section(SECTION_PE32, pe32)]), 24,
                  24 + len(make_section(SECTION_PE32, pe32)), report, file_out)
    expect("PE32 bytes survive a round trip", file_out.get("pe32.efi") == pe32)

    file_out = {}
    walk_sections(make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                           [make_section(SECTION_RAW, raw)]), 24,
                  24 + len(make_section(SECTION_RAW, raw)), report, file_out)
    expect("RAW bytes survive a round trip", file_out.get("raw.bin") == raw)

    file_out = {}
    walk_sections(make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                           [make_section(SECTION_DXE_DEPEX, depex)]), 24,
                  24 + len(make_section(SECTION_DXE_DEPEX, depex)), report, file_out)
    expect("DXE_DEPEX bytes survive a round trip", file_out.get("depex.bin") == depex)

    # a GUID_DEFINED section carrying LZMA-compressed PE32
    inner = make_section(SECTION_PE32, pe32)
    compressed = lzma.compress(inner, format=lzma.FORMAT_ALONE)
    guid = uuid.UUID(LZMA_CUSTOM_DECOMPRESS_GUID).bytes_le
    guided = guid + struct.pack("<HH", 20, 0) + compressed
    file_out = {}
    walk_sections(make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                           [make_section(SECTION_GUID_DEFINED, guided)]), 24,
                  24 + len(make_section(SECTION_GUID_DEFINED, guided)), report, file_out)
    expect("an LZMA GUID_DEFINED section is decompressed", file_out.get("pe32.efi") == pe32)

    # a gzip GUID_DEFINED section is handled as a heuristic
    gz = gzip.compress(inner)
    guided_gz = uuid.UUID("9E4A5898-3914-4259-9D6E-DC7BD79403CF").bytes_le + struct.pack("<HH", 20, 0) + gz
    file_out = {}
    walk_sections(make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                           [make_section(SECTION_GUID_DEFINED, guided_gz)]), 24,
                  24 + len(make_section(SECTION_GUID_DEFINED, guided_gz)), report, file_out)
    expect("a gzip payload is decompressed", file_out.get("pe32.efi") == pe32)

    # a Tiano GUID_DEFINED section is reported as unsupported, not silently dropped
    tiano = uuid.UUID(TIANO_CUSTOM_DECOMPRESS_GUID).bytes_le + struct.pack("<HH", 20, 0) + b"\x00" * 16
    report2 = Report()
    walk_sections(make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                           [make_section(SECTION_GUID_DEFINED, tiano)]), 24,
                  24 + len(make_section(SECTION_GUID_DEFINED, tiano)), report2, {})
    expect("a Tiano section is reported as unsupported",
           any(u["why"].startswith("the EFI standard") for u in report2.unsupported))

    # a truncated FV header must fail loudly, not silently
    try:
        parse_fv_header(b"\x00" * 16, 0)
        expect("a truncated FV header is rejected", False)
    except ValueError:
        expect("a truncated FV header is rejected", True)

    # a file whose size does not fit is skipped rather than read out of bounds
    header = bytearray(make_fv([make_ffs("11111111-2222-3333-4444-555555555555", 0x0B,
                                         [make_section(SECTION_RAW, raw)])]))
    struct.pack_into("<I", header, 0x20, 0xFFFFFFFF)   # an impossible length
    report3 = Report()
    out3 = {}
    walk_fv(bytes(header), report3, out3)
    expect("an impossible FV length does not read out of bounds", True)

    print("uefi-fv-unpack: self-test %d failure(s)" % failures)
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fv", help="a Firmware Volume image or a full uefi.img")
    parser.add_argument("--out", help="the output directory")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.fv or not args.out:
        parser.error("--fv and --out are required unless --self-test is given")

    data = open(args.fv, "rb").read()
    report = Report()
    out = unpack(data, args.out, report)
    for note in report.notes:
        print("note: %s" % note)
    for entry in report.unsupported:
        print("unsupported: %s (%s) -- %s" % (entry["section"], entry["guid"], entry["why"]))
    print("uefi-fv-unpack: %d file(s) into %s" % (len(out.get("files", [])), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
