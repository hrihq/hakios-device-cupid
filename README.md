# Device: Cupid based on Qualcomm Technologies, Inc SM8450 (cupid)

Made by `tools/new-device.py` on 2026-11-10, from the file cupid.dtb. Edit it as the port goes.

| What | Value |
|---|---|
| Board (the tree's `model`) | Cupid based on Qualcomm Technologies, Inc SM8450 |
| Compatible | `qcom,waipio-mtp qcom,waipio qcom,mtp` |

## The SoC addresses

**This tree differs from the reference phone's** in 7 value(s) and lacks 4: `soc_ipa_base`, `soc_gsi_base`, `soc_ipcc`, `soc_rsc`, `soc_ipa_stream`, `soc_ipa_stream_uc`, `soc_ipa_fw`, `soc_cmd_db`, `soc_mpss_mem`, `modem_ipa_fw_at`, `soc_pas_mpss`. Those are this phone's own addresses; `soc.args` carries them to the kernel and the run scripts add the file to the command line.

| Argument | Value | Against the reference |
|---|---|---|
| `soc_ipa_base` | `0x3e40000` | **differs from the reference** (`0x1e40000`) |
| `soc_gsi_base` | `0x3e04000` | **differs from the reference** (`0x1e04000`) |
| `soc_ipcc` | `0xed18000` | **differs from the reference** (`0x408000`) |
| `soc_aoss` | `0xc300000` | the same as the reference |
| `soc_rsc` | `0x17a20000` | **differs from the reference** (`0x18220000`) |
| `soc_apps_smmu` | `0x15000000` | the same as the reference |
| `soc_cmd_db` | `(not found)` | **missing**: the tree has no node this was read from; see the table in devices/redwood/README.md |
| `soc_mpss_mem` | `(not found)` | **missing**: the tree has no node this was read from; see the table in devices/redwood/README.md |
| `modem_ipa_fw_at` | `(not found)` | **missing**: the tree has no node this was read from; see the table in devices/redwood/README.md |
| `soc_smem` | `0x80900000` | the same as the reference |
| `soc_imem` | `0x14600000` | the same as the reference |
| `soc_ipa_stream` | `0x5c0` | **differs from the reference** (`0x480`) |
| `soc_ipa_stream_uc` | `0x5c2` | **differs from the reference** (`0x482`) |
| `soc_pas_mpss` | `(not found)` | **missing**: the tree has no node this was read from; see the table in devices/redwood/README.md |
| `soc_pas_ipa` | `0xf` | the same as the reference |
| `soc_ipa_fw` | `ipa_fws` | **differs from the reference** (`yupik_ipa_fws`) |

`soc.args` is what `tools/soc-args.py` read out of the tree; `pull-soc.sh` makes it again from the phone on
adb. The run scripts add it to the kernel command line. Where each argument comes from in the tree:
`devices/redwood/README.md`.

## What is this phone's own

The kernel, loader and user space know nothing about a phone: addresses, interrupts, rails and firmware
come from its tree and its Android. What is written for one phone is the list below. The head of each file
says where its numbers came from; that is the map of what to rewrite.

- [ ] **UEFI**: the firmware that starts the loader: devices/redwood/uefi/ is a port of Mu-Silicium; the vendor's drivers are extracted from your own phone (uefi/README.md)
- [ ] **Display, buttons, touch**: drivers/input/hakios.input.c, hakios.buttons.c, hakios.goodix.c (the reference phone's controller; another phone has another)
- [ ] **Storage**: hakios.ufs.c and hakios.ufshc.c (UFS); a phone with eMMC needs another driver
- [ ] **CPU clocks**: hakios.cpufreq.c
- [ ] **GPU**: hakios.adreno.c (Adreno 642L here: another generation needs its own firmware and registers)
- [ ] **Wi-Fi**: hakios.wifi.c, hakios.lx.c and wifi/lx/ (the WCN6750 radio of the reference phone)
- [ ] **Audio and battery**: hakios.adsp.c, hakios.audio.c, hakios.sound.c, hakios.speaker.c, hakios.mic.c, hakios.battery.c
- [ ] **Cellular**: hakios.mpss.c, hakios.qmi.c, hakios.nas.c, hakios.ipa.c, hakios.cell.c; soc.args carries the addresses, the IPA layout is for IPA 4.11 (docs/cellular.md)
- [ ] **Haptics and cameras**: hakios.haptic.c, hakios.camera.c

## Configuration

The kernel's settings are layered the way an Android kernel's are: the common kernel, the SoC's, this phone's
(`docs/configs.md`). Two short files make this phone a configuration:

    configs/cupid.config          CONFIG_DEVICE="cupid"   and whatever is true of this phone only
    configs/cupid_defconfig       #include common_defconfig
                                   #include <the SoC's fragment: sm8450.config for the SM8450 family>
                                   #include cupid.config

Then `make cupid_defconfig`. Turn on only what this phone has been shown to do; `tools/hakios-config.py check` says what the
choice needs.

The drivers are part of the configuration too (`docs/drivers-config.md`): every one is built unless a configuration leaves it out,
and the addresses, pins and rails in each are the reference phone's. Leave out in `configs/cupid.config` what has not been
ported to this phone yet (`# CONFIG_HAKIOS_GOODIX is not set`, ...; `configs/qemu_defconfig` leaves out all of them), and put
each one back when it has been made to work here. `tools/hakios-config.py show` lists what is built in.

## Firmware

Pulled from your own phone, never committed: `devices/redwood/pull-firmware.sh`, or
`pull-firmware-root.sh` where the firmware is readable by root only. Check with `make doctor`.

## Before you open a pull request

`tools/provenance-check.py` must pass: no vendor firmware, no UEFI drivers, no Apple files in the tree.

## The repository

A HakiOS device repository: what is true of this device and of no other. The kernel, the loader, the drivers and the tools are
the common repository's; the sm8450 family's facts are in `soc/`, carried with the device. How the three are put together:
[docs/porting/repositories.md](https://github.com/oosexgang/hakios-xnu-kernel/blob/main/docs/porting/repositories.md).

| File | What |
|---|---|
| `metal.args` | what `tools/metal-run.sh` gives this phone: its cores, its panel's rate, the threads that copy frames, the touch poll |
| `device.conf` | what the device is, and how far each part of it works: its page in the documentation is made from it |
| `configs/cupid_defconfig` | the common kernel, the SoC's fragment, this device's: `make cupid_defconfig` |
| `configs/cupid.config` | what is this device's own: the drivers built in, the arguments it needs |
| `soc/` | its SoC family's layer (sm8450): `soc.conf`, `configs/sm8450.config`, the SoC's drivers; carried here so that this one repository is all the device needs |
| `drivers/` | drivers of its own, if it needs any (`drivers/<subsystem>/conf`, as in the common repository) |

Every phone driver of the common repository is left out to begin with: their addresses and pins are the phone they were written
for. Put one back in `configs/cupid.config` when it has been made to work here, and say so in `device.conf`.

Check with `tools/hakios-device.py check cupid`.

## Status

**Scaffold. Nothing is built, nothing is run, no hardware has been touched.** The configuration holds together
(`tools/hakios-device.py check cupid` passes) and builds only the SoC-identity driver and QEMU's own; every phone
driver is left out.

| Step | State |
|---|---|
| Device tree, SoC addresses | read from the phone's own tree (`soc.args`, 12 of 16 `soc_*` found; the 4 missing are the modem's) |
| SoC layer `sm8450` | `socinfo` only; `cpufreq`, `thermal` and `pmic` need this SoC's own values |
| UEFI platform `cupidPkg` | scaffold: the SoC package (`WaipioPkg`) and the phone's own reservations are real; the FD base and the ACPI DSDT are not |
| Vendor UEFI drivers | absent, from the phone's own `xbl` |
| Drivers | none ported |
| GPU (Adreno 730) | facts read from the phone's tree and checked (`docs/gpu-facts.txt`); the register map verified against Linux; no driver code |

The order the documentation gives, and what each needs: [Port a device](https://github.com/oosexgang/hakios-xnu-kernel/blob/main/docs/porting/index.md).

## GPU

The GPU is a different generation from the reference phone's, so it is a second implementation of the
same step framework rather than a set of changed constants. What is known and what is not, the
register map with its sources, the licences, and the phased plan:
[Adreno 730 compatibility report](docs/gpu-adreno-730.md). The facts the port starts from are
`docs/gpu-facts.txt`, made from the phone's own tree by `tools/gpu-facts.py` and checked in CI.
The address layer -- every block, size, interrupt, clock, regulator, power level and stream,
plus the register offsets -- is `gpu/a730_resources.json`, which generates
`gpu/hakios.adreno-a730.h` and is checked against the tree and Linux's register dumps:
[address layer](docs/gpu-address-layer.md). It is data, not a driver; `drivers/gpu/` is untouched.
The firmware those facts point at -- `gmu_gen70000.bin`, `a730_sqe.fw`, `a730_zap.mbn` -- is
described and checked by `gpu/firmware/manifest.json` and `tools/gpu-firmware-check.py`:
[firmware dependencies](docs/gpu-firmware.md).
