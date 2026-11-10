import base64
import io

from PIL import Image


def encode(img, max_edge=1568, quality=80):
    img = img.convert("RGB")
    longest = max(img.size)
    if longest > max_edge:
        scale = max_edge / float(longest)
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def grab():
    from PIL import ImageGrab
    return encode(ImageGrab.grab())
