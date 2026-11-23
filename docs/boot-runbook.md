# Cupid boot runbook — first boot

This is the runbook for the first HakiOS boot on the Xiaomi 12. Every command below is
**temporary**: `fastboot boot` streams an image into RAM; nothing is flashed, no partition is
written, and Android stays intact. A reboot returns the phone to Android.

## 1. Artifacts

Built by CI, not fabricated:

| Artifact | CI run | SHA256 |
|---|---|---|
| `SILICIUM_UEFI.fd` | `44197867816` | see run summary |
| `cupid-kernel` | `44213175444` | `914c5fe1ef04d1f1d2e1709a417690824edd8ee81341bf147ad28a150b16d70d` |
| `cupid-loader.efi` | `44213175444` | `827c444d73e7daaab486427c79159facaa0ca3d1f0a2f426392eb2ed07bd8bce` |

The loader was built with `xnuloader/mkidentity.sh --placeholder`: **no Apple identity, no
IPSW**. It can boot the open kernel with an Apple-free ramdisk. It cannot start stock Darwin.
A full iOS user-space boot needs an IPSW 16.5 supplied by the user.

## 2. Put artifacts where `xl` expects them

`xl` runs from the **common** repository (`C:\Users\heri\hakios\hakios-xnu-kernel`):

```bash
cd C:/Users/heri/hakios/hakios-xnu-kernel
cp <artifacts>/cupid-kernel      hakios-kernel
cp <artifacts>/cupid-loader.efi  xnuloader/loader.efi
```

Verify:

```bash
sha256sum hakios-kernel xnuloader/loader.efi
file hakios-kernel    # Mach-O 64-bit arm64 executable
```

## 3. Host tools (Windows / git-bash)

`platform-tools` is not on `PATH` by default. Add it:

```bash
export PATH="$PATH:/c/Users/heri/Downloads/platform-tools"
adb version
fastboot version
```

The phone must be authorized for ADB at least once, or already in fastboot.

## 4. Connect the phone

Cable, then confirm:

```bash
adb devices -l          # expect: cupid 2201123G ... device
fastboot devices        # expect: <serial> fastboot
```

If the phone is in Android, `xl enter` reboots it into fastboot itself.

## 5. Get into the resident loader

```bash
cd C:/Users/heri/hakios/hakios-xnu-kernel
./xl enter
```

`xl enter` builds `usb-payload.bin` from `loader.efi`, wraps it into `xnu-usb.img`, then does
`fastboot boot xnu-usb.img` (twice if needed). Success looks like:

```
xl: loader is up
```

Confirm independently:

```bash
fastboot getvar product    # expect: product: xnuloader
```

`xl enter` is itself the definitive unlock check: a locked bootloader rejects the boot.

## 6. First kernel run — no IPSW

The smallest test exercises the kernel -> loader return path, with no ramdisk:

```bash
./xl selftest
./xl log                   # fetch logs/loader.log from the phone
```

Then a normal run (the default ramdisk is `userland/root.apfs`; set `XL_RAMDISK=userland/hello`
for the tiny raw-syscall program, which boots through mockfs):

```bash
XL_RAMDISK=userland/hello ./xl run
./xl screenshot logs/cupid-first-boot.png
./xl log
```

A framebuffer screenshot is the actual evidence of a boot — a green CI build is not.

## 7. First boot attempt — evidence and result (not yet a boot)

The first attempt on the real phone (serial `341db2b`) did **not** reach the loader. Evidence:

- `fastboot oem device-info` → `Device unlocked: true`, `critical unlocked: true`. Unlock is not the blocker.
- `fastboot boot <image>` → `OKAY` on every attempt; the image is transferred and accepted.
- Vendor UEFI log (`/dev/block/by-name/logfs`, FAT12, `UefiLog1.txt`): `Handling Cmd: download:001dd000`,
  `Handling Cmd: boot`, `Decompressing kernel image total time: 222 ms`, then `Start EBS`. ABL accepted
  and decompressed our kernel and handed off; no loader banner followed. The later `Cmdline:` and
  `initrd size` lines come from `vendor_boot`, not from the boot image.
