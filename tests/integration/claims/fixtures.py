import base64
import hashlib
from pathlib import Path
from urllib.request import urlopen


VIDEO_PATH = Path(__file__).parent / 'files' / 'ForBiggerEscapes.mp4'
VIDEO_URL = (
    'https://android.googlesource.com/platform/cts/+/'
    '55238dc2de183685bc6f98727811b7a802ea5731/'
    'tests/media/res/raw/forbiggerescapes.mp4?format=TEXT'
)
VIDEO_SHA384 = (
    '5f6811c83c1616df06f10bf5309ca61edb5ff949a9c1212ce784602'
    'd837bfdfc1c3db1e0580ef7bd1dadde41d8acf315'
)


def prepare_video():
    # The original Google sample bucket no longer permits public downloads.
    # Android CTS archived the same file; Gitiles serves its bytes as base64.
    if VIDEO_PATH.exists():
        data = VIDEO_PATH.read_bytes()
    else:
        with urlopen(VIDEO_URL, timeout=60) as response:
            data = base64.b64decode(response.read(), validate=True)
    if hashlib.sha384(data).hexdigest() != VIDEO_SHA384:
        raise ValueError(f'Unexpected test video checksum: {VIDEO_PATH}')
    if not VIDEO_PATH.exists():
        VIDEO_PATH.parent.mkdir(parents=True, exist_ok=True)
        VIDEO_PATH.write_bytes(data)


if __name__ == '__main__':
    prepare_video()
