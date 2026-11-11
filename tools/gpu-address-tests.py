#!/usr/bin/env python3
"""Tests for the Xiaomi 12 (cupid) Adreno 730 address layer.

These are the invariants Phase 2.1 exists to protect. Each test fails loudly, and CI runs all of
them. They check the *shape* of the address layer -- that a value with no public source cannot become
an operational one, that an uncertain address cannot be silently selected, that a container region is
not mistaken for a register range, and that the generated header cannot drift from the configuration.

They do not check hardware. Nothing here says a register write would work.

Usage:
  python3 tools/gpu-address-tests.py
  python3 tools/gpu-address-tests.py --config gpu/a730_resources.json \
      --dtb uefi/files/Resources/DTBs/cupid.dtb --header gpu/hakios.adreno-a730.h
"""

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ALLOWED_STATUS = {"verified", "cross-checked", "uncertain", "unverified-source", "unverified"}

TESTS = []


def test(function):
    TESTS.append(function)
    return function


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load("gpu_address_check", os.path.join(HERE, "gpu-address-check.py"))
FACTS = CHECKER.FACTS


def operational_blocks(config):
    """Blocks the port may use as ordinary register ranges: confirmed by the tree, and not containers."""
    return [b for b in config["blocks"]
            if b["status"] == "verified" and not b.get("container")]


def known_offsets(config):
    """Register offsets with a public source. Not 'safe to write' -- only 'the offset is known'."""
    return [r for r in config["registers"] if r["status"] == "verified"]


def by_name(entries):
    return {e["name"]: e for e in entries}


# --------------------------------------------------------------------------------------------------
# 1. the header and the configuration are the same thing
# --------------------------------------------------------------------------------------------------

@test
def header_is_reproducible():
    """Generating twice gives the same bytes, so the committed header is not hand-edited."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    first = CHECKER.render_header(config)
    second = CHECKER.render_header(config)
    assert first == second, "the generator is not deterministic"
    committed = open(os.path.join(ROOT, "gpu/hakios.adreno-a730.h"), encoding="utf-8").read()
    assert committed == first, ("gpu/hakios.adreno-a730.h does not match the configuration; "
                                "regenerate it with tools/gpu-address-check.py --emit-header")


@test
def every_header_define_comes_from_the_config():
    """Each of the 93 defines has an entry, and each entry has a define; the counts cannot drift."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    header = open(os.path.join(ROOT, "gpu/hakios.adreno-a730.h"), encoding="utf-8").read()
    defines = dict(re.findall(r"^#define\s+(A730_[A-Z0-9_]+)\s+((?:0x[0-9a-f]+|\d+))u", header, re.M))

    expected = {}
    for block in config["blocks"]:
        expected["A730_" + block["name"].upper() + "_PHYS"] = int(block["phys"], 16)
    for register in config["registers"]:
        expected["A730_" + register["name"].upper()] = int(register["offset"], 16)
    for stream in config["streams"]:
        expected["A730_STREAM_" + stream["name"].upper()] = stream["id"]
    for interrupt in config["interrupts"]:
        expected["A730_IRQ_" + interrupt["name"].upper()] = interrupt["number"]

    missing = sorted(set(expected) - set(defines))
    extra = sorted(set(defines) - set(expected))
    assert not missing, "the header is missing %d define(s): %s" % (len(missing), missing[:6])
    assert not extra, "the header has %d define(s) not in the configuration: %s" % (len(extra), extra[:6])
    wrong = sorted(k for k in expected if k in defines and int(defines[k], 0) != expected[k])
    assert not wrong, "%d define(s) disagree with the configuration: %s" % (len(wrong), wrong[:6])


# --------------------------------------------------------------------------------------------------
# 2. the four corrected RBBM secure-video offsets
# --------------------------------------------------------------------------------------------------

