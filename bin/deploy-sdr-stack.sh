#!/bin/bash
#
# Build UHD 4.11 and GNU Radio 3.10 from source, and stage the X310 FPGA images.
#
# Jammy's packaged uhd-host is 4.1, which will NOT talk to an X310 flashed for
# UHD 4.11 (RFNoC protocol 2.0 vs 1.0). Build from source so host and FPGA match.
#
# Usage: deploy-sdr-stack.sh [clock_source]

set -ex

CLOCK_SOURCE="${1:-external}"
UHD_TAG="v4.11.0.0"
SRCDIR=/var/tmp/sdr-src
STATUS=/var/tmp/sdr-stack-complete

if [ -f "$STATUS" ]; then
    echo "SDR stack already installed."
    exit 0
fi

export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
# Protobuf and gRPC are required by UHD 4.11's MPM/RFNoC services: cmake
# fails outright without them. DPDK is optional and left out.
sudo apt-get install -y \
    build-essential cmake git pkg-config \
    libboost-all-dev libusb-1.0-0-dev python3-dev python3-pip \
    python3-mako python3-numpy python3-requests python3-ruamel.yaml \
    python3-setuptools libudev-dev \
    libprotobuf-dev protobuf-compiler \
    libgrpc++-dev protobuf-compiler-grpc

# --- UHD ---------------------------------------------------------------
# Use the distro package if it is already >= 4.11 (saves ~15 min).
INSTALLED_UHD=$(uhd_config_info --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)
NEED_BUILD=yes
if [ -n "$INSTALLED_UHD" ]; then
    MAJOR=$(echo "$INSTALLED_UHD" | cut -d. -f1)
    MINOR=$(echo "$INSTALLED_UHD" | cut -d. -f2)
    if [ "$MAJOR" -gt 4 ] || { [ "$MAJOR" -eq 4 ] && [ "$MINOR" -ge 11 ]; }; then
        echo "UHD $INSTALLED_UHD already present, skipping source build."
        NEED_BUILD=no
    fi
fi

if [ "$NEED_BUILD" = "yes" ]; then
    mkdir -p "$SRCDIR"
    cd "$SRCDIR"
    [ -d uhd ] || git clone --depth 1 --branch "$UHD_TAG" https://github.com/EttusResearch/uhd.git
    mkdir -p uhd/host/build
    cd uhd/host/build
    cmake -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=OFF -DENABLE_MANUAL=OFF ..
    make -j"$(nproc)"
    sudo make install
    sudo ldconfig
fi

# FPGA images and firmware. The default image directory ships empty and the
# downloader needs root to write into it.
#
# Download the full set rather than filtering with -t: `-t b200` fetches
# usrp_b200_fpga.bin but NOT usrp_b200_fw.hex, and without that firmware the
# B210 never enumerates ("Could not find the image 'usrp_b200_fw.hex'").
sudo uhd_images_downloader || true

# USB permissions for the B210.
sudo cp "$(dirname "$(dirname "$(which uhd_find_devices)")")"/lib/uhd/utils/uhd-usrp.rules \
    /etc/udev/rules.d/ 2>/dev/null || \
    sudo find / -name 'uhd-usrp.rules' -exec cp {} /etc/udev/rules.d/ \; 2>/dev/null || true
sudo udevadm control --reload-rules && sudo udevadm trigger || true

# Larger socket buffers and jumbo frames for the 10 GbE path to an X310.
sudo sysctl -w net.core.wmem_max=25000000
sudo sysctl -w net.core.rmem_max=25000000

# --- GNU Radio ---------------------------------------------------------
# The Jammy package is 3.10.1.1, which matches the plan's requirement, so
# install it rather than spending an hour building it.
sudo apt-get install -y gnuradio gnuradio-dev || true

# --- Python for analysis ----------------------------------------------
sudo pip3 install --no-cache-dir numpy scipy matplotlib || true

echo "$CLOCK_SOURCE" | sudo tee /var/tmp/clock-source > /dev/null
sudo touch "$STATUS"
echo "SDR stack install complete."
