#!/bin/bash
#
# Enlarge socket buffers and set jumbo frames on the 10 GbE link to the X310.
# Advisory: never abort the startup chain.

sudo sysctl -w net.core.wmem_max=25000000 || true
sudo sysctl -w net.core.rmem_max=25000000 || true

# Find the interface holding the radio-side address. Use iproute2 rather than
# ifconfig, which is not installed on UBUNTU22-64-STD.
SDR_IFACE=$(ip -o -4 addr show | awk '$4 ~ /^192\.168\.[0-9]+\.1\// {print $2; exit}')

if [ -n "$SDR_IFACE" ]; then
    sudo ip link set dev "$SDR_IFACE" mtu 9000 \
        && echo "set mtu 9000 on $SDR_IFACE" \
        || echo "could not set mtu on $SDR_IFACE"
else
    echo "no SDR interface found; skipping mtu tuning"
fi

exit 0
