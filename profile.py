#!/usr/bin/env python

"""
OTA-FL Indoor OTA Lab profile.

Allocates the POWDER Indoor OTA Lab for over-the-air federated learning
experiments with both an analog (GNU Radio / B210) arm and a digital
(srsRAN / COTS UE) arm, per the research plan's section 5A.

Derived from POWDER's `srs-indoor-ota` (spectrum request, 5G core, COTS UE
handling) and `indoor-ota` (multi-X310 and NUC+B210 allocation patterns).

Key differences from both:
  * Requests spectrum (`indoor-ota` never did), defaulting to the approved
    3430-3470 MHz range taken from `srs-indoor-ota`.
  * Allocates a radio-free control node (N6) so the 5G core, RIC and Flower
    server stay off the real-time SDR host.
  * Supports 1-4 NUCs, each usable as BOTH an analog UE (B210) and a digital
    UE (COTS modem), and optional extra X310s.
  * Nothing auto-starts the radio: srsRAN and GNU Radio time-share the X310,
    so sequencing is left to the experimenter (plan 5A.6 constraint 2).
"""

import os

import geni.portal as portal
import geni.rspec.pg as rspec
import geni.rspec.igext as IG
import geni.rspec.emulab.spectrum as spectrum


tourDescription = """
### OTA-FL: analog and digital federated learning in the Indoor OTA Lab

Allocates the POWDER Indoor OTA Lab for over-the-air federated learning
experiments with two comparable arms:

* **Analog arm** - GNU Radio flowgraphs, B210 SDRs on the NUCs transmitting
  superposed model updates to an X310 acting as the aggregation receiver.
* **Digital arm** - srsRAN Project 5G gNodeB on the same X310, Open5GS core,
  and the COTS 5G modems attached to the same NUCs.

Both arms run on the same nodes in the same room, so the comparison between
them is not confounded by hardware or geometry.

Nothing that claims the radio is started automatically: the srsRAN gNodeB and
the GNU Radio flowgraph both want exclusive access to the X310, so you start
whichever arm you are running by hand.
"""

tourInstructions = """
Startup scripts are still running when the experiment becomes ready. Watch the
"Startup" column in the List View and wait for every compute node to show
"Finished" before proceeding.

#### 1. Verify the testbed

On the gNodeB compute node (`*-gnuradio-comp`):

```
uhd_find_devices
```

On each NUC (`ota-nucN-ue`), confirm both radios are present:

```
uhd_find_devices          # the B210
ls /dev/ttyUSB*           # the COTS modem
```

#### 2. Clock source (the impairment treatment)

Both `clock_source` and `time_source` are left at the profile parameter value
and are switchable at runtime. Note that the X310's `ref_locked` sensor reads
`True` under *both* `internal` and `external` and must not be used as evidence
that an external reference is present. Verify with a frequency measurement
instead:

```
/local/repository/bin/check-clock.py
```

#### 3. Digital arm

On the CN node the Open5GS services run as system services (`systemctl status
open5gs-*`). Start the gNodeB on the gNodeB compute node:

```
sudo /var/tmp/srsRAN_Project/build/apps/gnb/gnb \\
    -c /var/tmp/etc/srsran/gnb_x310_n78_e2.yml
```

Then bring up a COTS UE on a NUC:

```
sudo quectel-CM -s internet -4
# in another session
sudo sh -c "chat -t 1 -sv '' AT OK 'AT+CFUN=1' OK < /dev/ttyUSB2 > /dev/ttyUSB2"
```

#### 4. Analog arm

Stop the gNodeB first - it holds the X310. Then run your GNU Radio flowgraph
on the gNodeB compute node (receiver) and on the NUCs (transmitters).

#### 5. Frequency discipline

Transmit only inside the frequency range you requested and had approved.
Transmissions are not automatically policed.
"""


BIN_PATH = "/local/repository/bin"
ETC_PATH = "/local/repository/etc"
UBUNTU_IMG = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"
COTS_UE_IMG = "urn:publicid:IDN+emulab.net+image+PowderTeam:cots-jammy-image"
COMP_MANAGER_ID = "urn:publicid:IDN+emulab.net+authority+cm"

# srsRAN release_25_10. Ships E2 (KPM/RC/CCC) compiled in by default, unlike
# the 2024-era build the stock profile pins.
DEFAULT_SRSRAN_HASH = "release_25_10"