@test
def secvid_offsets_are_the_linux_values():
    """The generated table's four secure-video offsets are one hex digit too large and fall outside
    the GPU block. Linux's are the ones in force; a regression to the generated values must fail."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    registers = by_name(config["registers"])
    linux = {
        "RBBM_SECVID_TRUST_CNTL": 0x0F400,
        "RBBM_SECVID_TSB_TRUSTED_BASE": 0x0F800,
        "RBBM_SECVID_TSB_TRUSTED_SIZE": 0x0F802,
        "RBBM_SECVID_TSB_CNTL": 0x0F803,
    }
    generated_table = {
        "RBBM_SECVID_TRUST_CNTL": 0x0F4000,
        "RBBM_SECVID_TSB_TRUSTED_BASE": 0x0F8000,
        "RBBM_SECVID_TSB_TRUSTED_SIZE": 0x0F8002,
        "RBBM_SECVID_TSB_CNTL": 0x0F8003,
    }
    block = by_name(config["blocks"])["gpu"]
    block_dwords = int(block["size"], 16) // 4
    for name, offset in linux.items():
        assert name in registers, "%s is not in the configuration" % name
        assert int(registers[name]["offset"], 16) == offset, (
            "%s is 0x%x; Linux's a6xx.xml says 0x%x" % (name, int(registers[name]["offset"], 16), offset))
        assert offset < block_dwords, (
            "%s (0x%x) is outside the gpu block, which is 0x%x dwords" % (name, offset, block_dwords))
        assert int(registers[name]["offset"], 16) != generated_table[name], (
            "%s has gone back to the generated table's 0x%x" % (name, generated_table[name]))


# --------------------------------------------------------------------------------------------------
# 3. CP_PROTECT stays unverified and out of the operational list
# --------------------------------------------------------------------------------------------------

@test
def cp_protect_is_not_operational():
    """CP_PROTECT has no public source. It must stay marked as such and must not appear in the list
    of offsets the port treats as known."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    registers = by_name(config["registers"])
    assert "CP_PROTECT" in registers, "CP_PROTECT is missing from the configuration"
    entry = registers["CP_PROTECT"]
    assert entry["status"] != "verified", "CP_PROTECT must not be marked verified"
    assert "not in" in entry["source"].lower() or "no public" in entry["source"].lower(), (
        "CP_PROTECT's source should say it is not in the public dumps")
    names = {r["name"] for r in known_offsets(config)}
    assert "CP_PROTECT" not in names, "CP_PROTECT is in the operational offset list"
    header = open(os.path.join(ROOT, "gpu/hakios.adreno-a730.h"), encoding="utf-8").read()
    line = [l for l in header.splitlines() if "A730_CP_PROTECT " in l]
    assert line, "CP_PROTECT is not in the header"
    assert "unverified" in line[0], "the header does not mark CP_PROTECT as unverified: %r" % line[0]


# --------------------------------------------------------------------------------------------------
# 4. an uncertain address cannot be silently selected
# --------------------------------------------------------------------------------------------------

@test
def uncertain_blocks_are_not_operational():
    """The GMU's base is disputed between the phone's tree and Linux. It must be marked uncertain,
    must not appear in the operational block list, and must be flagged in the header."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    blocks = by_name(config["blocks"])
    assert blocks["gmu"]["status"] == "uncertain", (
        "the GMU's status is %r; it must be uncertain while the base is disputed"
        % blocks["gmu"]["status"])
    assert "gmu" not in {b["name"] for b in operational_blocks(config)}, (
        "the GMU is in the operational block list")
    uncertain = {b["name"] for b in config["blocks"] if b["status"] == "uncertain"}
    selected = {b["name"] for b in operational_blocks(config)}
    assert not (uncertain & selected), "uncertain block(s) selected as operational: %s" % (uncertain & selected)
    header = open(os.path.join(ROOT, "gpu/hakios.adreno-a730.h"), encoding="utf-8").read()
    line = [l for l in header.splitlines() if "A730_GMU_PHYS" in l]
    assert line and "UNCERTAIN" in line[0], "the header does not flag the GMU as uncertain: %r" % line


# --------------------------------------------------------------------------------------------------
# 5. a container region is not a register range
# --------------------------------------------------------------------------------------------------

@test
def gmu_container_is_not_a_register_range():
    """The GMU's reg covers the GPUCC, gpu_isense, gpu_cx_misc and the control registers. It is a
    container; no register offset may be mapped into it, and the header must not imply one."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    blocks = by_name(config["blocks"])
    assert blocks["gmu"].get("container") is True, "the GMU block is not marked as a container"
    mapped = sorted({r["block"] for r in config["registers"] if r["block"] == "gmu"})
    assert not mapped, "register offsets are mapped into the GMU container: %s" % mapped
    assert all(r["block"] == "gpu" for r in config["registers"]), (
        "every register offset must name the gpu block; found %s"
        % sorted({r["block"] for r in config["registers"]}))
    header = open(os.path.join(ROOT, "gpu/hakios.adreno-a730.h"), encoding="utf-8").read()
    section = header.split("/* dword offsets inside the gpu block")[1].split("/* the SMMU")[0]
    assert "A730_GMU_" not in section, "the register section implies a GMU register range"


