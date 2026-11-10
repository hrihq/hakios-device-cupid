#!/bin/bash
# Save the cupid platform from Mu-Silicium/ into files/ here (uefi/export.sh runs this; HakiOS's own changes are uefi/'s).
set -e
cd "$(dirname "$(readlink -f "$0")")"
MU=${MU:-../../../Mu-Silicium}
rm -rf files
mkdir -p files/Resources/Configs files/Resources/DTBs files/Platforms/Xiaomi files/Silicium-ACPI/Platforms/Xiaomi files/Binaries
cp -r $MU/Platforms/Xiaomi/cupidPkg files/Platforms/Xiaomi/
cp $MU/Resources/Configs/cupid.toml files/Resources/Configs/
cp $MU/Resources/DTBs/cupid.dtb files/Resources/DTBs/
cp -r $MU/Silicium-ACPI/Platforms/Xiaomi/cupid files/Silicium-ACPI/Platforms/Xiaomi/
cp -r $MU/Binaries/cupid files/Binaries/
find files -name __pycache__ -prune -exec rm -rf {} +
echo "devices/cupid/uefi/export.sh: $(find files -type f | wc -l) files"
