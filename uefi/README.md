# UEFI for cupid

The Xiaomi 12's platform for HakiOS's UEFI (`uefi/` of the common repository: Mu-Silicium with HakiOS's changes and banner).
It is modelled on `negroni` (the OnePlus 10 Pro, the same `WaipioPkg` SoC package) and on `redwood` (HakiOS's own boot path).

**Status: the platform's configuration is validated in CI; the firmware itself has not been built or started.**
`.github/workflows/build-uefi.yml` runs on every push and on `workflow_dispatch`: it assembles the tree,
validates it (37 checks, all passing) and uploads the report. The build step is skipped until the vendor's
UEFI drivers are supplied, because they are the phone's own. What is real and what is not:

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

## Building in GitHub Actions (no local WSL2)

`.github/workflows/build-uefi.yml` builds the platform on an Ubuntu GitHub-hosted runner, so no local
Linux, WSL2 or macOS is needed. It pins the runner image, Mu-Silicium's `BASE` commit, the `hakios-uefi`
revision and the action revisions; it clones shallow, applies HakiOS's patch and this platform to a local
copy (upstream is never modified), validates the DTB, the ACPI tables and the platform configuration, and
then builds `cupidPkg`.

**A green run means the platform compiles. It is not a boot test** — no boot on a phone is claimed.

### Trigger it manually

1. Open the repository on GitHub -> **Actions** -> **build-uefi-cupid** -> **Run workflow**.
2. Choose the branch (`main`) and fill in the inputs:

   | Input | Required | What |
   |---|---|---|
   | `vendor_binaries_url` | for a full build | URL of a `tar.gz` whose root is the contents of `Binaries/cupid/` |
   | `vendor_binaries_sha256` | no | SHA-256 of that archive, verified before it is used |
   | `build_target` | no | `RELEASE` (default) or `DEBUG` |

3. Press **Run workflow**.

Without `vendor_binaries_url` the workflow still runs: it assembles the tree, validates the platform and
uploads `cupid-uefi-logs` (the validation report and the build log). The build step itself is skipped,
because the vendor's drivers are not in the repository; the run's summary says so.

To supply the drivers without a public URL, set a repository secret named `VENDOR_BINARIES_URL` and run
the workflow with no inputs.

### Where the drivers come from

They are the vendor's, from your own phone: extract them from the `xbl` partition with UEFIReader, as the
common repository's `uefi/README.md` describes. Never commit them, and never put them in a public URL —
`tools/provenance-check.py` fails the build if they come back into the tree, and the workflow deletes them
from the workspace before any artifact is uploaded. The `cupid-uefi-binaries` artifact holds only what the
open sources built: `SILICIUM_UEFI.fd`, its `.gz`, and the boot image.

### Artifacts

| Artifact | Contents |
|---|---|
| `cupid-uefi-logs` | `validate.txt`, `validate.json`, `build.log` (always uploaded, also on failure) |
| `cupid-uefi-binaries` | the built FD and boot image (only when the vendor drivers were supplied) |

### What a failed run tells you

* `Missing build dependencies` — the runner's toolchain is incomplete; the step prints the `apt-get` line to fix it.
* `Not enough disk space` — shallow clones are already used; the message says what is needed.
* `No vendor UEFI drivers` — the warning tells you how to supply them.
* `validate.py` fails — the validation report names the exact check and file; nothing is built until it passes.
* `build_uefi.py` fails — `cupid-uefi-logs` holds the full compiler output.
