from __future__ import annotations
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import uuid


# Import core protocol implementations
from ..core import (
    OctetString, EMmState, EMmSubState, ECmState, ERrcState, ESmState,
    NasSecurityContext, TimerManager, Timer
)
from ..core.nas import (
    NasMessage, ENasMessageType, NasSecurity, UsimContext,
    RegistrationRequest, RegistrationAccept, PduSessionEstablishmentRequest,
    PduSessionEstablishmentAccept, UlNasTransport
)
from ..core.rrc import (
    RrcMessage, ERrcMessageType, RrcSetup, RrcSetupComplete,
    RrcReconfiguration, RrcStateMachine
)
from ..core.ngap import (
    ENgapMessageType, NgapConnection, NgSetupRequest, NgSetupResponse,
    InitialUeMessage, UplinkNasTransport, NgapTask
)


# UE Configuration
@dataclass
class UeConfig:
    """UE configuration matching UERANSIM format."""
    imsi: str = "imsi-208930000000001"
    key: str = "8baf473f2f8fd09487cccbd7097c6862"
    opc: str = "8e27b6af0e692e750f32667a3b14605d"
    amf: str = "8000"
    sqn: int = 0
    dnn: str = "internet"
    sst: int = 1
    sd: int = 0x010203
    # Additional UERANSIM-compatible fields
    protectionScheme: int = 0
    homeNetworkPublicKey: str = ""
    homeNetworkKeyId: int = 1
    routingIndicator: str = "0000"


@dataclass
class UeState:
    """UE state snapshot."""
    ue_id: str = ""
    mm_state: str = "MM_NULL"
    rrc_state: str = "RRC_IDLE"
    cm_state: str = "CM_IDLE"
    sm_state: str = "SM_NULL"
    connected_gnb: Optional[str] = None
    pdu_sessions: List[Dict] = field(default_factory=list)
    registration_attempts: int = 0
    last_registration_time: Optional[str] = None


