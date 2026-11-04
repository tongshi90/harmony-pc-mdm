# -*- coding: utf-8 -*-
"""独立 HAP 解析脚本：解包并打印 bundleName / 版本等字段.

用法（在本目录或任意目录）:
  python main.py

仅改下方 HAP_FILE_NAME 即可切换同目录下的不同 .hap。
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from typing import Any


# ---------------------------------------------------------------------------
# 可改：仅文件名；目录写死
# ---------------------------------------------------------------------------
HAP_DIR = r"E:\Desktop\applications_hap-master\applications_hap-master"
# 只改这一处文件名即可切换解析目标（目录写死）
# 注意：仓库里的 Calc_Demo.hap 若未经 git lfs pull，只是 131 字节的 LFS 指针，无法解包。
# 同目录已放置可解包示例 Clock_Demo_real.hap，需要解析 Calc 时先 git lfs pull 再改回 "Calc_Demo.hap"。
HAP_FILE_NAME = "Clock_Demo_real.hap"


def _is_git_lfs_pointer(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(200)
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def _read_zip_text(zf: zipfile.ZipFile, name: str) -> str | None:
    try:
        raw = zf.read(name)
    except KeyError:
        return None
    for enc in ("utf-8", "utf-8-sig"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _load_json_from_zip(zf: zipfile.ZipFile, name: str) -> Any | None:
    text = _read_zip_text(zf, name)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[WARN] JSON 解析失败: {name} -> {exc}")
        return None


def _find_member(zf: zipfile.ZipFile, candidates: list[str]) -> str | None:
    names = set(zf.namelist())
    for c in candidates:
        if c in names:
            return c
    # 兼容带目录前缀
    lower_map = {n.lower(): n for n in names}
    for c in candidates:
        hit = lower_map.get(c.lower())
        if hit:
            return hit
    for n in names:
        base = n.rsplit("/", 1)[-1].lower()
        for c in candidates:
            if base == c.lower():
                return n
    return None


def _dig(obj: Any, *paths: tuple[str, ...]) -> Any:
    """按多条候选路径取值，返回第一个非 None。"""
    for path in paths:
        cur = obj
        ok = True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and cur is not None and cur != "":
            return cur
    return None


def parse_hap(hap_path: str) -> dict[str, Any]:
    """解析 HAP，返回提取结果与原始关键片段。"""
    if not os.path.isfile(hap_path):
        raise FileNotFoundError(f"文件不存在: {hap_path}")

    size = os.path.getsize(hap_path)
    if size <= 0:
        raise ValueError("文件大小为 0")

    if _is_git_lfs_pointer(hap_path):
        raise ValueError(
            "该文件是 Git LFS 指针，不是真正的 HAP 二进制。\n"
            "  处理方式：\n"
            "  1) 在 applications_hap 仓库执行: git lfs pull\n"
            "  2) 或将 HAP_FILE_NAME 改为同目录下的真实包，例如 Clock_Demo_real.hap"
        )

    if not zipfile.is_zipfile(hap_path):
        raise ValueError(
            f"不是合法 ZIP/HAP（size={size}）。"
            "请确认文件完整且扩展名为 .hap"
        )

    result: dict[str, Any] = {
        "hap_path": hap_path,
        "file_size": size,
        "is_zip": True,
        "zip_entries": [],
        "module_json_path": None,
        "pack_info_path": None,
        "bundle_name": None,
        "version_name": None,
        "version_code": None,
        "vendor": None,
        "bundle_type": None,
        "module_name": None,
        "module_type": None,
        "main_element": None,
        "min_api_version": None,
        "target_api_version": None,
        "compile_sdk_version": None,
        "app_identifier": None,
        "app_distribution_type": None,  # Profile: enterprise_normal 等
        "raw_app": None,
        "raw_module": None,
        "raw_pack_summary_app": None,
    }

    with zipfile.ZipFile(hap_path, "r") as zf:
        names = zf.namelist()
        result["zip_entries"] = names

        module_path = _find_member(zf, ["module.json"])
        pack_path = _find_member(zf, ["pack.info"])
        result["module_json_path"] = module_path
        result["pack_info_path"] = pack_path

        module_obj = _load_json_from_zip(zf, module_path) if module_path else None
        pack_obj = _load_json_from_zip(zf, pack_path) if pack_path else None

        if isinstance(module_obj, dict):
            app = module_obj.get("app") if isinstance(module_obj.get("app"), dict) else {}
            mod = module_obj.get("module") if isinstance(module_obj.get("module"), dict) else {}
            result["raw_app"] = app
            result["raw_module"] = {
                k: mod.get(k)
                for k in (
                    "name",
                    "type",
                    "mainElement",
                    "deliveryWithInstall",
                    "installationFree",
                )
                if k in mod
            }
            result["bundle_name"] = _dig(module_obj, ("app", "bundleName"), ("bundleName",))
            result["version_name"] = _dig(module_obj, ("app", "versionName"), ("versionName",))
            result["version_code"] = _dig(module_obj, ("app", "versionCode"), ("versionCode",))
            result["vendor"] = _dig(module_obj, ("app", "vendor"), ("vendor",))
            result["bundle_type"] = _dig(module_obj, ("app", "bundleType"), ("bundleType",))
            result["min_api_version"] = _dig(module_obj, ("app", "minAPIVersion"), ("minAPIVersion",))
            result["target_api_version"] = _dig(
                module_obj, ("app", "targetAPIVersion"), ("targetAPIVersion",)
            )
            result["compile_sdk_version"] = _dig(
                module_obj, ("app", "compileSdkVersion"), ("compileSdkVersion",)
            )
            result["module_name"] = _dig(mod, ("name",), ("moduleName",))
            result["module_type"] = _dig(mod, ("type",), ("moduleType",))
            result["main_element"] = _dig(mod, ("mainElement",), ("mainAbility",))
            # AppIdentifier 通常在签名 Profile，不在 module.json；此处仅尽力查找
            result["app_identifier"] = _dig(
                module_obj,
                ("app", "appIdentifier"),
                ("app", "appId"),
                ("appIdentifier",),
                ("appId",),
            )

        if isinstance(pack_obj, dict):
            summary_app = _dig(pack_obj, ("summary", "app"))
            if isinstance(summary_app, dict):
                result["raw_pack_summary_app"] = summary_app
                result["bundle_name"] = result["bundle_name"] or summary_app.get("bundleName")
                result["bundle_type"] = result["bundle_type"] or summary_app.get("bundleType")
                ver = summary_app.get("version")
                if isinstance(ver, dict):
                    result["version_name"] = result["version_name"] or ver.get("name")
                    result["version_code"] = result["version_code"] or ver.get("code")
            modules = _dig(pack_obj, ("summary", "modules"))
            if isinstance(modules, list) and modules:
                m0 = modules[0] if isinstance(modules[0], dict) else {}
                distro = m0.get("distro") if isinstance(m0.get("distro"), dict) else {}
                result["module_name"] = result["module_name"] or distro.get("moduleName")
                result["module_type"] = result["module_type"] or distro.get("moduleType")
                result["main_element"] = (
                    result["main_element"] or m0.get("mainAbility") or m0.get("mainElement")
                )

        # 常见签名/Profile 文件名（有则列出，便于后续扩展解析 AppIdentifier）
        profile_hits = [
            n
            for n in names
            if any(
                x in n.lower()
                for x in ("profile", "provision", "p7b", "cert", "signature", "meta-inf")
            )
        ]
        result["signature_related_entries"] = profile_hits

    return result


def print_result(info: dict[str, Any]) -> None:
    print("=" * 60)
    print("HAP 解析结果")
    print("=" * 60)
    print(f"路径           : {info.get('hap_path')}")
    print(f"文件大小       : {info.get('file_size')} bytes")
    print(f"ZIP 条目数     : {len(info.get('zip_entries') or [])}")
    print(f"module.json    : {info.get('module_json_path') or '(未找到)'}")
    print(f"pack.info      : {info.get('pack_info_path') or '(未找到)'}")
    print("-" * 60)
    print("【关注字段】")
    # BundleName：来自 module.json / pack.info 的 app.bundleName
    bn = info.get("bundle_name")
    print(f"BundleName     : {bn if bn else '(未获得)'}")
    # AppID / AppIdentifier：一般不在 module.json，而在签名 Profile
    aid = info.get("app_identifier")
    print(f"AppID(AppIdentifier): {aid if aid else '(未获得 — 见下方说明)'}")
    # enterprise_normal：属于 Profile 的 app-distribution-type，不是 bundleType
    dist = info.get("app_distribution_type")
    print(
        f"app-distribution-type: {dist if dist else '(未获得 — 见下方说明)'}"
    )
    print(
        f"  是否 enterprise_normal: "
        f"{'是' if dist == 'enterprise_normal' else ('否' if dist else '无法判定')}"
    )
    print(f"bundleType(参考，≠企业分发类型): {info.get('bundle_type') or '(无)'}")
    print("-" * 60)
    print(f"Version Name   : {info.get('version_name')}")
    print(f"Version Code   : {info.get('version_code')}")
    print(f"Vendor         : {info.get('vendor')}")
    print(f"Module Name    : {info.get('module_name')}")
    print(f"Module Type    : {info.get('module_type')}")
    print(f"Main Element   : {info.get('main_element')}")
    print(f"minAPIVersion  : {info.get('min_api_version')}")
    print(f"targetAPIVersion: {info.get('target_api_version')}")
    print(f"compileSdkVersion: {info.get('compile_sdk_version')}")
    print("-" * 60)
    if info.get("raw_app"):
        print("app 段原始字段:")
        print(json.dumps(info["raw_app"], ensure_ascii=False, indent=2))
    if info.get("raw_module"):
        print("module 段摘要:")
        print(json.dumps(info["raw_module"], ensure_ascii=False, indent=2))
    if info.get("raw_pack_summary_app"):
        print("pack.info summary.app:")
        print(json.dumps(info["raw_pack_summary_app"], ensure_ascii=False, indent=2))
    sig = info.get("signature_related_entries") or []
    if sig:
        print("-" * 60)
        print("疑似签名/Profile 相关条目:")
        for n in sig[:30]:
            print(f"  - {n}")
    print("=" * 60)


def main() -> int:
    # 只改文件名即可切换包；目录固定
    hap_name = HAP_FILE_NAME
    hap_path = os.path.join(HAP_DIR, hap_name)

    print(f"[INFO] 解析目录: {HAP_DIR}")
    print(f"[INFO] 解析文件: {hap_name}")
    print(f"[INFO] 完整路径: {hap_path}")

    try:
        info = parse_hap(hap_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print_result(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
