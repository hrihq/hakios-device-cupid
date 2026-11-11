# The Adreno 730 address layer for the Xiaomi 12 (cupid)

**Status: the address layer only. No register has been written, no clock has been turned on, nothing
has been run on a phone.** This phase separates what is known from what is assumed, and puts the known
part in a form the port can include.

Phase 1's report is [gpu-adreno-730.md](gpu-adreno-730.md). This is its machine-checked half.

---

## What this is

Three files, one direction of dependence:

| File | What |
|---|---|
| `gpu/a730_resources.json` | the configuration: every address, size, interrupt, clock, regulator, power level and stream, each with the device-tree node it came from |
| `gpu/hakios.adreno-a730.h` | **generated** from the configuration; the header the port will include |
| `tools/gpu-address-check.py` | reads the phone's device tree and Linux's register dumps, checks the configuration against both, generates and checks the header |

The configuration is the only place an address is written down. The header is produced from it, so the
two cannot drift, and CI fails if they do.

## What this is not

* It is not a driver. Nothing here is compiled into the kernel, and `drivers/` is untouched, so the
  existing Adreno 642L support is untouched with it.
* It does not contain a single unverified register write. The one offset with no public source
  (`CP_PROTECT`, `0x0850`) is carried and marked, and nothing writes it.
* It does not decide anything about SC7280. The reference phone's block bases are listed in the
  validator only to be compared against; no address in the configuration may come from them, and the
  validator fails if a block is not in the cupid tree.

---

## The two kinds of number

They are different things and the header keeps them apart:

* **`A730_*_PHYS`** -- a physical address, from the phone's own device tree. Eight hex digits.
* **`A730_*`** inside the register section -- a **dword offset inside a block**, from Linux's A7XX
  register dumps. Five hex digits.

Adding a register offset to a block base is a bug. The header says so at the top, and the two sections
are separate so it is hard to do by accident.

---

## The blocks

Thirty blocks, each traced to a node in `uefi/files/Resources/DTBs/cupid.dtb`. Sizes are the node's
`reg` size, not a guess.

