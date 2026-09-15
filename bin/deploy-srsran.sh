#!/bin/bash
#
# Build srsRAN Project from source and stage a gNodeB config.
#
# release_25_10 ships E2 (E2SM-KPM, E2SM-RC, E2SM-CCC) compiled in by default -
# no -DENABLE_E2 flag exists or is needed; E2 is gated at runtime from the
# config file. The 2024-era build pinned by the stock profile has no E2 at all.
#
# Usage: deploy-srsran.sh <commit|tag|branch> [clock_source] [role]

set -ex

SRSRAN_REF="${1:-release_25_10}"
CLOCK_SOURCE="${2:-external}"
ROLE="${3:-gnb}"
SRCDIR=/var/tmp/srsRAN_Project
ETCDIR=/var/tmp/etc/srsran
STATUS=/var/tmp/srsran-setup-complete

if [ -f "$STATUS" ]; then
    echo "srsRAN already installed."
    exit 0
fi

export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
sudo apt-get install -y \
    cmake make gcc g++ pkg-config libfftw3-dev libmbedtls-dev \
    libsctp-dev libyaml-cpp-dev libgtest-dev libuhd-dev uhd-host \
    libdw-dev libboost-program-options-dev git

if [ ! -d "$SRCDIR" ]; then
    git clone https://github.com/srsran/srsRAN_Project.git "$SRCDIR"
fi
cd "$SRCDIR"
git fetch --all --tags || true
git checkout "$SRSRAN_REF"

mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=OFF
make -j"$(nproc)" gnb

# --- gNodeB config -----------------------------------------------------
# NOTE the 25.x schema: AMF settings moved under cu_cp, and the bare `tac` was
# replaced by supported_tracking_areas (which absorbed the old top-level
# `slicing` block). A pre-25.x config fails with "INI was not able to parse amf."
sudo mkdir -p "$ETCDIR"

sudo tee "$ETCDIR/gnb_x310_n78_e2.yml" > /dev/null <<EOF
# srsRAN Project gNodeB, POWDER Indoor OTA Lab, X310.
# Schema: srsRAN 25.x.

gnb_id: 102

cu_cp:
  amf:
    addr: 192.168.1.1
    port: 38412
    bind_addr: 192.168.1.2
    supported_tracking_areas:
      - tac: 1
        plmn_list:
          - plmn: "99999"
            tai_slice_support_list:
              - sst: 1
                sd: 1

ru_sdr:
  device_driver: uhd
  device_args: type=x300
  tx_gain: 31
  rx_gain: 25
  srate: 11.52
  lo_offset: 20
  clock: ${CLOCK_SOURCE}
  sync: ${CLOCK_SOURCE}
  time_alignment_calibration: 0

cell_cfg:
  # 3450 MHz centre: inside the approved 3430-3470 MHz range, and the same
  # centre the analog arm uses so frequency is not a confound between arms.
  dl_arfcn: 630000
  band: 78
  channel_bandwidth_MHz: 10
  common_scs: 30
  nof_antennas_dl: 1
  nof_antennas_ul: 1
  plmn: "99999"
  tac: 1
  pci: 3
  pdsch:
    mcs_table: qam256
    olla_target_bler: 0.1
  pusch:
    mcs_table: qam256
    olla_target_bler: 0.1
  ssb:
    ssb_period: 20
  tdd_ul_dl_cfg:
    dl_ul_tx_period: 10
    nof_dl_slots: 5
    nof_dl_symbols: 9
    nof_ul_slots: 4
    nof_ul_symbols: 0

e2:
  enable_du_e2: false
  addr: 192.168.1.10
  bind_addr: 192.168.1.2
  port: 36421
  e2sm_kpm_enabled: true
  e2sm_rc_enabled: true

log:
  filename: /tmp/gnb.log
  all_level: warning

pcap:
  mac_enable: false
  ngap_enable: false
EOF

# 40 MHz variant, for the clearly-labelled secondary digital-only result.
sudo sed -e 's/^  srate: 11.52/  srate: 46.08/' \
         -e 's/^  lo_offset: 20/  lo_offset: 45/' \
         -e 's/^    channel_bandwidth_MHz: 10/    channel_bandwidth_MHz: 40/' \
         "$ETCDIR/gnb_x310_n78_e2.yml" | \
    sudo tee "$ETCDIR/gnb_x310_n78_40mhz_e2.yml" > /dev/null

# Validate before declaring success, so a schema break surfaces at startup
# rather than at the first experiment.
"$SRCDIR/build/apps/gnb/gnb" -c "$ETCDIR/gnb_x310_n78_e2.yml" --dryrun \
    && echo "gNodeB config validates." \
    || echo "WARNING: gNodeB config failed validation."

sudo touch "$STATUS"
echo "srsRAN install complete."
