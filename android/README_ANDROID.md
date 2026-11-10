# Android 部署说明（Phase 1 第一步：题库加载验证）

## 本阶段做了什么
- 最小 Android 入口 `android/main.py`：只验证「资产复制 → SHA256 校验 → 只读打开 → 读第一题」，不做答题交互、不改移动端 UI。
- 题库 `quiz.db` 从打包资产复制到应用私有目录，绝不新建空库；复制或校验失败直接报错退出。
- 复用 Phase 0 的 PySide6 + buildozer + p4a 链路，应用名/包名仍为 Phase0Probe / org.phase0probe.phase0probe。

## 题库资产
- `android/assets/quiz.db`：从桌面现有题库原样复制（只读，565248 字节，1874 题）。
- `android/assets/quiz.db.sha256`：64 位大写十六进制 SHA256（8943EC01805C6876B0671F3278CF9E00749E12A01E1468D1F3B105BD74176533）。
- 打包时给 `source.include_exts` 追加 `db`，把 quiz.db 打进 APK 的 private 归档，运行时解压到应用私有目录，由 `app/platform.py` 校验后只读打开。

## 后续改名清单（本次不改名，保留 Phase0Probe）
以后要改应用名 / 包名时，需同步修改以下位置：
1. `android/pysidedeploy.spec` 的 `[app] title`，以及 workflow 打包步骤里的 `--name Phase0Probe` 参数。
2. 包名 `org.phase0probe.phase0probe` 出现的位置：由 pyside6-android-deploy 依据 title 生成
   （其内部 BuildozerConfig 设 `package.domain = org.{title}`、`package.name = title`）；
   改 title 即改包名；若需彻底独立的包名，需在生成的 `buildozer.spec` 里改 `package.name` / `package.domain`。
3. `android/main.py` 的窗口标题（`self.setWindowTitle("题库加载验证")`）。
4. 桌面版 `main.py` / `main_window.py` 的窗口标题（`app.setApplicationName("答题练习软件")` / `setWindowTitle(...)`）。
5. 改包名后必须先卸载旧包（`adb uninstall org.phase0probe.phase0probe`）再装新包；
   Android 本地数据（进度 / 历史 / 错题）通过 JSON 导入导出迁移，不直接拷贝数据库文件。
