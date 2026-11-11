# -*- coding: utf-8 -*-
"""补丁 p4a 的 qt bootstrap PythonActivity.java（常亮 + 返回键转发）。

pythonforandroid 是 pyside6-android-deploy 运行时才克隆/安装的，而且 Java 源码
会被复制到 build-<arch>/dists/<dist>/src/main/java 下再编译。所以这个脚本以
--watch 模式启动，反复扫描并按需补丁，直到 dists 下的副本也打上补丁为止：

1) Window 加 FLAG_KEEP_SCREEN_ON —— 答题过程屏幕常亮（不需要额外权限）；
2) BACK 键写标记文件 back_key.flag —— p4a 默认实现是「再按一次退出」Toast 并
   return true（把按键吞掉），这里改成交给 Python 侧处理：先关浮层，没有浮层
   就弹「确认退出练习吗？」。

补丁是幂等的，重复打不会叠加。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import time

KEEP_LINE = (
    "getWindow().addFlags("
    "android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);"
)

NEW_BACK = '''    long lastBackClick = SystemClock.elapsedRealtime();
    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        // 返回键转交 Python：写标记文件，由 Python 侧决定关浮层 / 二次确认退出
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            try {
                java.io.FileWriter w = new java.io.FileWriter(
                        new java.io.File(getFilesDir(), "back_key.flag"), false);
                w.write(String.valueOf(System.currentTimeMillis()));
                w.close();
            } catch (Exception e) {
                Log.e("PythonActivity", "back flag write failed", e);
            }
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }
'''

BACK_RE = re.compile(
    r"    long lastBackClick = SystemClock\.elapsedRealtime\(\);\s*"
    r"@Override\s*public boolean onKeyDown\(int keyCode, KeyEvent event\)\s*\{.*?\n    \}\n",
    re.S,
)


def _roots() -> list:
    env = os.environ.get("P4A_ROOTS", "")
    if env:
        return [pathlib.Path(p) for p in env.split(os.pathsep) if p]
    out = []
    for key in ("RUNNER_TEMP", "HOME", "GITHUB_WORKSPACE"):
        val = os.environ.get(key)
        if val:
            out.append(pathlib.Path(val))
    out.append(pathlib.Path("/opt"))
    return [p for p in out if p.exists()]


def _platform_dirs() -> list:
    """buildozer 平台目录：<base>/.buildozer/android/platform 及同级 build-*/。"""
    bases = [pathlib.Path.cwd(), pathlib.Path.cwd() / "android"]
    bases.extend(_roots())
    bases.extend([r / "android" for r in _roots()])
    out = []
    for base in bases:
        for platform in (base / ".buildozer" / "android" / "platform",):
            if platform.is_dir() and platform not in out:
                out.append(platform)
    return out


def _p4a_dirs() -> list:
    """pythonforandroid 包目录（buildozer 克隆优先，其次 site-packages）。"""
    dirs = []
    for platform in _platform_dirs():
        cand = platform / "python-for-android" / "pythonforandroid"
        if cand.is_dir() and cand not in dirs:
            dirs.append(cand)
    for root in _roots():
        for name in ("lib", "lib64"):
            base = root / name
            if not base.exists():
                continue
            for py in base.glob("python3*"):
                for cand in (py / "site-packages" / "pythonforandroid", py / "pythonforandroid"):
                    if cand.is_dir() and cand not in dirs:
                        dirs.append(cand)
    return dirs


def find_java() -> list:
    """返回 (是否会被编译, 路径)。

    p4a 的编译链路是：
      pythonforandroid/bootstraps/qt/build
        -> build-<arch>/build/bootstrap_builds/qt        (第一次复制)
        -> build-<arch>/dists/<dist>                     (第二次复制，gradle 在这里编译)
    所以三处都要打补丁，只有前两处（bootstrap / dists）算「可编译副本」。
    """
    found = []
    for p4a in _p4a_dirs():
        boot = p4a / "bootstraps"
        if boot.exists():
            found.extend((False, p) for p in boot.glob("**/PythonActivity.java"))
    for platform in _platform_dirs():
        for build in platform.glob("build-*/build/bootstrap_builds/**"):
            found.extend((True, p) for p in build.glob("**/PythonActivity.java") if p.is_file())
        for dist in platform.glob("build-*/dists/*/src/main/java"):
            found.extend((True, p) for p in dist.glob("**/PythonActivity.java"))
    found.sort(key=lambda item: (0 if "bootstraps/qt" in item[1].as_posix() else 1))
    return found


def patch(path: pathlib.Path) -> tuple:
    src = path.read_text(encoding="utf-8")
    changed = False

    if KEEP_LINE not in src:
        anchors = src.count("super.onCreate(savedInstanceState);")
        if anchors != 1:
            return False, "super.onCreate 命中 %d 次，无法定位常亮插入点" % anchors
        src = src.replace(
            "super.onCreate(savedInstanceState);",
            "super.onCreate(savedInstanceState);\n        " + KEEP_LINE,
            1,
        )
        changed = True

    if "back_key.flag" not in src:
        src, hits = BACK_RE.subn(lambda m: NEW_BACK, src)
        if hits != 1:
            return False, "onKeyDown 补丁未命中（%d）" % hits
        changed = True

    if changed:
        path.write_text(src, encoding="utf-8")
    return True, "patched" if changed else "already"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--marker", default="")
    ap.add_argument("--grace", type=int, default=180, help="补到 bootstrap 后再守多少秒等 dists 副本")
    args = ap.parse_args()

    deadline = time.time() + args.timeout
    grace_until = float("inf")
    done = []
    seen = set()
    while True:
        for is_dist, path in find_java():
            ok, msg = patch(path)
            key = (str(path), ok, msg)
            if key not in seen:
                seen.add(key)
                print("PATCH_JAVA dists=%d target=%s result=%s msg=%s"
                      % (int(is_dist), path, ok, msg), flush=True)
            if not ok:
                # 非 qt bootstrap（如 service_only）没有这段 onKeyDown，跳过即可，
                # 只有真正会被编译的那份才必须打上补丁。
                continue
            if is_dist and path not in done:
                done.append(path)
                if args.marker:
                    pathlib.Path(args.marker).write_text(str(path), encoding="utf-8")
                print("PATCH_JAVA 可编译副本已补丁：%s" % path, flush=True)
                if "/dists/" in path.as_posix():
                    print("PATCH_JAVA dists 副本已补丁，结束等待", flush=True)
                    return 0
                # 先补到 bootstrap_builds：再守一会儿，等 dists 副本出现也补上
                grace_until = time.time() + args.grace
        if done and time.time() > grace_until:
            return 0
        if not args.watch or time.time() > deadline:
            print("PATCH_JAVA 未找到可编译的 dists 副本 PythonActivity.java", flush=True)
            print("  cwd：", os.getcwd(), flush=True)
            print("  平台目录：", [str(p) for p in _platform_dirs()], flush=True)
            print("  pythonforandroid：", [str(p) for p in _p4a_dirs()], flush=True)
            print("  已补丁：", [str(p) for p in done], flush=True)
            return 1
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