| Block | Physical | Size | Device tree node | reg-name |
|---|---|---|---|---|
| `gpu` | `0x03d00000` | `0x00040000` | `/soc/qcom,kgsl-3d0@3d00000` | `kgsl_3d0_reg_memory` |
| `gpu_cx_dbgc` | `0x03d61000` | `0x00000800` | same | `cx_dbgc` |
| `gpu_rscc` | `0x03d50000` | `0x00010000` | same | `rscc` |
| `gpu_isense` | `0x03d8b000` | `0x00002000` | same | `isense_cntl` |
| `gpu_cx_misc` | `0x03d9e000` | `0x00001000` | same | `cx_misc` |
| `gpu_qdss` | `0x10900000` | `0x00080000` | same | `qdss_gfx` |
| `gpu_rdpm` | `0x00634000` | `0x00001000` | same | `rdpm_cx` |
| `gmu` | `0x03d68000` | `0x00037000` | `/soc/qcom,gmu@3d69000` | `gmu` -- **uncertain** |
| `gmu_pdc` | `0x0b290000` | `0x00010000` | same | `gmu_pdc` |
| `gmu_ao` | `0x03d40000` | `0x00010000` | same | `gmu_ao_blk_dec0` |
| `gpucc` | `0x03d90000` | `0x0000a000` | `/soc/clock-controller@3d90000` | `cc_base` |
| `smmu` | `0x03da0000` | `0x00040000` | `/soc/kgsl-smmu@3da0000` | `base` |
| `smmu_tcu` | `0x03de6000` | `0x00000020` | same | `tcu-base` |
| `tbu0` | `0x03de9000` | `0x00001000` | `/soc/kgsl-smmu@3da0000/gfx_0_tbu@3de9000` | `base` |
| `tbu0_status` | `0x03de6200` | `0x00000008` | same | `status-reg` |
| `tbu1` | `0x03ded000` | `0x00001000` | `/soc/kgsl-smmu@3da0000/gfx_1_tbu@3ded000` | `base` |
| `tbu1_status` | `0x03de6208` | `0x00000008` | same | `status-reg` |
| `iommu` | `0x03da0000` | `0x00040000` | `/soc/qcom,kgsl-iommu@3da0000` | the context-bank container |
| `gdsc_cx` | `0x03d99108` | `0x00000004` | `/soc/qcom,gdsc@3d99108` | alias `gpu_cc_cx_gdsc` |
| `gdsc_gx` | `0x03d9905c` | `0x00000004` | `/soc/qcom,gdsc@3d9905c` | alias `gpu_cc_gx_gdsc` |
| `cx_hw_ctrl` | `0x03d9953c` | `0x00000004` | `/soc/syscon@3d9953c` | alias `gpu_cc_cx_hw_ctrl` |
| `gx_sw_reset` | `0x03d99058` | `0x00000004` | `/soc/syscon@3d99058` | alias `gpu_cc_gx_sw_reset` |
| `gx_acd_reset` | `0x03d99358` | `0x00000004` | `/soc/syscon@3d99358` | alias `gpu_cc_gx_acd_reset` |
| `gx_acd_iroot_reset` | `0x03d9958c` | `0x00000004` | `/soc/syscon@3d9958c` | alias `gpu_cc_gx_acd_iroot_reset` |
| `gx_domain_addr` | `0x03d99504` | `0x00000004` | `/soc/syscon@3d99504` | alias `gpu_cc_gx_domain_addr` |
| `gcc` | `0x00100000` | `0x001f4200` | `/soc/clock-controller@100000` | `cc_base` |
| `qdss_stm` | `0x161c0000` | `0x00040000` | property `qcom,gpu-qdss-stm` on the gpu node | -- |
| `gpu_zap_mem` | `0x08b91a000` | `0x00002000` | `/reserved-memory/gpu_micro_code_region@8b91a000` | the zap shader's memory |
| `tsens0` | `0x00c263000` | `0x000001ff` | `/soc/thermal-sensor@c263000` | cooling cell 0 |
| `tsens1` | `0x00c265000` | `0x000001ff` | `/soc/thermal-sensor@c265000` | cooling cell 1 |

The five the port's first steps touch are `gpu`, `gmu`, `gpucc`, `smmu` and `gpu_rscc`; the validator
requires all five to be present.

### Overlaps

The validator checks every pair. On this SoC most overlaps are **containments**, and they are real:

* the GMU's `reg` is a coarse container: `gmu` (`0x03d68000` + `0x37000` = `0x03d9f000`) covers
  `gpucc`, `gpu_isense`, `gpu_cx_misc` and all seven control registers. The GMU's region is **not** its
  own register range, and the port must not treat it as one.
* `smmu` and `iommu` are the same region described by two nodes: `kgsl-smmu@3da0000` (the SMMU's
  registers and its TCU) and `qcom,kgsl-iommu@3da0000` (the context-bank container).
* the control registers sit inside `gpucc`, which is where the GPUCC keeps its own GDSC, reset and ACD
  controls.

Anything that is not a containment is a failure.

---

## Interrupts, clocks, power domains, IOMMU

**Interrupts** (GIC SPI numbers, from the tree):

| Name | Number | Node |
|---|---|---|
| `kgsl_3d0_irq` | 300 | gpu |
| `freq_limiter_irq` | 286 | gpu |
| `hfi` | 304 | gmu |
| `gmu` | 305 | gmu |

**Clocks**: the gpu node takes `gcc_gpu_memnoc_gfx`, `gcc_gpu_snoc_dvm_gfx`, `gpu_cc_ahb`, `apb_pclk`;
the gmu takes `gmu_clk`, `cxo_clk`, `axi_clk`, `memnoc_clk`, `ahb_clk`, `hub_clk`, `apb_pclk`; the GPUCC
takes `bi_tcxo`, `gpll0_out_main`, `gpll0_out_main_div`; the SMMU takes `gpu_cc_cx_gmu`,
`gpu_cc_hub_cx_int`, `gpu_cc_hlos1_vote_gpu_smmu`. All are the tree's `clock-names`, not invented names.