- Screen stayed black; the phone returned to fastboot only after the key combo.
- The BootShim taken from the CI image carried `FD_BASE=0xA2F00000`. It was changed to `0xA7000000`,
  the PT_LOAD address measured from the phone's own `uefi_a.img`, and the FD was rebuilt in
  [run 44253508613](https://github.com/hrihq/hakios-device-cupid/actions/runs/44253508613). The result
  was unchanged: no display, no loader.

So the failure is inside BootShim / the linked FD, not in transfer, unlock or verification. The FD
links and the platform compiles; neither is a boot test.

### Root cause found afterwards: the payload base was wrong in three places

BootShim does copy the appended `XNUP` payload (HakiOS's `hakios.patch` adds that loop), and
`mkxnuimg-cupid.py` compiled it with `-DPAYLOAD_BASE=0xB0000000`, so the payload really was at
`0xB0000000`. But the consumers were not:

- `XnuLoader.h` in hakios-uefi hard-codes `XNU_PAYLOAD_BASE=0xF0000000` with no `#ifndef` guard,
  and `cupid.dsc` had no `[BuildOptions]` override. The firmware looked for the payload at
  `0xF0000000` — inside waipio's TZ apps carve-out (`0xEA000000-0xF1400000`). Its
  `LogPayload()` / `LogPersistence()` read and write that address at startup.
- `build-kernel.yml` built `cupid-loader.efi` with the default
  `LOADER_CFLAGS=-DPAYLOAD_BASE=0xF0000000ULL`, so the loader looked there too.
- `MemoryMapLib.c` reserved `"XNU Payload"` at `0xF0000000` instead of the `Kernel` window
  containing `0xB0000000`.

A proven same-family port (`cotunjr/hakios-mayfly`, Xiaomi 12S / SM8475) measures
`PAYLOAD_BASE=0xB0000000` and overrides the UEFI base from its DSC. The fix on this branch:

1. device-level `XnuLoader.h` with an `#ifndef` guard (device files are copied last over HakiOS's);
2. `[BuildOptions] *_*_*_CC_FLAGS = -DXNU_PAYLOAD_BASE=0xB0000000ULL` in `cupid.dsc`;
3. `build-kernel.yml` default/fallback `0xB0000000ULL`;
4. remove the bogus `0xF0000000` payload reservation from `MemoryMapLib.c`;
5. `tools/payload-base-check.py`, run in `check-device` and before packing, so the five copies
   cannot drift again.

### Second cause: the shim never copied the payload

`build-silicium.yml` assembles its Mu-Silicium tree by downloading `BootShim.S` and `Makefile`
straight from Project-Silicium, so HakiOS's `hakios.patch` hunk that adds the `XNUP` payload copy
(`#ifdef PAYLOAD_BASE`, in `hakios-uefi/hakios.patch`) was never applied. The rebuilt image's shim
was 112 bytes with no copy loop, so `0xB0000000` held nothing no matter what the payload base said.
The workflow now applies that one hunk (`git apply --include='BootShim/BootShim.S'`) and asserts,
after packing, that the shim contains `movz x5, #0xb000, lsl #16` and that an `XNUP` payload follows
the FD.

The images must be rebuilt after this change. A green rebuild is still not a boot; only a loader
banner or `fastboot getvar product: xnuloader` on the phone is proof.

## 8. Safety

- `fastboot boot` only. **Never** `fastboot flash`.
- No partition is touched. Do not run `xl ramdisk` against a partition; it is a RAM upload.
- Do not change persistent boot configuration (`fastboot set_active`, `flash`, `erase`).
- If anything hangs: `./xl hang` waits for the watchdog and returns to Android; `./xl reboot`
  leaves the loader. Physical power hold is the last resort.
- Disconnecting the cable after the artifacts have been downloaded is safe.

## 8. What is NOT yet validated

- GPU acceleration, display driver, touch, audio, Wi-Fi/BT, camera, battery.
- First boot is expected to use the UEFI framebuffer plus software rendering, like `renoir`.
- `cupid.config` has all phone drivers off. Runtime driver work comes after the first boot.

## 9. U-Boot path (no UART needed)

The site's U-Boot guide (docs/u-boot.md in the common repository) is an alternative boot chain:
ABL fastboot-boots HakiOS's U-Boot, and U-Boot starts the loader from RAM. U-Boot writes its
log to the phone screen and answers `fastboot oem console`, so no serial cable is needed.

- Branch `uboot-cupid` builds it in CI: `.github/workflows/build-uboot.yml`.
- Run 44264429537 is green; artifact `cupid-uboot` holds `hakios-u-boot.img` and `u-boot.bin`.
- The phone's own `uefi/files/Resources/DTBs/cupid.dtb` is converted to a DTS with dtc and used
  as U-Boot's default tree. `CONFIG_SYS_INIT_SP_BSS_OFFSET=0x600000` is required: the default
  1.5 MiB fails `init_sp_bss_offset_check` with this ~780 KiB tree.
- A built image is still not a boot test. Try it with `fastboot boot` only; never flash.

## 9. Bring-up diagnostic: the shim runs, the FD does not

A second image (`shim_diag=-DCUPID_SHIM_BEACON`) paints the ABL splash buffer and then writes
IMEM `restart_reason` 0x77665500 at 0x146AA65C and asks PSCI to reset, before the FD is copied:

- The panel showed the painted colour, so **BootShim runs and the splash buffer ABL leaves at
  0xB8000000 is live**. The boot chain up to the shim is therefore proven; the phone then returned
  to Android by itself, so the reset path works too.
- The same image's FD still produced nothing, and so did the CI carrier image without any payload:
  the failure is in the FD, not in the payload or the handoff into BootShim.

The first response to that is the blob-free platform: `DXE.inc` no longer lists the phone's own DXE
drivers, `RamManagerDxe` is out of the FDF and `PcdDebugPropertyMask` is 0x03. On this SoC family the
vendor's DXE set is a documented dead end (ClockDxe stops the panel scanout, PmicDxe takes a
synchronous abort on SPMI); `Resources/Configs/cupid.toml` now declares
`[vendor_drivers] mode = "none"`, and both `uefi/tools/validate.py` and `tools/uefi-build-check.py`
accept that as a deliberate state instead of an unfinished one.

## 10. Bring-up log: what the phone actually showed (2026-11-18)

Every line below is an observation on the phone, not a build result.

| # | Image | Screen | What it proves |
|---|---|---|---|
| 1 | first packed image (os_version 13 / patch 2026-11) | stayed on the bootloader's logo, then Android | ABL accepted the download and **booted the slot instead**: `logfs` shows `Handling Cmd: download:<size>` then `Booting from slot (_a)` with the ROM's own `Cmdline:` |
| 2 | `shim_diag=-DCUPID_SHIM_BEACON -DCUPID_SHIM_HOLD` (os_version 0) | solid blue, stays | ABL ran **our** image; the panel and the splash buffer at 0xB8000000 are live |
| 3 | `-DCUPID_SHIM_STAGE2` | green ~3 s, then the phone drops off USB and comes back to Android | shim copied FD + payload and handed over; the firmware is what dies |
| 4 | CI carrier `Mu-cupid.img` (no payload at all) | same as 3 | the payload and the packer are not the cause |
| 5 | DEBUG FD instead of RELEASE (mayfly's working image used DEBUG) | same as 3 | not the build target |
| 6 | FD moved to 0xA2F00000, outside the phone's own firmware window (0xA7000000+0x2A0000) | same as 3 | not the FD address either |

Conclusion: the chain is proven up to `br FD_BASE`; everything after it is silent whatever the FD
contains. The next probe is inside the firmware: `-DCUPID_SEC_BEACON` paints **red** in the SEC
entry (`ModuleEntryPoint.S`, before `PlatformAssemblyInitialize`) and **magenta** in `SecMain` after
`PlatformInitialize ()`. Red without magenta localises the death to the firmware's own early setup;
no red at all means the firmware's SEC entry is never reached, and what XBL normally hands it (EL,
stack, DTB, the FV entry) becomes the question.

The vendor log is always the first place to look: `logfs` (`/dev/block/by-name/logfs`, FAT12,
`UefiLog*.txt`, one per boot in cycling slots) read from a root recovery with
`adb exec-out 'dd if=/dev/block/by-name/logfs bs=4096 count=2048 2>/dev/null' > logfs.img`.
`logdump` (HakiOS's own log partition) is all zeros until the loader writes to it.

## 11. The U-Boot path: the documented way to text on the panel

`docs/u-boot.md` in the common repository is the answer to "no UART, and the screen must say
something": ABL starts **Das U-Boot** from RAM, U-Boot writes its console to the panel and answers
`fastboot oem console` with the record of it. That record is machine-readable evidence, and the only
kind this port can collect without a human looking at the phone.

What this device needs for it, all measured here:

| Fact | Value | Where it comes from |
|---|---|---|
| framebuffer ABL leaves live | `0xB8000000`, 1080x2400, stride 4320 | `/reserved-memory/splash_region` in the phone's own tree, and the paint that stayed on the panel |
| payload window | `0xB0000000` + 64 MiB | the waipio family's measured base; `0xF0000000` is inside TZ apps |
| boot-image header | v4, `os_version`/`os_patch_level` 0 | anything else and ABL answers OKAY then boots the slot |
| device tree | the phone's own DTB plus `simple-framebuffer` and `hakios-payload` | an Android tree has no framebuffer node, so a running U-Boot paints nothing (`tools/uboot-dts.py`) |

`u-boot/files/configs/hakios_cupid_defconfig` + `u-boot/files/board/qualcomm/hakios-cupid.env` are
this device's; `uefi/u-boot/hakios.patch`, `cmd/hakios.c` and the Qualcomm USB device protocol come
from `hakios-uefi` at the revision `devices/manifest.conf` pins. Build and verification:

```sh
gh workflow run build-uboot.yml -R hrihq/hakios-device-cupid --ref fix/waipio-payload-base \
   -f payload_base=0xB0000000UL          # -> cupid-uboot artifact: hakios-u-boot.img
verify/uboot_boot.sh                     # fastboot boot, then `fastboot oem console`
```

Status: the image builds and was checked against the header of an image ABL has demonstrably
executed (same `ANDROID!` magic, kernel at `0x1000`, header v4, `os_version` 0; `u-boot.bin` carries
the `ARM\x64` header and prints `U-Boot 2026.07-dirty`; the appended tree carries
`simple-framebuffer`, `hakios-payload`, and USB in peripheral mode). **It has not been booted yet** —
a built image is not a boot, so this section stays at "written, not run" until the panel or the
console record says otherwise.

## 12. U-Boot runs on cupid: the first boot that printed anything

Observed on the phone, 2026-11-18: `fastboot boot` of `hakios-u-boot.img` reaches U-Boot, which paints
its console on the panel and prints text. Nothing was flashed.

What was wrong until then, in order of how much it mattered:

1. **U-Boot's control FDT was the phone's Android device tree** (`EXT_DTB`). That tree is a kernel's
   view and has no `simple-framebuffer` node, so a running U-Boot had nowhere to write and died in
   the first init calls without a word. `docs/u-boot.md` says it plainly: a device tree of its own,
   on top of the upstream SoC's. `u-boot/files/dts/upstream/src/arm64/qcom/sm8450-xiaomi-cupid.dts`
   is that tree (framebuffer at cont_splash_region, payload window at 0xB0000000, keys, UFS, USB as
   a device, the phone's own carve-outs).
2. **Payload base 0xF0000000** - inside the trusted apps' carve-out on this SoC family.
3. **Boot image header v1 with os_version 13** - ABL answers OKAY and starts the slot instead.

The diagnostic path that found it, for the next device: paint the framebuffer from the boot shim
(proves ABL ran our image), from `_main` in assembly, from `board_init_f` in C, and then one band per
early init call - 12 x 200 px with a distinct colour each, so one photograph reads out how far the
firmware got. Two traps met on the way: `board_init_f()` runs **before** U-Boot clears `.bss`, so a
`static` counter there starts as garbage (use `__COUNTER__`); and an early paint loop must not rely on
anything the C environment has not set up yet.

Still open: U-Boot's own USB gadget did not enumerate on the host after the banner, so the loader
(`hakios load`) has not been started yet and `fastboot oem console` has nothing to answer with. That
is the next step, and it is independent of the console, which works.

## 13. First loader boot on cupid: the embedded container

`fastboot boot` of the U-Boot image with the HKUB container **linked into the binary** finally got
past the handoff. Observed on the phone 2026-11-19:

```
[oosexgang] hakios: embedded container 14999552 bytes
[oosexgang] hakios: payload of ... bytes at 0xb0000000
HakiOS logo on the panel
```

Why this works when the ramdisk did not: on this phone ABL does not leave the boot image's ramdisk
anywhere U-Boot can read it. `/chosen` from ABL points at a 27.9 MB vendor ramdisk whose first word
was random (`0x184c2102`), and neither a 16 GB RAM scan nor clamping U-Boot's relocation below the
payload found our HKUB. Linking it in with `.incbin` (u-boot/embed-payload.patch) makes it part of
U-Boot's own relocated image: no ABI handoff, no ramdisk, no USB and no UFS needed to start the
loader. That is the "one image, loader and payload inside" row of docs/u-boot.md, taken one step
further.

The loader can now start; what it does next (kernel boot arguments, XNU drivers, userspace) has not
yet been checked on hardware. Keep that section marked unverified until the next log says.

Update, same session: the phone shows the HakiOS logo and `kernel.ver=...` below it, then stops.
So XNU is entered and has printed its first line; the freeze is inside early kernel init, not in any
bootloader stage. No USB device appeared from the loader, so the kernel log could not be collected
over the cable. The next diagnostic is the exact text after `kernel.ver=` (a close-up photo), then
the device's boot arguments (`soc.args`) and the first driver the kernel starts.

Latest evidence (photo of the panel at about 61 s into the boot, kernel still running):

```
[61.294213] vm_compressor_mode is 2
[61.294...] zone_init: map VI/RO/RW/CENO/GEN0..GEN3/DATA ...
[61.294...] VM_bootstrap_done: maps 163 entries, 500 holes
[61.299032] IOMMU_setownership ENABLED
[61.299041] ATM-subsystem is initialized.
[61.300516] Telemetry: Sampling all tasks once per 1 second
[61.305390] panic_trace: PE_early_debug_enable_trace enter/exit   (not a panic)
[61.306052] RegInitRedirHandler / Requested coredump handler for kernel
[61.306069] Initializing session KDP
[61.317021] iBoot usage: version:8.2.16.658
```

There is no `panic:` line, no `Assertion failed`, and no `SOCDump`. The loader's own watchdog is
not armed on cupid (`wdt_arm()` returns unless the platform is redwood). So XNU gets well past VM
and IOMMU init and the screen then goes dark without any device on USB. Remaining suspects are the
first IOKit drivers (the panel/framebuffer console and USB), and the payload's userland: it is only
the 16 KiB `prebuilt/userland/hello` test executable, not a full Darwin root filesystem. Confirm
with a readable log before changing any of it.

## 14. The resident root was rejected: the window reserve is bigger than the phone's RAM window

Observed 2026-11-19: every image carrying `resident=root.apfs` reset straight back to Android
(`logfs`: download + `Decompressing kernel image` + `Start EBS`, then a slot boot ~8 s later;
`logdump` all zeros). Every image without it ran the kernel to `bsd init` and the familiar dark
screen. Four boots isolate the variable:

| Image | u-boot.bin | resident | boot-image ramdisk | Result |
|---|---|---|---|---|
| CI `6b22724` (hakios-u-boot.img) | 20.7 MB | root.apfs 4 MiB | 19.2 MB HKUB | reset to Android |
| `boot-darwin.img` (same u-boot.bin, packed without ramdisk) | 20.7 MB | root.apfs 4 MiB | none | reset to Android |
| `ab-plat.img` (ub-plat, hello only) | 16.5 MB | none | none | kernel runs |
| `ab-sizeprobe.img` (20.7 MB layout, hello-only container swapped in) | 20.7 MB | none | none | kernel runs, `bsd init` |

So neither the binary size nor the ramdisk is the cause: the `resident` entry is. The loader places
a resident root at `win_base + RESIDENT_RD_OFFSET` (128 MiB) and refuses it unless
`win_size > RESIDENT_RD_OFFSET + RESIDENT_RD_RESERVE` = 128 + 768 = **896 MiB**. `choose_window()`
takes the largest free EFI block clear of the payload window `[0xB0000000, 0xB4000000)`: on cupid
that is at most `0xB4000000..0xEA000000` = 864 MiB, or ~738 MiB below the payload with U-Boot
relocated under the clamped ram_top. Both are < 896 MiB, so the check can never pass here; the
loader prints `resident ... does not fit in the memory window` and returns, and the phone ends up
back in Android. The kernel itself is unaffected: it ran with the same window when no resident was
present, and the reserve is a fit guard, not a subtraction from `dram-size`.

Fix: `kernel/resident-window.patch` lowers `RESIDENT_RD_RESERVE` to 256 MiB (requirement: window
> 384 MiB; margin ~354 MiB in the worst case), applied and asserted in `build-kernel.yml`.
**Written, not run** until a boot with the resident root says otherwise.

Update, same day: the rebuilt image (run `44494411804`, loader with the 256 MiB reserve) booted
twice. Both times the phone stayed up past 160 s / 90 s with no reset to Android — the resident
root is accepted now. The panel showed the kernel's `zone_init` map lines (the same VM stage as
the 61 s log), this time with root.apfs as md0. What rc.darwin does after that is **not yet
verified**: the last lines on the panel have not been read.

## 15. Home screen: assessed, not pursued (RAM-only chosen)

The iOS home screen (SpringBoard) needs the full Darwin userland (`system.apfs`, ~2.5 GB from the
IPSW 16.5 already unpacked in the common repo's `sysimage/`). That is larger than cupid's loader RAM
window (~738-864 MiB), so it cannot travel in the payload: it needs the `darwin` UFS partition, which
does not exist on this phone yet. Creating it is the dual-boot install (`docs/dual-boot.md` in the
common repo): carve 20 GiB from `userdata` — **erases Android's data** — `fastboot -w`, flash the
system volume and `boot_a`, `set_active`. Persistent and destructive. UFS read is also still untested
here, and `darwin-write.py`'s GPT constants are redwood's, not cupid's. The user chose to stay
RAM-only (Android intact), so this path is recorded, not taken. Software rendering could draw the
home screen without the Adreno 730 (QEMU does), but storage — not the GPU — is the gate.
