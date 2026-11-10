# Phase 0 探针：PySide6 Qt Widgets → Android APK 链路验证

本目录只用于 **Phase 0 最小切片验证**：确认「PySide6 + Qt Widgets → pyside6-android-deploy → debug APK」这条链路是否可行。
不包含真实题库、数据库、进度保存、业务逻辑；所有代码都在一个 `main.py` 里，硬编码一道「1+1=？」的假题。

## 目录结构

- `main.py`            —— 最小 QWidget 探针（题干 + 4 个选项按钮 + 结果标签 + 下一题按钮）
- `pysidedeploy.spec`  —— pyside6-android-deploy 的部署配置（应用名 / Qt 模块 / 架构 / 打包模式）
- `requirements.txt`   —— 宿主侧依赖（PySide6、aqtinstall），不包含 Android 侧依赖
- `README.md`          —— 本文件

## 如何在 GitHub Actions 手动触发

1. 打开仓库 `quiz-android-probe` 的 **Actions** 标签页。
2. 左侧选择 **Phase0 Probe** workflow。
3. 点击 **Run workflow** 按钮。
4. 分支选 `main`，参数保持默认：
   - `qt_version` = `6.8.3`
   - `ndk_version` = `26.1.10909125`
   - `run_cross_compile` = 不勾选（默认 false，只跑路径 A）
5. 点击绿色的 **Run workflow** 开始。

## 如何下载 APK

1. 在 Actions 页面等 run 结束（路径 A 预计 35–70 分钟）。
2. 进入该 run 的详情页，翻到页面底部 **Artifacts** 区域。
3. 点击 **phase0-apk** 下载 zip。
4. 解压后应包含：
   - 一个 `.apk`（debug 签名）
   - `pysidedeploy.spec`
   - 两个 `.whl`（PySide6 / shiboken6 的 android_aarch64 预编译轮子）
   - `SHA256SUMS`
   - `deploy.log`（完整构建日志）

## 手机上预期效果

- 打开应用，窗口标题为 **Phase0 Probe**。
- 自上而下：题号「第 1 题」、题干「题干：1+1=？」、四个选项按钮（A. 1 / B. 2 / C. 3 / D. 4）、结果标签、「下一题」按钮。
- 点 **B**：B 变绿底白字，结果显示「回答正确」，所有选项锁定。
- 点 **A / C / D** 任意一个：该按钮变红底白字，同时 B 变绿底白字，结果显示「回答错误」，所有选项锁定。
- 点「下一题」：颜色清空、选项恢复可点、题号 +1、结果清空。

## 路径 A 通过后的下一步

1. 进 Phase 1：在本地 WSL2（Ubuntu 24.04）复现同样的构建环境。
2. 主应用改造：新增 `app/platform.py` 抽象平台差异、新增触控友好的移动端布局。
3. 题库只读迁移：把 `quiz.db` 复制到 Android 资源目录 + SHA256 双校验后只读打开。
4. 业务规则（session / progress / wrongbook）原样保留，仅适配存储路径。

## 路径 A 失败后的下一步

1. 先按 `deploy.log` 定位失败步骤与错误行。
2. 版本问题 → 换 Qt 6.10.3 官方轮子重试。
3. 需要 patch Qt 或官方轮子不够用 → 勾选 `run_cross_compile=true` 验证路径 B。
4. 只有路径 A 也彻底失败时才讨论换 Kivy。
