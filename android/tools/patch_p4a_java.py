# -*- coding: utf-8 -*-
"""补丁 p4a 的 qt bootstrap PythonActivity.java。

pythonforandroid 是在 pyside6-android-deploy 运行时才装进环境的，
所以这个脚本以 --watch 模式在 deploy 之前启动，等它出现后立刻打补丁：

1) Window 加 FLAG_KEEP_SCREEN_ON —— 答题过程屏幕常亮（不需要额外权限）；
2) BACK 键写成标记文件 back_key.flag —— p4a 默认实现是「再按一次退出」的
   Toast 并 return true（把按键吞掉），这里改成交给 Python 侧处理：
   先关浮层，没有浮层就弹「确认退出练习吗？」。

补丁是幂等的，重复运行不会叠加。
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


def _site_roots() -> list:
    """p4a 可能装到的 site-packages 目录（venv / --user / 系统）。"""
    out = []
    for root in _roots():
        for name in ("lib", "lib64"):
            base = root / name
            if not base.exists():
                continue
            out.extend([p for p in base.glob("python3*") if p.is_dir()])
        # venv 可能直接给出 site-packages 层级
        sp = root / "site-packages"
        if sp.exists():
            out.append(sp)
    return out


def _p4a_dirs() -> list:
    dirs = []
    for base in _site_roots():
        for cand in (base / "site-packages" / "pythonforandroid", base / "pythonforandroid"):
            if cand.is_dir() and cand not in dirs:
                dirs.append(cand)
    return dirs


def find_java() -> list:
    found = []
    for p4a in _p4a_dirs():
        boot = p4a / "bootstraps"
        if not boot.exists():
            continue
        found.extend(boot.glob("**/PythonActivity.java"))
    found.sort(key=lambda p: 0 if "bootstraps/qt" in p.as_posix() else 1)
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
    args = ap.parse_args()

    deadline = time.time() + args.timeout
    while True:
        cands = find_java()
        if cands:
            target = cands[0]
            ok, msg = patch(target)
            print("PATCH_JAVA target=%s result=%s msg=%s" % (target, ok, msg))
            if not ok:
                return 1
            if args.marker:
                pathlib.Path(args.marker).write_text(str(target), encoding="utf-8")
            return 0
        if not args.watch or time.time() > deadline:
            print("PATCH_JAVA 未找到 PythonActivity.java")
            print("  搜索的 site 根：", [str(p) for p in _site_roots()])
            print("  找到的 pythonforandroid：", [str(p) for p in _p4a_dirs()])
            return 1
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
