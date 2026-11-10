# UEFI for cupid

The Xiaomi 12's platform for HakiOS's UEFI (`uefi/` of the common repository: Mu-Silicium with HakiOS's changes and banner).
It is modelled on `negroni` (the OnePlus 10 Pro, the same `WaipioPkg` SoC package) and on `redwood` (HakiOS's own boot path).

**Status: scaffold, not built, not run.** Nothing here has been compiled or started. What is real and what is not:

| Part | State |
|---|---|
| `Platforms/Xiaomi/cupidPkg` | the structure and the SoC paths are right; the memory map's HakiOS regions are a provisional choice (below) |
| `Resources/DTBs/cupid.dtb`, `FdtBlob/sm8450-xiaomi-cupid.dtb` | the phone's own tree, from `sm8450-mainline/fdt` |
| `Silicium-ACPI/Platforms/Xiaomi/cupid/AcpiTables.inf` | the SoC's tables (`Waipio`); a device DSDT is still needed |
| `Binaries/cupid` | **absent**: the vendor's UEFI drivers, extracted from your own phone (the common `uefi/README.md` says how) |
| the display, touch and PCIe drivers | **absent**: they are the vendor's binaries above, plus a PCIe driver for the QCA6490 |

What is here, in `files/`:

- `Platforms/Xiaomi/cupidPkg`: the memory map and the driver list;
- `Resources/Configs/cupid.toml`, `Resources/DTBs/cupid.dtb` (the device tree);
- `Silicium-ACPI/Platforms/Xiaomi/cupid/AcpiTables.inf`: the ACPI tables the loader leaves for the kernel;
- `Binaries/cupid`: the vendor's UEFI drivers, **not tracked**: you make this directory yourself from your own phone
  (`uefi/README.md` says how); `files/Binaries/cupid/README.md` is kept for the patches applied to them.

```sh
devices/cupid/uefi/apply.sh     # = uefi/apply.sh cupid
```

The build and the vendor's drivers: [uefi/README.md](../../../uefi/README.md).

## The memory map's provisional part

The vendor's reservations in `Library/MemoryMapLib/MemoryMapLib.c` are read from the phone's own tree (`/reserved-memory`).
The regions HakiOS adds for itself -- the UEFI FD, its stacks and heaps, the kernel and the XNU payload -- are placed in the
gap the tree leaves after `adsp` (0xA2E00000-0xA6B80000), with the FD at **0xA2E00000**. That address is a choice, not a
measurement: confirm it against the phone's own memory map (the vendor's UEFI, or a boot log) before the first run. The XNU
payload at 0xF0000000 is HakiOS's own, from `BootShim.S`, and is fixed.
