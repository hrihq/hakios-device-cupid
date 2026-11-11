# The Xiaomi 12 (cupid) Adreno 730's address layer

This directory is **not a driver**. It holds the device's GPU facts in a form the port can include, and
the tool that checks them. Nothing here is compiled into the kernel, and `drivers/gpu/` -- the existing
Adreno 642L support -- is untouched.

| File | What |
|---|---|
| `a730_resources.json` | the configuration: every block, size, interrupt, clock, regulator, power level and stream, each with the device-tree node it came from |
| `hakios.adreno-a730.h` | **generated** from the configuration; the header the port will include |
| `../tools/gpu-address-check.py` | checks the configuration against the phone's device tree and Linux's register dumps, and generates the header |

Read [../docs/gpu-address-layer.md](../docs/gpu-address-layer.md) for what is known, what is uncertain,
and what Phase 2 deliberately leaves alone.

```
python3 tools/gpu-address-check.py --config gpu/a730_resources.json \
    --dtb uefi/files/Resources/DTBs/cupid.dtb \
    --linux <dir with a6xx.xml, adreno_common.xml, a6xx_gmu.xml> \
    --check-header gpu/hakios.adreno-a730.h
```

`--emit-header` writes the header; CI fails if the committed header does not match.
