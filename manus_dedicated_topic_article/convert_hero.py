from PIL import Image
from pathlib import Path

src = Path('/home/ubuntu/projects/dedicated-topic-article-090d06d7/20260806_AMR_AGV_Post9_hero.jpg')
tmp = src.with_suffix('.converted.jpg')
with Image.open(src) as im:
    rgb = im.convert('RGB')
    rgb.save(tmp, format='JPEG', quality=95, optimize=True)
tmp.replace(src)
print(src, Image.open(src).format, Image.open(src).size)
