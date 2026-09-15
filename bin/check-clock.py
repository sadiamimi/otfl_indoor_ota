#!/usr/bin/env python3
"""Verify that the external (Octoclock) reference is actually in use.

The X310's `ref_locked` sensor reads True under BOTH `internal` and `external`
and would report success with the reference cable disconnected, so it is not
evidence of anything. This measures the sample clock instead: the device's own
clock times the stream, so N samples at a nominal rate should take exactly
N/rate seconds. Any deviation against host time is the combined device-vs-host
reference error.

Usage: check-clock.py [device_args] [--secs N]
"""
import argparse
import sys
import time

import numpy as np
import uhd

p = argparse.ArgumentParser()
p.add_argument("args", nargs="?", default="type=x300",
               help="UHD device args (e.g. type=x300 or type=b200)")
p.add_argument("--secs", type=float, default=30.0,
               help="capture length per source; 30 s puts host jitter well "
                    "below the ppm scale of interest")
p.add_argument("--rate", type=float, default=5e6)
p.add_argument("--freq", type=float, default=3.45e9)
opts = p.parse_args()

try:
    u = uhd.usrp.MultiUSRP(opts.args)
except RuntimeError as e:
    print("FAIL: cannot open radio ->", e)
    print("      An RFNoC 2.0/1.0 mismatch means the FPGA image does not match")
    print("      the installed UHD. Reflash with uhd_image_loader, then")
    print("      power-cycle the radio.")
    sys.exit(1)

print("mboard        :", u.get_mboard_name(0))
print("clock sources :", u.get_clock_sources(0))
print("time sources  :", u.get_time_sources(0))


def measure(clk):
    u.set_clock_source(clk, 0)
    u.set_time_source(clk if clk in u.get_time_sources(0) else "internal", 0)
    time.sleep(3.0)
    u.set_rx_rate(opts.rate, 0)
    u.set_rx_freq(uhd.types.TuneRequest(opts.freq), 0)
    u.set_rx_gain(20, 0)

    st = uhd.usrp.StreamArgs("fc32", "sc16")
    st.channels = [0]
    rx = u.get_rx_stream(st)
    buf = np.zeros((1, rx.get_max_num_samps()), dtype=np.complex64)
    md = uhd.types.RXMetadata()

    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
    cmd.stream_now = True
    rx.issue_stream_cmd(cmd)

    target = int(opts.rate * opts.secs)
    got, t0 = 0, None
    while got < target:
        n = rx.recv(buf, md, 2.0)
        if md.error_code == uhd.types.RXMetadataErrorCode.overflow:
            continue
        if t0 is None and n > 0:
            t0 = time.time()   # start timing once samples actually flow
            got = 0
            continue
        got += n
    elapsed = time.time() - t0
    rx.issue_stream_cmd(uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont))
    measured = got / elapsed
    return measured, (measured - opts.rate) / opts.rate * 1e6


print("\n--- sample-clock accuracy by source ---")
results = {}
for clk in ("internal", "external", "internal", "external"):
    if clk not in u.get_clock_sources(0):
        print("  [%s] not supported by this device" % clk)
        continue
    try:
        rate, ppm = measure(clk)
        results.setdefault(clk, []).append(ppm)
        print("  [{:8s}] measured={:,.1f} Hz  error={:+8.3f} ppm".format(
            clk, rate, ppm))
    except Exception as e:
        print("  [%-8s] FAILED: %s" % (clk, e))

if "internal" in results and "external" in results:
    spread = max(results["internal"]) - min(results["internal"])
    sep = abs(sum(results["internal"]) / len(results["internal"])
              - sum(results["external"]) / len(results["external"]))
    print("\ninternal repeatability: %.3f ppm spread" % spread)
    print("internal vs external  : %.3f ppm separation" % sep)
    print("\nPASS if internal is tight and repeatable and external does not")
    print("reproduce it. Do NOT use ref_locked as evidence - it reads True")
    print("under both sources even with the reference disconnected.")
