#!/bin/bash
#
# NUC provisioning: SDR stack for the analog arm, ML stack for local training.
# Runs on top of PowderTeam/cots-jammy-image, so all Quectel tooling
# (quectel-CM, modem drivers, AT scripting) is inherited and left untouched.
#
# Usage: deploy-ue-stack.sh <install_sdr yes|no> <install_ml yes|no> [clock_source]

set -ex

INSTALL_SDR="${1:-yes}"
INSTALL_ML="${2:-yes}"
CLOCK_SOURCE="${3:-external}"
STATUS=/var/tmp/ue-stack-complete

if [ -f "$STATUS" ]; then
    echo "UE stack already installed."
    exit 0
fi

export DEBIAN_FRONTEND=noninteractive

if [ "$INSTALL_SDR" = "yes" ]; then
    # Same source build as the SDR hosts: the packaged UHD is 4.1 and will not
    # match an X310 flashed for 4.11.
    /local/repository/bin/deploy-sdr-stack.sh "$CLOCK_SOURCE"
fi

if [ "$INSTALL_ML" = "yes" ]; then
    sudo apt-get update
    sudo apt-get install -y python3-pip
    # CPU-only torch: these nodes have no GPU, and the CUDA wheels are ~2 GB.
    sudo pip3 install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu torch || true
    sudo pip3 install --no-cache-dir flwr numpy scipy || true
fi

# RAPL readable without root, for the energy accounting the plan needs.
if [ -d /sys/class/powercap/intel-rapl ]; then
    sudo chmod -R a+r /sys/class/powercap/intel-rapl || true
fi

# PTP for host-level burst timing. The RF timebase comes from the Octoclock,
# not from this.
sudo apt-get install -y linuxptp || true

# Confirm both radios survived the install: the B210 and the COTS modem share
# the USB tree, and a botched udev rule can take out the modem.
echo "=== B210 ==="
uhd_find_devices 2>&1 | grep -A3 B210 || echo "WARNING: no B210 found"
echo "=== COTS modem ==="
ls /dev/ttyUSB* 2>&1 || echo "WARNING: no modem tty found"
lsusb | grep -i quectel || echo "WARNING: no Quectel modem on USB"

sudo touch "$STATUS"
echo "UE stack install complete."
