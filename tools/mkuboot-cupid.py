#!/usr/bin/env python3
"""Pack HakiOS's U-Boot for the Xiaomi 12 (cupid) as an Android boot image for `fastboot boot`.

Same shape as the common repository's tools/mkubootimg.py — gzip(u-boot.bin) followed by the phone's
device tree, which is what ABL expects — with the two values that are measured facts on waipio
instead of redwood's defaults: header version 4, and os_version/os_patch_level left at 0. With
anything else ABL answers OKAY and boots the slot instead (see docs/boot-runbook.md).

  tools/mkuboot-cupid.py --uboot build/u-boot.bin --dtb cupid-u-boot.dtb --out hakios-uboot-cupid.img
"""
import argparse
import gzip
import os
import subprocess
import sys

HEADER = 4               # waipio ABL: v1 is accepted but boots the slot instead
OS_VERSION, OS_PATCH = '0', '0'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--uboot', required=True, help='u-boot.bin (CONFIG_LINUX_KERNEL_IMAGE_HEADER)')
    ap.add_argument('--dtb', required=True,
                    help="the phone's own device tree (what ABL gets: appended after gzip(u-boot.bin))")
    ap.add_argument('--uboot-dtb',
                    help="U-Boot's own built device tree (build/u-boot.dtb); this is the tree the console "
                         "comes from, so it is the one that must carry simple-framebuffer")
    ap.add_argument('--ramdisk',
                    help='an HKUB container (hakios load takes the loader and payload from it); '
                         'empty = U-Boot waits for the host over fastboot instead')
    ap.add_argument('--mkbootimg', default='mkbootimg.py')
    ap.add_argument('--out', default='hakios-uboot-cupid.img')
    a = ap.parse_args()

    ub = open(a.uboot, 'rb').read()
    dtb = open(a.dtb, 'rb').read()
    if b'ARM\x64' not in ub[:64]:
        sys.exit('mkuboot-cupid.py: u-boot.bin has no arm64 image header '
                 '(CONFIG_LINUX_KERNEL_IMAGE_HEADER)')
    if dtb[:4] != bytes.fromhex('d00dfeed'):
        sys.exit('mkuboot-cupid.py: the device tree is not a dtb (no d00dfeed)')
    # Two different trees, on purpose:
    #   --dtb       the phone's Android tree, appended for ABL (it has no framebuffer node)
    #   --uboot-dtb U-Boot's own tree, built from u-boot/files/dts/... (it must have one)
    ubdtb = open(a.uboot_dtb, 'rb').read() if a.uboot_dtb else b''
    if a.uboot_dtb and b'simple-framebuffer' not in ubdtb:
        sys.exit("mkuboot-cupid.py: U-Boot's own device tree has no simple-framebuffer node, so the\n"
                 '  console has nowhere to write: check u-boot/files/dts/.../sm8450-xiaomi-cupid.dts')
    if a.uboot_dtb and b'hakios-payload' not in ubdtb:
        sys.exit("mkuboot-cupid.py: U-Boot's own device tree has no hakios-payload window")

    kernel = os.path.abspath('u-boot-kernel.bin')
    with open(kernel, 'wb') as f:
        f.write(gzip.compress(ub, 6) + dtb)

    cmd = [sys.executable, a.mkbootimg, '--kernel', kernel, '--header_version', str(HEADER),
           '--os_version', OS_VERSION, '--os_patch_level', OS_PATCH, '-o', a.out]
    if a.ramdisk:
        rd = open(a.ramdisk, 'rb').read()
        if rd[:4] != b'HKUB':
            sys.exit('mkuboot-cupid.py: the ramdisk is not an HKUB container (mkubootimg.py -c)')
        cmd += ['--ramdisk', a.ramdisk]
    print(' '.join(cmd))
    subprocess.check_call(cmd)
    print('%s: %d bytes (u-boot %d gz\'d, dtb %d, header v%d, os_version %s/%s)'
          % (a.out, os.path.getsize(a.out), len(ub), len(dtb), HEADER, OS_VERSION, OS_PATCH))


if __name__ == '__main__':
    main()