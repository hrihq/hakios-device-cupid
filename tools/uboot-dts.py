#!/usr/bin/env python3
"""Add what U-Boot needs to the phone's own device tree, and nothing else.

The Xiaomi 12's ABL leaves the splash framebuffer live at 0xB8000000 (the tree calls it
cont_splash_region) and hands U-Boot an Android device tree. An Android tree has no
`simple-framebuffer` node, so U-Boot's vidconsole has nothing to paint on and a running U-Boot
writes nothing to the panel. This adds that node, plus the payload window the hakios command uses,
and leaves every other node of the phone's tree untouched.

  dtc -I dtb -O dts cupid.dtb -o cupid.dts
  tools/uboot-dts.py --in cupid.dts --out cupid-u-boot.dts

Values are the phone's own, measured: the framebuffer address and its reserved size come from
/splash_region, the panel geometry from the DSI panel, the payload base from the waipio family.
"""
import argparse
import re
import sys

FB = 0xB8000000          # /reserved-memory/splash_region
WIDTH, HEIGHT = 1080, 2400
PAYLOAD = 0xB0000000     # the waipio family's measured payload base
PAYLOAD_SIZE = 0x04000000  # 64 MiB, as the sibling ports reserve

MARK = '// added by tools/uboot-dts.py'


def block(fb, width, height, payload, payload_size):
    stride = width * 4
    size = stride * height
    return f"""
{MARK}: U-Boot's console on the framebuffer ABL left live, and the payload window.
/ {{
	simple-framebuffer@{fb:x} {{
		compatible = "simple-framebuffer";
		reg = <0x0 0x{fb:x} 0x0 0x{size:x}>;
		width = <{width}>;
		height = <{height}>;
		stride = <{stride}>;
		format = "a8r8g8b8";
		status = "okay";
	}};
}};

/* a path reference, not a label: dtc -I dtb -O dts drops every label, so &reserved_memory does not
   exist in the phone's decompiled tree. 0xB0000000 is the waipio family's measured payload base. */
&{{/reserved-memory}} {{
	hakios-payload@{payload:x} {{
		reg = <0x0 0x{payload:x} 0x0 0x{payload_size:x}>;
		no-map;
	}};
}};
"""


def main():
    ap = argparse.ArgumentParser(description=(__doc__ or '').split('\n\n')[0])
    ap.add_argument('--in', dest='src', required=True, help='the phone device tree as dts (dtc -I dtb -O dts)')
    ap.add_argument('--out', dest='dst', required=True)
    ap.add_argument('--fb', type=lambda s: int(s, 0), default=FB)
    ap.add_argument('--width', type=int, default=WIDTH)
    ap.add_argument('--height', type=int, default=HEIGHT)
    ap.add_argument('--payload', type=lambda s: int(s, 0), default=PAYLOAD)
    ap.add_argument('--payload-size', type=lambda s: int(s, 0), default=PAYLOAD_SIZE)
    ap.add_argument('--usb-peripheral', action='store_true',
                    help='set every dr_mode to peripheral: U-Boot answers fastboot over the cable')
    a = ap.parse_args()

    text = open(a.src, encoding='utf-8', errors='replace').read()
    problems = []
    if '/dts-v1/;' not in text:
        problems.append('not a dts (no /dts-v1/;)')
    if 'reserved-memory {' not in text:
        problems.append('the tree has no reserved-memory node (the phone should have one)')
    if 'simple-framebuffer' in text:
        problems.append('the tree already has a simple-framebuffer node: refusing to add a second')
    if MARK in text:
        problems.append('already patched')
    if problems:
        sys.exit('uboot-dts.py: ' + '; '.join(problems))

    if a.usb_peripheral:
        text, n = re.subn(r'dr_mode = "[^"]*"', 'dr_mode = "peripheral"', text)
        print(f'uboot-dts.py: {n} dr_mode set to peripheral')

    out = text.rstrip() + '\n' + block(a.fb, a.width, a.height, a.payload, a.payload_size)
    open(a.dst, 'w', encoding='utf-8', newline='\n').write(out)
    print(f'uboot-dts.py: framebuffer 0x{a.fb:x} {a.width}x{a.height} '
          f'({a.width * 4 * a.height:#x} bytes), payload 0x{a.payload:x}+0x{a.payload_size:x}')


if __name__ == '__main__':
    main()