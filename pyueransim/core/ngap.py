"""
NGAP Protocol Implementation for pyueransim.
Real SCTP connections to AMF - no simulation fallback.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
import asyncio
import socket
import ipaddress


# NGAP Payload Protocol Identifier (PPID)
NGAP_PPID = 0  # NGAP uses PPID 0

# NGAP Message Types
class ENgapMessageType(Enum):
    """NGAP message types."""
    NG_SETUP_REQUEST = 0x00
    NG_SETUP_RESPONSE = 0x01
    NG_SETUP_FAILURE = 0x02
    INITIAL_UE_MESSAGE = 0x04
    UPLINK_NAS_TRANSPORT = 0x06
    DOWNLINK_NAS_TRANSPORT = 0x07
    UE_CONTEXT_RELEASE_REQUEST = 0x08
    UE_CONTEXT_RELEASE_CMD = 0x09
    UE_CONTEXT_RELEASE_COMPLETE = 0x0a
    UE_CONTEXT_MODIFICATION_REQUEST = 0x0b
    UE_CONTEXT_MODIFICATION_RESPONSE = 0x0c
    UE_CONTEXT_MODIFICATION_FAILURE = 0x0d
    UE_CONTEXT_SETUP_REQUEST = 0x0e
    UE_CONTEXT_SETUP_RESPONSE = 0x0f
    UE_CONTEXT_SETUP_FAILURE = 0x10
    PDU_SESSION_RESOURCE_SETUP_REQUEST = 0x12
    PDU_SESSION_RESOURCE_SETUP_RESPONSE = 0x13
    PDU_SESSION_RESOURCE_MODIFY_REQUEST = 0x15
    PDU_SESSION_RESOURCE_MODIFY_RESPONSE = 0x16
    PDU_SESSION_RESOURCE_RELEASE_COMMAND = 0x19
    PDU_SESSION_RESOURCE_RELEASE_REQUEST = 0x1a
    PDU_SESSION_RESOURCE_RELEASE_COMPLETE = 0x1b


@dataclass
class NgSetupRequest:
    """NG Setup Request message."""
    global_gnb_id: bytes = b""
    supported_ta_list: bytes = b""
    default_paging_drx: int = 64

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = b""

        # Home NG-RAN Node Global ID
        data += bytes([0x00, 0x0f])  # IEI + Length
        data += bytes([0x00, 0x04])  # PLMN Identity length
        data += bytes([0x08, 0x86, 0x93])  # MCC=208, MNC=93
        data += bytes([0x00, 0x09])  # gNB ID length
        data += bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00])  # gNB ID

        # Supported TAI List
        data += bytes([0x00, 0x54])  # IEI + Length placeholder
        data += bytes([0x00, 0x01])  # Number of TAIs
        data += bytes([0x08, 0x86, 0x93])  # PLMN
        data += bytes([0x00, 0x00, 0x01])  # TAC

        # Default Paging DRX
        data += bytes([0x00, 0x4f, 0x01, self.default_paging_drx])

        return data


@dataclass
class NgSetupResponse:
    """NG Setup Response message."""
    amf_name: bytes = b""
    served_tai_list: bytes = b""
    relative_amf_capacity: int = 10
    plmn_support_list: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x00, 0x38])
        data += bytes([0x41, 0x4d, 0x46, 0x00])  # "AMF"
        data += bytes([0x00, 0x54])
        data += bytes([0x00, 0x01])
        data += bytes([0x08, 0x86, 0x93])
        data += bytes([0x00, 0x00, 0x01])
        data += bytes([0x00, 0x28, self.relative_amf_capacity])
        return data


@dataclass
class InitialUeMessage:
    """Initial UE Message (NGAP)."""
    ran_ue_ngap_id: int = 0
    nas_pdu: bytes = b""
    user_location_info: bytes = b""
    rrc_establishment_cause: int = 0

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x00, 0x55, 0x00, 0x00, 0x00, 0x00])
        data = data[:2] + bytes([self.ran_ue_ngap_id & 0xff, (self.ran_ue_ngap_id >> 8) & 0xff]) + data[4:]
        data += bytes([0x38, len(self.nas_pdu)]) + self.nas_pdu
        data += bytes([0xa7, 0x07, 0x00, 0x01, 0x08, 0x86, 0x93, 0x00, 0x01])
        return data


@dataclass
class UplinkNasTransport:
    """Uplink NAS Transport message."""
    ue_associated_ngap_id: int = 0
    nas_pdu: bytes = b""
    user_location_info: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x00, 0x4a])
        data += bytes([0x00, 0x00, 0x00, 0x00])
        data += bytes([0x38, len(self.nas_pdu)]) + self.nas_pdu
        data += bytes([0xa7, 0x07, 0x00, 0x01, 0x08, 0x86, 0x93, 0x00, 0x01])
        return data


@dataclass
class DownlinkNasTransport:
    """Downlink NAS Transport message."""
    ue_associated_ngap_id: int = 0
    nas_pdu: bytes = b""

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x00, 0x0c, 0x00, 0x00, 0x00, 0x00])
        data = data[:2] + bytes([self.ue_associated_ngap_id & 0xff, (self.ue_associated_ngap_id >> 8) & 0xff]) + data[4:]
        data += bytes([0x38, len(self.nas_pdu)]) + self.nas_pdu
        return data


class SctpSocket:
    """
    SCTP socket wrapper for AMF connection.
    Uses pysctp library for real SCTP connections.
    """

    def __init__(self, local_address: str, local_port: int = 0):
        self.local_address = local_address
        self.local_port = local_port
        self.socket = None
        self.connected = False
        self.is_ipv6 = ':' in local_address

    async def create(self, max_in_streams: int = 10, max_out_streams: int = 10) -> None:
        """Create SCTP socket."""
        import sctp

        family = socket.AF_INET if not self.is_ipv6 else socket.AF_INET6

        # pysctp API: sctpsocket(family, style, sk=None)
        # style can be sctp.TCP_STYLE or sctp.UDP_STYLE
        try:
            self.socket = sctp.sctpsocket(family, sctp.TCP_STYLE, None)
        except TypeError:
            # Older API without sk parameter
            try:
                self.socket = sctp.sctpsocket(family, sctp.TCP_STYLE)
            except AttributeError:
                # Fallback: use socket module directly
                self.socket = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_SCTP)

        # Bind if port specified
        if self.local_port > 0:
            self.socket.bind((self.local_address, self.local_port))

    async def connect(self, remote_address: str, remote_port: int) -> bool:
        """Connect to remote endpoint."""
        if not self.socket:
            raise RuntimeError("Socket not created. Call create() first.")

        try:
            self.socket.connect((remote_address, remote_port))
            self.connected = True
            return True
        except Exception as e:
            print(f"SCTP connection failed to {remote_address}:{remote_port}: {e}")
            self.connected = False
            return False

    async def send(self, data: bytes, stream: int = 0, ppid: int = NGAP_PPID) -> bool:
        """Send data over SCTP."""
        if not self.socket or not self.connected:
            return False

        try:
            # Use sendall for TCP-style SCTP
            self.socket.sendall(data)
            return True
        except Exception as e:
            print(f"SCTP send failed: {e}")
            return False

    async def recv(self, buffer_size: int = 8192) -> Optional[bytes]:
        """Receive data from SCTP."""
        if not self.socket or not self.connected:
            return None

        try:
            data = self.socket.recv(buffer_size)
            return data
        except Exception as e:
            print(f"SCTP recv failed: {e}")
            return None

    def close(self) -> None:
        """Close the socket."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            self.connected = False


