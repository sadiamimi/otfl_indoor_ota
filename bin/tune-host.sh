#!/bin/bash
#
# Host tuning for the real-time radio path, made persistent across reboots.
#
# Settings applied once with sysctl -w / ip link do not survive a reboot: after
# one, the gNodeB host came back at MTU 1500, a 1 MB send buffer and the
# schedutil governor, and long X310 captures overflowed (236 overflows in an
# hour). So this installs the settings as boot-time configuration:
#   * /etc/sysctl.d/90-otafl.conf: 32 MB socket buffers (UHD's recommendation
#     for the 10 GbE X310 path; harmless on the NUCs)
#   * otafl-tune.service: performance CPU governor, C-states off, and MTU 9000
#     on the interface holding a 192.168.N.1 address (the link to the X310)
# Run on the gNodeB compute nodes and on the NUCs (the UE's post-beacon
# processing has ~2 ms of margin; a down-clocked CPU costs it).
#
# Advisory: never abort the startup chain.

export DEBIAN_FRONTEND=noninteractive

if ! command -v cpupower > /dev/null 2>&1; then
    sudo apt-get update -qq || true
    sudo apt-get install -y "linux-tools-$(uname -r)" linux-tools-generic \
        > /dev/null 2>&1 || true
fi

sudo tee /etc/sysctl.d/90-otafl.conf > /dev/null <<'EOF'
net.core.wmem_max = 33554432
net.core.rmem_max = 33554432
EOF
sudo sysctl -q -p /etc/sysctl.d/90-otafl.conf || true

sudo tee /usr/local/sbin/otafl-tune > /dev/null <<'EOF'
#!/bin/bash
# Installed by otafl-indoor-ota/bin/tune-host.sh; run at every boot.
if command -v cpupower > /dev/null 2>&1; then
    cpupower frequency-set -g performance > /dev/null 2>&1 \
        || echo "cpupower: could not set the performance governor"
    cpupower idle-set -D 2 > /dev/null 2>&1 \
        || echo "cpupower: could not disable C-states"
else
    for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        [ -w "$g" ] && echo performance > "$g"
    done
fi
SDR_IFACE=$(ip -o -4 addr show | awk '$4 ~ /^192\.168\.[0-9]+\.1\// {print $2; exit}')
if [ -n "$SDR_IFACE" ]; then
    ip link set dev "$SDR_IFACE" mtu 9000 && echo "mtu 9000 on $SDR_IFACE"
fi
sysctl -q -w net.core.wmem_max=33554432 net.core.rmem_max=33554432
exit 0
EOF
sudo chmod 755 /usr/local/sbin/otafl-tune

sudo tee /etc/systemd/system/otafl-tune.service > /dev/null <<'EOF'
[Unit]
Description=OTA-FL radio host tuning (governor, C-states, X310 MTU, buffers)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/otafl-tune
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload || true
sudo systemctl enable otafl-tune.service > /dev/null 2>&1 || true
sudo systemctl restart otafl-tune.service || true
sudo systemctl status otafl-tune.service --no-pager 2>/dev/null | tail -3 || true

exit 0
