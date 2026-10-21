# Original B weather system v1

统一母版为用户选中的原B写实 `../partly-cloudy.png`，`original.png` 是逐字节原样复制，不改造原云形。其余9款均使用内置 imagegen，以同一母版作为参考逐款生成，不使用 CLI/API 模型脚本，不再混入 Meteocons。

## 设计约束

- 单色银白/石墨灰、连续色调、真实体积和细节；固定柔和白光与云层材质。
- 共用自然云体，以天体/降水/云层形态表达语义；禁用卡通轮廓、玩具云、描边月亮、星星装饰、玻璃效果。
- 1536×1024 RGBA透明原图；显示前由业务渲染器合成400×300连续灰度PNG，SDK按真实色板转Gray16。素材不预抖色。
- 首页大图、总览当前天气、七日小图共用同一素材注册表。夜间多云的大图有额外顶部安全留白，避免月亮与日期重叠；小图保持标准缩放。
- 原B日间多云保持既有版式；强弱雨雪、冰雹等细分由真实天气文字说明，图形表达基础天气家族，不宣称每个WMO代码都有独立图形。
- 月亮为夜间天气示意，不是基于实际天文月相计算。

## 注册表

`manifest.json` 包含版本、资产文件、SHA-256、WMO代码到昼夜资产的映射和特殊大图安全框。未知天气没有猜测图，显示文字。发布包不包含停用的旧图集。

基础语义：日晴、夜晴、日多云、夜多云、阴、雨、雪、雾、冻雨、雷雨，共10款。标题“原B”为基准素材。`contact-sheet.png` 是本地连续灰度素材对照，不是实屏色板模拟。

## 生成记录与提示词

内置 imagegen 生成；参考/编辑目标统一为原B资产。`build-inputs.json` 记录每项条件提示词。原文件复制入此目录，工程不依赖Codex生成缓存。

所有8项晴/阴/降水生成使用以下完整公共提示词，后接 build-inputs.json 对应项的 condition：

> Use case: lighting-weather. Reference image: the established master cloud asset for a 16-gray e-paper weather application. Create ONE companion weather cutout in precisely this photorealistic monochrome silver-gray style, same soft directional white light, realistic detailed volumetric textures and broad smooth shadows. Consistent refined natural realism, never cartoon, never vector/outline, never toy-like rounded shapes. Generous transparent margin, subject centered and filling most of a 3:2 frame. Genuinely transparent clean alpha background, including any gaps between precipitation. No black/gray rectangle, no landscape, text, labels, border, stars, UI, noise or dithering. Preserve original cloud's shape and texture wherever clouds are requested. Condition:

夜间多云使用以下完整提示词：

> Use case: lighting-weather. Edit target: the supplied partly-cloudy weather asset, the established master asset for a grayscale e-paper weather application. Create its NIGHT PARTLY CLOUDY companion. Preserve the SAME detailed natural billowing cumulus cloud silhouette, position, proportions, fine volumetric texture, broad gray shadow masses and silver-white highlights. Change only the celestial object behind upper left: replace the sun with a natural photographic gibbous moon with subtle lunar craters, its lower portion naturally occluded by the unchanged clouds. The moon must be recognizable as moon, with no symbolic crescent outline, no rays, no drawn stars. Keep a predominantly white/silver-gray cloud with readable darker undersides, not a black night scene. Same camera, framing, scale, white light direction, sophisticated photorealistic weather cutout style as supplied asset, not cartoon, not vector, not rounded toy cloud. GENUINELY TRANSPARENT BACKGROUND AND CLEAN ALPHA outside the cloud and moon. No black/gray rectangular background, no square glow backdrop, no scene, no text, no border, no UI, no noise or halftone/dither. Output one single matching night partly cloudy asset.

生成结果做一次本地形态/透明度检查、整套对照与400×300主屏/总览预览；用户新一轮实屏风格验收另计，不把生成完成等同于全部实屏验收。
