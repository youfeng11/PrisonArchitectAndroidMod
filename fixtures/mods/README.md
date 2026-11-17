# 本地模组回归样本

完整兼容性回归从本目录读取以下 ZIP。用你有权使用的副本，文件名保持一致。归档中的版本差异可能影响基于内容的断言。

- `mods_Office_Chair.zip`
- `mods_Additional_Guard_Sprites.zip`
- `mods_Additional_Staff_Sprites.zip`
- `mods_2010s_Chinese_style_Prison_Mod.zip`
- `mods_clearer_needs_icons.zip`
- `batman-callout.zip`
- `super-grants.zip`
- `log-export-fix.zip`
- `劳动者mod.zip`（Workshop Laborers，FileID F2129789082）
- `mods_Manufactury_4_0.zip`（Manufactury 4.0 棉花种植园）

没有这些样本时，可运行 `./gradlew.bat buildGame checkGame "-Pgame.checks=smoke"` 检查构建。

`mods_2010s_Chinese_style_Prison_Mod.zip` 请保留上游原样：它的 `data/materials.txt` 在同一个 Sprite 里重复写了四次 `BEGIN Sprite`，导入时应被合并成一个 Sprite 块，其后的 `ArmedGuard` 和 `Guard` 定义才不会被引擎丢弃。`game/build_chinese_style_update.py` 可以离线生成修复后的版本，两者内容应一致。