class UeSimulation:
    """
    UE Simulation Component.
    Implements 5G NAS/RRC protocols and connects to real gNB via IP.
    """

    def __init__(self, config: UeConfig, ue_id: str):
        self.config = config
        self.ue_id = ue_id
        self.state = UeState(ue_id=ue_id)

        # Protocol state
        self.mm_state = EMmState.MM_NULL
        self.mm_substate = EMmSubState.MM_DEREGISTERED_NORMAL_SERVICE
        self.rrc_state = ERrcState.RRC_IDLE
        self.cm_state = ECmState.CM_IDLE
        self.sm_state = ESmState.SM_NULL

        # Security context
        self.security_context: Optional[NasSecurityContext] = None
        self.usim_context = UsimContext(
            imsi=config.imsi,
            key=bytes.fromhex(config.key),
            opc=bytes.fromhex(config.opc),
            amf=bytes.fromhex(config.amf),
            sqn=config.sqn
        )

        # Timer manager
        self.timers = TimerManager()

        # Callbacks for sending messages
        self.on_rrc_message: Optional[Callable[[bytes], None]] = None
        self.on_nas_message: Optional[Callable[[bytes], None]] = None

        # Connection state
        self.connected_gnb_id: Optional[str] = None
        self.ran_ue_ngap_id: Optional[int] = None

        # Logging
        self.log_callback: Optional[Callable[[str, str], None]] = None

    def log(self, level: str, message: str) -> None:
        """Log a message."""
        if self.log_callback:
            self.log_callback(level, f"[UE-{self.ue_id}] {message}")

    def get_state(self) -> UeState:
        """Get current state snapshot."""
        self.state.mm_state = self.mm_state.name
        self.state.rrc_state = self.rrc_state.name
        self.state.cm_state = self.cm_state.name
        self.state.sm_state = self.sm_state.name
        self.state.connected_gnb = self.connected_gnb_id
        self.state.registration_attempts += 1
        return self.state

    def create_registration_request(self) -> bytes:
        """Create NAS Registration Request message."""
        req = RegistrationRequest()

        # 5GMM Capability
        req.ie_5gmm_capability = bytes([0x80, 0x00, 0x00])

        # UE Security Capability
        req.ie_ue_security_capability = bytes([0xe0, 0x00, 0x00])

        # Mobile Identity - SUPI
        supi_parts = self.config.imsi.split("-")[1]
        supi_bytes = bytes([0x01])
        for i in range(0, len(supi_parts), 3):
            if i + 3 <= len(supi_parts):
                supi_bytes += bytes([int(supi_parts[i:i+3])])
        req.ie_mobile_identity = supi_bytes[:8]

        # Registration Type
        req.ie_registration_type = 0x01

        # Requested NSSAI
        sst = self.config.sst & 0xff
        sd = (self.config.sd >> 16) & 0xff
        req.ie_requested_nssai = bytes([sst, 0x01, 0x00, sd])

        nas_msg = NasMessage(
            message_type=ENasMessageType.REGISTRATION_REQUEST,
            plain_message=req.encode()
        )
        return nas_msg.encode()

    async def start(self, gnb_ip: str) -> None:
        """Start UE and connect to gNB."""
        self.log("INFO", f"Starting UE, connecting to gNB at {gnb_ip}")
        await self.start_registration(gnb_ip)

    async def start_registration(self, gnb_id: str) -> None:
        """Start 5G registration process."""
        from ..core.rrc import RrcSetupRequest, ERrcEstablishmentCause

        self.connected_gnb_id = gnb_id
        self.mm_state = EMmState.MM_REGISTERED_INITIATED
        self.mm_substate = EMmSubState.MM_REGISTERED_NORMAL_SERVICE

        # Create RRC Setup Request
        setup_req = RrcSetupRequest(
            establishment_cause=ERrcEstablishmentCause.MO_SIGNAL
        )
        rrc_msg = RrcMessage(
            message_type=ERrcMessageType.RRC_SETUP_REQUEST,
            payload=setup_req.encode()
        )

        self.log("INFO", "Sending RRC Setup Request")
        if self.on_rrc_message:
            self.on_rrc_message(rrc_msg.encode())

    async def handle_rrc_message(self, data: bytes) -> Optional[bytes]:
        """Handle incoming RRC message."""
        msg = RrcMessage.decode(data)

        if self.rrc_state == ERrcState.RRC_IDLE:
            if msg.message_type == ERrcMessageType.RRC_SETUP:
                self.rrc_state = ERrcState.RRC_CONNECTED
                self.cm_state = ECmState.CM_CONNECTED
                self.log("INFO", "RRC Connection established")

                # Send RRC Setup Complete with Registration Request
                nas_pdu = self.create_registration_request()
                setup_complete = RrcSetupComplete(
                    dedicated_nas_message=nas_pdu
                )
                rrc_msg = RrcMessage(
                    message_type=ERrcMessageType.RRC_SETUP_COMPLETE,
                    payload=setup_complete.encode()
                )
                self.log("INFO", "Sending Registration Request")
                return rrc_msg.encode()

        elif self.rrc_state == ERrcState.RRC_CONNECTED:
            if msg.message_type == ERrcMessageType.RRC_RECONFIGURATION:
                self.log("INFO", "RRC Reconfiguration received")
                complete = RrcMessage(
                    message_type=ERrcMessageType.RRC_CONN_RECONFIGURATION_COMPLETE,
                    rrc_transaction_id=msg.rrc_transaction_id
                )
                return complete.encode()

            elif msg.message_type == ERrcMessageType.RRC_DL_INFORMATION_TRANSFER:
                if self.on_nas_message:
                    self.log("INFO", "Forwarding NAS message to UE")
                    self.on_nas_message(msg.payload)

            elif msg.message_type == ERrcMessageType.RRC_RELEASE:
                self.log("INFO", "RRC Release received")
                self.rrc_state = ERrcState.RRC_IDLE
                self.cm_state = ECmState.CM_IDLE
                self.mm_state = EMmState.MM_DEREGISTERED
                self.connected_gnb_id = None

        return None

    async def handle_nas_message(self, data: bytes) -> Optional[bytes]:
        """Handle incoming NAS message."""
        nas_msg = NasMessage.decode(data)

        if nas_msg.message_type == ENasMessageType.REGISTRATION_ACCEPT:
            self.log("INFO", "Registration Accept received")
            self.mm_state = EMmState.MM_REGISTERED
            self.mm_substate = EMmSubState.MM_REGISTERED_NORMAL_SERVICE
            self.state.last_registration_time = datetime.now().isoformat()
            await self.start_pdu_session()

        elif nas_msg.message_type == ENasMessageType.PDU_SESSION_ESTABLISHMENT_ACCEPT:
            self.log("INFO", "PDU Session Established")
            self.sm_state = ESmState.SM_ACTIVE
            session = {"id": 1, "state": "ACTIVE", "type": "IPv4", "apn": self.config.dnn}
            self.state.pdu_sessions.append(session)

        return None

    async def start_pdu_session(self) -> None:
        """Start PDU session establishment."""
        self.sm_state = ESmState.SM_PENDING

        pdu_req = PduSessionEstablishmentRequest(
            ie_pdu_session_type=0x01,
            ie_request_type=0x01,
            ie_s_nssai=bytes([self.config.sst, 0x03, 0x00, (self.config.sd >> 16) & 0xff]),
            ie_dnn=self.config.dnn.encode('ascii')
        )

        nas_msg = NasMessage(
            message_type=ENasMessageType.PDU_SESSION_ESTABLISHMENT_REQUEST,
            plain_message=pdu_req.encode()
        )

        self.log("INFO", "Sending PDU Session Establishment Request")
        if self.on_nas_message:
            self.on_nas_message(nas_msg.encode())

    def get_metrics(self) -> Dict[str, Any]:
        """Get UE metrics."""
        return {
            "ue_id": self.ue_id,
            "imsi": self.config.imsi,
            "mm_state": self.mm_state.name,
            "rrc_state": self.rrc_state.name,
            "cm_state": self.cm_state.name,
            "sm_state": self.sm_state.name,
            "connected": self.rrc_state == ERrcState.RRC_CONNECTED,
            "pdu_sessions": len(self.state.pdu_sessions),
            "registration_attempts": self.state.registration_attempts,
            "last_registration": self.state.last_registration_time
        }