class NgapConnection:
    """
    NGAP connection handler for AMF communication.
    Manages real SCTP connection to AMF.
    """

    def __init__(self, gnb_id: int, amf_host: str, amf_port: int,
                 local_address: str = "127.0.0.1", local_port: int = 0):
        self.gnb_id = gnb_id
        self.amf_host = amf_host
        self.amf_port = amf_port
        self.local_address = local_address
        self.local_port = local_port

        self.sctp_socket: Optional[SctpSocket] = None
        self.connected = False
        self.ue_contexts: Dict[int, Dict] = {}
        self.next_ran_ue_id = 1

        self.on_message: Optional[Callable[[bytes, int], None]] = None
        self.on_association_change: Optional[Callable[[str], None]] = None

    async def connect(self) -> bool:
        """Establish SCTP connection to AMF."""
        try:
            self.sctp_socket = SctpSocket(self.local_address, self.local_port)
            await self.sctp_socket.create(max_in_streams=10, max_out_streams=10)

            connected = await self.sctp_socket.connect(self.amf_host, self.amf_port)
            if connected:
                self.connected = True
                print(f"[NGAP] Connected to AMF {self.amf_host}:{self.amf_port}")
                return True
            else:
                print(f"[NGAP] Failed to connect to AMF {self.amf_host}:{self.amf_port}")
                return False
        except Exception as e:
            print(f"[NGAP] Connection error: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from AMF."""
        self.connected = False
        if self.sctp_socket:
            self.sctp_socket.close()
            self.sctp_socket = None
        print("[NGAP] Disconnected from AMF")

    async def send_ng_setup_request(self) -> bool:
        """Send NG Setup Request."""
        msg = NgSetupRequest()
        data = msg.encode()
        print(f"[NGAP] Sending NG Setup Request to {self.amf_host}:{self.amf_port}")
        return await self._send(data)

    async def send_initial_ue_message(self, nas_pdu: bytes, ran_ue_id: int) -> bool:
        """Send Initial UE Message."""
        msg = InitialUeMessage(ran_ue_ngap_id=ran_ue_id, nas_pdu=nas_pdu)
        data = msg.encode()
        return await self._send(data, stream=0)

    async def send_uplink_nas(self, ue_associated_id: int, nas_pdu: bytes) -> bool:
        """Send Uplink NAS Transport."""
        msg = UplinkNasTransport(ue_associated_ngap_id=ue_associated_id, nas_pdu=nas_pdu)
        data = msg.encode()
        return await self._send(data, stream=0)

    async def _send(self, data: bytes, stream: int = 0) -> bool:
        """Send data over SCTP."""
        if not self.connected or not self.sctp_socket:
            return False
        return await self.sctp_socket.send(data, stream=stream, ppid=NGAP_PPID)

    async def receive_loop(self) -> None:
        """Run the receive loop for incoming messages."""
        if not self.sctp_socket:
            return

        buffer_size = 8192
        while self.connected:
            data = await self.sctp_socket.recv(buffer_size)
            if data:
                if self.on_message:
                    self.on_message(data, 0)
            else:
                await asyncio.sleep(0.1)

    def generate_ran_ue_id(self) -> int:
        """Generate new RAN UE NGAP ID."""
        ue_id = self.next_ran_ue_id
        self.next_ran_ue_id += 1
        return ue_id

    def get_connected(self) -> bool:
        """Check if connected to AMF."""
        return self.connected


class NgapTask:
    """
    NGAP Task for handling NGAP procedures.
    Manages connection and message handling with AMF.
    """

    def __init__(self, gnb_id: int, amf_host: str = "127.0.0.1", amf_port: int = 38412,
                 local_address: str = "127.0.0.1", local_port: int = 0):
        self.gnb_id = gnb_id
        self.connection = NgapConnection(
            gnb_id, amf_host, amf_port, local_address, local_port
        )
        self.state = "idle"
        self.receive_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """Start NGAP task and connect to AMF."""
        self.state = "connecting"
        connected = await self.connection.connect()

        if connected:
            self.state = "connected"
            await self.connection.send_ng_setup_request()
            self.receive_task = asyncio.create_task(self.connection.receive_loop())
        else:
            self.state = "idle"

        return connected

    async def stop(self) -> None:
        """Stop NGAP task."""
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        await self.connection.disconnect()
        self.state = "idle"

    def is_connected(self) -> bool:
        """Check if connected to AMF."""
        return self.connection.get_connected()

    def generate_ue_id(self) -> int:
        """Generate UE ID."""
        return self.connection.generate_ran_ue_id()

    async def send_initial_ue(self, nas_pdu: bytes) -> int:
        """Send Initial UE Message and return RAN UE ID."""
        ran_id = self.connection.generate_ran_ue_id()
        await self.connection.send_initial_ue_message(nas_pdu, ran_id)
        return ran_id

    async def send_uplink_nas(self, ue_id: int, nas_pdu: bytes) -> None:
        """Send Uplink NAS Transport."""
        await self.connection.send_uplink_nas(ue_id, nas_pdu)

    def set_message_handler(self, handler: Callable[[bytes], None]) -> None:
        """Set handler for incoming NGAP messages."""
        self.connection.on_message = handler
