# 可复用提示词

## 开发与二次修改提示词

以下是根据最终实现整理的复现需求，并非完整原始聊天记录。设备地址和 ID 请只填写在本地配置，不写进提示词或提交到仓库。

> 使用本仓库固定版本的 Zectrix 官方本地推送 SDK，开发 NOTE4 400×300 天气应用。先读 README、vendor/zectrix-local-push-sdk/docs/API.md 和协议，保留官方固件。Python 管理天气数据、缓存、页面、控制页；Rust 桥保持一个 SDK 会话和一个事件消费者。应用从 config.json 读取城市坐标、明确指定的 IPv4 和预期设备 ID，连接前只读 INFO 核验身份、完整画布与空闲状态；不选择其他设备、不抢占、不自动重连。提供天气首页和天气总览两页：写实银灰云图、透明细框，大温度、体感、湿度、天气与低高温；总览包含此刻、未来六个完整小时与七天预报。首页不显示时钟和城市名。顶部显示日期和真实电池，底部显示农历、数据时间和来源。统一写实天气图集，不混入卡通图。图像输出连续灰度 PNG，只在 SDK 内根据设备色板转 Gray16，禁止重复预抖色，不宣称 Gray16 局刷。Open-Meteo 每小时取数，重启复用新鲜缓存；失败标注缓存，超过六小时清空数值；相同图不重发。电池每分钟只缓存，不因此渲染或推图。按键短按在两页间切换；长按下进入总览，长按上回天气。录音期间暂停图片任务，最多一张在途，仅保留最新更新。ResultUnknown 锁定并等待显式重试。退出显式 close。配置和日志留在私人目录，不打包密钥、私人路径、设备 ID、NAS 地址和聊天记录。先做离线测试和预览，再由用户明确操作连接真机；以 SDK 显示完成回执报告状态，区分视觉验收。不要扩展为固件烧录、云端五槽或独立的第二推送端。

## 母版生成提示词（原文）

```text
A single beautifully crafted monochrome partly cloudy weather icon, isolated on fully transparent background. A luminous silver-white billowing cumulus cloud with sculptural soft 3D volume, smooth layered shadows from charcoal gray underneath to brilliant white on top, a pale circular sun peeking behind upper left of the cloud. Refined realistic editorial weather illustration designed for a high resolution grayscale e-paper clock, broad clean tonal regions, readable silhouette, no noise, no halftone or stippled texture, no text, no border, no background, no colored pixels, no extra icons, no user interface. Cloud centered, fills most of frame, generous padding around shape.
```

## 同风格天气变体完整提示词

公共风格、夜间多云的完整编辑提示词见 [图集 README](../assets/weather-realistic-v1/README.md)。其余八种变体的完整输入是「公共提示词 + 对应 condition」，每种 condition 原文见 [build-inputs.json](../assets/weather-realistic-v1/build-inputs.json)。日间多云直接复用母版。

使用母版 `assets/partly-cloudy.png` 作为参考图，输出带透明 alpha 的单张 PNG；不要生成整张 UI，不加文字、边框、黑色底或抖色。将结果合成到 400×300 灰度画布后，由官方 SDK 转为 Gray16。

生成图像具有随机性，复用提示词不保证逐像素相同；可直接使用仓库内已经生成的 PNG。manifest 中保留 SHA-256 校验。夜间月亮是示意，不代表实时月相。
