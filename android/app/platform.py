# -*- coding: utf-8 -*-
"""平台适配层：Android 资源复制与题库完整性校验。

Android 下题库只读、从打包进 APK 的资产复制到应用私有目录，并做 SHA256 校验；
桌面环境直接使用 database.get_default_db_path() 的现有逻辑，不复制、不新建。
"""
from __future__ import annotations

import hashlib
import os
import sys

# 题库校验锚点：完整 SHA256 由现有 quiz.db 计算（前 8 位 8943EC01，后 8 位 74176533）。
# 字节数同时作为快速校验。二者任一不匹配都会抛异常，绝不生成空库。
EXPECTED_BANK_SHA256 = "8943EC01805C6876B0671F3278CF9E00749E12A01E1468D1F3B105BD74176533"
EXPECTED_BANK_SIZE = 565248

BANK_FILENAME = "quiz.db"


def is_android() -> bool:
    """是否运行在 Android。

    Python 3.11/3.12 在 Android 上 sys.platform 仍是 "linux"（3.13 才改成 "android"），
    所以不能只看 sys.platform；python-for-android 的启动器一定会设置 ANDROID_* 环境变量。
    """
    if sys.platform == "android":
        return True
    return bool(
        os.environ.get("ANDROID_ARGUMENT")
        or os.environ.get("ANDROID_PRIVATE")
        or os.environ.get("ANDROID_APP_PATH")
        or os.environ.get("ANDROID_BOOTLOGO")
    )


def app_data_dir() -> str:
    """应用私有数据目录（QStandardPaths.AppDataLocation），确保目录存在。"""
    from PySide6.QtCore import QStandardPaths
    loc = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation)
    if not loc:
        raise RuntimeError("无法取得 AppDataLocation（QStandardPaths 返回空）")
    os.makedirs(loc, exist_ok=True)
    return loc


def sha256_file(path: str) -> str:
    """计算文件 SHA256（大写十六进制）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _android_asset_roots():
    """返回可能存放打包资产的候选目录（按优先级）。

    p4a 把 source.dir（= android/）原样解压到应用私有目录，因此：
    - android/assets/quiz.db -> <private>/assets/quiz.db（主路径）
    下面两个是容错兜底，防止 p4a 版本差异导致结构不同。
    """
    here = os.path.dirname(os.path.abspath(__file__))  # <private>/app
    private = os.path.dirname(here)                    # <private>
    return [
        os.path.join(private, "assets"),
        os.path.join(here, "assets"),
        private,
    ]


def bundle_asset(name: str) -> bytes:
    """读取打包资产文件的字节；Android 从私有目录读，桌面从项目 data/ 目录读。"""
    if is_android():
        roots = _android_asset_roots()
        for root in roots:
            path = os.path.join(root, name)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read()
        raise FileNotFoundError(
            f"Android 资产缺失：{name}（已查找 {roots}）")
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", name)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    raise FileNotFoundError(f"资源文件缺失：{path}")


def ensure_bank_from_assets() -> str:
    """返回题库文件路径。

    Android：从资产复制到应用私有目录并做 SHA256 + 字节数校验，失败抛异常（不生成空库）。
    桌面：直接返回现有 database.get_default_db_path()，不复制。
    """
    if not is_android():
        from . import database
        return database.get_default_db_path()

    target = os.path.join(app_data_dir(), BANK_FILENAME)

    # 已存在且校验通过：直接复用（卸载重装后目录被清空，会重新复制）
    if os.path.isfile(target) and sha256_file(target) == EXPECTED_BANK_SHA256:
        return target

    data = bundle_asset(BANK_FILENAME)
    if len(data) != EXPECTED_BANK_SIZE:
        raise RuntimeError(
            f"题库资产字节数不符：期望 {EXPECTED_BANK_SIZE}，实际 {len(data)}")

    part = target + ".part"
    try:
        with open(part, "wb") as f:
            f.write(data)
        if os.path.getsize(part) != EXPECTED_BANK_SIZE:
            raise RuntimeError("写入 .part 后字节数不符")
        if sha256_file(part) != EXPECTED_BANK_SHA256:
            raise RuntimeError("题库 SHA256 校验失败：资产与现有 quiz.db 不一致")
        os.replace(part, target)  # 原子落盘
    except Exception:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        raise
    return target
