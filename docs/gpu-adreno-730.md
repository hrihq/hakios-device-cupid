# Adreno 730 on the Xiaomi 12 (cupid): a compatibility report

**Status: research and planning. No GPU code has been written, nothing has been run on a phone, and no
GPU acceleration is claimed.** What is here is what could be read and checked: HakiOS's existing driver,
the A730 as the phone's own tree and Linux describe it, and what the iOSPlus10/slop project did and
verified.

The branch is `adreno-730-cupid`. The facts the port starts from are in `docs/gpu-facts.txt`, made from
the phone's own device tree by `tools/gpu-facts.py`.

---

## Verdict

The A730 is a **different GPU generation** from the Adreno 642L HakiOS drives today, in the same way a
different SoC is: the *shape* of the bring-up is the same (clocks, GMU, firmware, HFI, command
processor, zap shader), and nearly every **register offset, the firmware, the power levels and the
protocol** are not. A port is therefore a second implementation of the same step framework, not a set of
changed constants.

Three things are genuinely reusable:

1. the step framework itself (`drivers/gpu/hakios.adreno.c`: the `struct block` table, `get`/`put`/`set`/
   `wait_for`, the step table, the boot-args, the read-before-write discipline, the teardown);
2. the IOKit service shape (`drivers/gpu/hakios.gpu.cpp`: the user client, the two request numbers,
   the buffer/fence model) -- the *interface* is reusable, the A6xx submit path inside it is not;
3. the Metal layer above it (`hakios-metal/`), which speaks PM4 and does not care which GPU it is,
   provided the kernel's ring and fences behave.

Three things are not:

1. the register offsets and the GMU/RSC/PDC/HFI sequences (A6xx versus Gen7);
2. the firmware (`a660_gmu.bin`, `a660_sqe.fw`, `a660_zap.mdt` versus `gmu_gen70000.bin`, `a730_sqe.fw`,
   `a730_zap`);
