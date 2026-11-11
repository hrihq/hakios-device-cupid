# GPU firmware dependencies on the Xiaomi 12 (cupid)

**Status: tooling and documentation only. Nothing has been loaded, nothing has been authenticated, and
no claim is made that any of these images works.** This document records what the three Adreno 730
images are, which one needs which, what a public source can verify about them, and what cannot be
verified without the phone.

The images themselves are **not in this repository**. They are the phone's proprietary firmware, and
the same rule as every other vendor blob applies: pull them from the phone, never commit them.

---

## The three images and their dependency chain

```
gmu_gen70000.bin  -- the GMU's firmware
      |
      | the GMU brings up the 3D core's power, bus and SMMU context, and answers HFI
      v
a730_sqe.fw       -- the 3D core's microcode
      |
      | the core stays in secure mode until a zap shader is authenticated
      v
a730_zap.mbn      -- the zap shader, signed and authenticated by TrustZone
      |
      v
   the core can draw
```

**The order matters and none of it is optional.** Without the GMU firmware the GMU does not start and
there is no one to answer HFI. Without the microcode the core has no instruction stream. Without the
zap shader the core stays in secure mode and nothing is drawn -- the zap shader is what takes the core
out of secure mode.

| Image | Role | Loaded into | Format | Public source |
|---|---|---|---|---|
| `gmu_gen70000.bin` | the GMU's firmware | GMU ITCM, DTCM and its buffer memory | a block table: `{u32 addr, u32 size, u32 type, u32 value}` entries; `size == 0` entries are descriptors carrying a length in `value`, and entries with `type == 0xefbeadde` carry data | Linux `a6xx_gmu.c` (`struct block_header`, `a6xx_gmu_fw_load()`) |
| `a730_sqe.fw` | the 3D core's microcode | the core's instruction ring | **undocumented** -- no public source describes it | none |
| `a730_zap.mbn` | the zap shader | `0x08b91a000`, the reserved node `gpu_micro_code_region` (0x2000 bytes) | a Qualcomm MDT: a 32-bit little-endian ELF whose program headers describe the segments | Linux `mdt_loader.c` (`mdt_header_valid()`, `qcom_mdt_get_size()`) and `adreno_gpu.c` (`zap_shader_load_mdt()`) |

The zap shader is loaded through TrustZone: Linux's `adreno_gpu.c` calls `qcom_pas_auth_and_reset()`
after writing the segments, and treats `-EOPNOTSUPP` as "this target does not need a zap shader". A
HakiOS port must answer the same question, and no source can predict the answer.

---

## What the checker verifies

`tools/gpu-firmware-check.py` reads `gpu/firmware/manifest.json` and checks a directory of images:

* **presence** -- each expected file is there;
* **size** -- within a range, not an exact match, because the phone's own files may differ from the
  public mirror the sizes were taken from;
* **GMU structure** -- the block table consumes the file exactly, and the data blocks are reported by
  address and size;
* **zap structure** -- ELF32 magic, 32-bit little-endian, `e_phentsize == 32`, the program header
  table fits, and the loadable (non-hash) segments' span fits the reserved region, computed the way
  `qcom_mdt_get_size()` computes it;
* **SQE** -- word alignment and non-emptiness only.

```
python3 tools/gpu-firmware-check.py --dir <path with the three images>
python3 tools/gpu-firmware-check.py --self-test
```

`--self-test` builds synthetic fixtures that must pass and broken ones that must fail, so the tool is
tested in CI without the phone and without any firmware.

### What it found in the public mirror

The community mirror `sm8450-mainline/firmware-xiaomi-cupid` carries all three images. Running the
checker over them:

* `gmu_gen70000.bin`, 57,272 bytes: 11 descriptor entries and 4 data blocks; the table consumes the
  file exactly. Data blocks land at `0x00000000` (476 bytes), `0x00004000` (56,492 bytes),
  `0x10007f98` (40 bytes) and `0x10007fdc` (24 bytes).
* `a730_sqe.fw`, 74,484 bytes: 18,621 words, word-aligned. The word `0xfbadc0de` appears at offset
  `0x38` and the last 16 bytes are 81% printable ASCII. **This is recorded, not interpreted.**
* `a730_zap.mbn`, 11,308 bytes: ELF32, machine `0x00a4`, 3 program headers, one `PT_LOAD` at physical
  address `0x1000` with `p_memsz` `0x8bc`. The loadable span, computed as `qcom_mdt_get_size()`
  computes it, is `0x1000` bytes at `0x1000` -- which fits the `0x2000` reserved region.

---

## What the checker cannot verify

These are the open questions, and they are the reason the port stops here until the phone arrives:

1. **The GMU blob's 56 KB block at `0x00004000`.** Linux's `a6xx_gmu_fw_load()` writes blocks into
   ITCM (`0x0`..`0x4000`), DTCM (`0x10004000`..`0x10008000`) or one of the GMU's buffer objects
   (`icache`, `dcache`, `dummy`). The 56 KB block is outside both windows, so it would have to go to a
   buffer -- and the buffer layout is not public. The checker reports this; it does not decide it.
2. **The SQE image's format.** No public source documents it, so the checker checks only that it is
   word-aligned and non-empty. Anything more would be invented.
3. **Whether the phone's own files match the public mirror.** The sizes and structures above are from
   the mirror. The phone's may differ.
4. **Whether TrustZone will accept the zap shader for this kernel.** That is a run on the phone.
5. **Whether the GMU starts and the core leaves secure mode.** Also a run on the phone.

---

## Getting the images

The phone holds them under `/vendor/firmware/`. They are never committed: add them to
`.gitignore`-style exclusions, or keep them in a directory the workflow is told about. The checker
takes a directory path, so the workflow can run it when the images are supplied without storing them
in the repository.

What the port needs from the phone, in one line each:

| Image | Why the port cannot proceed without it |
|---|---|
| `gmu_gen70000.bin` | without it the GMU does not start and nothing else can |
| `a730_sqe.fw` | without it the 3D core has no instruction stream |
| `a730_zap.mbn` | without it the core stays in secure mode and nothing is drawn |
