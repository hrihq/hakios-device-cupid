# Driver compatibility: HakiOS's drivers against the Xiaomi 12 (cupid)

**Status: a comparison of what HakiOS's drivers are written for, against what the Xiaomi 12's device
tree says is in the phone. No driver has been ported and none has been run.**

HakiOS's drivers are written for the **POCO X5 Pro (redwood)**, a Snapdragon 778G (SM7325, SC7280
family): the Adreno 642L, the WCN6750 Wi-Fi/Bluetooth, a Goodix GT9916 or FocalTech FT3680
touchscreen on SPI, two I2C speaker amplifiers, an Awinic AW86927 haptic motor, and the PM8350C flash
LED. Every driver's `conf` in `drivers/` names its hardware; the table below reads those names and
compares them with `docs/device-facts.txt`.

`tools/driver-matrix-check.py` checks that every driver named here still exists in the common
repository, so the matrix cannot drift from the drivers it describes.

---

## The matrix

| Driver | Written for (POCO X5 Pro) | cupid (SM8450) | Verdict |
|---|---|---|---|
| **SOCINFO** | any Qualcomm SoC keeping SMEM item 137 | SM8450 | **reusable** — needs `soc_smem=` from cupid's FD |
| **PMIC** | the SPMI arbiter and the PMIC blocks | SPMI 0/1, RPMh, AOSS | **reusable** — the arbiter is the same design |
| **THERMAL** | the SoC's temperature sensors | two TSENS blocks, 32 sensors | **reusable** — the sensor core is the same |
| **CPUFREQ** | the core clocks and the memory bus votes | GCC, the same RPMh | **adaptable** — the clock names differ |
| **BATTGUARD** | the run handed back before the battery is flat | same | **reusable** |
| **QMI** | the IPC router and the QMI messages | same | **reusable** |
| **UFS** | the POCO X5 Pro's UFS flash | UFS 3.1, `ufshc@1d84000`, PHY `@1d87000` | **adaptable** — same host controller design, different device |
| **ADSP** | the SC7325's audio DSP | the waipio ADSP | **adaptable** — the framework, not the firmware |
| **SOUND** | the speakers playing | the LPASS + WCD938x | **adaptable** — needs ADSP and SPEAKER |
| **MIC** | the microphones through the DSP | the LPASS | **adaptable** — needs ADSP and SOUND |
| **SPEAKER** | two amplifiers on I2C | WSA883x on soundwire | **new** — a different bus and a different chip |
| **BATTERY** | the state from the audio DSP's battery manager | the charger under `pmic_glink` | **adaptable** — the source of the state changes |
| **BUTTONS** | the power and volume keys through the PMIC's SPMI | `/soc/gpio_keys` | **adaptable** — different keys, same idea |
| **TORCH** | the PM8350C's flash LED | cupid's flash LED | **adaptable** — the PMIC is a different one |
| **GOODIX** | GT9916 or FT3680 on SPI | a Synaptics TCM on I2C | **new** — a different controller, bus and protocol |
| **HAPTIC** | an Awinic AW86927 | an Awinic AW8697 | **new** — the same vendor, a different chip |
| **BT** | the WCN6750's Bluetooth half | the QCA6490 | **new** |
| **WIFI** | the WCN6750, Linux's ath11k linked in | the QCA6490 | **new** — a different radio and a different stack |
| **CAMERA** | the POCO X5 Pro's sensors and the ISP's interface | the SDE-class camera subsystem, CSI/IPE/BPS | **new** — the sensors, the tables and the ISP firmware |
| **MODEM** | the POCO X5 Pro's modem, over QMI and UFS | the waipio modem | **adaptable framework** — the firmware and the file systems differ |
| **ADRENO** | the Adreno 642L of the SC7280 | the Adreno 730 | **new** — phases 3 to 6; phases 1 and 2 are the facts and the address layer |
| **VIRTIO_INPUT**, **VIRTIO_BLK**, **VIRTIO_NET**, **VIRTIO_SOUND** | QEMU's virtio devices | — | **out of scope** — they serve the QEMU port, not the phone |

