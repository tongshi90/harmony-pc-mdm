"""Harmony 签名工具封装：证书签发 / Profile p7b / hapResign（解包+重签）。

依赖 data/sign/（或 MDM_STORE_SIGN_DIR）下：
  - hap-sign-tool.jar
  - OpenHarmony.p12
  - OpenHarmonyProfileRelease.pem   # Profile 签名证书链
模式 2（hapResign）另需：
  - openvalley.pem（或 MDM_STORE_APP_CERT_FILE）+ p12 中对应别名私钥
可选：
  - 环境变量覆盖 issuer / Root CA；CSR 追加 root 可读 data/sign/root.cer
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.config import DATA_DIR, settings

logger = logging.getLogger("mdm.store_sign")

UNSIGNED_PROFILE_JSON = "UnsgnedReleasedProfileTemplate.json"
APP_DISTRIBUTION_TYPE = "os_integration"
DEVELOPER_ID = "OpenHarmony"
APL_NORMAL = "normal"
APP_FEATURE_NORMAL = "hos_normal_app"
DEFAULT_VERSION_CODE = 1
DEFAULT_VERSION_NAME = "1.0.0"

_DEFAULT_ROOT_CERT = """-----BEGIN CERTIFICATE-----
MIICRDCCAcmgAwIBAgIED+E4izAMBggqhkjOPQQDAwUAMGgxCzAJBgNVBAYTAkNO
MRQwEgYDVQQKEwtPcGVuSGFybW9ueTEZMBcGA1UECxMQT3Blbkhhcm1vbnkgVGVh
bTEoMCYGA1UEAxMfT3Blbkhhcm1vbnkgQXBwbGljYXRpb24gUm9vdCBDQTAeFw0y
MTAyMDIxMjE0MThaFw00OTEyMzExMjE0MThaMGgxCzAJBgNVBAYTAkNOMRQwEgYD
VQQKEwtPcGVuSGFybW9ueTEZMBcGA1UECxMQT3Blbkhhcm1vbnkgVGVhbTEoMCYG
A1UEAxMfT3Blbkhhcm1vbnkgQXBwbGljYXRpb24gUm9vdCBDQTB2MBAGByqGSM49
AgEGBSuBBAAiA2IABE023XmRaw2DnO8NSsb+KG/uY0FtS3u5LQucdr3qWVnRW5ui
QIL6ttNZBEeLTUeYcJZCpayg9Llf+1SmDA7dY4iP2EcRo4UN3rilovtfFfsmH4ty
3SApHVFzWUl+NwdH8KNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMC
AQYwHQYDVR0OBBYEFBc6EKGrGXzlAE+s0Zgnsphadw7NMAwGCCqGSM49BAMDBQAD
ZwAwZAIwd1p3JzHN93eoPped1li0j64npgqNzwy4OrkehYAqNXpcpaEcLZ7UxW8E
I2lZJ3SbAjAkqySHb12sIwdSFKSN9KCMMEo/eUT5dUXlcKR2nZz0MJdxT5F51qcX
1CumzkcYhgU=
-----END CERTIFICATE-----"""

def sign_dir() -> Path:
    raw = (settings.store_sign_dir or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = DATA_DIR / p
        return p
    return DATA_DIR / "sign"


def _java_bin() -> str:
    return (settings.store_java_bin or "").strip() or "java"


def _keytool_bin() -> str:
    return (settings.store_keytool_bin or "").strip() or "keytool"


def _read_text_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None



def root_cert_pem() -> str:
    override = (settings.store_root_cert or "").strip()
    if override:
        return override.replace("\\n", "\n").strip()
    from_file = _read_text_file(sign_dir() / "root.cer")
    if from_file:
        return from_file
    return _DEFAULT_ROOT_CERT.strip()


def issuer() -> str:
    return (
        (settings.store_issuer or "").strip()
        or "C=CN,O=OpenValley,OU=OpenValley Team,CN= OpenValley Application CA"
    )


@dataclass
class SignToolStatus:
    ready: bool
    sign_dir: str
    missing: list[str] = field(default_factory=list)
    files: dict[str, bool] = field(default_factory=dict)
    java_ok: bool = False
    message: str = ""


def platform_app_cert_path() -> Path:
    name = (settings.store_app_cert_file or "openvalley.pem").strip() or "openvalley.pem"
    return sign_dir() / Path(name).name


def read_platform_app_cert_pem() -> str:
    path = platform_app_cert_path()
    if not path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"缺少平台应用证书：{path.name}（模式 2 / hapResign 需要）",
        )
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if "BEGIN CERTIFICATE" not in text:
        raise HTTPException(status_code=400, detail=f"{path.name} 不是有效的证书 PEM")
    return text + "\n"


def check_sign_tools(
    *,
    for_profile: bool = False,
    for_csr: bool = False,
    for_resign: bool = False,
) -> SignToolStatus:
    """检查签名工具与证书材料是否齐备。"""
    base = sign_dir()
    required: list[str] = []
    if for_profile or for_resign:
        required.extend(
            [
                "hap-sign-tool.jar",
                "OpenHarmony.p12",
                "OpenHarmonyProfileRelease.pem",
            ]
        )
    if for_resign:
        required.append(platform_app_cert_path().name)
    if for_csr:
        required.append("OpenHarmony.p12")

    files = {name: (base / name).is_file() for name in sorted(set(required))}
    missing = [n for n, ok in files.items() if not ok]

    java_ok = False
    try:
        r = subprocess.run(
            [_java_bin(), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        java_ok = r.returncode == 0 or bool(r.stderr or r.stdout)
    except (OSError, subprocess.TimeoutExpired):
        java_ok = False

    need_java = for_profile or for_resign
    ready = not missing and (java_ok if need_java else True)
    if for_csr and not for_profile and not for_resign:
        ready = "OpenHarmony.p12" not in missing
        try:
            kr = subprocess.run(
                [_keytool_bin()],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ready = ready and (kr.returncode in (0, 1) or bool(kr.stderr or kr.stdout))
        except (OSError, subprocess.TimeoutExpired):
            ready = False
            missing.append("keytool")

    if not java_ok and need_java:
        if "java" not in missing:
            missing.append("java")

    msg_parts = []
    if missing:
        msg_parts.append(f"缺少：{', '.join(missing)}")
    if not java_ok and need_java:
        msg_parts.append("无法执行 java（请安装 JDK 或配置 MDM_STORE_JAVA_BIN）")
    if ready:
        msg = "签名工具就绪"
    else:
        msg = "；".join(msg_parts) or "签名工具未就绪"
        msg += f"。请将材料放到 {base}"

    return SignToolStatus(
        ready=ready,
        sign_dir=str(base),
        missing=missing,
        files=files,
        java_ok=java_ok,
        message=msg,
    )


def _run_cmd(cmd: list[str], *, cwd: Path | None = None) -> None:
    logger.info("store_sign exec: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=int(settings.store_sign_timeout_seconds or 300),
            shell=False,
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=500, detail="签名命令执行超时") from e
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"无法执行签名命令：{e}"
        ) from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        logger.error("store_sign failed rc=%s err=%s", proc.returncode, err[:2000])
        raise HTTPException(
            status_code=500,
            detail=f"签名命令失败（exit {proc.returncode}）：{err[:800] or '无输出'}",
        )


def _validity_unix(months: int = 48) -> dict[str, int]:
    now = datetime.utcnow()
    later = now + timedelta(days=30 * months)
    return {
        "not-before": int(now.timestamp()),
        "not-after": int(later.timestamp()),
    }


def build_provision_for_app(
    *,
    bundle_name: str,
    app_cert_pem: str,
    version_code: int = DEFAULT_VERSION_CODE,
    version_name: str = DEFAULT_VERSION_NAME,
    provision_uuid: str | None = None,
) -> dict[str, Any]:
    """对齐 InfoProfileServiceImpl.buildProfile。"""
    return {
        "version-code": version_code,
        "version-name": version_name,
        "app-distribution-type": APP_DISTRIBUTION_TYPE,
        "uuid": provision_uuid or str(uuid.uuid4()),
        "type": "release",
        "issuer": issuer(),
        "validity": _validity_unix(48),
        "bundle-info": {
            "developer-id": DEVELOPER_ID,
            "distribution-certificate": (app_cert_pem or "").strip() + "\n",
            "bundle-name": bundle_name,
            "apl": APL_NORMAL,
            "app-feature": APP_FEATURE_NORMAL,
        },
    }


def sign_profile_p7b(
    provision: dict[str, Any],
    *,
    work_dir: Path,
    out_name: str,
) -> Path:
    """生成 Profile JSON 并用 hap-sign-tool sign-profile 产出 .p7b。"""
    status = check_sign_tools(for_profile=True)
    if not status.ready:
        raise HTTPException(status_code=400, detail=status.message)

    work_dir.mkdir(parents=True, exist_ok=True)
    json_path = work_dir / UNSIGNED_PROFILE_JSON
    json_path.write_text(
        json.dumps(provision, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not out_name.endswith(".p7b"):
        out_name = f"{out_name}.p7b"
    out_path = work_dir / out_name
    base = sign_dir()
    jar = base / "hap-sign-tool.jar"
    profile_cert = base / "OpenHarmonyProfileRelease.pem"
    keystore = base / "OpenHarmony.p12"

    cmd = [
        _java_bin(),
        "-jar",
        str(jar),
        "sign-profile",
        "-keyAlias",
        "openharmony application profile release",
        "-signAlg",
        "SHA256withECDSA",
        "-mode",
        "localSign",
        "-profileCertFile",
        str(profile_cert),
        "-inFile",
        str(json_path),
        "-keystoreFile",
        str(keystore),
        "-outFile",
        str(out_path),
        "-keyPwd",
        "123456",
        "-keystorePwd",
        "123456",
    ]
    _run_cmd(cmd, cwd=work_dir)
    if not out_path.is_file():
        raise HTTPException(status_code=500, detail="Profile 签名成功但未找到输出文件")
    return out_path


def issue_cer_from_csr(csr_bytes: bytes, *, cert_name: str, out_dir: Path) -> tuple[bytes, str]:
    """对齐 CertServiceImpl：keytool -gencert 签发 .cer，再 append Root。

    保留 keytool 完整输出（通常已含叶子 + Application CA），仅在末尾追加 root-cert；
    返回 (完整 .cer 字节, 叶子 PEM)——叶子 PEM 供入库 app_cert / Profile 使用。
    """
    status = check_sign_tools(for_csr=True)
    if not status.ready:
        raise HTTPException(status_code=400, detail=status.message)

    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = out_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    csr_path = temp_dir / f"{uuid.uuid4().hex}.csr"
    csr_path.write_bytes(csr_bytes)

    base = sign_dir()
    keystore = base / "OpenHarmony.p12"
    cer_path = out_dir / f"{cert_name}.cer"

    cmd = [
        _keytool_bin(),
        "-gencert",
        "-alias",
        "OpenHarmony Application CA",
        "-infile",
        str(csr_path),
        "-outfile",
        str(cer_path),
        "-keystore",
        str(keystore),
        "-sigalg",
        "SHA384withECDSA",
        "-storepass",
        "123456",
        "-ext",
        "KeyUsage:critical=digitalSignature",
        "-validity",
        "3650",
        "-rfc",
    ]
    _run_cmd(cmd, cwd=out_dir)
    if not cer_path.is_file():
        raise HTTPException(status_code=500, detail="keytool 签发失败：未生成 cer 文件")

    # 对齐 appendRootCertToFile：保留 keytool 全文，再追加 Root（勿先截成叶子）
    issued = cer_path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").strip()
    leaf_pem = _first_pem(issued) or (issued + "\n")
    root = root_cert_pem().strip().replace("\r\n", "\n")
    if root and root not in issued:
        content = issued + "\n" + root + "\n"
    else:
        content = issued + "\n"
    cer_path.write_text(content, encoding="utf-8")
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except OSError:
        pass
    return content.encode("utf-8"), leaf_pem


def _first_pem(text: str) -> str | None:
    m = re.search(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        text,
        re.DOTALL,
    )
    if not m:
        return None
    return m.group(0).replace("\r\n", "\n").strip() + "\n"


def unpack_to_hap(src: Path, work_dir: Path) -> Path:
    """从 .hap / .app / .sap / .zip 取出用于重签的 hap 文件。

    - 纯 .hap：复制为 unsign-*.hap
    - .app/.zip/.sap：解压后取第一个 .hap（对齐 hm-appstore 取包内首个 HAP）
    """
    if not src.is_file():
        raise HTTPException(status_code=400, detail="待重签安装包不存在")
    work_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()
    if suffix == ".hap":
        dest = work_dir / f"unsign-{src.name}"
        shutil.copy2(src, dest)
        return dest

    if suffix not in {".app", ".sap", ".zip"}:
        raise HTTPException(
            status_code=400,
            detail="重签仅支持 .hap / .app / .sap / .zip",
        )

    extract_dir = work_dir / "unpack"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="安装包不是有效的 zip/app 包") from e

    hap_files = sorted(extract_dir.rglob("*.hap"))
    if not hap_files:
        raise HTTPException(status_code=400, detail="解包后未找到 .hap 文件")
    hap_src = hap_files[0]
    dest = work_dir / f"unsign-{hap_src.name}"
    shutil.copy2(hap_src, dest)
    logger.info("hapResign unpack: picked %s -> %s", hap_src, dest)
    return dest


def sign_app_hap(
    *,
    in_hap: Path,
    profile_p7b: Path,
    out_hap: Path,
    app_cert_file: Path | None = None,
) -> Path:
    """调用 hap-sign-tool sign-app（平台固定密钥，对齐模式 2）。"""
    status = check_sign_tools(for_resign=True)
    if not status.ready:
        raise HTTPException(status_code=400, detail=status.message)
    if not in_hap.is_file():
        raise HTTPException(status_code=400, detail="待签名 hap 不存在")
    if not profile_p7b.is_file():
        raise HTTPException(status_code=400, detail="Profile p7b 不存在")

    base = sign_dir()
    jar = base / "hap-sign-tool.jar"
    keystore = base / "OpenHarmony.p12"
    cert = app_cert_file or platform_app_cert_path()
    out_hap.parent.mkdir(parents=True, exist_ok=True)

    alias = (settings.store_app_key_alias or "openvalley").strip() or "openvalley"
    key_pwd = settings.store_app_key_pwd or "123456"
    store_pwd = settings.store_keystore_pwd or "123456"
    compatible = (settings.store_compatible_version or "9").strip() or "9"

    cmd = [
        _java_bin(),
        "-jar",
        str(jar),
        "sign-app",
        "-mode",
        "localSign",
        "-keyAlias",
        alias,
        "-signAlg",
        "SHA256withECDSA",
        "-appCertFile",
        str(cert),
        "-profileFile",
        str(profile_p7b),
        "-inFile",
        str(in_hap),
        "-keystoreFile",
        str(keystore),
        "-outFile",
        str(out_hap),
        "-keyPwd",
        key_pwd,
        "-keystorePwd",
        store_pwd,
        "-compatibleVersion",
        compatible,
        "-signCode",
        "1",
    ]
    _run_cmd(cmd, cwd=out_hap.parent)
    if not out_hap.is_file():
        raise HTTPException(status_code=500, detail="sign-app 成功但未找到输出 hap")
    return out_hap


def hap_resign(
    src_package: Path,
    *,
    bundle_name: str,
    work_dir: Path,
    out_hap: Path,
    version_code: int | str = DEFAULT_VERSION_CODE,
    version_name: str = DEFAULT_VERSION_NAME,
) -> Path:
    """完整 hapResign：解包 → 平台证写 Profile → sign-profile → sign-app。"""
    status = check_sign_tools(for_resign=True)
    if not status.ready:
        raise HTTPException(status_code=400, detail=status.message)
    bundle = (bundle_name or "").strip()
    if not bundle:
        raise HTTPException(status_code=400, detail="缺少 Bundle Name，无法生成 Profile")

    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        unsign_hap = unpack_to_hap(src_package, work_dir)
        app_cert_pem = read_platform_app_cert_pem()
        try:
            vc = int(str(version_code).strip())
        except (TypeError, ValueError):
            vc = DEFAULT_VERSION_CODE
        provision = build_provision_for_app(
            bundle_name=bundle,
            app_cert_pem=app_cert_pem,
            version_code=vc,
            version_name=str(version_name or DEFAULT_VERSION_NAME),
        )
        p7b = sign_profile_p7b(
            provision, work_dir=work_dir / "profile", out_name="openvalley.p7b"
        )
        return sign_app_hap(
            in_hap=unsign_hap,
            profile_p7b=p7b,
            out_hap=out_hap,
            app_cert_file=platform_app_cert_path(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("hapResign failed: %s", e)
        raise HTTPException(status_code=500, detail=f"平台重签失败：{e}") from e


def check_resign_ready() -> SignToolStatus:
    return check_sign_tools(for_resign=True)