**Power**: the GMU's `vddcx` is the CX GDSC and its `vdd` is the GX GDSC; the GPUCC's `vdd_cx`,
`vdd_mx` and `vdd_mxc` are the RPMh regulators `pm8350c-s6-level`, `pm8450-s6-level` and
`pm8350c-s2-level`. The SMMU's `vdd` is the CX GDSC.

**Power levels**: 12, from 220 MHz to 818 MHz, each with a bus level and an ACD level, read from the
gpu node's operating points. The initial level is 10.

**IOMMU**: the SMMU's translation contexts are `gfx3d_user` (0), `gfx3d_lpac` (1), `gfx3d_secure` (2),
and the GMU is stream 5. The GMU reaches the SMMU through its own `iommus` property (`311,5,1024`). The
context banks carry `qcom,iommu-dma = "disabled"`.

**Mempools**: 4K, 8K, 64K, 128K, 256K, 1M.

---

## Cross-checks against Linux's SM8450 reference

`arch/arm64/boot/dts/qcom/sm8450.dtsi` at Linux commit `067c5c24cef23d913b67eaaf71ae67e7169a6620`
is the SoC-level reference. Eleven addresses were compared:

| What | cupid | Linux sm8450.dtsi | Verdict |
|---|---|---|---|
| gpu base and size | `0x03d00000` `0x40000` | the same | agree |
| gpu cx_dbgc | `0x03d61000` `0x800` | the same | agree |
| gpu cx memory | `0x03d9e000` `0x1000` (`cx_misc`) | the same (`cx_mem`) | agree |
| rscc | `0x03d50000` `0x10000` | the same (in the gmu node) | agree |
| **gmu base and size** | **`0x03d68000` `0x37000`** | **`0x03d6a000` `0x35000`** | **disagree** |
| gmu_pdc | `0x0b290000` `0x10000` | the same | agree |
| gpucc base and size | `0x03d90000` `0xa000` | the same | agree |
| smmu base and size | `0x03da0000` `0x40000` | the same | agree |
| smmu tcu-base | `0x03de6000` `0x20` | not listed | this tree only |
| gmu interrupts | hfi 304, gmu 305 | the same | agree |
| gpu interrupt | 300 and 286 | 300 only | this tree has an extra |

Ten of eleven agree, which is what makes the SoC-level reference useful. The one disagreement is the
GMU's base.

---

## Unresolved

These are marked `uncertain` in the configuration and are **not** decided here:

1. **The GMU's base.** The phone's own tree says `0x03d68000` (size `0x37000`); Linux's `sm8450.dtsi`
   says `0x03d6a000` (size `0x35000`). Both regions end at `0x03d9f000`; the difference is the start,
   `0x2000`. The node's unit address (`0x3d69000`) matches neither. HakiOS's SC7280 driver uses
   `0x3d6a000`. The phone's tree is taken as authoritative for this phone, and the disagreement is
   recorded rather than hidden. Only the phone can settle it.
2. **The A730's hardware clock gating and protection values.** 53 `hwcg` and 46 `protect` values exist
   only in a generated table whose source is a private vendor checkout. They are not in this
   configuration and nothing implements them.
3. **The GPU speed bin and chip id.** The cupid tree has no `qcom,gpu-speed-bin` and no `qcom,chipid`.
   The A730's performance comes from its operating points, so there is nothing to read here.
4. **`CP_PROTECT` (`0x0850`).** In the generated table, in none of Linux's three dumps. Carried as
   unverified.

---

## The validator

