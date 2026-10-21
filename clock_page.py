"""Shared canvas, timezone, font discovery and lunar date helpers."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
TZ = ZoneInfo('Asia/Shanghai')
SCALE = 4


def lunar_label(now: datetime) -> str:
    try:
        from lunardate import LunarDate
        lunar = LunarDate.from_solar_date(now.year, now.month, now.day)
        months = ['正','二','三','四','五','六','七','八','九','十','冬','腊']
        days = ['初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
                '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
                '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十']
        return f'农历 {"闰" if lunar.is_leap_month else ""}{months[lunar.month-1]}月{days[lunar.day-1]}'
    except (ImportError, ValueError):
        return '农历暂不可用'


def font_path(kind: str) -> str:
    custom = os.environ.get('NOTE4_CLOCK_DIGIT_FONT' if kind == 'digits' else 'NOTE4_CLOCK_TEXT_FONT')
    candidates = [custom] if custom else []
    if kind == 'digits':
        candidates += ['/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf',
                       '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    else:
        candidates += ['/System/Library/Fonts/PingFang.ttc',
                       '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                       '/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError(f'请配置 {kind} 字体路径')


class Canvas:
    def __init__(self):
        self.im = Image.new('L', (400*SCALE,300*SCALE),255)
        self.d = ImageDraw.Draw(self.im)
        self.boxes = []

    def text(self, text, x, y, size, fill=15, digits=False, anchor='left'):
        f = ImageFont.truetype(font_path('digits' if digits else 'text'),round(size*SCALE))
        b = self.d.textbbox((0,0),text,font=f)
        w,h = b[2]-b[0],b[3]-b[1]
        px = x*SCALE-(w if anchor=='right' else w/2 if anchor=='center' else 0)
        py = y*SCALE
        if px<0 or px+w>400*SCALE or py<0 or py+h>300*SCALE:
            raise ValueError(f'文字越界：{text}')
        self.boxes.append((text,(px/SCALE,py/SCALE,(px+w)/SCALE,(py+h)/SCALE)))
        self.d.text((round(px-b[0]),round(py-b[1])),text,font=f,fill=fill)

    def line(self, points, fill=0, width=1):
        self.d.line([(round(x*SCALE),round(y*SCALE)) for x,y in points],fill=fill,width=round(width*SCALE))

    def rounded(self, box, radius, fill, outline=None, width=1):
        self.d.rounded_rectangle(tuple(round(v*SCALE) for v in box),radius=round(radius*SCALE),
                                 fill=fill,outline=outline,width=round(width*SCALE))

    def ellipse(self, box, fill):
        self.d.ellipse(tuple(round(v*SCALE) for v in box),fill=fill)

