from __future__ import annotations

from pydantic import BaseModel, Field


class AppCreate(BaseModel):
    """新建应用：仅需名称与 Bundle Name；App ID / 应用编码由平台自动生成，版本另行上传."""

    app_name: str = Field(..., min_length=1, max_length=64)
    bundle_name: str = Field(..., min_length=1, max_length=128, description="端侧 Bundle Name")
    description: str | None = None
    status: int = Field(1, ge=0, le=1)


class AppUpdate(BaseModel):
    """编辑仅允许改名称、描述、图标；上下架走 status。App ID / Bundle Name / 应用编码创建后不可改."""

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


class AppProfileCreate(BaseModel):
    profile_name: str = Field(..., min_length=1, max_length=128)
    # 雪花 ID：前端以字符串提交，避免 JS 精度丢失
    cert_id: str | int


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
