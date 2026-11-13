# Device facts for the Xiaomi 12 (cupid)

**Status: facts read out of the phone's own device tree, and nothing more.** No driver has been
written from them and none has been run. This document summarises what the tree says per subsystem;
the full, generated, machine-checked list is `docs/device-facts.txt`, produced by
`tools/device-facts.py` from `uefi/files/Resources/DTBs/cupid.dtb` and re-checked in CI.

```
python3 tools/device-facts.py --out docs/device-facts.txt
python3 tools/device-facts.py --check docs/device-facts.txt   # CI
```

Thirteen subsystems, 76 anchor nodes. Every line names the node it came from, so a fact that moves is
caught rather than discovered on the phone.

---

## display -- the SDE pipeline and the panel

| Block | Address | Notes |
|---|---|---|
| SDE/MDP core (`qcom,sde-kms`) | `0x00ae00000` (0x84000), `0x00aeb0000` (vbif), `0x00aeac000` (regdma) | irq 83; clocks include `core_clk`, `vsync_clk`, `lut_clk`, `rot_clk` |
| DSI controller 0 (`qcom,dsi-ctrl-hw-v2.6`) | `0x00ae94000` | plus `disp_cc_base` and `mdp_intf_base` |
| DSI controller 1 | `0x00ae96000` | |
| DSI PHY 0 / 1 (`qcom,dsi-phy-v4.3`) | `0x00ae94400`, `0x00ae96400` | pll and dynamic-refresh registers |
| DisplayPort (`qcom,dp-display`) | `0x00ae90000` + `0x0088eaa00` | |
| SDE RSCC (`qcom,sde-rsc`) | `0x00af20000` | its own RPMh resource controller |
| display clock controller (`qcom,waipio-dispcc`) | `0x00af00000` | |

The panel itself is described by `qcom,dsi-display-primary` / `-secondary` and the panel power
supplies (`dsi_panel_pwr_supply*`, `display_gpio_regulator@1..2`). A driver needs: the MDP register
blocks, the DSI controllers and PHYs, the display clocks, the panel power sequence and the panel's
own init commands -- **the panel init commands are not in the device tree and must come from the
vendor kernel or the panel driver.**

## touch

| Node | What |
|---|---|
| `/soc/ssusb@a600000/synaptics_tcm@20` | the Synaptics touch controller (`synaptics,tcm-i2c`), on the SSUSB node |
| `/soc/xiaomi_touch` | the Xiaomi touch wrapper (`xiaomi-touch`) |
| `/soc/fingerprint_goodix` | the Goodix fingerprint sensor (`goodix,fingerprint`) |

The touch controller's I2C address, its interrupt and its power sequence are in the tree; the firmware
and the init sequence are not.

## USB

| Block | Address | Notes |
|---|---|---|
| USB 3 wrapper (`qcom,dwc-usb3-msm`) | `0x00a600000` (0x100000) | clocks: `core_clk`, `iface_clk`, `bus_aggr_clk`, `utmi_clk`, `sleep_clk` |
| DWC3 core (`snps,dwc3`) | `0x00a600000` (0xd93c) | irq 133 |
| high-speed PHY (`qcom,usb-hsphy-snps-femto`) | `0x0088e3000` | `vdd-supply` = `pm8350-l5` |
| SuperSpeed PHY (`qcom,usb-ssphy-qmp-dp-combo`) | `0x0088e8000` | `vdd-supply` = `pm8350-l1` |
| GSI DMA (`qcom,msm_gsi`) | -- | the DMA engine the USB and other peripherals use |
| DMA heaps (`qcom,dma-heaps`) | -- | 12 named heaps, including `qseecom`, `secure_cdsp`, `display` |

## Wi-Fi and Bluetooth (QCA6490)

| Node | What |
|---|---|
| `/soc/qcom,cnss-qca6490@b0000000` | the QCA6490 host interface (`qcom,cnss-qca6490`), reg `0x0b0000000` (0x10000) for `smmu_iova_ipa`, clock `rf_clk` |
| `/soc/bt_qca6490` | the Bluetooth interface (`qcom,qca6490`), clock `ref3_clk` |
| `/reserved-memory/cnss_wlan_region` | the WLAN reserved region (`shared-dma-pool`) |

The QCA6490 needs its own firmware and device blobs (`wlanmdsp.mbn`, the regulatory database, the
board data). **None of those are in the device tree**; they come from the phone's firmware partition.

## audio

The audio subsystem is the LPASS: the DAI nodes (`qcom,msm-dai-q6`), the PCM graphs
(`qcom,msm-pcm`, `-low-latency`, `-ultra-low-latency`, `-voice`), the routing
(`qcom,msm-pcm-routing`), the packet core (`qcom,audio-pkt-core-platform`), the SPF core platform
(`spf_core_platform`) and the codec, a **WCD938x** with `wsa883x` speaker amplifiers on the soundwire
bus, under `/soc/spf_core_platform/lpass-cdc/`. The ADSP reserved region is `0x9fd00000` and its heap
is a `shared-dma-pool`.

