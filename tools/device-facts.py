#!/usr/bin/env python3
"""Read the Xiaomi 12 (cupid) device tree and emit, per subsystem, the facts a driver needs.

This is the same shape as tools/gpu-facts.py, applied to every subsystem the port has to bring up:
display, touch, USB, Wi-Fi, Bluetooth, audio, battery, sensors, storage, camera, modem, haptics,
buttons, PMIC and the SoC fabric. Each subsystem names its anchor nodes; the tool reads them out of
the phone's own tree and writes docs/device-facts.txt.

The tool records what the tree says: the node path, the compatible string, the register ranges and
their names, the interrupts and their names, the clocks, the supplies, the DMA channels and the
status. It does not interpret them and it does not decide which driver to write.

Usage:
  python3 tools/device-facts.py --dtb uefi/files/Resources/DTBs/cupid.dtb --out docs/device-facts.txt
  python3 tools/device-facts.py --dtb uefi/files/Resources/DTBs/cupid.dtb \
      --check docs/device-facts.txt
"""

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _facts():
    spec = importlib.util.spec_from_file_location("gpu_facts", os.path.join(HERE, "gpu-facts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FACTS = _facts()

SUPPLY_PROPERTIES = (
    "vdd-supply", "vddcx-supply", "vdd_mx-supply", "vdd_mxc-supply", "vdd_cx-supply",
    "vddio-supply", "avdd-supply", "iovdd-supply", "qcom,vddc",
)

# Each subsystem names the nodes it is about. The paths are the phone's own; if the tree moves, the
# check fails and the facts are regenerated -- never hand-edited.
SUBSYSTEMS = [
    ("display", "the SDE display pipeline and the panel", [
        ("/soc/qcom,mdss_mdp@ae00000", "the SDE/MDP core"),
        ("/soc/qcom,mdss_dsi_ctrl0@ae94000", "DSI controller 0"),
        ("/soc/qcom,mdss_dsi_ctrl1@ae96000", "DSI controller 1"),
        ("/soc/qcom,mdss_dsi_phy0@ae94900", "DSI PHY 0"),
        ("/soc/qcom,mdss_dsi_phy1@ae96900", "DSI PHY 1"),
        ("/soc/qcom,dp_display@ae90000", "the DisplayPort output"),
        ("/soc/qcom,sde_rscc@af20000", "the SDE RSCC"),
        ("/soc/clock-controller@af00000", "the display clock controller"),
        ("/soc/qcom,dsi-display-primary", "the primary panel"),
        ("/soc/qcom,dsi-display-secondary", "the secondary panel"),
        ("/reserved-memory/non_secure_display_region", "the display reserved region"),
    ]),
    ("touch", "the touchscreen, the fingerprint sensor", [
        ("/soc/spi@990000/fts@0", "the STM FTS touch controller"),
        ("/soc/ssusb@a600000/synaptics_tcm@20", "the Synaptics TCM on I2C"),
        ("/soc/xiaomi_touch", "the Xiaomi touch wrapper"),
        ("/soc/fingerprint_goodix", "the Goodix fingerprint sensor"),
    ]),
    ("usb", "USB 3 and the PHYs", [
        ("/soc/ssusb@a600000", "the USB 3 controller wrapper"),
        ("/soc/ssusb@a600000/dwc3@a600000", "the DWC3 core"),
        ("/soc/hsphy@88e3000", "the high-speed PHY"),
        ("/soc/ssphy@88e8000", "the SuperSpeed PHY"),
        ("/soc/qcom,msm_gsi", "the GSI DMA engine"),
        ("/soc/qcom,dma-heaps", "the DMA heaps"),
    ]),
    ("wifi-bluetooth", "Wi-Fi and Bluetooth (QCA6490)", [
        ("/soc/qcom,cnss-qca6490@b0000000", "the QCA6490 host interface"),
        ("/soc/bt_qca6490", "the QCA6490 Bluetooth interface"),
        ("/reserved-memory/cnss_wlan_region", "the WLAN reserved region"),
    ]),
    ("audio", "the LPASS audio subsystem and the codec", [
        ("/soc/qcom,msm-dai-q6", "the DAI nodes"),
        ("/soc/qcom,msm-pcm-routing", "the PCM routing"),
        ("/soc/qcom,msm-pcm", "the PCM playback graph"),
        ("/soc/qcom,msm-pcm-low-latency", "the low-latency playback graph"),
        ("/soc/qcom,msm-ultra-low-latency", "the ultra-low-latency playback graph"),
        ("/soc/qcom,msm-pcm-voice", "the voice graph"),
        ("/soc/qcom,audio-pkt-core-platform", "the audio packet core"),
        ("/soc/spf_core_platform", "the SPF core platform"),
        ("/reserved-memory/adsp_region@9fd00000", "the ADSP reserved region"),
        ("/reserved-memory/adsp_heap_region", "the ADSP heap"),
    ]),
    ("battery-power", "the PMIC, the RPMh resources and charging", [
        ("/soc/qcom,spmi@c42d000", "SPMI bus 0"),
        ("/soc/qcom,spmi@c432000", "SPMI bus 1"),
        ("/soc/rsc@17a00000", "the RPMh resource controller"),
        ("/soc/power-controller@c300000", "the AOSS power controller"),
        ("/soc/qcom,pmic_glink/qcom,battery_charger", "the battery charger"),
        ("/soc/qcom,pmic_glink/qcom,ucsi", "the UCSI Type-C manager"),
        ("/soc/qcom,pmic_glink/qcom,altmode", "the alt-mode manager"),
        ("/soc/pmic-pon-log", "the PMIC power-on log"),
    ]),
    ("storage", "UFS and the SD host", [
        ("/soc/ufshc@1d84000", "the UFS host controller"),
        ("/soc/ufsphy_mem@1d87000", "the UFS PHY"),
        ("/soc/sdhci@8804000", "the SD host"),
    ]),
    ("sensors", "the sensor subsystem and the thermal sensors", [
        ("/soc/qcom,msm-ssc-sensors", "the SSC sensors"),
        ("/soc/qmi-ts-sensors", "the QMI thermal sensors"),
        ("/soc/thermal-sensor@c263000", "thermal sensor 0"),
        ("/soc/thermal-sensor@c265000", "thermal sensor 1"),
    ]),
    ("camera", "the camera subsystem", [
        ("/soc/qcom,cam-cpas@ac13000", "the camera bus performance adjuster"),
        ("/soc/qcom,cam_smmu", "the camera SMMU"),
        ("/soc/clock-controller@ade0000", "the camera clock controller"),
        ("/soc/qcom,csid0@acb7000", "the CSI receiver 0"),
        ("/soc/qcom,ife0@ac62000", "the video front end 0"),
        ("/soc/qcom,bps@ac2c000", "the byte stream processor"),
        ("/soc/qcom,ipe0@ac42000", "the image processing engine"),
        ("/soc/qcom,cam-icp", "the image control processor"),
        ("/soc/qcom,vidc@aa00000", "the video codec"),
        ("/reserved-memory/camera_region@9f500000", "the camera reserved region"),
    ]),
    ("modem-adsp", "the modem and the other remote processors", [
        ("/soc/remoteproc-mss@04080000", "the modem"),
        ("/soc/remoteproc-adsp@03000000", "the ADSP"),
        ("/soc/remoteproc-cdsp@32300000", "the CDSP"),
        ("/soc/remoteproc-slpi@02400000", "the SLPI"),
        ("/soc/remoteproc-spss@1880000", "the SPSS"),
        ("/reserved-memory/mpss_region@8bc00000", "the modem reserved region"),
    ]),
    ("haptics", "the haptic driver", [
        ("/soc/i2c@884000/aw8697_haptic@5A", "the AW8697 haptic driver"),
    ]),
    ("buttons", "the physical keys", [
        ("/soc/gpio_keys", "the GPIO keys"),
    ]),
    ("soc-fabric", "clocks, interconnects, DMA and the RNG", [
        ("/soc/clock-controller@100000", "the global clock controller"),
        ("/soc/clock-controller@0", "the debug clock controller"),
        ("/soc/interrupt-controller@17100000", "the GIC"),
        ("/soc/rsc@af20000", "the display RPMh resource controller"),
        ("/soc/qcom,gpi-dma@800000", "GPI DMA 0"),
        ("/soc/qcom,gpi-dma@900000", "GPI DMA 1"),
        ("/soc/qcom,gpi-dma@a00000", "GPI DMA 2"),
        ("/soc/qrng@10c3000", "the random number generator"),
        ("/soc/qcedev@1de0000", "the crypto engine"),
        ("/soc/qseecom@c1700000", "the secure application loader"),
    ]),
]


def strings(raw):
    if not raw:
        return []
    return [part.decode("utf-8", "replace")
            for part in raw.replace(b"\\x00", b"\0").split(b"\0") if part.strip()]


def describe_node(nodes, path):
    props = nodes.get(path)
    if props is None:
        return ["    node MISSING from the tree"]
    lines = []
    compatible = strings(props.get("compatible"))
    if compatible:
        lines.append("    compatible   %s" % ", ".join(compatible))
    if "reg" in props:
        names = strings(props.get("reg-names"))
        pairs = FACTS.reg_pairs(nodes, path)
        for i, (address, size) in enumerate(pairs):
            name = names[i] if i < len(names) else ""
            lines.append("    reg[%d]       0x%09x 0x%08x %s" % (i, address, size, name))
    if "interrupts" in props:
        names = strings(props.get("interrupt-names"))
        values = FACTS.cells(props["interrupts"])
        numbers = [values[i + 1] for i in range(0, len(values) - 2, 3)]
        for i, number in enumerate(numbers):
            name = names[i] if i < len(names) else ""
            lines.append("    irq          %d %s" % (number, name))
    if "clocks" in props:
        names = strings(props.get("clock-names"))
        if names:
            lines.append("    clocks       %s" % ", ".join(names))
    for supply in SUPPLY_PROPERTIES:
        if supply in props:
            phandle = FACTS.cells(props[supply])[0]
            target = next((p for p, pr in nodes.items()
                           if "phandle" in pr and FACTS.cells(pr["phandle"])[0] == phandle), "?")
            lines.append("    %-12s %s" % (supply, target))
    if "dmas" in props:
        names = strings(props.get("dma-names"))
        lines.append("    dmas         %s" % (", ".join(names) if names else "(unnamed)"))
    if "status" in props:
        lines.append("    status       %s" % strings(props["status"])[0] if strings(props["status"]) else "    status       (none)")
    if not lines:
        lines.append("    (no registers, interrupts, clocks or supplies)")
    return lines


def render(nodes):
    out = []
    out.append("# Xiaomi 12 (cupid) device facts, read out of the phone's own device tree.")
    out.append("#")
    out.append("# Generated by tools/device-facts.py. Do not edit by hand; regenerate it.")
    out.append("# Every line names the node it came from. This is what the tree says, not what a driver")
    out.append("# should do with it.")
    out.append("")
    for name, description, anchors in SUBSYSTEMS:
        out.append("=" * 78)
        out.append("%s -- %s" % (name, description))
        out.append("=" * 78)
        for path, role in anchors:
            out.append("  %s" % role)
            out.append("  node         %s" % path)
            out.extend(describe_node(nodes, path))
        out.append("")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dtb", default="uefi/files/Resources/DTBs/cupid.dtb")
    parser.add_argument("--out", default="docs/device-facts.txt")
    parser.add_argument("--check")
    args = parser.parse_args()

    nodes = FACTS.fdt_nodes(open(args.dtb, "rb").read())
    text = render(nodes)
    if args.check:
        current = open(args.check, encoding="utf-8").read()
        if current != text:
            print("device-facts: %s does not match %s; regenerate it with --out" % (args.check, args.dtb))
            return 1
        print("device-facts: %s matches %s" % (args.check, os.path.basename(args.dtb)))
        return 0
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    total_anchors = sum(len(anchors) for _, _, anchors in SUBSYSTEMS)
    missing = sum(1 for _, _, anchors in SUBSYSTEMS for path, _ in anchors if path not in nodes)
    print("device-facts: wrote %s (%d subsystem(s), %d anchor(s), %d missing)"
          % (args.out, len(SUBSYSTEMS), total_anchors, missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