OPEN5GS_DEPLOY_SCRIPT = os.path.join(BIN_PATH, "deploy-open5gs.sh")
SRSRAN_DEPLOY_SCRIPT = os.path.join(BIN_PATH, "deploy-srsran.sh")
SDR_DEPLOY_SCRIPT = os.path.join(BIN_PATH, "deploy-sdr-stack.sh")
UE_DEPLOY_SCRIPT = os.path.join(BIN_PATH, "deploy-ue-stack.sh")
CONTROL_DEPLOY_SCRIPT = os.path.join(BIN_PATH, "deploy-control.sh")

# Per-role IPv4 on the shared experiment LAN. The CN takes .1 so it matches
# the address baked into the stock srsRAN/Open5GS configs.
CN_IP = "192.168.1.1"
GNB_IP_BASE = 2      # gNodeB compute nodes get .2, .3, ...
CTRL_IP = "192.168.1.10"
UE_IP_BASE = 20      # NUCs get .20, .21, ...


pc = portal.Context()

node_types = [
    ("d430", "Emulab, d430"),
    ("d740", "Emulab, d740"),
    ("d760p", "Emulab, d760"),
    ("d760-gpu", "Emulab, d760 with L40S GPU"),
]

indoor_ota_x310s = [
    ("ota-x310-1", "USRP X310 #1 (Channel 0 antennas only)"),
    ("ota-x310-2", "USRP X310 #2 (2x2, antennas on Ch0 and Ch1)"),
    ("ota-x310-3", "USRP X310 #3 (2x2, antennas on Ch0 and Ch1)"),
    ("ota-x310-4", "USRP X310 #4 (Channel 0 antennas only)"),
]

indoor_ota_nucs = [
    ("ota-nuc{}".format(i), "Indoor OTA nuc{} with B210 and COTS UE".format(i))
    for i in range(1, 5)
]

clock_sources = [
    ("external", "External (Octoclock-G 10 MHz / 1 PPS)"),
    ("internal", "Internal (free-running oscillator)"),
]


# ---------------------------------------------------------------- parameters

pc.defineParameter(
    name="sdr_nodetype",
    description="Type of compute node paired with the X310 SDRs",
    typ=portal.ParameterType.STRING,
    defaultValue=node_types[1],          # d740
    legalValues=node_types
)

pc.defineParameter(
    name="include_cn",
    description="Include the 5G core network node (needed for the digital arm)",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True
)

pc.defineParameter(
    name="cn_nodetype",
    description="Type of compute node to use for the CN node",
    typ=portal.ParameterType.STRING,
    defaultValue=node_types[0],          # d430
    legalValues=node_types
)

pc.defineParameter(
    name="include_control_node",
    description="Include a separate radio-free control node (RIC, Flower server, "
                "orchestration). Keeps the control plane off the real-time SDR host.",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=False
)

pc.defineParameter(
    name="control_nodetype",
    description="Type of compute node to use for the control node",
    typ=portal.ParameterType.STRING,
    defaultValue=node_types[0],          # d430
    legalValues=node_types
)

pc.defineParameter(
    name="clock_source",
    description="Radio clock and time source. Switchable at runtime; this only "
                "sets the starting value.",
    typ=portal.ParameterType.STRING,
    defaultValue=clock_sources[0],       # external
    legalValues=clock_sources
)

pc.defineParameter(
    name="install_sdr_stack",
    description="Build UHD 4.11 and GNU Radio 3.10 from source on the SDR nodes "
                "(needed for the analog arm; adds time to startup)",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True
)

pc.defineParameter(
    name="install_srsran",
    description="Build srsRAN Project on the gNodeB compute node (needed for "
                "the digital arm)",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True
)

pc.defineParameter(
    name="install_ml_stack",
    description="Install PyTorch (CPU) and Flower on the NUCs for local training",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True
)

pc.defineParameter(
    name="srsran_commit_hash",
    description="Commit hash, tag or branch for srsRAN Project",
    typ=portal.ParameterType.STRING,
    defaultValue=DEFAULT_SRSRAN_HASH,
    advanced=True
)

pc.defineParameter(
    name="sdr_compute_image",
    description="Override image for compute nodes connected to SDRs",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True
)

pc.defineParameter(
    name="ue_image",
    description="Override image for the NUCs. Leave blank for the stock COTS UE "
                "image. Set this to a custom snapshot that already has the SDR "
                "and ML stack baked in to skip the source builds.",
    typ=portal.ParameterType.STRING,
    defaultValue="",
    advanced=True
)

pc.defineParameter(
    name="multiplex_lans",
    description="Multiplex experiment networks over physical interfaces using VLANs",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True,
    advanced=True
)

