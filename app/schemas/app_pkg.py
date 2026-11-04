from __future__ import annotations

from pydantic import BaseModel, Field


class AppCreate(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=64)
    app_code: str = Field(..., min_length=1, max_length=64)
    app_id: str = Field(..., min_length=1, max_length=128, description="端侧 AppIdentifier")
    bundle_name: str = Field(..., min_length=1, max_length=128, description="端侧 Bundle Name")
    description: str | None = None
    status: int = Field(1, ge=0, le=1)
    # 首个版本（安装包通过独立上传接口绑定；包名统一用应用 Bundle Name）
    version_name: str = Field("1.0.0", min_length=1, max_length=64)
    version_code: str = Field("100", min_length=1, max_length=20)


class AppUpdate(BaseModel):
    """编辑仅允许改名称、描述、图标；上下架走 status。App ID / Bundle Name / 编码创建后不可改."""

    app_name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = None
    status: int | None = Field(None, ge=0, le=1)
    app_icon: str | None = Field(None, max_length=255)


class AppVersionCreate(BaseModel):
    version_name: str = Field(..., min_length=1, max_length=64)
    version_code: str = Field(..., min_length=1, max_length=20)
    status: int = Field(2, ge=0, le=3, description="默认已发布；UI 以卡片切换发布/下架")


class AppVersionUpdate(BaseModel):
    version_name: str | None = Field(None, min_length=1, max_length=64)
    version_code: str | None = Field(None, min_length=1, max_length=20)
    status: int | None = Field(None, ge=0, le=3)


class AppBatchInstallIn(BaseModel):
    """应用批量安装：按分组范围写入 APP_MANAGEMENT 预期."""

    group_ids: list[str] = Field(default_factory=list, description="成员分组 ID；传空且 all_groups=true 表示全部")
    all_groups: bool = Field(False, description="是否选择全部分组")
    version_id: str = Field(..., min_length=1, description="已发布版本 ID")
    public_base_url: str | None = Field(
        None, description="下载地址前缀（如 https://host:8080）；缺省用相对路径"
    )


class AppBatchUninstallIn(BaseModel):
    """应用批量卸载：按分组范围写入 APP_MANAGEMENT 预期."""

    group_ids: list[str] = Field(default_factory=list)
    all_groups: bool = Field(False, description="是否选择全部分组")
