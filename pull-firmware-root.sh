#!/bin/bash
# pull-firmware.sh, through root. Some ROMs mount /vendor/firmware_mnt for the system user only, so the
# plain `adb pull` of pull-firmware.sh gets nothing ("not on the phone" for every file) although every
# file is there. This does the same pull by way of su: the firmware is copied, under root, to a
# world-readable staging directory in /data/local/tmp, pulled from there, and the staging directory is
# removed again. Nothing on the phone is changed.
#
# Needs the phone in Android with adb and a root that answers `su -c` (Magisk, KernelSU).
set -e
cd "$(dirname "$0")/../.."
S=/data/local/tmp/cupid-fw

adb get-state >/dev/null

# the copy itself, under root. The firmware names are the phone's own; the globs take what is there.
adb shell "su -c 'sh -c \"S=$S; rm -rf \$S; mkdir -p \$S/gpu \$S/wifi \$S/audio \$S/modem \$S/haptic \$S/camera
cp /vendor/firmware/gmu_gen70000.bin /vendor/firmware/a730_sqe.fw /vendor/firmware/a730_zap.* \$S/gpu/ 2>/dev/null
cp /vendor/firmware_mnt/image/wlan* /vendor/firmware_mnt/image/wcn* /vendor/firmware_mnt/image/wpss* \$S/wifi/ 2>/dev/null
cp /vendor/firmware_mnt/image/adsp* \$S/audio/ 2>/dev/null
cp /vendor/firmware_mnt/image/modem* \$S/modem/ 2>/dev/null
cp /vendor/firmware/aw8697_haptic.bin \$S/haptic/ 2>/dev/null
cp /vendor/lib64/camera/com.qti.sensormodule.*.bin \$S/camera/ 2>/dev/null
chmod -R a+rX \$S\"'"

rm -rf fw-stage
adb pull "$S" fw-stage >/dev/null
adb shell "su -c 'rm -rf $S'" >/dev/null 2>&1 || true

rm -rf fw-gpu fw-wifi fw-audio fw-modem fw-haptic fw-camera
for d in gpu wifi audio modem haptic camera; do
	[ -d "fw-stage/$d" ] && mv "fw-stage/$d" "fw-$d"
done
rm -rf fw-stage

for d in fw-gpu fw-wifi fw-audio fw-modem fw-haptic fw-camera; do
	echo "pull-firmware-root.sh: $d: $(ls -1 "$d" 2>/dev/null | wc -l | tr -d ' ') files"
done

# the phone's own device tree, which only root can read
mkdir -p prebuilt
adb shell "su -c 'cat /sys/firmware/fdt'" > prebuilt/device-tree.dtb 2>/dev/null \
	&& [ -s prebuilt/device-tree.dtb ] \
	|| echo "pull-firmware-root.sh: /sys/firmware/fdt: not readable; the platform's own DTB stays"

echo "pull-firmware-root.sh: done; the staging directory is removed"