```
python3 tools/gpu-address-check.py \
    --config gpu/a730_resources.json \
    --dtb uefi/files/Resources/DTBs/cupid.dtb \
    --linux <dir with a6xx.xml, adreno_common.xml, a6xx_gmu.xml> \
    --check-header gpu/hakios.adreno-a730.h
```

It checks, and fails on:

* a block whose node is missing from the tree, or whose address or size differs from the tree's `reg`;
* a block with a `reg-name` the node does not have;
* a missing required block, stream or interrupt;
* any overlap that is not a containment;
* a register offset that differs from Linux's dumps, or that is in none of them;
* a header that does not match the configuration.

It reports, without failing: containments, blocks marked uncertain, and registers with no public source.

The Linux register dumps are pinned to commit `067c5c24cef23d913b67eaaf71ae67e7169a6620` of
`torvalds/linux`. The dump entry for a name is chosen by its `variants` attribute, so an `A8XX-` offset
is never compared against the A730; where `a6xx.xml` and `adreno_common.xml` both define a name, the
more specific file wins.

---

## Hardening: the tests

`tools/gpu-address-tests.py` holds ten tests that protect the invariants above. CI runs them; each
fails loudly rather than reporting a warning.

| Test | What it protects |
|---|---|
| `header_is_reproducible` | generating twice gives the same bytes, and the committed header matches -- a hand edit cannot survive |
| `every_header_define_comes_from_the_config` | all 93 defines have an entry and all entries have a define; none disagrees |
| `secvid_offsets_are_the_linux_values` | the four RBBM secure-video offsets are Linux's, are inside the GPU block, and have not gone back to the generated table's values |
| `cp_protect_is_not_operational` | `CP_PROTECT` stays unverified, is absent from the known-offset list, and is marked unverified in the header |
| `uncertain_blocks_are_not_operational` | the GMU stays `uncertain`, is absent from the operational block list, and is flagged in the header |
| `gmu_container_is_not_a_register_range` | no register offset is mapped into the GMU container, and the register section implies no GMU range |
| `smmu_iommu_alias_is_explicit` | the alias is declared, the two bases and sizes agree, no two blocks share a name, and the validator reports no overlap conflict |
| `every_resource_has_a_source_and_a_status` | every block, register, stream, interrupt, clock, regulator, mempool and power level carries a source and an allowed status |
| `every_block_is_confirmed_by_the_cupid_tree` | every block's node exists in the phone's tree -- the guard against reusing SC7280 values |
| `the_device_repository_carries_no_gpu_driver` | the device repository has no `drivers/`, so the Adreno 642L driver cannot be touched from here |

The operational lists the tests reason about are derived, not stored: a block is operational when it is
`verified` and not a `container`; an offset is known when it is `verified`. Nothing marks a value safe
to write -- only known.

## The blocker report

`docs/gpu-blockers.json` is generated by `tools/gpu-blocker-report.py` from the configuration and
lists everything that stops the port moving on. Fifteen entries: thirteen unresolved, two resolved.

The unresolved ones are the GMU's base and size, the GMU's container versus its own register range, the
A730's hardware clock gating and protection values (no public source), the absent speed bin, the three
firmware images, TrustZone, SMMU acceptance, power stability, the absence of a physical device, and the
vendor UEFI drivers. Each carries what would resolve it, so the list is a work list.

The two resolved ones are the register disagreements recorded above: they are kept in the report so a
later reader does not rediscover them.

```
python3 tools/gpu-blocker-report.py --out docs/gpu-blockers.json
python3 tools/gpu-blocker-report.py --check docs/gpu-blockers.json   # CI
```

---

## What Phase 2 deliberately does not do

* no GMU initialization, no firmware load, no TrustZone call;
* no register write of any kind -- the header is data, not code;
* no change to `drivers/gpu/`, so the Adreno 642L path is untouched;
* no flashing, no hardware modification.

The next phase (GMU and firmware) needs the phone's three firmware images and a phone to run on. This
phase's outputs are checkable without either, and are.
