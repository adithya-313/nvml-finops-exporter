from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TelemetryRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GpuMetric(_message.Message):
    __slots__ = ("uuid", "utilization_percent", "memory_used_mb", "memory_total_mb", "temperature_c", "power_draw_w")
    UUID_FIELD_NUMBER: _ClassVar[int]
    UTILIZATION_PERCENT_FIELD_NUMBER: _ClassVar[int]
    MEMORY_USED_MB_FIELD_NUMBER: _ClassVar[int]
    MEMORY_TOTAL_MB_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_C_FIELD_NUMBER: _ClassVar[int]
    POWER_DRAW_W_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    utilization_percent: float
    memory_used_mb: int
    memory_total_mb: int
    temperature_c: float
    power_draw_w: float
    def __init__(self, uuid: _Optional[str] = ..., utilization_percent: _Optional[float] = ..., memory_used_mb: _Optional[int] = ..., memory_total_mb: _Optional[int] = ..., temperature_c: _Optional[float] = ..., power_draw_w: _Optional[float] = ...) -> None: ...

class TelemetryResponse(_message.Message):
    __slots__ = ("system_status", "error_message", "gpus", "timestamp_utc", "ntp_offset_ms")
    SYSTEM_STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    GPUS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_UTC_FIELD_NUMBER: _ClassVar[int]
    NTP_OFFSET_MS_FIELD_NUMBER: _ClassVar[int]
    system_status: str
    error_message: str
    gpus: _containers.RepeatedCompositeFieldContainer[GpuMetric]
    timestamp_utc: int
    ntp_offset_ms: int
    def __init__(self, system_status: _Optional[str] = ..., error_message: _Optional[str] = ..., gpus: _Optional[_Iterable[_Union[GpuMetric, _Mapping]]] = ..., timestamp_utc: _Optional[int] = ..., ntp_offset_ms: _Optional[int] = ...) -> None: ...
