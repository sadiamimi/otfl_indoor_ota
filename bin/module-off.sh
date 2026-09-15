#!/bin/bash
#
# Put the COTS modem in airplane mode so it does not attach during startup.
# chat intermittently returns an error on the first attempt, so retry, and
# never abort the startup chain.

for attempt in 1 2 3; do
    if sudo sh -c "chat -t 1 -sv '' AT OK 'AT+CFUN=0' OK < /dev/ttyUSB2 > /dev/ttyUSB2" 2>/dev/null; then
        echo "modem in airplane mode"
        exit 0
    fi
    sleep 2
done

echo "could not put modem in airplane mode; continuing"
exit 0