# gNB Configuration
@dataclass
class GnbConfig:
    """gNB configuration matching UERANSIM format."""
    mcc: str = "208"
    mnc: str = "93"
    nci: int = 0x000000010
    id_length: int = 32
    tac: int = 1
    ngap_ip: str = "127.0.0.1"
    gtp_ip: str = "127.0.0.1"
    amf_ip: str = "127.0.0.1"
    amf_port: int = 38412


@dataclass
class GnbState:
    """gNB state snapshot."""
    gnb_id: str = ""
    state: str = "GNB_INVALID"
    connected_ues: int = 0
    amf_connected: bool = False
    ngap_state: str = "NGAP_IDLE"


class GnbSimulation:
    """
    gNB Simulation Component.
    Implements NGAP/RRC protocols and connects to real AMF via SCTP.
    """

    def __init__(self, config: GnbConfig, gnb_id: str):
        self.config = config
        self.gnb_id = gnb_id
        self.state = GnbState(gnb_id=gnb_id)

        # NGAP connection to AMF
        self.ngap_connection: Optional[NgapConnection] = None

        # UE management
        self.ues: Dict[str, UeSimulation] = {}
        self.ue_contexts: Dict[int, Dict] = {}

        # State
        self.gnb_state = "GNB_POWERING_ON"
        self.ngap_state = "NGAP_IDLE"
        self.amf_connected = False

        # Callbacks
        self.on_log: Optional[Callable[[str, str], None]] = None

        # Metrics
        self.metrics = {
            "total_ues": 0,
            "connected_ues": 0,
            "registration_requests": 0,
            "pdu_sessions_established": 0,
            "messages_exchanged": 0
        }

    def log(self, level: str, message: str) -> None:
        """Log a message."""
        timestamp = datetime.now().isoformat()
        msg = f"[{timestamp}] [{level}] [{self.gnb_id}] {message}"
        if self.on_log:
            self.on_log(level, msg)
        print(msg)

    async def start(self) -> None:
        """Start gNB and connect to real AMF via SCTP."""
        self.gnb_state = "GNB_CONFIGURATION"
        self.log("INFO", "gNB starting...")

        # Create NGAP connection to AMF
        self.ngap_connection = NgapConnection(
            gnb_id=hash(self.gnb_id) % 0xFFFFFFFF,
            amf_host=self.config.amf_ip,
            amf_port=self.config.amf_port,
            local_address=self.config.ngap_ip,
            local_port=0
        )

        self.ngap_state = "NGAP_CONNECTING"
        self.gnb_state = "GNB_WAITING_FOR_N2"

        # Connect to AMF via SCTP
        self.log("INFO", f"Connecting to AMF {self.config.amf_ip}:{self.config.amf_port}")

        connected = await self.ngap_connection.connect()
        if connected:
            self.log("INFO", "Connected to AMF")
            self.ngap_state = "NGAP_CONNECTED"
            self.amf_connected = True
            self.state.amf_connected = True

            # Start NGAP receive loop
            asyncio.create_task(self.ngap_receive_loop())

            # Send NG Setup Request
            self.log("INFO", "Sending NG Setup Request")
            await self.ngap_connection.send_ng_setup_request()

            self.gnb_state = "GNB_READY"
            self.state.state = "GNB_READY"
            self.state.ngap_state = "NGAP_CONNECTED"
            self.log("INFO", "gNB is ready")
        else:
            self.log("ERROR", "Failed to connect to AMF")
            self.gnb_state = "GNB_FAILURE"

    async def ngap_receive_loop(self) -> None:
        """Receive NGAP messages from AMF."""
        if not self.ngap_connection:
            return

        while self.amf_connected:
            data = await self.ngap_connection.receive()
            if data:
                await self.handle_ngap_message(data)

    async def handle_ngap_message(self, data: bytes) -> None:
        """Handle incoming NGAP message from AMF."""
        self.metrics["messages_exchanged"] += 1

        # Parse NGAP message
        # This is simplified - full implementation would decode properly
        self.log("INFO", f"Received NGAP message ({len(data)} bytes)")

        # Handle NG Setup Response
        if len(data) > 0 and data[0] == 0x00:  # NGAP initiateiatingMessage
            self.log("INFO", "NG Setup Response received from AMF")

    async def handle_ue_rrc(self, ue_id: str, data: bytes) -> bytes:
        """Handle RRC message from UE."""
        self.metrics["messages_exchanged"] += 1

        if ue_id not in self.ues:
            self.ues[ue_id] = UeSimulation(UeConfig(), ue_id)
            self.metrics["total_ues"] += 1

        ue = self.ues[ue_id]
        response = await ue.handle_rrc_message(data)

        if response:
            return response

        return b""

    async def handle_ue_nas(self, ue_id: str, data: bytes) -> bytes:
        """Handle NAS message from UE."""
        self.metrics["messages_exchanged"] += 1

        if ue_id not in self.ues:
            return b""

        ue = self.ues[ue_id]
        response = await ue.handle_nas_message(data)

        if response:
            return response

        return b""

    def get_state(self) -> GnbState:
        """Get current state snapshot."""
        self.state.connected_ues = len([u for u in self.ues.values() if u.rrc_state == ERrcState.RRC_CONNECTED])
        self.state.state = self.gnb_state
        self.state.ngap_state = self.ngap_state
        self.state.amf_connected = self.amf_connected
        return self.state

    def get_metrics(self) -> Dict[str, Any]:
        """Get gNB metrics."""
        return {
            **self.metrics,
            "connected_ues": len([u for u in self.ues.values() if u.rrc_state == ERrcState.RRC_CONNECTED]),
            "total_ues": len(self.ues),
            "gnb_state": self.gnb_state,
            "amf_connected": self.amf_connected
        }

    def get_ue_states(self) -> List[Dict[str, Any]]:
        """Get states of all UEs."""
        return [ue.get_state() for ue in self.ues.values()]

    async def stop(self) -> None:
        """Stop gNB and disconnect from AMF."""
        self.log("INFO", "Stopping gNB...")
        self.gnb_state = "GNB_POWERING_OFF"

        if self.ngap_connection:
            await self.ngap_connection.disconnect()
            self.ngap_connection = None

        self.amf_connected = False
        self.ngap_state = "NGAP_IDLE"
        self.log("INFO", "gNB stopped")