# --------------------------------------------------------------------------------------------------
# 6. the SMMU and IOMMU aliases do not become two mappings
# --------------------------------------------------------------------------------------------------

@test
def smmu_iommu_alias_is_explicit():
    """kgsl-smmu@3da0000 and qcom,kgsl-iommu@3da0000 describe the same region. The alias must be
    declared, and the validator must report it as a containment, never as a conflict."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    blocks = by_name(config["blocks"])
    assert blocks["iommu"].get("alias_of") == "smmu", "the iommu block does not declare its alias"
    assert blocks["smmu"]["phys"] == blocks["iommu"]["phys"], "the alias has a different base"
    assert blocks["smmu"]["size"] == blocks["iommu"]["size"], "the alias has a different size"
    names = [b["name"] for b in config["blocks"]]
    assert len(names) == len(set(names)), "two blocks share a name"
    # a containment is a note; anything else is a failure. Run the validator's own check.
    import contextlib
    import io
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        CHECKER.check(config, os.path.join(ROOT, "uefi/files/Resources/DTBs/cupid.dtb"))
    conflicts = [line for line in captured.getvalue().splitlines()
                 if "FAIL" in line and "overlap" in line]
    assert not conflicts, "the validator reports an overlap conflict: %s" % conflicts


# --------------------------------------------------------------------------------------------------
# 7. provenance: every resource carries a source and a status
# --------------------------------------------------------------------------------------------------

@test
def every_resource_has_a_source_and_a_status():
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    lists = [("blocks", "dt"), ("registers", "source"), ("streams", "dt"), ("interrupts", "dt"),
             ("clocks", "dt"), ("regulators", "dt"), ("mempools", "dt")]
    for key, source_field in lists:
        for entry in config[key]:
            assert entry.get(source_field), "%s %r has no %s" % (key, entry.get("name"), source_field)
            assert entry.get("status") in ALLOWED_STATUS, (
                "%s %r has status %r" % (key, entry.get("name"), entry.get("status")))
    for level in config["power_levels"]:
        assert level.get("status") in ALLOWED_STATUS, "power level %r has no status" % level.get("index")
    for check in config["cross_checks"]:
        assert check.get("this") and check.get("sm8450.dtsi") and check.get("verdict"), (
            "a cross-check is missing a side: %r" % check.get("what"))
    for entry in config["uncertain"]:
        assert entry.get("what") and entry.get("note"), "an uncertain entry has no note: %r" % entry.get("what")


# --------------------------------------------------------------------------------------------------
# 8. no address comes from the reference phone
# --------------------------------------------------------------------------------------------------

@test
def every_block_is_confirmed_by_the_cupid_tree():
    """An address that is not in the phone's own tree fails the validator, whatever its source. This
    is the guard against reusing SC7280 values."""
    config = json.load(open(os.path.join(ROOT, "gpu/a730_resources.json"), encoding="utf-8"))
    nodes = FACTS.fdt_nodes(open(os.path.join(ROOT, "uefi/files/Resources/DTBs/cupid.dtb"), "rb").read())
    for block in config["blocks"]:
        assert block["dt"] in nodes, (
            "block %r points at %s, which the cupid tree does not have" % (block["name"], block["dt"]))
    reference = CHECKER.REFERENCE_BLOCKS
    matched = sorted(b["name"] for b in config["blocks"]
                     if int(b["phys"], 16) in reference.values())
    assert matched, "no block address matches a reference value; the guard is not exercising anything"
    # a match is fine only because the tree confirms it; the validator above is what enforces that


# --------------------------------------------------------------------------------------------------
# 9. the existing Adreno 642L support is untouched
# --------------------------------------------------------------------------------------------------

@test
def the_device_repository_carries_no_gpu_driver():
    """The device repository must not contain a driver of its own: the address layer is data, and
    drivers/gpu/ in the common kernel is the Adreno 642L implementation."""
    drivers = os.path.join(ROOT, "drivers")
    assert not os.path.exists(drivers), (
        "the device repository has a drivers/ directory; the Adreno 642L driver must stay untouched")


# --------------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    failures = 0
    for function in TESTS:
        try:
            function()
        except AssertionError as error:
            failures += 1
            print("FAIL %-46s %s" % (function.__name__, error))
        except Exception as error:  # a crash is a failure too
            failures += 1
            print("FAIL %-46s %s: %s" % (function.__name__, type(error).__name__, error))
        else:
            print("ok   %s" % function.__name__)
    print("gpu-address-tests: %d test(s), %d failure(s)" % (len(TESTS), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