# gNodeB X310(s). Two entries gives the simultaneous dual-arm topology, which
# needs a second server-class compute node.
pc.defineStructParameter(
    name="x310_radios",
    description="X310 radios to allocate. The first is the primary gNodeB / "
                "aggregation receiver. Prefer ota-x310-2 or -3: they have "
                "antennas on both channels.",
    defaultValue=[{"node_id": "ota-x310-2"}],
    multiValue=True,
    min=1,
    max=4,
    members=[
        portal.Parameter(
            "node_id",
            "Indoor OTA X310",
            portal.ParameterType.STRING,
            indoor_ota_x310s[1],         # ota-x310-2
            indoor_ota_x310s
        )
    ]
)

# NUCs. Each carries a B210 (analog UE) and a COTS modem (digital UE).
pc.defineStructParameter(
    name="ue_nodes",
    description="Indoor OTA NUCs. Each provides a B210 for the analog arm and a "
                "COTS 5G modem for the digital arm.",
    defaultValue=[{"node_id": "ota-nuc{}".format(i)} for i in range(1, 5)],
    multiValue=True,
    min=1,
    max=4,
    members=[
        portal.Parameter(
            "node_id",
            "Indoor OTA NUC",
            portal.ParameterType.STRING,
            indoor_ota_nucs[0],
            indoor_ota_nucs
        )
    ]
)

# Spectrum. Defaults lifted from srs-indoor-ota.
pc.defineStructParameter(
    "freq_ranges", "Frequency Ranges To Transmit In",
    defaultValue=[{"freq_min": 3430.0, "freq_max": 3470.0}],
    multiValue=True,
    min=1,
    multiValueTitle="Frequency ranges to be used for transmission.",
    members=[
        portal.Parameter(
            "freq_min",
            "Frequency Range Min",
            portal.ParameterType.BANDWIDTH,
            3430.0,
            longDescription="Values are rounded to the nearest kilohertz."
        ),
        portal.Parameter(
            "freq_max",
            "Frequency Range Max",
            portal.ParameterType.BANDWIDTH,
            3470.0,
            longDescription="Values are rounded to the nearest kilohertz."
        ),
    ]
)

params = pc.bindParameters()


# ---------------------------------------------------------------- validation

x310_ids = [r.node_id for r in params.x310_radios]
if len(set(x310_ids)) != len(x310_ids):
    pc.reportError(portal.ParameterError(
        "Each X310 may be selected only once.", ["x310_radios"]))

ue_ids = [n.node_id for n in params.ue_nodes]
if len(set(ue_ids)) != len(ue_ids):
    pc.reportError(portal.ParameterError(
        "Each NUC may be selected only once.", ["ue_nodes"]))

for fr in params.freq_ranges:
    if fr.freq_min < 3358 or fr.freq_max > 3600:
        pc.reportError(portal.ParameterError(
            "Frequency range must lie within 3358 - 3600 MHz.", ["freq_ranges"]))
    if fr.freq_max - fr.freq_min < 1:
        pc.reportError(portal.ParameterError(
            "Frequency range must be at least 1 MHz wide.", ["freq_ranges"]))

if params.install_srsran and not params.include_cn:
    pc.reportWarning(portal.ParameterWarning(
        "srsRAN is being installed but no core network node was requested. The "
        "digital arm needs the CN node.", ["include_cn"]))

# The simultaneous topology needs one compute node per X310.
if len(params.x310_radios) > 1:
    pc.reportWarning(portal.ParameterWarning(
        "Each X310 gets its own paired compute node. Confirm your reservation "
        "covers {} server-class nodes.".format(len(params.x310_radios)),
        ["x310_radios"]))

pc.verifyParameters()
request = pc.makeRequestRSpec()


# ---------------------------------------------------------------- topology

# Shared experiment LAN. Carries model distribution, E2, Flower and the NG
# interface between the gNodeB and the core.
cn_link = request.LAN("cn-link")
cn_link.setNoBandwidthShaping()
if params.multiplex_lans:
    cn_link.link_multiplexing = True
    cn_link.best_effort = True