The display has no `drivers/` conf: in the GPU driver's IOKit the display asks whether the GPU is
done with a surface, so the display is served from the GPU driver's service. Bringing it up is part
of the GPU work, not a separate driver.

---

## What "reusable" means, and what it does not

* **Reusable** — the code talks to a Qualcomm block that is the same design on both SoCs (the SPMI
  arbiter, the TSENS core, the IPC router). It still needs the phone's addresses, which are not in
  the tree's compatible string but in its `reg` ranges, and it still needs the phone's firmware.
  **"Reusable" does not mean unchanged:** every driver carries the first phone's addresses as
  `#define`s, and the audit at the end of this document is the check that says which of them this
  phone shares.
* **Adaptable** — the shape of the driver is right but the blocks it names are different: a
  different clock list, a different PMIC, a different source for the battery's state.
* **New** — the driver is written against a different chip. It cannot be adapted; it has to be
  written, and its firmware comes from the phone.

No verdict here is a claim that the driver works. Every one of them needs the phone: at minimum the
addresses, and for most of them the firmware and the init sequences.

---

## The order the drivers come up in

The dependency order is the same as the `requires` lines in the `conf` files, and it is why the
bring-up is long:

```
SOCINFO, PMIC, THERMAL, BATTGUARD, CPUFREQ     -- the SoC, read only
  └─ UFS                                     -- storage, then the root
       └─ QMI                                 -- the IPC router
            ├─ WIFI  (needs fw-wifi)
            └─ MODEM (needs fw-modem)
  └─ ADSP          (needs fw-audio)
       └─ SPEAKER
            └─ SOUND
                 └─ MIC
  └─ ADRENO        (needs fw-gpu; phases 3-6)
       └─ the display, through the GPU's service
  └─ GOODIX, BUTTONS, HAPTIC, TORCH, CAMERA, BT
```

The three longest poles are the GPU, Wi-Fi/Bluetooth, and audio: each needs its own firmware from
the phone, and each has a step-by-step bring-up that cannot be validated without the hardware.

---

## What each "new" driver needs

| Driver | Needs |
|---|---|
| ADRENO | the GMU and 3D core firmware; the zap shim; then the user client and the Metal service |
| SPEAKER | the WSA883x amplifiers' init and tuning, and the soundwire bus |
| GOODIX → a Synaptics TCM driver | the controller's firmware, its I2C address and its init sequence |
| HAPTIC | the AW8697's register map and waveforms |
| BT | the QCA6490's Bluetooth firmware and its host interface |
| WIFI | the QCA6490's WLAN firmware, the regulatory database and the board data |
| CAMERA | the sensors' identity, their tables and the ISP firmware |

Every one of those is in `docs/device-blockers.json`.

---

## The modem's SoC addresses

The modem and IPA drivers carry the first phone's addresses as built-in defaults and take any that
differ from `soc_*` boot-args, which `soc.args` holds. `tools/soc-args.py` in the common repository
reads them off a phone's own device tree -- but it matches the reserved-memory nodes by the first
phone's names, and this phone names three of them differently:

| Argument | First phone's node | This phone's node | Value |
|---|---|---|---|
| `soc_cmd_db` | `cmd_db` | `aop_cmd_db_region` | `0x80860000` |
| `soc_mpss_mem` | `mpss` | `mpss_region` | `0x8bc00000` |
| `modem_ipa_fw_at` | `ipa_gsi` | `ipa_gsi_region` | `0x8b910000` |

So the common tool alone leaves `soc.args` three values short, and two of the three differ from the
built-in defaults (`soc_mpss_mem` and `modem_ipa_fw_at`) -- without them the modem driver would use
the first phone's addresses. `tools/soc-args-cupid.py` reads the tree with this phone's node names
and writes the complete file; CI re-checks it.

