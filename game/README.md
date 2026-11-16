# v49 游戏补丁开发说明

在项目根目录打开 Gradle 工程。构建目标为 Android 2.0.9（49）的 ARMv7，包名为 `com.paradoxplaza.prisonarchitect`。

## 源码导航

| 子系统 | 入口 |
| --- | --- |
| 构建入口与工具检查 | `build-logic` 中的 `GameBuildPlugin` |
| ELF、ARM 指令与 NDK 构建 | `NativePatcher`、`Binary`、`V49Profile` |
| APK、资源表与 Manifest | `ApkBuilder`、`ResourceTables`、`ManifestPatcher` |
| 离线 DEX 处理 | `OfflineDex` |
| 回归编排 | `GameChecks`，调用本目录的 `verify_*.py` |
| 原生模组行为 | `native_sprite_replacements.c`、`register_object_sprites.S` |
| 版本定义 | `profiles/v49.json`，Python 经 `patch_profile.py` 读取 |
| Android 文件与模组操作 | `obb-bridge/NativeModStore.java`、`ModArchive.java`、`MaterialDefinitionRepair.java` |

模组页是 `:mod-manager` 子工程。Kotlin 源码位于 `obb-bridge/compose/src/main/java/com/paradoxplaza/prisonarchitect/patools/`。

- `NativeModsActivity` 处理生命周期、文件选择器和外部打开。
- `NativeModsModel` 管理异步操作与状态，`NativeModsRoute` 连接状态和界面。
- `NativeModsScreen` 组织页面，`NativeModsList` 处理刷新和拖动。
- `NativeModCard`、`NativeModsDialogs`、`ModThumbnail` 绘制卡片、弹窗和缩略图。

## 工具与构建参数

固定版本为 Gradle 9.6.0、AGP 9.5.1、Compose 插件 2.2.10、Build Tools 36.1.0、NDK 29.0.13113456。smali／baksmali 3.0.10 通过 Gradle 解析。

| 参数 | 默认值或用途 |
| --- | --- |
| `game.sourceApk` | 根目录的 `com.paradoxplaza.prisonarchitect.apk` |
| `game.obb` | 根目录包名目录中的 v49 OBB |
| `game.sdkDir` | 构建工具 SDK 路径，依次回退到 `sdk.dir`、`ANDROID_HOME`、`ANDROID_SDK_ROOT` |
| `game.signingProperties` | 本地签名配置，默认 `signing/signing.properties` |
| `game.keystore` | 可选的密钥路径覆盖，默认读取签名配置的 `storeFile` |
| `game.checkApk` | 验证目标，默认为 `build/PrisonArchitect.apk` |
| `game.checks` | `full`，可选 `smoke` |
| `game.python` | Windows 为 `python`，Linux 为 `python3` |
| `game.device` | 安装时明确指定的 ADB 序列号 |
| `game.launch` | 安装后启动游戏，默认 `false` |
| `game.smaliDir` | 可选的本地 smali 依赖 JAR 目录 |

SDK 同时需要供 Android 子工程发现，使用 `ANDROID_HOME` 或根目录本地 `local.properties` 的 `sdk.dir`。属性参数在 PowerShell 中使用引号。

```powershell
./gradlew.bat buildGame
./gradlew.bat checkGame "-Pgame.checks=smoke"
./gradlew.bat installGame "-Pgame.device=<序列号>"
```

所有构建固定输出到 `build/PrisonArchitect.apk`。构建器在临时目录完成修改、对齐、签名和检查，成功后原子替换产物。失败工具日志保存在 `build/diagnostics/tool-failures/`。

构建时在原 APK 的版本名后追加 `-mod`，例如 `2.0.9-mod`；版本代码保持 49。

## APK 签名

游戏使用项目专用签名。本地 `signing/signing.properties` 配置如下，`storeFile` 相对项目根目录解析：

