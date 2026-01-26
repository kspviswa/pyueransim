"""
Core data structures for pyueransim.
Implements OctetString, timers, and state machines.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Any
from datetime import datetime
import secrets
import struct


class OctetString:
    """Byte string with helper methods - port of C++ OctetString class."""

    def __init__(self, data: bytes | None = None, length: int = 0):
        if data is None:
            self._data = bytes(length)
        elif isinstance(data, bytes):
            self._data = data
        else:
            self._data = bytes(data, 'utf-8') if isinstance(data, str) else bytes(data)

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, index: int) -> int:
        return self._data[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, OctetString):
            return self._data == other._data
        elif isinstance(other, bytes):
            return self._data == other
        return False

    def __hash__(self) -> int:
        return hash(self._data)

    def __repr__(self) -> str:
        return f"OctetString({self._data.hex()})"

    def hex(self) -> str:
        """Return hexadecimal representation."""
        return self._data.hex()

    def to_bytes(self) -> bytes:
        """Return raw bytes."""
        return self._data

    def from_hex(self, hex_str: str) -> 'OctetString':
        """Create from hex string."""
        self._data = bytes.fromhex(hex_str)
        return self

    def from_number(self, value: int, length: int) -> 'OctetString':
        """Create from integer value with specified byte length."""
        self._data = value.to_bytes(length, 'big')
        return self

    def to_number(self) -> int:
        """Convert to integer."""
        return int.from_bytes(self._data, 'big')

    def from_string(self, s: str) -> 'OctetString':
        """Create from ASCII string."""
        self._data = s.encode('ascii')
        return self

    def size(self) -> int:
        """Return size in bytes."""
        return len(self._data)

    def empty(self) -> bool:
        """Check if empty."""
        return len(self._data) == 0

    def allocate(self, size: int) -> None:
        """Allocate buffer of specified size."""
        self._data = bytes(size)

    def set(self, data: bytes) -> None:
        """Set data."""
        self._data = data

    def append(self, other: 'OctetString') -> None:
        """Append another OctetString."""
        self._data += other._data

    def prefix(self, other: 'OctetString') -> None:
        """Prepend another OctetString."""
        self._data = other._data + self._data

    def reserve(self, size: int) -> None:
        """Reserve buffer space."""
        if len(self._data) < size:
            self._data += bytes(size - len(self._data))

    @staticmethod
    def random(length: int) -> 'OctetString':
        """Generate random bytes."""
        return OctetString(secrets.token_bytes(length))


# UE State Enums (port of C++ enums)
class EMmState(Enum):
    """UE Mobility Management state."""
    MM_NULL = auto()
    MM_DEREGISTERED = auto()
    MM_REGISTERED_INITIATED = auto()
    MM_REGISTERED = auto()
    MM_DEREGISTERED_INITIATED = auto()
    MM_SERVICE_REQUEST_INITIATED = auto()


class EMmSubState(Enum):
    """UE MM substate."""
    MM_DEREGISTERED_NORMAL_SERVICE = auto()
    MM_DEREGISTERED_ATTACH_NEEDED = auto()
    MM_DEREGISTERED_ATTEMPTING_ATTACH = auto()
    MM_DEREGISTERED_PLMN_SEARCH = auto()
    MM_DEREGISTERED_NO_IMSI = auto()
    MM_DEREGISTERED_ONLY_IMSI = auto()
    MM_DEREGISTERED_UPDATE_NEEDED = auto()
    MM_DEREGISTERED_ATTACH_EXPIRED = auto()
    MM_REGISTERED_NORMAL_SERVICE = auto()
    MM_REGISTERED_ATTEMPTING_UPDATE = auto()
    MM_REGISTERED_PLMN_SEARCH = auto()
    MM_REGISTERED_UPDATE_NEEDED = auto()
    MM_REGISTERED_NO_CELL_AVAILABLE = auto()


class ECmState(Enum):
    """UE Connection Management state."""
    CM_IDLE = auto()
    CM_CONNECTED = auto()


class ERrcState(Enum):
    """UE RRC state."""
    RRC_IDLE = auto()
    RRC_CONNECTED = auto()
    RRC_INACTIVE = auto()


class ESmState(Enum):
    """UE Session Management state."""
    SM_NULL = auto()
    SM_PENDING = auto()
    SM_ACTIVE = auto()


class EpsState(Enum):
    """EPS state (for backward compatibility)."""
    PS_INACTIVE = auto()
    PS_ACTIVE_PENDING = auto()
    PS_ACTIVE = auto()


# gNB State Enums
class GNbState(Enum):
    """gNB state."""
    GNB_INVALID = auto()
    GNB_POWERING_ON = auto()
    GNB_POWERING_OFF = auto()
    GNB_CONFIGURATION = auto()
    GNB_WAITING_FOR_S1 = auto()
    GNB_WAITING_FOR_N2 = auto()
    GNB_READY = auto()
    GNB_CONNECTION_REFUSED = auto()


class NgapState(Enum):
    """NGAP connection state."""
    NGAP_IDLE = auto()
    NGAP_CONNECTING = auto()
    NGAP_CONNECTED = auto()
    NGAP_SHUTDOWN = auto()


# Timer management
@dataclass
class Timer:
    """Timer object for protocol timers."""
    id: int
    timeout: float  # seconds
    started_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None

    def is_running(self) -> bool:
        """Check if timer is running."""
        return self.started_at is not None

    def is_expired(self) -> bool:
        """Check if timer has expired."""
        if not self.started_at:
            return False
        elapsed = (datetime.now() - self.started_at).total_seconds()
        return elapsed >= self.timeout

    def start(self) -> None:
        """Start the timer."""
        self.started_at = datetime.now()

    def stop(self) -> None:
        """Stop the timer."""
        self.started_at = None

    def remaining(self) -> float:
        """Get remaining time in seconds."""
        if not self.started_at:
            return self.timeout
        elapsed = (datetime.now() - self.started_at).total_seconds()
        return max(0, self.timeout - elapsed)


@dataclass
class TimerManager:
    """Manager for protocol timers."""
    timers: Dict[int, Timer] = field(default_factory=dict)
    next_id: int = 1
    _lock = None

    def allocate(self, timeout: float, data: Optional[Dict] = None) -> int:
        """Allocate a new timer."""
        timer_id = self.next_id
        self.next_id += 1
        self.timers[timer_id] = Timer(timer_id, timeout, data=data)
        return timer_id

    def start(self, timer_id: int) -> bool:
        """Start a timer."""
        if timer_id in self.timers:
            self.timers[timer_id].start()
            return True
        return False

    def stop(self, timer_id: int) -> bool:
        """Stop a timer."""
        if timer_id in self.timers:
            self.timers[timer_id].stop()
            return True
        return False

    def get(self, timer_id: int) -> Optional[Timer]:
        """Get a timer by ID."""
        return self.timers.get(timer_id)

    def expire(self, timer_id: int) -> bool:
        """Force expire a timer."""
        if timer_id in self.timers:
            self.timers[timer_id].started_at = datetime.min
            return True
        return False

    def running(self) -> List[Timer]:
        """Get all running timers."""
        return [t for t in self.timers.values() if t.is_running()]

    def check_expired(self) -> List[Timer]:
        """Get and remove all expired timers."""
        expired = []
        expired_ids = []
        for timer_id, timer in self.timers.items():
            if timer.is_expired():
                expired.append(timer)
                expired_ids.append(timer_id)
        for timer_id in expired_ids:
            del self.timers[timer_id]
        return expired

    def clear(self) -> None:
        """Clear all timers."""
        self.timers.clear()
        self.next_id = 1


# Security context
@dataclass
class NasSecurityContext:
    """NAS security context."""
    k_nas_int: OctetString = field(default_factory=lambda: OctetString(16))
    k_nas_enc: OctetString = field(default_factory=lambda: OctetString(16))
    integrity_algorithm: int = 0
    encryption_algorithm: int = 0
    count: int = 0
    bearer: int = 0
    direction: int = 0

    def is_valid(self) -> bool:
        """Check if security context is valid."""
        return not self.k_nas_int.empty()


# UE context for gNB
@dataclass
class UeContext:
    """UE context stored in gNB."""
    ue_id: int = 0
    ran_ue_ngap_id: int = 0
    amf_ue_ngap_id: int = 0
    security_context: Optional[NasSecurityContext] = None
    mm_state: EMmState = EMmState.MM_NULL
    rrc_state: ERrcState = ERrcState.RRC_IDLE
    cm_state: ECmState = ECmState.CM_IDLE
    registration_requested: bool = False
    pdu_sessions: Dict[int, Any] = field(default_factory=dict)

    def is_connected(self) -> bool:
        """Check if UE is connected."""
        return self.mm_state == EMmState.MM_REGISTERED and self.rrc_state == ERrcState.RRC_CONNECTED