**One value the tree does not carry:** `soc_pas_mpss`, the modem's PAS id. No node in this phone's
device tree has a `qcom,pas-id` property -- not the modem, not any other. The driver's built-in value
is the first phone's `4`; this phone's is not in the tree and has to come from the vendor kernel's
modem configuration. Until then the modem driver will start the wrong processor, so this is a real
gap and not a formality.

### The audit

`tools/driver-args-check.py` reads every boot-argument each driver takes and compares it with what
this device provides (`soc.args`, `metal.args`, the config fragment). Of 189 arguments across 35
driver files, 13 are `soc_*` and 11 of those are provided.

The two that are not:

| Argument | Driver | Why it is not a gap |
|---|---|---|
| `soc_smem_size` | `hakios.socinfo.c` | its documented default is `0x200000`, and this phone's `smem_region` is exactly 2097152 bytes -- the default is right |
| `soc_pas_mpss` | `hakios.mpss.c` | **a real gap** -- see above; the tree does not carry it and the built-in value is the first phone's 4 |

So of the 13 `soc_*` arguments the drivers read, the only one that would silently take the wrong
value is the modem's PAS id.

---

## The addresses the drivers carry

`tools/driver-addresses.py` reads every `#define` that looks like a physical address out of the
common repository's drivers and looks each one up in this phone's device tree. 29 driver files, 155
address constants, 37 found in the tree, 118 not.

**An address the driver carries and the tree does not have is not proof of a bug** -- the driver may
compute it, or the block may be outside the tree. But the ones below are the first phone's constants
pointing at blocks this phone puts elsewhere, and each is a silent wrong register until it is fixed.

| Driver | Constant | First phone | This phone |
|---|---|---|---|
| `hakios.adsp.c` | `ADSP_MEMORY` | `0x86700000` | `0x9fd00000` (`adsp_region`) |
| `hakios.camera.c` | `CAMCC_PHYS` | `0x0ad00000` | `0x0ade0000` |
| `hakios.camera.c` | `CSID_PHYS` | `0x0acc8000` | `0x0acb7000` |
| `hakios.camera.c` | `IFE_PHYS` | `0x0acc4000` | `0x0ac62000` |
| `hakios.camera.c` | `RSC_PHYS` | `0x18220000` | `0x17a20000` |
| `hakios.cpufreq.c` | `EPSS_PHYS` | `0x18591000` | `0x17d91000` |
| `hakios.goodix.c` | `RSC_PHYS` | `0x18220000` | `0x17a20000` |
| `hakios.mpss.c` | `MPSS_MEMORY_DEFAULT` | `0x8b800000` | `0x8bc00000` (already in `soc.args`) |
| `hakios.mpss.c` | `RMTFS_BUFFER_PA_DEFAULT` | `0x9c700000` | needs `modem_buffer=` |
| `hakios.pmic.c` | `ARB_CNFG_PHYS`, `ARB_OBSERVER_PHYS` | `0x0c40a000`, `0x0e600000` | not in the tree |
| `hakios.adreno.c` | `GPU_CHIP_ID` | `0x06030500` (Adreno 642L) | the Adreno 730 |
| `hakios.wifi.c` | `WPSS_MEMORY` | `0x9ae00000` | the QCA6490's own |

The ones that **match**, and so need nothing:

| Driver | Constant | Value |
|---|---|---|
| `hakios.thermal.c` | `REFERENCE_TM0`, `REFERENCE_TM1` | `0xc263000`, `0xc265000` |
| `hakios.ufshc.c` | `UFSHC_PHYS` | `0x01d84000` |
| `hakios.pmic.c` | `ARB_CORE_PHYS` | `0x0c440000` (this phone's SPMI register 3) |
| `hakios.speaker.c`, `hakios.goodix.c` | `GCC_PHYS` | `0x00100000` |
| `hakios.mpss.c` | `IPA_IMEM_DEFAULT` | `0x14600000` |

**What this corrects in the matrix above:** "reusable" there meant the driver talks to a
SoC-family-generic block, not that it runs unchanged. Every driver carries the first phone's
constants; the audit above is the check that says which of them this phone shares.
