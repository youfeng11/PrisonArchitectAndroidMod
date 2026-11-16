# 第三方声明

## Google Material Symbols

`game/obb-bridge/compose/src/main/res/drawable/ms_*.xml` 使用 Google Material Symbols Outlined 的 24px 图标，采用 Apache License 2.0。Android VectorDrawable 文件保留了来源声明。

- [上游项目](https://github.com/google/material-design-icons)
- [随本项目提供的许可证文本](licenses/Material-Symbols-Apache-2.0.txt)

## Gradle Wrapper

根目录的 Gradle Wrapper 脚本及 JAR 来自 Gradle 9.6.0，随附 [许可证](licenses/Gradle-LICENSE.txt) 和 [NOTICE](licenses/Gradle-NOTICE.txt)。分发包校验值固定在 Wrapper 配置中。

## 构建依赖

模组导入使用 [libarchive-android](https://github.com/zhanghai/libarchive-android)（Apache-2.0）及其中的 [libarchive 和解码库](https://github.com/zhanghai/libarchive-android#libarchive-android)。

Gradle、Android 工具链、AndroidX、smali 以及 Python 测试依赖由各自渠道获取，并适用各自的许可证。版本和依赖项见 [构建说明](game/README.md)、Compose 的构建文件及 [requirements.txt](requirements.txt)。
