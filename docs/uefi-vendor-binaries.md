# Vendor UEFI binaries: what the cupid port needs

**Status: analysis and tooling only. No binary has been extracted, no driver has been built, and the
firmware volume does not link without these.** This document records what the port needs, where the
binaries come from, and what the tools do and do not do.

---

## Why the port stops here

Mu-Silicium drives the phone's hardware with **Qualcomm's own DXE drivers**: clocks, RPMh, SPMI,
TLMM, UFS, USB, the TrustZone drivers and the rest. They are proprietary and are not in any
repository. Without them the firmware volume cannot link, so there is no UEFI, so there is no
`xnuloader`, so there is no kernel.

The cupid platform today names none of them: its `cupid.dsc` pulls in `WaipioPkg.dsc.inc` and its own
`AcpiTables.inf`, and the firmware volume stops there. Adding the drivers needs the phone's
`uefi.img`.

## Where they come from

The phone's own `uefi.img` (the UEFI firmware volume, inside the `xbl` / firmware partitions) holds
them as FFS files inside a Firmware Volume. The reference ports take them from the stock OTA image,
unpack the volume, and place one directory per driver under `Binaries/<board>/`.

The same-SoC reference is the OnePlus 10 Pro (negroni, SM8450). Its platform names **46 vendor
drivers**; that list was read out of its own `.inc`/`.fdf` files, not copied by hand, and is committed
here as `uefi/firmware/vendor-binaries.json`.

### The reference list, by group

| Group | Drivers |
|---|---|
| power and clocks | ClockDxe, VcsDxe, RpmhDxe, CmdDbDxe, PwrUtilsDxe, NpaDxe, PmicDxe, DDRInfoDxe |
| buses and pin control | SPMIDxe, TLMMDxe, I2CDxe, SPIDxe, GpiDxe, SmemDxe, ICBDxe, ShmBridgeDxe, GLinkDxe, IPCCDxe, HWIODxe |
| storage and disks | UFSDxe, DiskIoDxe, PartitionDxe, UsbMsdDxe |
| USB | XhciDxe, XhciPciEmulationDxe, UsbfnDwc3Dxe, UsbConfigDxe, UsbDeviceDxe, UsbInitDxe, UsbPwrCtrlDxe, UCDxe |
| TrustZone | TzDxeLA, ScmDxeLA, PILDxe, PILProxyDxe |
| thermal and misc | TsensDxe, ChipInfoDxe, PlatformInfoDxe, EnvDxe, ULogDxe, RNGDxe, DALSYSDxe, HALIOMMUDxe |
| display | DisplayDxe, CPRDxe |
| SD (board-dependent) | SdcDxe, SdccDxe |

`PmicDxe`, `SdcDxe`, `SdccDxe`, `SPSSDxe` and `DisplayDxe` are board-dependent: which of them cupid
needs is decided by the phone's own device tree and firmware, not by this list.

## The tools

| Tool | What it does |
|---|---|
| `tools/uefi-fv-unpack.py` | Pure-Python Firmware Volume / FFS unpacker. Reads the `_FVH` header, walks the FFS files (24- and 32-byte headers), walks the sections, and writes one directory per file GUID with `pe32.efi`, `depex.bin`, `raw.bin`, `name.txt` and `index.txt`. Handles PE32/TE/PIC, RAW, DXE_DEPEX, VERSION, UI, FREEFORM, COMPRESSION type 0, GUID_DEFINED with LZMA, and a gzip payload (reported as a heuristic). Reports the rest as unsupported rather than skipping it. `--self-test` builds synthetic volumes and checks the tool against them. |
| `tools/uefi-binaries-check.py` | `--reference DIR --board NAME` reads a platform's own `.inc`/`.fdf` files and emits the vendor INF list as a manifest. `--check DIR` checks a `Binaries/<board>` tree against a manifest and reports what is missing. `--self-test` proves the checker accepts a complete tree and rejects one with a file missing. |
| `uefi/firmware/vendor-binaries.json` | The reference manifest: 46 drivers, read from the negroni platform, with a role for each. |

```
# what the workflow looks like when the phone is available
adb pull /dev/block/by-name/xbl_a uefi.img        # or the firmware partition that holds the FV
python3 tools/uefi-fv-unpack.py --fv uefi.img --out out/uefi/modules
python3 tools/uefi-binaries-check.py --manifest uefi/firmware/vendor-binaries.json \
    --check uefi/files/Binaries/cupid
```

## What the FD is, and what it needs

The cupid firmware volume is a fixed region at `0xA2F00000`, `0x300000` bytes (see
`uefi/files/Resources/Configs/cupid.toml`), built from `FVMAIN_COMPACT`. Its size is not the
constraint: the contents are. The FDF names modules; the vendor modules are the ones that cannot be
satisfied from Mu-Silicium's own source tree, and every one of them is a binary that must be
extracted, not written.

## What cannot be checked without the phone

1. **Which of the 46 drivers cupid actually needs.** The negroni list is the same SoC, not the same
   board. Cupid's own list must be derived from its own platform files once those name the drivers.
2. **Whether the extracted binaries are the right build.** The reference ports port patches from one
   vendor build onto another; cupid's `uefi.img` build is its own, and a driver from a different
   build may or may not work. Nothing here decides that.
3. **Whether the volume links.** A missing or mismatched driver is a link error, not a runtime one,
   and no source can predict it.
4. **Whether the drivers do what the platform expects at runtime.** That needs the phone.

## The order this has to happen in

1. pull the phone's `uefi.img` (read-only, nothing is flashed);
2. unpack it, and see which FFS files the volume actually holds;
3. write cupid's own `.inc` list from what the phone's volume provides, derived from cupid's device
   tree and platform -- never copied from negroni;
4. place the binaries under `Binaries/cupid`, run the checker until it reports none missing;
5. build the volume, and only then see whether it links.

Steps 1 and 2 need the phone. Steps 3 to 5 are blocked on them.