3. the power levels, the bus votes and the SMMU streams (all different, all in the phone's tree).

The honest size of the work: HakiOS's driver is 3852 lines for the A6xx. The A730 port is of the same
order, and **none of it can be verified without the phone** -- a register that is wrong ends the run, and
often silently.

---

## 1. What HakiOS has today

`drivers/gpu/hakios.adreno.c` (3852 lines) wakes an Adreno 642L in 22 numbered steps, each of which
announces what it is about to touch, reads before it writes, and stops the sequence if a step does not
find what it needs:

| Steps | What |
|---|---|
| 1 | the GPU's clocks in the global clock controller, and RPMh's names for its supplies |
| 2 | the fuses that say which GPU this is |
| 3 | the GPU's own clock controller, as the boot loader left it |
| 4 | the CX power switch on (the half that is not the 3D core: GMU, bus, SMMU) |
| 5 | the CX clocks, measured with the SoC's frequency counter |
| 6-10 | the GMU's registers, its RPMh channel, the SMMU's ID registers and first translation context, and two words written into the GMU's memory and read back |
| 11-12 | TrustZone: whether it takes calls from this kernel, and the zap shader's signature |
| 13-16 | the GMU's page tables and SMMU context, the GMU's firmware (`a660_gmu.bin`), its configuration, and its processor out of reset |
| 17 | HFI: the tables the GMU needs and the request to power the 3D core |
| 18-20 | the 3D core's translation context, its ring and microcode (`a660_sqe.fw`), the zap shader, and the core's command processor |
| 21-22 | the core out of secure mode, and a picture of three colours on the panel |

The blocks are a table of `{name, phys, size}`: `gcc` 0x100000, `qfprom` 0x780000, `gpucc` 0x3d90000,
`gmu` 0x3d6a000, `gbif` 0x3d0f000, `cx_misc` 0x3d9e000, `rscc` 0x3de0000, `smmu` 0x3da0000,
`pdc` 0xb290000, `gpu` 0x3d00000, `tsens1` 0xc265000, `dispcc` 0xaf00000. The offsets inside them are
`GPUCC_*`, `GMU_*`, `RSCC_*`, `SMMU_*`, `CP_*` defines. Every one of those is a reference-phone value.

`drivers/gpu/hakios.gpu.cpp` (1326 lines) is the IOKit service `HakiosGPU`. Its requests are Linux's msm
DRM requests by number plus two of its own (`0x7e` an IOSurface's ID, `0x7d` a caller's own pages). It
carries the buffers, the fences, the submit ring and the memory map for one client. `hakios-metal/` is a
PM4-level Metal on top of it, and does not know which GPU it is driving.

The driver is started by `gpu=1` (or `adreno=N` for steps 1..N) and needs the phone's GPU firmware in
`fw-gpu/`. Without it the system draws in software.

---

## 2. What the A730 is

From the phone's own tree (`docs/gpu-facts.txt`, every line traced to a node):

| Fact | Value |
|---|---|
| compatible | `qcom,adreno-gpu-gen7-0-1` |
| model | `Adreno730v2` |
| GPU block | 0x3d00000, 0x40000 |
| GMU | 0x3d68000, 0x37000 (`qcom,gen7-gmu`) |
| GMU PDC | 0xb290000, 0x10000 |
| GMU AO | 0x3d40000, 0x10000 |
| GPUCC | 0x3d90000, 0xa000 (`qcom,waipio-gpucc-v2`) |
| RSCC | 0x3d50000, 0x10000 |
| SMMU | 0x3da0000, 0x40000 |
| SMMU streams | user 0, lpac 1, secure 2, GMU 5 |
| power levels | 12, 220 MHz to 818 MHz, each with a bus level and an ACD level |
| zap shader memory | 0x8b91a000, 0x2000 (the reserved `gpu_micro_code_region`) |
| thermal zones | gpuss-0, gpuss-1 (tsens0 0xc263000, tsens1 0xc265000) |
| mempools | 4K, 8K, 64K, 128K, 256K, 1M |

Linux's KGSL calls this `qcom,adreno-gpu-gen7-0-1`, chipid `0x07030001`, features APRIV, IOCOHERENT,
CONTENT_PROTECTION, IFPC, ACD, L3_VOTE, BCL, PREEMPTION; **no** LM, DMS, LPAC or HW_FENCE. Its driver is
`adreno_gen7_gmu_gpudev` -- the non-hwsched Gen7 driver, with a GMU and HFI, not the newer hardware
scheduler. Firmware: `a730_sqe.fw`, `gmu_gen70000.bin`, `a730_zap`.

Two of the block bases are the same as the reference phone's (`gpu` 0x3d00000, `gpucc` 0x3d90000,
`cx_misc` 0x3d9e000, `smmu` 0x3da0000, `gcc` 0x100000, tsens) and three are not (`gmu` 0x3d68000 versus
0x3d6a000, `rscc` 0x3d50000 versus 0x3de0000, `pdc` is part of the GMU's own region now). That is the
only part of the port that is a table edit.

---

## 3. What iOSPlus10/slop did, and what is actually verified

The iOSPlus10 project (OnePlus 10 Pro, the same SM8450/A730) wrote its A730 support as a set of XNU
patches: `0097`-`0115` (GMU, CX clocks, RSCC SMMU, GMU memory and TrustZone, zap signature, GMU space
and firmware, GMU start and HFI, HFI messages, first frame, initial perf vote, zap segments), then
`0230`-`0237`, `0281`, `0285`, `0286`, `0287`, `0290`, `0298`, `0384`, `0389`, `0402` (surface import,
present, host import, per-client VA, clock probe, perf table, DCVS, power collapse, hang recovery,
KGSL parity, governor, frame pace, memory).

Its own audit (`docs/audit/2026-10-26-gpu.md`, read for this report) grades every KGSL function against
their implementation. The summary:

| Area | State |
|---|---|
| GMU boot: GDSC, clocks, TCM, RSC/PDC, register config, CM3 start, HFI start | done |
| HFI queues and messages, perf/bw tables, OOB GPU_SET, zap shader, secure mode | done |
| CP init, ringbuffer, submit, fences, timestamps | done |
| SMMU context and streams, page tables | done |
| DCVS governor, IFPC, thermal cap | partial |
| Bus votes from the DT's cmd-db, CNOC vote, ACD table | missing |
| HWCG (55 registers), CP_PROTECT, CHICKEN_DBG, DMS disable | missing |
| GPU reset and recovery after a lost WPTR or a hang | missing |
| Completion interrupt (polling instead) | missing |

Its own status page says the kernel driver is "written, builds, not run on the phone" for several parts,
and the phone has been sold; the repository is kept as a reference. Its GPU register table
(`negroni-ios/gpu/NativeAdrenoA730HwInit.h`) is **not linked into XNU** -- it is a generated reference
the kernel patches do not yet use.

### What this report verified independently

The register table's 54 offsets were checked against mainline Linux's own A7XX register dumps
(`drivers/gpu/drm/msm/registers/adreno/a6xx.xml`, `adreno_common.xml`, `a6xx_gmu.xml`):
**54 of 54 match**, register for register. That is a real check, and it is the reason the A730 register
map can be treated as known.

The table's 53 hardware-clock-gating values and 46 protection writes come from `a6xx_catalog.c`'s
`a730_hwcg`/`a730_protect`, which **do not exist in mainline Linux** -- the generator's pinned source is
a private OnePlus checkout. Those values could not be verified against a public source, and are
recorded here as *unverified* rather than as facts.

The header's own `source-sha256` lines do not match any mainline Linux tag (checked v6.9 through v6.14);
only `adreno_common.xml` matches. So the header's provenance is its author's private checkout, and its
values are trustworthy only where a public source confirms them.

---

## 4. Reusable versus incompatible

| Component | Reusable? | Why |
|---|---|---|
| the step framework (`struct block`, `get`/`put`/`set`/`wait_for`, the step table, the boot-args, the read-first discipline, the teardown) | **yes** | it is the shape of the bring-up, not the hardware |
| `HakiosGPU`'s user-client interface (request numbers, buffer and fence model) | **yes, the shape** | Mesa's freedreno and Metal speak msm DRM; the A730 needs the same requests |
| `HakiosGPU`'s A6xx submit path, ring and fence code | **no** | Gen7's ring, contexts and fences differ |
| `hakios-metal/` | **yes** | it is PM4-level and GPU-family agnostic |
| the GPU block bases | **partly** | 0x3d00000/0x3d90000/0x3d9e000/0x3da0000/0x100000 are the same; gmu, rscc, pdc are not |
| every register offset inside a block | **no** | A6xx versus Gen7: verified different (Appendix A) |
| the GMU/RSC/PDC sequences and HFI messages | **no** | Gen7 has its own RSC sequencer, PDC and HFI tables |
| the firmware | **no** | `gmu_gen70000.bin`, `a730_sqe.fw`, `a730_zap` |
| the power levels and bus votes | **no** | 12 levels, 220-818 MHz, with ACD; all in the phone's tree |
| the SMMU streams | **partly** | the block is at the same base; the stream numbers are 0/1/2/5 |
| the zap shader path | **partly** | the TrustZone calls are the same shape; the image and its memory differ |

---

## 5. Firmware dependencies

The A730 needs three images from the phone's own `/vendor/firmware`, none of which is in any repository:

| File | What it is | Where it goes |
|---|---|---|
| `gmu_gen70000.bin` | the GMU's firmware | `fw-gpu/`, loaded into the GMU's ITCM/DTCM and its memory |
| `a730_sqe.fw` | the 3D core's microcode | `fw-gpu/`, into the core's instruction ring |
| `a730_zap` | the zap shader, authenticated by TrustZone | `fw-gpu/`, into 0x8b91a000 (the tree's `gpu_micro_code_region`) |

The zap shader is the gate: without a signed image the 3D core stays in secure mode and nothing draws.
HakiOS's step 12 (TrustZone signature check) and step 19 (zap load) are the same shape as the A6xx ones;
the image and its memory are not. `tools/pull-firmware.sh` for the device must collect these three, and
they are never committed.

---

## 6. Licensing

| Source | Licence | Can HakiOS take it? |
|---|---|---|
| HakiOS's own driver | APSL 2.0 (XNU-derived), the rest MIT | -- |
| iOSPlus10's kernel patches | **private, no licence** | **no** -- read as a reference only |
| UniXNU's NativeAdreno | NOASSERTION | no |
| `NativeAdrenoA730HwInit.h` | MIT (generated) | with the notice kept; but it is derived from Linux register data, so treat it as a **pointer**, and re-derive from Linux |
| Linux's register dumps and KGSL | GPL-2.0 | **write from them, do not copy** -- the same way HakiOS's existing driver was written |

The practical rule for this port: read everything, copy nothing. The register offsets are facts (and
Appendix A records which public source each came from); the sequences and the code are to be written.

---

## 7. Porting plan

Each phase has a milestone that can be checked **without a phone**, and one that cannot. Only the first
kind is a delivery.

### Phase 1 -- facts and plan (this branch)
- [x] the cupid GPU facts, read out of the phone's tree by a tool (`docs/gpu-facts.txt`)
- [x] a check that the facts still match the tree (`tools/gpu-facts.py --check`, run in CI)
- [x] the A730 register map verified against mainline Linux (Appendix A)
- [x] this report

### Phase 2 -- the address layer (feasible, no phone)
- a device-local GPU fact header: the block bases and the A730 offsets, each with its source
- the step table and the boot-args for the new device, with the steps that only **read** written first
  (clocks, fuses, GPUCC, the first words)
- milestone: the kernel builds with the new device's GPU layer, and the read-only steps are reached.
  Not runnable; a wrong register ends the run.

### Phase 3 -- GMU and firmware (needs the phone's blobs)
- the Gen7 GMU boot: GDSC, clocks, TCM split, RSC/PDC sequencer, register config, CM3 start, HFI start
- the GMU's firmware from the phone
- milestone: HFI answers. Everything before it is a log line.

### Phase 4 -- the 3D core and the zap shader (needs TrustZone and the blobs)
- the core's context and ring, its microcode, the zap shader, secure mode off, a first command
- milestone: a filled picture on the panel. This is the first phase that can be *seen*.

### Phase 5 -- the user client (needs a working core)
- `HakiosGPU`'s A730 submit, ring and fence path; the memory map and the IOSurface/userptr imports
- milestone: `vk_test`/`ngl_test`-style bounded submit and fence waits

### Phase 6 -- Metal
- `hakios-metal/` over the A730 ring; the performance work (HWCG, a real busy counter, bus votes, ACD)
- milestone: the window server drawing through Metal

Phases 3 to 6 are not started, and none of them is verifiable without the phone and its firmware.

---

## 8. What cannot be verified without the phone

- every register write: a wrong offset ends the run, sometimes silently
- the GMU and HFI behaviour: only a log line from the phone says whether it answered
- the zap shader and TrustZone: whether this kernel may call it, and whether it accepts the image
- the power levels and bus votes: whether the GPU is stable at 818 MHz
- the SMMU: whether the streams and contexts are accepted
- every performance number

This report claims none of the above. A build that succeeds, or a step that logs, is not a working GPU.

---

## Appendix A -- the A730 register offsets, and where each came from

The 54 offsets below were read from the A7XX register dumps in mainline Linux
(`drivers/gpu/drm/msm/registers/adreno/`); each is the dword offset inside the GPU block at 0x3d00000.
They were cross-checked against the generated table in `NativeAdrenoA730HwInit.h` (MIT) and every one
matched. Regesters marked **common** are in `adreno_common.xml`, **gmu** in `a6xx_gmu.xml`, the rest in
`a6xx.xml`.

| Register | Offset | Source file |
|---|---|---|
| `CP_RB_BASE` | 0x0800 | a6xx.xml |
| `CP_RB_CNTL` | 0x0802 | a6xx.xml |
| `CP_RB_RPTR_ADDR` | 0x0804 | a6xx.xml |
| `CP_RB_RPTR` | 0x0806 | a6xx.xml |
| `CP_RB_WPTR` | 0x0807 | a6xx.xml |
| `CP_SQE_CNTL` | 0x0808 | a6xx.xml |
| `CP_SQE_INSTR_BASE` | 0x0830 | a6xx.xml |
| `CP_AHB_CNTL` | 0x098d | a6xx.xml |
| `CP_PROTECT_CNTL` | 0x084f | a6xx.xml |
| `CP_PROTECT` | 0x0850 | a6xx.xml |
| `CP_APRIV_CNTL` | 0x0844 | a6xx.xml |
| `CP_BV_APRIV_CNTL` | 0x0ad0 | a6xx.xml |
| `CP_LPAC_APRIV_CNTL` | 0x0b31 | a6xx.xml |
| `CP_HW_FAULT` | 0x0821 | a6xx.xml |
| `CP_INTERRUPT_STATUS` | 0x0823 | a6xx.xml |
| `CP_SQE_STAT_ADDR` / `DATA` | 0x0908 / 0x0909 | a6xx.xml |
| `CP_ALWAYS_ON_COUNTER` | 0x0980 | a6xx.xml |
| `CP_APERTURE_CNTL_HOST` | 0x0a00 | a6xx.xml |
| `RBBM_STATUS` | 0x0210 | a6xx.xml |
| `RBBM_STATUS3` | 0x0213 | a6xx.xml |
| `RBBM_INT_0_STATUS` | 0x0201 | a6xx.xml |
| `RBBM_INT_0_MASK` | 0x0038 | a6xx.xml |
| `RBBM_INT_CLEAR_CMD` | 0x0037 | a6xx.xml |
| `RBBM_CLOCK_CNTL` | 0x00ae | a6xx.xml |
| `RBBM_PERFCTR_CNTL` | 0x0500 | a6xx.xml |
| `RBBM_PERFCTR_GPU_BUSY_MASKED` | 0x050b | a6xx.xml |
| `RBBM_INTERFACE_HANG_INT_CNTL` | 0x001f | a6xx.xml |
| `RBBM_GBIF_HALT` | 0x0016 | common |
| `RBBM_GBIF_CLIENT_QOS_CNTL` | 0x0011 | common |
| `RBBM_NC_MODE_CNTL` | 0x0534 | a6xx.xml |
| `RBBM_SECVID_TSB_TRUSTED_BASE` | 0x0f800 | a6xx.xml |
| `RBBM_SECVID_TSB_TRUSTED_SIZE` | 0x0f802 | a6xx.xml |
| `RBBM_SECVID_TSB_CNTL` | 0x0f803 | a6xx.xml |
| `RBBM_SECVID_TRUST_CNTL` | 0x0f400 | a6xx.xml |
| `UCHE_CACHE_WAYS` | 0x0e17 | a6xx.xml |
| `UCHE_CLIENT_PF` | 0x0e19 | a6xx.xml |
| `UCHE_GBIF_GX_CONFIG` | 0x0e3a | a6xx.xml |
| `UCHE_CMDQ_CONFIG` | 0x0e3c | a6xx.xml |
| `UCHE_TRAP_BASE` | 0x0e09 | a6xx.xml |
| `UCHE_WRITE_THRU_BASE` | 0x0e07 | a6xx.xml |
| `UCHE_GMEM_RANGE_MIN` / `MAX` | 0x0e0b / 0x0e0d | a6xx.xml |
| `UCHE_MODE_CNTL` | 0x0e01 | a6xx.xml |
| `GBIF_HALT` | 0x03c45 | a6xx.xml |
| `RB_NC_MODE_CNTL` | 0x8e08 | a6xx.xml |
| `SP_NC_MODE_CNTL` | 0x0ae02 | a6xx.xml |
| `TPL1_NC_MODE_CNTL` | 0x0b604 | a6xx.xml |
| `GRAS_NC_MODE_CNTL` | 0x8602 | a6xx.xml |
| `RB_CMP_DBG_ECO_CNTL` | 0x8e28 | a6xx.xml |
| `GPU_GMU_AO_GMU_CGC_MODE_CNTL` | 0x23b09 | gmu |
| `GPU_GMU_AO_GMU_CGC_DELAY_CNTL` | 0x23b0a | gmu |
| `GPU_GMU_AO_GMU_CGC_HYST_CNTL` | 0x23b0b | gmu |

**Not verified**: the 53 `a730_hwcg` values and 46 `a730_protect` values. Their source is not in
mainline Linux. They are needed for the port (sections 2.6 and 2.7 of the iOSPlus10 audit) and they
must be re-derived from a Linux tree that carries them, or read from the phone's own vendor kernel.

## Appendix B -- what the phone's tree says

See `docs/gpu-facts.txt`, regenerated by `tools/gpu-facts.py --dtb uefi/files/Resources/DTBs/cupid.dtb`
and checked by `--check` in CI. It is the source of every address in section 2.
