"""
RRC Protocol Implementation for pyueransim.
Implements 5G RRC messages for gNB-UE communication.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum, auto
import struct
import secrets


# RRC Message Types
class ERrcMessageType(Enum):
    """RRC message types."""
    # UE -> gNB
    RRC_SETUP_REQUEST = 0x01
    RRC_REESTABLISHMENT_REQUEST = 0x08
    RRC_SETUP_COMPLETE = 0x09
    RRC_REESTABLISHMENT_COMPLETE = 0x0b
    RRC_UL_INFORMATION_TRANSFER = 0x0c
    RRC_SECURITY_MODE_COMPLETE = 0x0d
    RRC_SECURITY_MODE_FAILURE = 0x0e
    RRC_UE_CAPABILITY_INFORMATION = 0x10
    RRC_COUNTER_CHECK_RESPONSE = 0x13
    RRC_UE_ASSISTANCE_INFORMATION = 0x17
    RRC_CONN_RECONFIGURATION_COMPLETE = 0x1b
    RRC_CONN_SETUP_COMPLETE = 0x1c
    RRC_CONN_REESTABLISHMENT_COMPLETE = 0x1f

    # gNB -> UE
    RRC_SETUP = 0x02
    RRC_RECONFIGURATION = 0x03
    RRC_REESTABLISHMENT = 0x05
    RRC_RELEASE = 0x06
    RRC_CONN_SETUP = 0x07
    RRC_CONN_RECONFIGURATION = 0x0a
    RRC_CONN_RELEASE = 0x0c
    RRC_DL_INFORMATION_TRANSFER = 0x0f
    RRC_UECAPABILITY_ENQUIRY = 0x12
    RRC_COUNTER_CHECK = 0x14
    RRC_UE_ASSISTANCE_INFORMATION_IND = 0x16
    RRC_MIB = 0x01
    RRC_SIB1 = 0x05


# RRC Establishment Causes
class ERrcEstablishmentCause(Enum):
    """RRC connection establishment causes."""
    EMERGENCY = 0
    HIGH_PRIORITY_ACCESS = 1
    MT_ACCESS = 2
    MO_SIGNAL = 3
    MO_DATA = 4
    MO_VOICE_CALL = 5
    MO_VIDEO_CALL = 6
    MO_SMS = 7
    MMTEL_VOICE = 8
    MMTEL_VIDEO = 9
    MO_IMS_SIGNAL = 10
    SPARE = 11


# Rejection Causes
class ERrcRejectionCause(Enum):
    """RRC connection rejection causes."""
    CONGESTION = 0
    NORMAL = 1
    SPARE = 2


@dataclass
class RrcMessage:
    """RRC message container."""
    rrc_transaction_id: int = 0
    message_type: ERrcMessageType = ERrcMessageType.RRC_SETUP_REQUEST
    payload: bytes = b""

    def encode(self) -> bytes:
        """Encode RRC message to bytes."""
        # RRC Layer 3 message: RRCTransactionIdentifier + MessageType + Payload
        data = bytes([
            (self.rrc_transaction_id << 2) | 0x01,  # RRC Transaction ID
            self.message_type.value,  # Message Type
        ])
        data += self.payload
        return data

    @staticmethod
    def decode(data: bytes) -> 'RrcMessage':
        """Decode RRC message from bytes."""
        if len(data) < 2:
            return RrcMessage()

        msg = RrcMessage()
        msg.rrc_transaction_id = (data[0] >> 2) & 0x03
        msg.message_type = ERrcMessageType(data[1])
        msg.payload = data[2:]
        return msg


@dataclass
class RrcSetupRequest:
    """RRC Setup Request message."""
    ue_id: bytes = b""  # 39-bit UE ID (TMSI or random)
    establishment_cause: ERrcEstablishmentCause = ERrcEstablishmentCause.MO_SIGNAL
    spare: int = 0

    def encode(self) -> bytes:
        """Encode to bytes."""
        # ASN.1 encoding for RRC Setup Request
        cause_value = self.establishment_cause.value & 0x0f

        data = bytes([0x00])  # Spare + configSIB
        data += bytes([cause_value & 0x0f])  # Establishment Cause

        # UE Identity (39 bits)
        ue_id_bytes = self.ue_id if self.ue_id else secrets.token_bytes(5)
        ue_id_bits = int.from_bytes(ue_id_bytes[-5:], 'big') & 0x7FFFFFFFFF

        # Encode UE ID as 5 bytes
        data += bytes([
            (ue_id_bits >> 32) & 0x7f,
            (ue_id_bits >> 24) & 0xff,
            (ue_id_bits >> 16) & 0xff,
            (ue_id_bits >> 8) & 0xff,
            ue_id_bits & 0xff
        ])

        return data


@dataclass
class RrcSetup:
    """RRC Setup message."""
    radio_bearer_config: bytes = b""
    master_cell_group_config: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = b""

        # Radio Bearer Config (simplified)
        data += bytes([0x1d])  # IEI
        data += bytes([0x01, 0x00])  # drb-ToAddModList (empty)

        # Master Cell Group Config
        data += bytes([0x24])  # IEI
        data += bytes([0x0c])  # Length

        # PHY Config
        data += bytes([0x00])  # servingCellConfigCommon
        data += bytes([0x04, 0x00, 0x40, 0x00])  # ssb-PositionsInBurst

        # DMRS Config
        data += bytes([0x02, 0x02, 0x00])  # dmrs-Config

        return data


@dataclass
class RrcSetupComplete:
    """RRC Setup Complete message."""
    selected_plmn_id: int = 1
    dedicated_nas_message: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x00])  # RRC Transaction ID

        # Selected PLMN ID (1 = first in SIB1)
        data += bytes([0x01, self.selected_plmn_id & 0x0f])

        # Registered AMF (optional)
        # Gym State (optional)

        # Dedicated NAS Message (contains Registration Request)
        if self.dedicated_nas_message:
            data += bytes([0x39])  # IEI for dedicatedNAS-Message
            data += bytes([len(self.dedicated_nas_message)]) + self.dedicated_nas_message

        return data


@dataclass
class RrcReconfiguration:
    """RRC Reconfiguration message."""
    rrc_transaction_id: int = 0
    radio_bearer_config: Optional[bytes] = None
    meas_config: Optional[bytes] = None
    non_crit_ext_config: Optional[bytes] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([(self.rrc_transaction_id << 2) | 0x01])

        # Radio Bearer Config (if present)
        if self.radio_bearer_config:
            data += bytes([0x1d]) + bytes([len(self.radio_bearer_config)]) + self.radio_bearer_config

        # Meas Config (optional)
        if self.meas_config:
            data += bytes([0x13]) + bytes([len(self.meas_config)]) + self.meas_config

        return data


@dataclass
class RrcRelease:
    """RRC Release message."""
    rrc_transaction_id: int = 0
    release_cause: int = 0
    redirected_freq_info: Optional[bytes] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([(self.rrc_transaction_id << 2) | 0x01])

        # Release Cause (0 = norml release)
        data += bytes([0x00])  # spare + releaseCause

        # Redirected Frequency Info (optional)
        if self.redirected_freq_info:
            data += bytes([0x05]) + len(self.redirected_freq_info).to_bytes(2, 'big') + self.redirected_freq_info

        return data


@dataclass
class RrcDlInformationTransfer:
    """RRC DL Information Transfer message."""
    rrc_transaction_id: int = 0
    dedicated_nas_message: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([(self.rrc_transaction_id << 2) | 0x01])

        if self.dedicated_nas_message:
            data += bytes([0x39])  # IEI
            data += bytes([len(self.dedicated_nas_message)]) + self.dedicated_nas_message

        return data


@dataclass
class RrcUlInformationTransfer:
    """RRC UL Information Transfer message."""
    dedicated_nas_message: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = b""

        if self.dedicated_nas_message:
            data += bytes([0x39])  # IEI
            data += bytes([len(self.dedicated_nas_message)]) + self.dedicated_nas_message

        return data


@dataclass
class RrcCapability:
    """RRC UE Capability."""
    nr_capability: bytes = b""
    eutra_capability: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes (simplified)."""
        data = bytes([0x00])  # RRC Transaction ID

        # NR Capability (5G)
        nr_cap = bytes([0x40, 0x08, 0x0f, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff])
        data += bytes([0x1c])  # IEI
        data += bytes([len(nr_cap)]) + nr_cap

        return data


