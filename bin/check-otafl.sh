#!/bin/bash
#
# Bring-up check, run at the end of startup on every radio node. Writes
# /var/tmp/otafl-check.txt; each line is OK or WARN. Read it before the first
# experiment of a new reservation:  cat /var/tmp/otafl-check.txt
#
# Advisory: never abort the startup chain.

OUT=/var/tmp/otafl-check.txt
{
echo "otafl bring-up check on $(hostname) at $(date -Is)"

# the version the experiments use: the Python bindings (/usr/local), not the
# apt uhd-host 4.1 that srsRAN's dependencies can put first on root's PATH
v=$(python3 -c 'import uhd; print("UHD", uhd.get_version_string())' 2>/dev/null | tail -1)
case "$v" in *4.11*) echo "OK   UHD $v" ;; *) echo "WARN UHD version '$v' (want 4.11)" ;; esac

if python3 -c 'import uhd' > /dev/null 2>&1; then
    echo "OK   python3 import uhd"
else
    echo "WARN python3 cannot import uhd"
fi
abi=$(python3 -c 'import uhd' 2>&1 | grep -c '_ARRAY_API\|compiled using NumPy 1.x')
[ "$abi" = 0 ] && echo "OK   UHD bindings match NumPy" || echo "WARN UHD bindings built for another NumPy major version"
echo "INFO numpy $(python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null), scipy $(python3 -c 'import scipy; print(scipy.__version__)' 2>/dev/null), torch $(python3 -c 'import torch; print(torch.__version__)' 2>/dev/null || echo none)"

g=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
[ "$g" = performance ] && echo "OK   CPU governor performance" || echo "WARN CPU governor '$g'"

w=$(sysctl -n net.core.wmem_max)
[ "$w" -ge 33554432 ] 2>/dev/null && echo "OK   wmem_max $w" || echo "WARN wmem_max $w"

SDR_IFACE=$(ip -o -4 addr show | awk '$4 ~ /^192\.168\.[0-9]+\.1\// {print $2; exit}')
if [ -n "$SDR_IFACE" ]; then
    m=$(cat /sys/class/net/$SDR_IFACE/mtu)
    [ "$m" = 9000 ] && echo "OK   MTU 9000 on $SDR_IFACE" || echo "WARN MTU $m on $SDR_IFACE"
fi

systemctl is-enabled otafl-tune.service > /dev/null 2>&1 && echo "OK   otafl-tune.service enabled (survives reboot)" \
    || echo "WARN otafl-tune.service not enabled"

[ -d /proj/AIEdgeOSU/afrose4/otafl/experiments ] && echo "OK   /proj code present" \
    || echo "WARN /proj/AIEdgeOSU/afrose4/otafl/experiments missing (run experiments/deploy.sh from the repo)"

devs=$(timeout 40 uhd_find_devices 2>/dev/null | grep -oE 'B210|X310|X300' | sort -u | tr '\n' ' ')
[ -n "$devs" ] && echo "OK   radios found: $devs" || echo "WARN no radio found by uhd_find_devices"
if echo "$devs" | grep -q 'X3'; then
    if timeout 60 python3 -c 'import uhd; uhd.usrp.MultiUSRP("type=x300")' 2>&1 | grep -q 'protocol mismatch'; then
        echo "WARN X310 FPGA image predates UHD: sudo uhd_image_loader --args 'type=x300,fpga=XG', then power-cycle the -sdr node"
    else
        echo "OK   X310 opens"
    fi
fi
echo "INFO beacon margins need the gNB: after startup run GNB_HOST=<gNB host> experiments/b1/margin_check.sh (weakest UE gets the first sounding slot)"
} 2>&1 | tee "$OUT"
exit 0