```properties
storeFile=signing/prisonarchitect.p12
keyAlias=prisonarchitect
storePassword=<本地密钥库密码>
keyPassword=<本地私钥密码>
```

首次自行构建时，创建 `signing/`，用 JDK 的 `keytool` 生成密钥，然后填写上述配置：

```text
keytool -genkeypair -keystore signing/prisonarchitect.p12 -storetype PKCS12 -alias prisonarchitect -keyalg RSA -keysize 3072 -validity 9125
```

密钥和密码文件均保存在已忽略的 `signing/` 目录，不提交到公开仓库；构建时也不把密码放进命令行参数。请备份该目录，后续更新需继续使用同一密钥。更换签名的 APK 无法直接覆盖旧签名版本，安装前需另行处理旧版存档和迁移。

## 验证与预览

先运行 `python -m pip install -r requirements.txt`，按 [模组样本说明](../fixtures/mods/README.md) 准备本地样本。需要生成精灵坐标时执行 `./gradlew.bat generateNativeRegions`。

```powershell
./gradlew.bat :build-logic:test
./gradlew.bat buildGame checkGame
./gradlew.bat :mod-manager:assemblePreview
```

`checkGame` 要求安装包包含内置 OBB，并检查资源内容与启动补丁。完整回归包含贴图、字体、脚本、材料、生产和导入。Linux 的 Java 可执行文件名与类路径分隔符由运行器处理，实际 Linux 验收暂缓。

在 Android Studio 选择 `:mod-manager` 的 `preview` 变体，打开 `NativeModsPreviews.kt` 可查看空列表、多模组和同名覆盖。

## 游戏内模组管理

游戏 APK 在启动器中的「监狱建筑师模组」入口使用 Jetpack Compose。可导入带 `manifest.txt` 的 ZIP、RAR（RAR4 或 RAR5）、7z、TAR、TAR.GZ、TAR.BZ2 和 TAR.XZ。导入按压缩包内容识别格式，这些压缩包也可以使用 `.mod` 后缀。请使用单卷、无密码的压缩包。模组可直接启停、调整顺序或删除。冷启动游戏后生效，游戏已运行时可以先返回保存，再选择重启。

也可以在文件管理器选中压缩包，通过「打开方式」选择「监狱建筑师模组」，然后确认导入。

开发模组页时，在 Android Studio 打开项目根目录，将 Build Variants 切换到 `preview`，再打开 `NativeModsPreviews.kt` 的 Design 或 Split 视图。空列表、已安装模组和同名覆盖都使用样例数据，可直接预览。

已启用的模组按覆盖优先级显示。长按卡片可拖动排序，上面的模组会覆盖下面的模组。导入同名模组时可确认覆盖，覆盖后会保留启用状态和顺序。详情中可查看模组清单提供的作者、版本、日期和说明。

`data/events.txt`、`data/jobs.txt` 和 `data/prefabs.txt` 支持添加新定义。桌面模组中的 `data/prefabs_dlc.txt` 会在同一模组的 `prefabs.txt` 之后读取。后加载的同名定义保留已有编号，用于随机事件、工作和快速搭建模板。

加工配方既可放在 `data/production.txt`，也可放在独立的 `data/processors.txt`，两处均使用 `BEGIN Processor` 定义。游戏先读原版生产表，再按优先级从低到高读取各模组。同一模组同时提供两份文件时，先读 `production.txt`。

新增对象同时声明 `Properties Entity`、`Properties Staff` 和 `Properties DefaultBehaviour` 时，可使用移动版 Worker 的找工作、执行任务和闲置行为。`HangOutRoom` 按房间名称解析；`StaffNeeds` 接入移动版已有的疲劳和休息逻辑，并不提供桌面版完整的员工需求系统。带 `Properties Scripted` 的对象继续由脚本控制。规则来自模组定义，不依赖具体对象名称或编号；重新加载材料时会清理旧配置。

