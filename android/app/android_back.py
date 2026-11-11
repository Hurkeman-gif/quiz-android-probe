# -*- coding: utf-8 -*-
"""Android 平台适配：屏幕常亮 + 系统返回键接管。

实际生效路径有两条：
1) 构建期补丁改 p4a 的 PythonActivity.java：Window 加 FLAG_KEEP_SCREEN_ON，
   并把 BACK 键写成标记文件（见 .github/workflows/phase0_probe.yml）；
2) 本模块在 Python 侧轮询该标记文件，交给主窗口做「先关浮层 / 再二次确认退出」。

另外保留 pyjnius 版本的实现作为可选增强（没有 pyjnius 时静默降级）。
"""
from __future__ import annotations

import os

# 注册给系统的回调必须保持引用，否则会被 GC 回收导致返回键失效。
_keep_alive = []

BACK_FLAG_NAME = "back_key.flag"


def back_flag_path():
    """返回键标记文件路径（由 Java 侧写入）。非 Android 环境返回 None。"""
    root = os.environ.get("ANDROID_PRIVATE")
    if not root:
        return None
    return os.path.join(root, BACK_FLAG_NAME)


def consume_back_flag() -> bool:
    """检查并清除返回键标记；读到标记返回 True。"""
    path = back_flag_path()
    if not path:
        return False
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception:
        return False
    return False


def keep_screen_on() -> bool:
    """让答题界面保持常亮（WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON）。"""
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return False
        # FLAG_KEEP_SCREEN_ON == 0x00000080
        activity.getWindow().addFlags(0x00000080)
        return True
    except Exception:
        return False


def install_back_handler(callback) -> bool:
    """Android 13+ 接管系统返回键。

    Android 13 起返回键走 OnBackInvokedCallback（预测性返回），
    旧的 onBackPressed 不再被调用，因此必须注册新的回调。
    需要应用 targetSdk >= 33 才会启用该机制，构建时已把 android.api 提到 34。
    """
    if callback is None:
        return False
    try:
        from jnius import PythonJavaClass, autoclass, java_method
    except Exception:
        return False

    class _BackCallback(PythonJavaClass):
        __javainterfaces__ = ["android/window/OnBackInvokedCallback"]
        __javacontext__ = "app"

        @java_method("()V")
        def onBackInvoked(self):
            try:
                callback()
            except Exception:
                pass

    try:
        version = autoclass("android.os.Build$VERSION")
        if int(version.SDK_INT) < 33:
            return False
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return False
        dispatcher = activity.getOnBackInvokedDispatcher()
        if dispatcher is None:
            return False
        proxy = _BackCallback()
        # 0 == OnBackInvokedDispatcher.PRIORITY_DEFAULT
        dispatcher.registerOnBackInvokedCallback(0, proxy)
        _keep_alive.append(proxy)
        return True
    except Exception:
        return False