A driver needs the LPASS register blocks, the ADSP and its firmware, the soundwire bus, the codec and
the amplifier init sequences. **The amplifier and codec init sequences are not in the tree.**

## battery and power

| Block | Address | Notes |
|---|---|---|
| SPMI bus 0 / 1 (`qcom,spmi-pmic-arb`) | `0x00c42d000`, `0x00c432000` | five register regions each |
| RPMh resource controller (`qcom,rpmh-rsc`) | `0x017a00000` | four drivers, irqs 3-5 |
| AOSS power controller (`qcom,waipio-aoss-qmp`) | `0x00c300000` | |
| battery charger (`qcom,battery-charger`) | -- | under `qcom,pmic_glink` |
| UCSI (`qcom,ucsi-glink`) | -- | the Type-C manager |
| alt-mode (`qcom,altmode-glink`) | -- | |

The PMICs are on SPMI; the regulators are under `/soc/rsc@17a00000/rpmh-regulator-*`. **The charger's
firmware and the battery profile are not in the tree.**

## storage

| Block | Address | Notes |
|---|---|---|
| UFS host controller (`qcom,ufshc`) | `0x001d84000` (0x3000), `0x001d88000` (ICE), `0x001d90000` (ICE hwkm) | irq 265; nine clocks |
| UFS PHY (`qcom,ufs-phy-qmp-v4-waipio`) | `0x001d87000` | nine clocks |
| SD host (`qcom,sdhci-msm-v5`) | `0x008804000` | irqs 207, 223; **status: disabled** |

The UFS device is a UFS 3.1 part; the tree does not name the manufacturer or the geometry. A driver
needs the host controller, the PHY and the reference clocks.

## camera

| Block | Address |
|---|---|
| camera bus performance adjuster (`qcom,cam-cpas`) | `0x00ac13000` |
| camera SMMU (`qcom,cam_smmu`) | -- |
| camera clock controller (`qcom,waipio-camcc-v2`) | `0x00ade0000` |
| CSI receiver 0 (`qcom,csid680`) | `0x00acb7000` |
| video front end 0 (`qcom,vfe680`) | `0x00ac62000` |
| byte stream processor (`qcom,cam-bps680`) | `0x00ac2c000` |
| image processing engine (`qcom,cam-ipe680`) | `0x00ac42000` |
| image control processor (`qcom,cam-icp`) | -- |
| video codec (`qcom,msm-vidc`) | `0x00aa00000` |
| camera reserved region | `0x9f500000` |

The sensors themselves are I2C devices under the camera graph; their init sequences and the ISP
firmware are not in the tree.

## modem and the other remote processors

| Node | Address |
|---|---|
| modem (`qcom,waipio-modem-pas`) | `0x04080000` |
| ADSP (`qcom,waipio-adsp-pas`) | `0x03000000` |
| CDSP (`qcom,waipio-cdsp-pas`) | `0x32300000` |
| SLPI (`qcom,waipio-slpi-pas`) | `0x02400000` |
| SPSS (`qcom,waipio-spss-pas`) | `0x1880000` |
| modem reserved region | `0x8bc00000` |

Each remote processor needs its own firmware image from the phone. **The firmware is not in the
tree.**

## sensors

| Node | What |
|---|---|
| `/soc/qcom,msm-ssc-sensors` | the SSC sensor hub (`qcom,msm-ssc-sensors`) |
| `/soc/qmi-ts-sensors` | the QMI thermal sensors, with `cdsp` and `modem` children |
| `/soc/thermal-sensor@c263000`, `@c265000` | the two TSENS blocks (`qcom,tsens-v2`), 16 sensors each |

The motion sensors (accelerometer, gyroscope, magnetometer, proximity, pressure) are I2C devices;
**the tree does not name them** -- they come from the vendor's board configuration.

## soc-fabric

| Block | Address | Notes |
|---|---|---|
| global clock controller (`qcom,waipio-gcc`) | `0x00100000` (0x1f4200) | every clock in the SoC |
| debug clock controller (`qcom,waipio-debugcc`) | `0x00000000` | |
| GIC (`arm,gic-v3`) | `0x017100000` | |
| display RPMh (`qcom,sde-rsc`) | `0x00af20000` | |
| GPI DMA 0/1/2 (`qcom,gpi-dma`) | `0x000800000`, `0x000900000`, `0x000a00000` | |
| RNG (`qcom,msm-rng`) | `0x0010c3000` | |
| crypto engine (`qcom,qcedev`) | `0x001de0000` | |
| secure application loader (`qcom,qseecom`) | `0x00c1700000` | |

---

## What the tree cannot tell you

Every subsystem above has the same shape: the tree gives the blocks, the clocks, the interrupts, the
supplies and the DMA channels. It does **not** give:

* firmware images (GPU, ADSP, CDSP, modem, SLPI, SPSS, WLAN, ISP, codec, charger);
* init sequences and tuning data (panel, touch, camera sensors, speaker amplifiers);
* device identity (UFS geometry, the camera sensors, the motion sensors);
* anything about whether a block works when it is written to.

Those come from the phone's firmware partitions and the vendor kernel. Until the phone is available,
the facts above are the whole of what can be known -- and the check that keeps them honest is in CI.