@dataclass
class SIB1:
    """System Information Block 1."""
    plmn_identity_list: bytes = b""
    tracking_area_code: bytes = b""
    cell_identity: bytes = b""
    cell_barred: bool = False
    intra_freq_reselection: bool = True
    common_drx_parameters: bytes = b""
    ssb_periodicity_serving_cell: int = 5

    def encode(self) -> bytes:
        """Encode SIB1 to bytes."""
        data = b""

        # PLMN Identity List
        data += bytes([0x00])  # IEI
        plmn = bytes([0x06]) + bytes([0xf1, 0x01]) + bytes([0x08, 0x93])  # MCC=208, MNC=93
        data += bytes([len(plmn)]) + plmn

        # Tracking Area Code (3 bytes)
        data += bytes([0x03, 0x00, 0x00, 0x01])  # TAC = 1

        # Cell Identity (4 bytes)
        data += bytes([0x04, 0x00, 0x00, 0x00, 0x01])  # Cell ID = 1

        # Cell Barred
        data += bytes([0x04, 0x01])  # barred + reselection

        # Intra Frequency Reselection
        data += bytes([0x05, 0x01])  # subCarrierSpacingCommon + ssb-PeriodicityServingCell

        # SSB Periodicity
        data += bytes([0x08, self.ssb_periodicity_serving_cell])

        return data


