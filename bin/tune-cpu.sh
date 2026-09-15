#!/bin/bash
#
# Disable CPU C-states to reduce latency spikes in the real-time radio path.
#
# cpupower lives in a kernel-version-specific package that is not present on
# every image, so install it if missing and treat the whole step as advisory:
# tuning is a performance optimization, not a correctness requirement, and it
# must never abort the startup chain.

if ! command -v cpupower > /dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    sudo apt-get update -qq || true
    sudo apt-get install -y "linux-tools-$(uname -r)" linux-tools-generic \
        > /dev/null 2>&1 || true
fi

if command -v cpupower > /dev/null 2>&1; then
    sudo cpupower idle-set -D 2 || echo "cpupower: could not disable C-states"
else
    echo "cpupower unavailable; skipping C-state tuning"
fi

exit 0
