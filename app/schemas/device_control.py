from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

CONTROL_TYPES = frozenset({"reboot", "shutDown", "lockScreen", "DISK_ERASURE"})


class DeviceControlIn(BaseModel):
    control_type: str = Field(
        ...,
        description="reboot | shutDown | lockScreen | DISK_ERASURE",
    )

    @field_validator("control_type")
    @classmethod
    def _check_control_type(cls, v: str) -> str:
        value = (v or "").strip()
        if value not in CONTROL_TYPES:
            raise ValueError("不支持的控制类型")
        return value