def x310_node_pair(idx, x310_radio):
    """A compute node paired with an X310 over 10 GbE.

    idx 0 is the primary gNodeB / aggregation receiver.
    """
    role = "gnb" if idx == 0 else "gnb{}".format(idx + 1)
    node = request.RawPC("{}-comp".format(x310_radio))
    node.component_manager_id = COMP_MANAGER_ID
    node.hardware_type = params.sdr_nodetype
    node.disk_image = params.sdr_compute_image or UBUNTU_IMG

    # Dedicated 10 GbE link to the radio.
    node_radio_if = node.addInterface("usrp_if")
    node_radio_if.addAddress(
        rspec.IPv4Address("192.168.40.1", "255.255.255.0"))
    radio_link = request.Link("radio-link-{}".format(idx))
    radio_link.bandwidth = 10 * 1000 * 1000
    radio_link.addInterface(node_radio_if)

    radio = request.RawPC("{}-sdr".format(x310_radio))
    radio.component_id = x310_radio
    radio.component_manager_id = COMP_MANAGER_ID
    radio_link.addNode(radio)

    # Experiment LAN.
    cn_if = node.addInterface("cn-if")
    cn_if.addAddress(rspec.IPv4Address(
        "192.168.1.{}".format(GNB_IP_BASE + idx), "255.255.255.0"))
    cn_link.addInterface(cn_if)

    node.addService(rspec.Execute(
        shell="bash", command=os.path.join(BIN_PATH, "tune-cpu.sh")))
    node.addService(rspec.Execute(
        shell="bash", command=os.path.join(BIN_PATH, "tune-sdr-iface.sh")))

    if params.install_sdr_stack:
        node.addService(rspec.Execute(
            shell="bash",
            command="{} '{}'".format(SDR_DEPLOY_SCRIPT, params.clock_source)))

    if params.install_srsran:
        srsran_hash = params.srsran_commit_hash or DEFAULT_SRSRAN_HASH
        node.addService(rspec.Execute(
            shell="bash",
            command="{} '{}' '{}' '{}'".format(
                SRSRAN_DEPLOY_SCRIPT, srsran_hash, params.clock_source, role)))

    return node


def ue_node(idx, nuc_id):
    """A NUC carrying both a B210 (analog UE) and a COTS 5G modem (digital UE)."""
    node = request.RawPC("{}-ue".format(nuc_id))
    node.component_manager_id = COMP_MANAGER_ID
    node.component_id = nuc_id
    node.disk_image = params.ue_image or COTS_UE_IMG

    cn_if = node.addInterface("cn-if")
    cn_if.addAddress(rspec.IPv4Address(
        "192.168.1.{}".format(UE_IP_BASE + idx), "255.255.255.0"))
    cn_link.addInterface(cn_if)

    # Keep the modem quiet until the experimenter brings it up, so it cannot
    # attach to a stray network during startup.
    node.addService(rspec.Execute(
        shell="bash", command=os.path.join(BIN_PATH, "module-off.sh")))
    node.addService(rspec.Execute(
        shell="bash", command=os.path.join(BIN_PATH, "update-udhcpc-script.sh")))
    node.addService(rspec.Execute(
        shell="bash",
        command="{} '{}' '{}' '{}'".format(
            UE_DEPLOY_SCRIPT,
            "yes" if params.install_sdr_stack else "no",
            "yes" if params.install_ml_stack else "no",
            params.clock_source)))

    return node


# Core network node.
if params.include_cn:
    cn_node = request.RawPC("cn5g")
    cn_node.component_manager_id = COMP_MANAGER_ID
    cn_node.hardware_type = params.cn_nodetype
    cn_node.disk_image = UBUNTU_IMG
    cn_if = cn_node.addInterface("cn-if")
    cn_if.addAddress(rspec.IPv4Address(CN_IP, "255.255.255.0"))
    cn_link.addInterface(cn_if)
    cn_node.addService(rspec.Execute(
        shell="bash", command=OPEN5GS_DEPLOY_SCRIPT))

# Radio-free control node: RIC, Flower server, orchestration, results.
if params.include_control_node:
    ctrl_node = request.RawPC("ctrl")
    ctrl_node.component_manager_id = COMP_MANAGER_ID
    ctrl_node.hardware_type = params.control_nodetype
    ctrl_node.disk_image = UBUNTU_IMG
    ctrl_if = ctrl_node.addInterface("cn-if")
    ctrl_if.addAddress(rspec.IPv4Address(CTRL_IP, "255.255.255.0"))
    cn_link.addInterface(ctrl_if)
    ctrl_node.addService(rspec.Execute(
        shell="bash", command=CONTROL_DEPLOY_SCRIPT))

for idx, x310_radio in enumerate(params.x310_radios):
    x310_node_pair(idx, x310_radio.node_id)

for idx, n in enumerate(params.ue_nodes):
    ue_node(idx, n.node_id)

# Spectrum. Without this the experiment has no authorization to transmit.
for frange in params.freq_ranges:
    request.requestSpectrum(frange.freq_min, frange.freq_max, 0)


tour = IG.Tour()
tour.Description(IG.Tour.MARKDOWN, tourDescription)
tour.Instructions(IG.Tour.MARKDOWN, tourInstructions)
request.addTour(tour)

pc.printRequestRSpec(request)
