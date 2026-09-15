#!/usr/bin/env bash
set -e
BINDIR=`dirname $0`

sudo cp $BINDIR/default.script /etc/udhcpc/default.script
sudo chmod 755 /etc/udhcpc/default.script
