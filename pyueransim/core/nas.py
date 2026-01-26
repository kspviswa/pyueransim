"""
NAS Protocol Implementation for pyueransim.
Implements 5G NAS messages (MM, SM) and security.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum, auto
import struct
import hashlib
import hmac

from . import OctetString, EMmState, EMmSubState, ECmState, ESmState, NasSecurityContext


# NAS Message Types
class ENasMessageType(Enum):
    """NAS message types."""
    # Registration
    REGISTRATION_REQUEST = 0x41
    REGISTRATION_ACCEPT = 0x42
    REGISTRATION_COMPLETE = 0x43
    REGISTRATION_REJECT = 0x44

    # De-registration
    DEREGISTRATION_REQUEST = 0x45
    DEREGISTRATION_ACCEPT_UE_ORIG = 0x46
    DEREGISTRATION_ACCEPT_UE_TERM = 0x47

    # Service
    SERVICE_REQUEST = 0x48
    SERVICE_REJECT = 0x49

    # Control
    CONTROL_MESSAGE_SERVICE_REQUEST = 0x4c

    # Authentication
    AUTHENTICATION_REQUEST = 0x56
    AUTHENTICATION_RESPONSE = 0x57
    AUTHENTICATION_REJECT = 0x58
    AUTHENTICATION_FAILURE = 0x59
    AUTHENTICATION_RESULT = 0x5b

    # Security Mode
    SECURITY_MODE_COMMAND = 0x5d
    SECURITY_MODE_COMPLETE = 0x5e
    SECURITY_MODE_REJECT = 0x5f

    # NAS Transport
    UL_NAS_TRANSPORT = 0x67
    DL_NAS_TRANSPORT = 0x68

    # PDU Session
    PDU_SESSION_ESTABLISHMENT_REQUEST = 0xa1
    PDU_SESSION_ESTABLISHMENT_ACCEPT = 0xa2
    PDU_SESSION_ESTABLISHMENT_REJECT = 0xa3
    PDU_SESSION_MODIFICATION_REQUEST = 0xa9
    PDU_SESSION_MODIFICATION_COMPLETE = 0xaa
    PDU_SESSION_MODIFICATION_COMMAND_REJECT = 0xab
    PDU_SESSION_RELEASE_REQUEST = 0xa5
    PDU_SESSION_RELEASE_REJECT = 0xa6
    PDU_SESSION_RELEASE_COMPLETE = 0xa8


class E3gppType(Enum):
    """3GPP IE types."""
    IE5GMM_CAPABILITY = 0x10
    IE5GMM_CONTAINER = 0x17
    IE5GUE_SECURITY_CAPABILITY = 0x2e
    IEACCESS_TYPE = 0x01
    IEADDITIONAL_INFORMATION = 0x43
    IEALWAYS_ON_PDU_SESSION_REQUESTED = 0x12
    IEAMF_SET_ID = 0x39
    IEAMF_REGION_ID = 0x3a
    IEAMF_POINTER = 0x3b
    IE_AUTHENTICATION_FAILURE_PARAMETER = 0x30
    IE_AUTHENTICATION_RESPONSE_PARAMETER = 0x23
    IE_CAUSE_5GMM = 0x16
    IE_CAUSE_5GSM = 0x15
    IE_CONFIGURATION_UPDATE_INDICATION = 0x25
    IE_CONTROL_PLANE_SERVICE_TYPE = 0x31
    IE_COPNI = 0x03
    IE_COPNI_LIST = 0x02
    IE_DAYLIGHT_SAVING_TIME = 0x36
    IE_DRX_PARAMETER = 0x18
    IE_EAP_MESSAGE = 0x78
    IE_EXTENDED_DRX_PARAMETER = 0x37
    IE_GPRS_COPNI_APN = 0x33
    IE_GPRS_TIMER = 0x13
    IE_GPRS_TIMER_2 = 0x35
    IE_IMEI = 0x41
    IE_IMEI_SV = 0x42
    IE_LADN_D = 0x79
    IE_LADN_INFORMATION = 0x4a
    IE_MICO_INDICATION = 0x0b
    IE_MOBILE_DEVICE_CLASSMARK2_TLV = 0x21
    IE_MOBILE_DEVICE_CLASSMARK3_TLV = 0x20
    IE_MOBILE_ID = 0x23
    IE_NAS_MESSAGE_CONTAINER = 0x19
    IE_NETWORK_NAME = 0x43
    IE_NSSAI_INFORMATION = 0x64
    IE_PDU_SESSION_ID = 0x12
    IE_PDU_SESSION_TYPE = 0x9
    IE_PLMN_LIST = 0x4a
    IE_PTI = 0x08
    IE_QOS_FLOW_DESCRIPTIONS = 0x58
    IE_QOS_RULES = 0x57
    IE_REJECTED_NSSAI = 0x11
    IE_REQUEST_TYPE = 0x08
    IE_SCS_AS_ASSISTED_INFORMATION = 0x24
    IE_SEGMENTATION_HEADER = 0x00
    IE_SERVED_PARTITION_INDEX = 0x85
    IE_SERVICE_AREA_LIST = 0x45
    IE_SSN = 0x47
    IE_SST = 0x09
    IE_S_TMSI = 0x10
    IE_TIME_ZONE = 0x46
    IE_TIME_ZONE_AND_TIME = 0x44
    IE_TRACKING_AREA_IDENTITY = 0x04
    IE_TRACKING_AREA_IDENTITY_LIST = 0x45
    IE_UE_ADDITIONAL_SECURITY_CAPABILITY = 0x2f
    IE_UE_SECURITY_CAPABILITY = 0x2e
    IE_UU_LTE_RRC_CONTAINER = 0x17


# 5GMM Cause values
class E5gmmCause(Enum):
    """5GMM cause values."""
    CAUSE_5GMM_IMPLICITLY_DETACHED = 0x02
    CAUSE_5GMM_PLMN_NOT_ALLOWED = 0x03
    CAUSE_5GMM_TRACKING_AREA_NOT_ALLOWED = 0x04
    CAUSE_5GMM_ROAMING_NOT_ALLOWED = 0x05
    CAUSE_5GMM_NO_SUITABLE_CELLS = 0x06
    CAUSE_5GMM_CSG_NOT_AUTHORIZED = 0x08
    CAUSE_5GMM_SERVICE_NOT_ALLOWED = 0x09
    CAUSE_5GMM_TEMPORARILY_NOT_AUTHORIZED = 0x0a
    CAUSE_5GMM_THROTTLED = 0x0b
    CAUSE_5GMM_AUTH_FAILURE = 0x14
    CAUSE_5GMM_USER_AUTHENTICATION_FAILED = 0x15
    CAUSE_5GMM_NETWORK_AUTHENTICATION_FAILED = 0x16
    CAUSE_5GMM_SYNC_FAILURE = 0x17
    CAUSE_5GMM_UE_SECURITY_CAPABILITY_MISMATCH = 0x23
    CAUSE_5GMM_SECURITY_MODE_REJECTED = 0x24
    CAUSE_5GMM_NON_5G_AUTHENTICATION_ACCEPTED = 0x26
    CAUSE_5GMM_UPLINK_DATA_TRANSFER = 0x27


# 5GSM Cause values
class E5gsmCause(Enum):
    """5GSM cause values."""
    CAUSE_5GSM_INSUFFICIENT_RESOURCES = 0x1a
    CAUSE_5GSM_UNKNOWN_OR_MISSING_DNN = 0x1b
    CAUSE_5GSM_UNKNOWN_PDU_SESSION_TYPE = 0x1c
    CAUSE_5GSM_USER_AUTHENTICATION_FAILED = 0x1d
    CAUSE_5GSM_OPERATION_NOT_ALLOWED = 0x1e
    CAUSE_5GSM_OPERATION_NOT_SUPPORTED = 0x1f
    CAUSE_5GSM_PDU_SESSION_ID_IN_USE = 0x20
    CAUSE_5GSM_PDU_SESSION_CONTEXT_NOT_FOUND = 0x21
    CAUSE_5GSM_INVALID_PDU_SESSION_STATE = 0x22
    CAUSE_5GSM_DNN_NOT_SUPPORTED = 0x28


@dataclass
class NasMessage:
    """NAS message container."""
    security_header: int = 0
    message_type: ENasMessageType = ENasMessageType.REGISTRATION_REQUEST
    plain_message: bytes = b""
    encrypted_message: bytes = b""

    def encode(self) -> bytes:
        """Encode NAS message to bytes."""
        data = bytes([self.security_header, self.message_type.value])
        if self.security_header == 0:
            data += self.plain_message
        else:
            data += self.encrypted_message
        return data

    @staticmethod
    def decode(data: bytes) -> 'NasMessage':
        """Decode NAS message from bytes."""
        msg = NasMessage()
        if len(data) >= 2:
            msg.security_header = data[0]
            msg.message_type = ENasMessageType(data[1])
        if msg.security_header == 0:
            msg.plain_message = data[2:]
        else:
            msg.encrypted_message = data[2:]
        return msg


@dataclass
class RegistrationRequest:
    """5G Registration Request message."""
    ie_5gmm_capability: Optional[bytes] = None
    ie_ue_security_capability: Optional[bytes] = None
    ie_mobile_identity: Optional[bytes] = None
    ie_registration_type: Optional[int] = None
    ie_requested_nssai: Optional[bytes] = None
    ie_drx_parameter: Optional[bytes] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = b""
        # IE: 5GMM Capability
        if self.ie_5gmm_capability:
            data += bytes([0xe, len(self.ie_5gmm_capability)]) + self.ie_5gmm_capability
        # IE: UE Security Capability
        if self.ie_ue_security_capability:
            data += bytes([0x2e, len(self.ie_ue_security_capability)]) + self.ie_ue_security_capability
        # IE: Mobile Identity (SUCI or 5G-GUTI)
        if self.ie_mobile_identity:
            data += bytes([0x10, len(self.ie_mobile_identity)]) + self.ie_mobile_identity
        # IE: Registration Type
        if self.ie_registration_type is not None:
            data += bytes([0x0e, 1, self.ie_registration_type])
        return data


@dataclass
class RegistrationAccept:
    """5G Registration Accept message."""
    ie_5g_guti: Optional[bytes] = None
    ie_recommended_dnn_list: Optional[bytes] = None
    ie_tai_list: Optional[bytes] = None
    ie_allowed_nssai: Optional[bytes] = None
    ie_configured_nssai: Optional[bytes] = None
    ie_5gmm_cause: Optional[int] = None
    ie_plmn_list: Optional[bytes] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = b""
        if self.ie_5g_guti:
            data += bytes([0x77, len(self.ie_5g_guti)]) + self.ie_5g_guti
        if self.ie_tai_list:
            data += bytes([0x54, len(self.ie_tai_list)]) + self.ie_tai_list
        if self.ie_allowed_nssai:
            data += bytes([0x15, len(self.ie_allowed_nssai)]) + self.ie_allowed_nssai
        if self.ie_configured_nssai:
            data += bytes([0x31, len(self.ie_configured_nssai)]) + self.ie_configured_nssai
        return data


@dataclass
class PduSessionEstablishmentRequest:
    """PDU Session Establishment Request."""
    ie_pdu_session_type: int = 0  # IPv4 = 1
    ie_request_type: int = 1  # Initial request
    ie_s_nssai: Optional[bytes] = None
    ie_dnn: Optional[bytes] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x09, 1, self.ie_pdu_session_type])  # PDU Session Type
        data += bytes([0x08, 1, self.ie_request_type])  # Request Type
        if self.ie_s_nssai:
            data += bytes([0x39, len(self.ie_s_nssai)]) + self.ie_s_nssai
        if self.ie_dnn:
            data += bytes([0x25, len(self.ie_dnn)]) + self.ie_dnn
        return data


@dataclass
class PduSessionEstablishmentAccept:
    """PDU Session Establishment Accept."""
    ie_pdu_session_type: int = 1
    ie_selected_qos_rule: Optional[bytes] = None
    ie_session_ambr: Optional[bytes] = None
    ie_dnn: Optional[bytes] = None
    ie_qos_flow_descriptions: Optional[bytes] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x09, 1, self.ie_pdu_session_type])
        return data


# Security functions (simplified for simulation)
class NasSecurity:
    """NAS security functions - simplified for simulation."""

    # EIA algorithm IDs
    EIA0 = 0
    EIA1 = 1
    EIA2 = 2
    EIA3 = 3

    # EEA algorithm IDs
    EEA0 = 0
    EEA1 = 1
    EEA2 = 2
    EEA3 = 3

    @staticmethod
    def encode_nas_message(
        security_context: NasSecurityContext,
        nas_message: NasMessage,
        algorithm_type: int,
        algorithm_id: int
    ) -> bytes:
        """Encode NAS message with security protection (simplified)."""
        # In real implementation, this would:
        # 1. Derive NAS keys (k_nas_enc, k_nas_int)
        # 2. Encrypt/Integrity protect the message
        # 3. Add security header

        encoded = nas_message.encode()

        if algorithm_type == 0:  # Integrity
            if algorithm_id == NasSecurity.EIA0:
                # No integrity protection
                return bytes([0x00]) + encoded
            else:
                # Add MAC (simplified)
                mac = b'\x00' * 4
                return bytes([0x40 | (algorithm_id & 0x0f), 0x00]) + mac + encoded[2:]
        else:  # Encryption
            if algorithm_id == NasSecurity.EEA0:
                return bytes([0x00]) + encoded
            else:
                # Add COUNT, BEARER, DIRECTION in security header
                sec_header = bytes([
                    0x20 | (algorithm_id & 0x0f),
                    0x00,  # SEQ is in upper nibble
                    (security_context.count & 0x0f),
                    (security_context.count >> 8) & 0xff,
                    (security_context.count >> 16) & 0xff,
                    security_context.bearer | (security_context.direction << 5)
                ])
                return sec_header + encoded[2:]

    @staticmethod
    def decode_nas_message(
        security_context: NasSecurityContext,
        data: bytes
    ) -> NasMessage:
        """Decode and verify NAS message."""
        if len(data) < 2:
            return NasMessage()

        security_header = data[0]
        message_type = data[1] if len(data) > 1 else 0

        msg = NasMessage()
        msg.security_header = security_header
        msg.message_type = ENasMessageType(message_type)

        # Parse security header
        if security_header & 0x30:  # Protected
            msg.plain_message = data[8:]  # Skip security header (6 bytes) + MAC (2)
        else:
            msg.plain_message = data[2:]

        return msg


# NAS transport for UL/DL messages
@dataclass
class UlNasTransport:
    """UL NAS Transport message (UE to gNB)."""
    ie_ran_container: bytes = b""
    ie_ran_nas_container: bytes = b""
    ie_cause: Optional[int] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x67, 0x00])  # Message type + length placeholder

        if self.ie_ran_container:
            data = data[:2] + bytes([len(self.ie_ran_container) + 2, 0x01, len(self.ie_ran_container)]) + self.ie_ran_container

        if self.ie_ran_nas_container:
            container_len = len(self.ie_ran_nas_container)
            data += bytes([0x02, container_len]) + self.ie_ran_nas_container

        # Update length
        data = bytes([data[0]]) + bytes([len(data) - 2]) + data[2:]
        return data


@dataclass
class DlNasTransport:
    """DL NAS Transport message (gNB to UE)."""
    ie_ran_nas_container: bytes = b""
    ie_cause: Optional[int] = None

    def encode(self) -> bytes:
        """Encode to bytes."""
        data = bytes([0x68, 0x00])  # Message type + length placeholder
        if self.ie_ran_nas_container:
            data += bytes([0x02, len(self.ie_ran_nas_container)]) + self.ie_ran_nas_container
        data = bytes([data[0]]) + bytes([len(data) - 2]) + data[2:]
        return data


# USIM simulation
@dataclass
class UsimContext:
    """USIM context for authentication."""
    imsi: str = ""
    key: bytes = b""
    opc: bytes = b""
    amf: bytes = b"\x80\x00"
    sqn: int = 0

    def generate_authentication_response(self, rand: bytes, autn: bytes) -> tuple[bytes, bytes]:
        """
        Generate authentication response using Milenage (simplified).
        Returns (xres, ik, ck) tuple.
        """
        # Simplified for simulation - real implementation needs full Milenage
        key_bytes = bytes.fromhex(self.key.hex()[:32])
        opc_bytes = bytes.fromhex(self.opc.hex()[:32])

        # Generate XRES using simplified algorithm
        # In real UERANSIM, this uses full Milenage with f1-f5
        combined = rand + opc_bytes + key_bytes[:16]
        xres = hashlib.sha256(combined).digest()[:16]

        # IK and CK (simplified)
        ik = hashlib.sha256(key_bytes + rand).digest()[:16]
        ck = hashlib.sha256(opc_bytes + rand).digest()[:16]

        return xres, ik, ck