@dataclass
class MIB:
    """Master Information Block."""
    system_frame_number: int = 0
    subcarrier_spacing_common: int = 0
    ssb_subcarrier_offset: int = 0
    dmrs_type_a_position: int = 0
    pdcch_config_sib1: int = 0
    cell_barred: bool = False
    intra_freq_reselection: bool = True

    def encode(self) -> bytes:
        """Encode MIB to bytes (23 bits)."""
        # MIB is transmitted on PBCH with 23 bits payload
        mib_data = 0

        # System Frame Number (10 bits)
        mib_data |= (self.system_frame_number & 0x3ff) << 0

        # Subcarrier Spacing Common (1 bit)
        mib_data |= (self.subcarrier_spacing_common & 0x01) << 10

        # SSB Subcarrier Offset (4 bits)
        mib_data |= (self.ssb_subcarrier_offset & 0x0f) << 11

        # DMRS Type A Position (1 bit)
        mib_data |= (self.dmrs_type_a_position & 0x01) << 15

        # PDCCH Config SIB1 (8 bits)
        mib_data |= (self.pdcch_config_sib1 & 0xff) << 16

        # Cell Barred (1 bit)
        mib_data |= (0 if self.cell_barred else 1) << 24

        # Intra Frequency Reselection (1 bit)
        mib_data |= (0 if self.intra_freq_reselection else 1) << 25

        # Spare (6 bits)
        mib_data |= 0x3f << 26

        # Encode as 4 bytes (MIB is 24 bits total)
        return mib_data.to_bytes(4, 'big')[:3]


# RRC State Machine for UE
class RrcStateMachine:
    """RRC State Machine for UE."""

    def __init__(self):
        self.state = "idle"
        self.setup_complete_received = False
        self.reconfiguration_complete_received = False

    async def handle_message(self, msg: RrcMessage) -> Optional[RrcMessage]:
        """Handle RRC message and return response."""
        if self.state == "idle":
            if msg.message_type == ERrcMessageType.RRC_SETUP:
                self.state = "connecting"
                return RrcMessage(
                    message_type=ERrcMessageType.RRC_SETUP_COMPLETE,
                    rrc_transaction_id=msg.rrc_transaction_id
                )

        elif self.state == "connecting":
            if msg.message_type == ERrcMessageType.RRC_RECONFIGURATION:
                self.state = "connected"
                return RrcMessage(
                    message_type=ERrcMessageType.RRC_CONN_RECONFIGURATION_COMPLETE,
                    rrc_transaction_id=msg.rrc_transaction_id
                )

        elif self.state == "connected":
            if msg.message_type == ERrcMessageType.RRC_RELEASE:
                self.state = "idle"
                return None

        return None

    def is_connected(self) -> bool:
        """Check if RRC is connected."""
        return self.state == "connected"


# RRC Task for gNB
class RrcTask:
    """RRC Task for gNB."""

    def __init__(self, gnb_id: int):
        self.gnb_id = gnb_id
        self.ue_connections: Dict[int, RrcStateMachine] = {}

    async def handle_rrc_message(self, ue_id: int, data: bytes) -> Optional[bytes]:
        """Handle incoming RRC message from UE."""
        msg = RrcMessage.decode(data)

        if msg.message_type == ERrcMessageType.RRC_SETUP_REQUEST:
            # Create new connection state
            self.ue_connections[ue_id] = RrcStateMachine()

            # Send RRC Setup
            response = RrcMessage(
                message_type=ERrcMessageType.RRC_SETUP,
                payload=RrcSetup().encode()
            )
            return response.encode()

        elif msg.message_type == ERrcMessageType.RRC_SETUP_COMPLETE:
            # UE setup complete - send RRC Reconfiguration
            if ue_id in self.ue_connections:
                self.ue_connections[ue_id].setup_complete_received = True

                response = RrcMessage(
                    message_type=ERrcMessageType.RRC_RECONFIGURATION,
                    payload=RrcReconfiguration().encode()
                )
                return response.encode()

        elif msg.message_type == ERrcMessageType.RRC_CONN_RECONFIGURATION_COMPLETE:
            if ue_id in self.ue_connections:
                self.ue_connections[ue_id].reconfiguration_complete_received = True
                self.ue_connections[ue_id].state = "connected"

        elif msg.message_type == ERrcMessageType.RRC_UL_INFORMATION_TRANSFER:
            # Forward to NAS layer
            return msg.payload

        return None

    def get_connected_ue_count(self) -> int:
        """Get count of connected UEs."""
        return sum(1 for sm in self.ue_connections.values() if sm.is_connected())

    def release_ue(self, ue_id: int) -> bool:
        """Release UE connection."""
        if ue_id in self.ue_connections:
            response = RrcMessage(
                message_type=ERrcMessageType.RRC_RELEASE,
                payload=RrcRelease().encode()
            )
            del self.ue_connections[ue_id]
            return True
        return False
