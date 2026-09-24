"""Build a captioned, silent 3-minute walkthrough from verified screenshots.

Optional presentation tooling only: pip install pillow imageio-ffmpeg
The project runtime does not depend on these packages.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
OUTPUT = HERE / "demo-original.mp4"
WIDTH, HEIGHT, FPS = 1280, 720, 2
BG = (21, 43, 59)
TEAL = (48, 187, 170)
PALE = (234, 244, 242)
WHITE = (250, 253, 252)
MUTED = (176, 197, 206)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError("需要本机安装微软雅黑或 Noto Sans CJK 字体")


SMALL = font(17)
CAPTION = font(27)
TITLE = font(33, bold=True)
BIG = font(52, bold=True)
MID = font(28, bold=True)


SLIDES = [
    {
        "seconds": 8,
        "title": "商析：从变化到核查任务",
        "caption": "Olist 巴西多卖家平台历史样本；非商业作品集，无声截图演示。",
        "kind": "title",
    },
    {
        "seconds": 17,
        "title": "01 经营概览",
        "caption": "全量原始订单 99,441 笔；2018 年 7 月已交付 6,159 单，商品金额 R$ 867,953.46。",
        "image": DOCS / "core" / "overview-desktop.png",
        "y": (120, 210),
    },
    {
        "seconds": 12,
        "title": "02 统一指标口径",
        "caption": "最终已交付、按下单日归属、商品金额不含运费；订单、品类和地区共用筛选。",
        "image": DOCS / "core" / "overview-desktop.png",
        "y": (475, 700),
    },
    {
        "seconds": 14,
        "title": "03 商品分析",
        "caption": "商品排名来自观察期成交；没有库存与上架数据，因此不把低销量写成库存滞销。",
        "image": DOCS / "core" / "products-desktop.png",
        "y": (450, 700),
    },
    {
        "seconds": 12,
        "title": "04 履约与评价",
        "caption": "缺送达日期仍计入销售，却不进入延迟率分母；缺评价不会被记作零分。",
        "image": DOCS / "core" / "products-desktop.png",
        "y": (1150, 1370),
    },
    {
        "seconds": 18,
        "title": "05 客户分析：拉长观察窗",
        "caption": "2018 年 2–7 月购买客户 38,560 位，窗口复购 747 位，复购率约 1.94%。",
        "image": HERE / "customer-long-window.png",
        "y": (420, 500),
    },
    {
        "seconds": 14,
        "title": "06 RFM：真正展示远期分组",
        "caption": "同一长窗中 32,460 位购买客户距窗口末次购买＞30 天；八组互斥且覆盖窗口购买者。",
        "image": HERE / "customer-long-window.png",
        "y": (1020, 1230),
    },
    {
        "seconds": 18,
        "title": "07 七月销售变化案例",
        "caption": "7 月总商品金额较 6 月增加 1.39%，但日均商品金额下降 1.88%；不能只看月总额。",
        "image": DOCS / "reports" / "desktop.png",
        "y": (440, 640),
    },
    {
        "seconds": 11,
        "title": "08 贡献拆解",
        "caption": "先拆订单量与客单价，再看品类和客户州贡献；算术分解不等于经营动作的因果效果。",
        "image": DOCS / "reports" / "desktop.png",
        "y": (900, 1100),
    },
    {
        "seconds": 22,
        "title": "09 把销售发现转成核查任务",
        "caption": "2–7 月金额差额 R$ 1,063,516.76；事实、证据、待验证假设和验证指标分开呈现。",
        "image": HERE / "investigation-workflow.png",
        "y": (800, 950),
    },
    {
        "seconds": 17,
        "title": "10 履约核查：相关不等于因果",
        "caption": "长窗延迟组有评分 3,213 单、均分 2.181；按期组 35,906 单、均分 4.294。",
        "image": HERE / "investigation-workflow.png",
        "y": (1550, 1750),
    },
    {
        "seconds": 11,
        "title": "11 数据到页面的核对链",
        "caption": "事务导入可重跑，金额与订单数经过原始 CSV、MySQL、接口与页面独立核对。",
        "kind": "architecture",
    },
    {
        "seconds": 6,
        "title": "无声历史截图演示",
        "caption": "Olist · CC BY-NC-SA 4.0。核查记录仅本机暂存，尚无商家采纳或收益证据。",
        "kind": "end",
    },
]


def wrap(draw: ImageDraw.ImageDraw, message: str, face: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    rows, current = [], ""
    for char in message:
        candidate = current + char
        if current and draw.textlength(candidate, font=face) > max_width:
            rows.append(current)
            current = char
        else:
            current = candidate
    if current:
        rows.append(current)
    return rows


def screenshot(draw: ImageDraw.ImageDraw, canvas: Image.Image, slide: dict, progress: float) -> None:
    source = Image.open(slide["image"]).convert("RGB")
    x = 230
    source_width = min(1200, source.width - x)
    target_x, target_y, target_w, target_h = 48, 95, 1184, 470
    source_height = round(source_width * target_h / target_w)
    first, last = slide["y"]
    top = max(0, min(round(first + (last - first) * progress), source.height - source_height))
    crop = source.crop((x, top, x + source_width, top + source_height))
    crop = crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
    canvas.paste(crop, (target_x, target_y))
    draw.rounded_rectangle((target_x - 1, target_y - 1, target_x + target_w + 1, target_y + target_h + 1), radius=7, outline=TEAL, width=2)


def architecture(draw: ImageDraw.ImageDraw) -> None:
    boxes = [
        (45, "Olist CSV"),
        (288, "Pandas 校验"),
        (531, "MySQL 分析表"),
        (774, "FastAPI"),
        (1017, "Vue 四页"),
    ]
    for left, label in boxes:
        draw.rounded_rectangle((left, 240, left + 200, 385), radius=18, fill=(31, 68, 82), outline=TEAL, width=3)
        w = draw.textlength(label, font=MID)
        draw.text((left + (200 - w) / 2, 291), label, fill=WHITE, font=MID)
    for idx in range(4):
        x0 = boxes[idx][0] + 207
        x1 = boxes[idx + 1][0] - 8
        draw.line((x0, 312, x1, 312), fill=TEAL, width=4)
        draw.polygon(((x1, 312), (x1 - 9, 305), (x1 - 9, 319)), fill=TEAL)
    draw.text((87, 445), "先处理一对多关系，再做聚合；避免商品 × 支付 × 评价放大金额。", fill=PALE, font=CAPTION)


def frame(slide: dict, within: float, elapsed: float) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((45, 23, 105, 70), radius=11, fill=TEAL)
    draw.text((61, 29), "商析", fill=BG, font=SMALL)
    draw.text((126, 26), slide["title"], fill=WHITE, font=TITLE)
    draw.text((1090, 39), "无声字幕版", fill=MUTED, font=SMALL)

    if "image" in slide:
        screenshot(draw, canvas, slide, within)
    elif slide["kind"] == "architecture":
        architecture(draw)
    else:
        eyebrow = "COMMERCE INSIGHT · HISTORICAL ANALYSIS"
        draw.text((66, 179), eyebrow, fill=TEAL, font=SMALL)
        lines = wrap(draw, slide["title"], BIG, 1120)
        for idx, line in enumerate(lines):
            draw.text((66, 240 + idx * 70), line, fill=WHITE, font=BIG)
        draw.rounded_rectangle((66, 414, 1060, 418), radius=2, fill=TEAL)
        if slide["kind"] == "end":
            draw.text((67, 448), "本片由已验收页面截图制作，不是在线站点或实时录屏。", fill=PALE, font=CAPTION)

    draw.rounded_rectangle((46, 580, 1234, 675), radius=15, fill=(32, 67, 76))
    lines = wrap(draw, slide["caption"], CAPTION, 1130)
    y = 595 + (1 - min(len(lines), 2)) * 14
    for line in lines[:2]:
        draw.text((69, y), line, fill=WHITE, font=CAPTION)
        y += 35
    draw.text((46, 682), "Olist · CC BY-NC-SA 4.0 · 无声历史截图演示", fill=MUTED, font=SMALL)
    draw.text((1097, 682), f"{math.floor(elapsed):02d} / 180 秒", fill=MUTED, font=SMALL)
    draw.rectangle((0, 714, round(WIDTH * min(elapsed / 180, 1)), 719), fill=TEAL)
    return canvas


def main() -> None:
    duration = sum(slide["seconds"] for slide in SLIDES)
    if duration != 180:
        raise RuntimeError(f"演示时长必须为 180 秒，当前为 {duration}")
    for slide in SLIDES:
        if "image" in slide and not slide["image"].is_file():
            raise FileNotFoundError(slide["image"])

    command = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
        "-r", str(FPS), "-i", "pipe:0", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUTPUT),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        elapsed_frames = 0
        for slide in SLIDES:
            count = slide["seconds"] * FPS
            for index in range(count):
                current = elapsed_frames / FPS
                picture = frame(slide, index / max(1, count - 1), current)
                assert process.stdin is not None
                process.stdin.write(picture.tobytes())
                elapsed_frames += 1
        assert process.stdin is not None
        process.stdin.close()
        result = process.wait()
        if result != 0:
            raise RuntimeError(f"FFmpeg failed: {result}")
        print(f"{OUTPUT} | {duration}s | {OUTPUT.stat().st_size / 1024 / 1024:.2f} MiB")
    finally:
        if process.poll() is None:
            process.terminate()


if __name__ == "__main__":
    main()
