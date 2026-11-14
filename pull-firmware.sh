#!/bin/bash
# Pull the Xiaomi 12 (cupid)'s own firmware out of its Android into the fw-*/ directories at the top of
# the repository (never committed: it is the vendor's). The phone is on adb, in Android.
#
# Nothing on the phone is written: this only reads. If the adb shell user cannot read /vendor/firmware*
# (some ROMs mount them for the system user only), use pull-firmware-root.sh, which stages the files
# under root and removes the staging directory again.
set -e
cd "$(dirname "$0")/../.."

pull() { # DIR SOURCE...  (a missing file is told, not fatal)
	local dir=$1; shift
	mkdir -p "$dir"
	for f in "$@"; do adb pull "$f" "$dir/" >/dev/null 2>&1 || echo "pull-firmware.sh: $f: not on the phone"; done
	echo "pull-firmware.sh: $dir: $(ls -1 "$dir" | wc -l | tr -d ' ') files"
}

adb get-state >/dev/null

# the GPU: the GMU, the 3D core's instruction stream, and the zap shim. The names are the ones
# Linux's a7xx driver asks for this SoC; tools/gpu-firmware-check.py checks what lands.
pull fw-gpu /vendor/firmware/gmu_gen70000.bin /vendor/firmware/a730_sqe.fw \
	/vendor/firmware/a730_zap.mdt /vendor/firmware/a730_zap.b00 \
	/vendor/firmware/a730_zap.b01 /vendor/firmware/a730_zap.b02

# the remote processors and the radio, from the firmware volume's image directory. The prefixes are
# matched rather than listed: the file names are the phone's own and this script does not assume them.
mkdir -p fw-wifi fw-audio fw-modem fw-camera
adb shell "ls /vendor/firmware_mnt/image/" 2>/dev/null | tr -d '\r' | while read -r f; do
	case "$f" in
		wlan*|wcn*|wpss*) adb pull "/vendor/firmware_mnt/image/$f" fw-wifi/  >/dev/null 2>&1 || true ;;
		adsp*)             adb pull "/vendor/firmware_mnt/image/$f" fw-audio/ >/dev/null 2>&1 || true ;;
		modem*)            adb pull "/vendor/firmware_mnt/image/$f" fw-modem/  >/dev/null 2>&1 || true ;;
	esac
done
echo "pull-firmware.sh: fw-wifi: $(ls -1 fw-wifi | wc -l | tr -d ' ') files, fw-audio: $(ls -1 fw-audio | wc -l | tr -d ' '), fw-modem: $(ls -1 fw-modem | wc -l | tr -d ' ')"

# the haptic driver's waveforms
pull fw-haptic /vendor/firmware/aw8697_haptic.bin

# the camera sensors' modules, which carry the sensors' own init sequences
pull fw-camera $(adb shell ls /vendor/lib64/camera/com.qti.sensormodule.*.bin 2>/dev/null | tr -d '\r')

# the phone's own device tree. The UEFI platform ships a stand-in DTB; this is the phone's, and
# tools/device-facts.py reads it to check every fact in this repository.
mkdir -p prebuilt
adb pull /sys/firmware/fdt prebuilt/device-tree.dtb >/dev/null 2>&1 \
	|| echo "pull-firmware.sh: /sys/firmware/fdt: not readable; the platform's own DTB stays"

echo "pull-firmware.sh: done; Wi-Fi also wants fw-wifi/mac (the radio's address)"
