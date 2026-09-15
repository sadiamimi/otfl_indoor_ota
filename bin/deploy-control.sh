#!/bin/bash
#
# Control node: near-RT RIC, Flower server, orchestration, results store.
# Deliberately radio-free - keeping this off the SDR host avoids contending
# with the real-time radio processes.

set -ex

STATUS=/var/tmp/control-complete
[ -f "$STATUS" ] && { echo "Control stack already installed."; exit 0; }

export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
sudo apt-get install -y \
    build-essential cmake git pkg-config python3-pip \
    libsctp-dev lksctp-tools autoconf libtool bison flex \
    libpcre2-dev

sudo pip3 install --no-cache-dir flwr numpy scipy pandas matplotlib || true

# FlexRIC: near-RT RIC and xApp host. Built here rather than on the SDR node
# so the control loop is decoupled from the radio.
SRCDIR=/var/tmp/flexric-src
if [ ! -d "$SRCDIR" ]; then
    git clone https://gitlab.eurecom.fr/mosaic5g/flexric.git "$SRCDIR" || true
fi
if [ -d "$SRCDIR" ]; then
    mkdir -p "$SRCDIR/build"
    cd "$SRCDIR/build"
    # Non-fatal: FlexRIC's dependencies move, and a failure here should not
    # take down the whole experiment startup.
    cmake .. -DCMAKE_BUILD_TYPE=Release || true
    make -j"$(nproc)" || true
    sudo make install || true
fi

sudo mkdir -p /var/tmp/results
sudo chmod 1777 /var/tmp/results

sudo touch "$STATUS"
echo "Control stack install complete."
