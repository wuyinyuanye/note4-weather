# 第三方与素材说明

- `vendor/zectrix-local-push-sdk/`：Zectrix SDK，固定提交 c71412f3f1e1d039bf4f09b9e7867c4661ae1237，保留上游 MIT LICENSE、Opus 声明、源码和文档，未包含固件或编译产物。
- Python：Pillow（HPND）、lunardate（GPL-3.0）；Rust 的完整依赖版本见 bridge/Cargo.lock，各依赖适用其自身许可。本发布包不包含 Python/Rust 依赖的预编译副本。
- 天气：[Open-Meteo](https://open-meteo.com/)，数据 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。应用将接口数据整理、取整并渲染；不表示气象站实测。API 服务使用还须遵守 [服务条款](https://open-meteo.com/en/terms)。
- 写实天气 PNG 为 AI 生成素材，提示词见 docs/PROMPTS.md 和 assets/weather-realistic-v1/；未包含用户照片或专有系统字体。各地对 AI 素材的权利认定可能不同，不承诺独占权。
- 数字与中文字体从用户系统读取。Linux 用户安装 Noto CJK / DejaVu 或自行配置合法字体；仓库不分发 macOS 系统字体。

本项目源码公开供阅读和构建；未额外授予原创应用代码的开源许可。第三方文件继续适用原许可。
