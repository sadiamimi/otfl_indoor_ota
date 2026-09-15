# otafl-indoor-ota

A POWDER profile for over-the-air federated learning in the Indoor OTA Lab,
supporting an **analog arm** (GNU Radio + B210) and a **digital arm**
(srsRAN 5G + COTS modems) on the same nodes, in the same room, in the same
band.

Implements §5A of the research plan.

## What it allocates

| Node | Client ID | Role |
|---|---|---|
| X310 + paired d740 | `ota-x310-N-comp`, `ota-x310-N-sdr` | gNodeB: analog aggregation RX, digital gNB |
| NUCs ×1–4 | `ota-nucN-ue` | UEs for **both** arms: B210 (analog) + COTS modem (digital) |
| d430 | `cn5g` | Open5GS 5G core |
| d430 (optional) | `ctrl` | Radio-free control node: RIC, Flower server, orchestration |

Default is `ota-x310-2` — one of the two units with antennas on **both**
channels. `ota-x310-1` and `-4` have Channel 0 antennas only; their second
channel enumerates but is unantennaed, usable as a cabled phase reference.

## Frequency

**This profile requests spectrum.** The `indoor-ota` profile it borrows its
allocation patterns from imports the spectrum module but never calls
`requestSpectrum`, so it grants no authorization to transmit.

Default **3430–3470 MHz**, taken from `srs-indoor-ota`. Settable on the
instantiate form. Validated to lie within 3358–3600 MHz.

The staged gNodeB config uses **NR-ARFCN 630000 = 3450.000 MHz**, centred in
the approved range with 15 MHz of margin on each side. Note the stock profile's
`dl_arfcn 628668` is 3430.02 MHz — a 10 MHz channel there would spill below the
approved lower edge.

### Channel plan

| Mode | Analog | Digital | Purpose |
|---|---|---|---|
| Sequential (default) | 3445–3455 | 3445–3455 | C1, C2, C3. One arm at a time on one X310. Frequency cannot confound the comparison. |
| Simultaneous | 3432.5–3442.5 | 3457.5–3467.5 | C4, coexistence. Needs two X310s and a second server-class node. |

Both arms default to **10 MHz**, not 40: it keeps PRB-slot accounting
comparable to the baseline paper, and a B210 over USB3 cannot reliably sustain
40 MHz. A 40 MHz digital-only config is staged alongside as
`gnb_x310_n78_40mhz_e2.yml`.

## Server-class ("d") node cost

X310s and NUCs are bound to named components and do **not** draw from the
general compute pool. Only X310-paired compute, the CN and the control node do.

| Topology | d740 | d430 | Total |
|---|---|---|---|
| **NUCs only** (no X310, no CN) | 0 | 0 | **0** |
| Minimal (1 X310, no CN) | 1 | 0 | **1** |
| **Default** (1 X310, 4 NUCs, CN) | 1 | 1 | **2** |
| + control node | 1 | 2 | **3** |
| Simultaneous (2 X310s + control) | 2 | 2 | **4** |

Four NUCs cost zero d-nodes, so compute is the binding constraint, not radios.

**The NUC-only topology matters for sequencing.** Plan Tier 0 — the analog
arm, the impairment sweep, the error decomposition, the whole week-14 preprint
— needs no 5G stack and no X310-paired server. Set the X310 count to zero and
`include_cn` off, and the experiment consumes no server-class nodes at all,
which is the easiest thing to get scheduled. You lose the X310 receiver, so
this is for B210-to-B210 work and NUC-local development, not full aggregation.

## Parameters

- **`clock_source`** — `external` (Octoclock) or `internal`. Exposed, never
  baked: the impairment treatment depends on switching it mid-session.
- **Frequency ranges** — multi-valued, validated.
- **X310 radios** — 1–4. More than one gives the simultaneous topology and
  needs one compute node each.
- **NUCs** — 1–4.
- **Control node** — off by default.
- **Install toggles** — SDR stack, srsRAN, ML stack.
- **`srsran_commit_hash`** — defaults to `release_25_10`.
- **`ue_image`** (advanced) — point at a custom snapshot with the stack
  pre-baked to skip the source builds.

## What gets installed

**SDR nodes and NUCs:** UHD 4.11 (source), X310/B210 FPGA images, GNU Radio
3.10, jumbo frames and socket tuning.

UHD is built from source deliberately. Jammy packages UHD 4.1, which **will
not** talk to an X310 flashed for 4.11 — it fails with
`RFNoC protocol mismatch between SW and HW (SW: 2.0, HW: 1.0)`. The script
skips the build if a new enough UHD is already present.

**NUCs additionally:** CPU-only PyTorch, Flower, `linuxptp`, readable RAPL.
Built on top of `PowderTeam/cots-jammy-image`, so Quectel tooling is inherited
intact. The script verifies at the end that the B210 *and* the modem both still
enumerate.

**gNodeB compute:** srsRAN Project `release_25_10`. E2 (E2SM-KPM, E2SM-RC,
E2SM-CCC) is compiled in by default in 25.10 — there is no `-DENABLE_E2` flag
and none is needed; E2 is gated at runtime from the config. The profile stages
a config using the **25.x schema**, where AMF settings live under `cu_cp` and
`supported_tracking_areas` replaces the bare `tac` (absorbing the old top-level
`slicing` block). Pre-25.x configs fail with `INI was not able to parse amf.`

**Control node:** FlexRIC, Flower server, analysis stack.

## Nothing auto-starts the radio

srsRAN and the GNU Radio flowgraph both want exclusive access to the X310.
Only one can hold it. The profile installs both and starts neither; you
sequence them.

## Verifying the clock

`bin/check-clock.py` measures sample-clock accuracy over a 30 s capture under
each source.

**Do not use the X310's `ref_locked` sensor as evidence.** It reads `True`
under `internal` *and* `external`, across repeated switches — it would report
success with the reference cable disconnected. Measured behaviour: `internal`
is tight and repeatable at +3.2…+3.5 ppm against the host; `external` does not
reproduce it.

## Acceptance test

Per plan §5A.8, the profile is done when, in one instantiation:

- [ ] `uhd_find_devices` sees the B210 on every NUC and the X310 from the gNB node
- [ ] the modem still enumerates on `/dev/ttyUSB0-3` on every NUC
- [ ] `clock_source` flips to `external` and a 30 s measurement distinguishes it
      from `internal` (not `ref_locked`)
- [ ] `gnb --dryrun` validates against the 25.x schema
- [ ] four COTS UEs attach simultaneously
- [ ] the GNU Radio flowgraph opens the X310 after srsRAN releases it

For the simultaneous topology, additionally: two X310s hold centres 15 MHz
apart without desensitizing each other, measured at the receiver.

## Status

Validated offline against Emulab's `geni-lib`: the profile executes, produces
well-formed rspec, emits the `emulab:spectrum` request, and its parameter
validation rejects duplicate radios and out-of-band frequencies. The gNodeB
config's **schema** was validated against a real srsRAN 25.10 binary; the
ARFCN/bandwidth/clock values in this profile have not been run on hardware yet.

**Not yet tested on hardware.** Work through the acceptance test on first
instantiation.

## Provenance

- Spectrum request, 5G core, COTS UE handling, `deploy-open5gs.sh` and the
  `tune-*`/`module-off` scripts: POWDER `srs-indoor-ota`
- Multi-X310 and NUC+B210 allocation patterns: POWDER `indoor-ota`
- The rest is new.
