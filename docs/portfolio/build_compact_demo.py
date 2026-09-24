"""Build the small, directly playable GitHub edition of the 3-minute demo.

Optional presentation dependencies: pillow and imageio-ffmpeg. The full-size
moving edition can be generated separately with build_demo_video.py.
"""

import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

from build_demo_video import SLIDES, frame


OUTPUT = Path(__file__).resolve().parent / 'demo-screenshots.mp4'


def main():
    seconds = sum(slide['seconds'] for slide in SLIDES)
    if seconds != 180:
        raise ValueError(f'Expected a 180-second storyboard, got {seconds}')
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '960x540', '-r', '1',
               '-i', 'pipe:0', '-c:v', 'libx264', '-preset', 'slow', '-crf', '44',
               '-tune', 'stillimage', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(OUTPUT)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    elapsed = 0
    try:
        for slide in SLIDES:
            # One stable frame per scene keeps captions readable at small size.
            picture = frame(slide, 0.5, elapsed + slide['seconds'] // 2)
            data = picture.resize((960, 540), Image.Resampling.LANCZOS).tobytes()
            for _ in range(slide['seconds']):
                process.stdin.write(data)
            elapsed += slide['seconds']
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('FFmpeg did not complete the public video')
    finally:
        if process.poll() is None:
            process.terminate()
    print(f'{OUTPUT} | {elapsed}s | {OUTPUT.stat().st_size} bytes')


if __name__ == '__main__':
    main()