Workshop Laborers（劳动者）是这条路径的回归样本，包含四套外观和四条加工配方。`Processor` 中重复的 `Worker` 字段由移动版原生生产加载器读取，决定可操作该配方的角色；`ProductionRule` 中的同名字段没有对应注册项，不应依靠它限制搬运人员。

`sprites.png` 高度不必是 32 的倍数。打包器把占位矩形补齐到整格，并按原生 Blit 的底边对齐方式放置 PNG；顶部的空行参与精灵坐标。例如劳动者的 300 像素图集占 320 像素高，顶部保留 20 像素，避免截断头部或取到相邻变体。

模组精灵和覆盖图集仍使用 RGBA4444，但 RGB 采用 8×8 有序抖动量化，减少渐变和低对比纹理被压成大色块。三个颜色通道使用同一阈值，灰色不会产生彩色噪点；透明度独立舍入，透明色键保持清空。已有的 17 倍数颜色精确保留，未被模组覆盖的原版像素不重新量化。`verify_native_quantization.py` 从实际 ARM Blit 入口检查平均颜色、灰阶层次、透明边缘和写入边界。

游戏读取顶点和片元着色器时，优先使用已启用模组中同路径的文件。例如 `data/shaders/gles/lightmap.vs` 和 `data/shaders/gles/lightmap.fs`。提供的着色器须符合移动版的 GLES 接口。

引擎按 `BEGIN`/`END` 嵌套解析 `data/materials.txt`。桌面版模组常在同一个 Sprite 里重复写 `BEGIN Sprite` 而不先闭合，导致其后的对象定义全部变成该 Sprite 的子项而被丢弃——2010s 中国风监狱模组就是这样。导入时会把重复声明合并成单个 Sprite 块并补上 `END`；已经装好的模组在下次打开模组页时也会被整理。只合并字段完全一致的重复声明，字段冲突时保持文件原样。修复结果先写入同目录临时文件，再原子替换材料文件。

模组可使用本文列出的资源入口。`data/materials_dlc.txt`、`data/objects_d11_2.png`、`data/staffnames.txt` 和 `D11Logo.png`/`PDXLogo.png` 属于尚未接入的桌面版或 DLC 内容。`data/materials.txt`、`data/objects.png`、`data/people.png`、`data/special-entities.png`、`data/sprites.png`、`data/PAlogo.png`、`data/effects.bmp`、`data/sounds.txt` 和语言目录会按前面各节的方式应用。

位图字体按模组优先级查找。同一模组提供同名字体的 FNT 和 BMP 时，先尝试 FNT。FNT 引用的字形图片应与字体文件一同放入模组。没有可用的模组字体时，读取游戏自带的字体。

与 Android v49 原版布局一致的 2048×2048 `data/objects.png`、`data/people.png` 和 `data/special-entities.png` 会应用到对应的合成图区域。每层只覆盖相对原版 PNG 有变化的像素；原图的其余 RGBA4444 像素保留。

与原版布局一致的 512×512 `data/effects.bmp` 会覆盖移动版特效图集，保留未修改像素和特效帧的位置。

只有 `data/language/manifest.txt` 的语言包也能导入。管理器会从语言清单生成供游戏扫描的根清单，并保留原语言目录。

游戏内可在「设置 → 语言」选择「简体中文」。APK 提供语言入口，翻译和字库来自 v49 OBB。构建检查会验证语言入口、三份简体中文翻译表和菜单字形。

## 游戏内置 OBB 服务

构建为游戏增加了签名权限和独立 OBB 服务。PATools 客户端可使用该服务读取、安装和恢复游戏 OBB。游戏构建所需的 AIDL 已包含在 [obb-bridge/aidl](obb-bridge/aidl/)。

客户端与游戏必须使用相同签名才能调用该服务。小米 HyperOS 上若系统阻止绑定服务，可在后台自启动设置里允许监狱建筑师。
