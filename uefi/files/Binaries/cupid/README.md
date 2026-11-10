# Binaries/cupid

The vendor's UEFI drivers for the Xiaomi 12, **not tracked**. Make this directory yourself from your own phone:
the common repository's `uefi/README.md` says how (extract them from the phone's `xbl` with UEFIReader).
`tools/provenance-check.py` fails the build if they come back into the tree.

Until they are here, `mkxnuimg.py` stops with a message that points at that README.
