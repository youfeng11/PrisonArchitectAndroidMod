# Prison Architect Android v49 游戏补丁

面向 Prison Architect Android 2.0.9（版本代码 49）的 ARMv7 游戏补丁。提供游戏内模组管理、原生模组加载和精灵索引扩展。

## 构建

从项目根目录使用 Gradle Wrapper。准备 JDK 17+、Android SDK Platform 36 和 37、Build Tools 36.1.0、NDK 29.0.13113456。SDK 通过 `ANDROID_HOME` 或本地 `sdk.dir` 配置。

把本地原版 APK 命名为 `com.paradoxplaza.prisonarchitect.apk`，OBB 放到 `com.paradoxplaza.prisonarchitect/main.49.com.paradoxplaza.prisonarchitect.obb`，再按 [APK 签名说明](game/README.md#apk-签名) 准备本地密钥和配置，然后执行：

```powershell
./gradlew.bat buildGame
```

Linux 首次使用时运行 `chmod +x gradlew`，之后使用 `./gradlew buildGame`。构建和打包由 Kotlin 完成，生成内置 OBB 的游戏安装包，固定输出到 `build/PrisonArchitect.apk`。包名为 `com.paradoxplaza.prisonarchitect.mod`；项目版本由 `gradle.properties` 的 `version` 定义，目前生成 `2.0.9-0.1.0`。签名读取本地 `signing/signing.properties`。

## 验证与开发

```powershell
python -m pip install -r requirements.txt
./gradlew.bat checkGame
./gradlew.bat :mod-manager:assemblePreview
```

`checkGame` 验证已有 APK，完整回归需要本地模组样本。Kotlin 构建插件的单元检查使用 `./gradlew.bat :build-logic:test`。源码导航、构建参数和安装命令见 [开发说明](game/README.md)。

| 目录 | 用途 |
| --- | --- |
| `build-logic/` | Kotlin 构建插件、二进制处理和打包 |
| `game/profiles/` | 新构建器与 ARM 回归共享的 v49 补丁定义 |
| `game/` | C／ARM 补丁和 Python 回归、辅助工具 |
| `game/obb-bridge/compose/` | 游戏内模组管理页 |
| [fixtures/mods/](fixtures/mods/) | 本地回归样本的准备说明 |

Windows 构建与回归在本地验收。Linux 已有工具调用适配，实际打包验收待执行。

## 本地文件

`build/` 放置当前构建产物，`releases/history/` 保存历史 APK，`build/diagnostics/` 保存本地截图、验证日志和迁移基准。`archive/` 与 `PATools-game-audit/` 保存历史逆向资料；不适用于当前构建的 `run-as` 注入脚本保留在本地 `archive/legacy-game-tools/`。`signing/` 保存项目私钥和密码配置。这些目录由 `.gitignore` 排除。

提交范围为源码、构建配置、Gradle Wrapper、回归脚本和文档。原版游戏、模组样本、签名密钥与生成文件留在本地。提交前检查：

```text
git diff --cached --stat
git diff --cached --check
```

## 许可证

项目自有源码采用 [GPL-3.0-or-later](LICENSE)。第三方声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

原版 APK、OBB 和第三方模组由使用者在本地提供，并适用各自的权利和许可条款。游戏名称用于说明兼容性。本项目由社区维护。
