import hashlib
import subprocess
import time
import os
from PIL import Image

# Function to compute MD5 hash of a file
def md5sum(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

class timer():
    def __init__(self):
        self.t0 = time.perf_counter()
        self.t0_init = self.t0
    
    def elapsed(self):
        return time.perf_counter() - self.t0
    
    def reset(self):
        t1 = time.perf_counter()
        elapsed = t1 - self.t0
        self.t0 = t1
        return elapsed
    
    def since_init(self):
        return self.t0 - self.t0_init

# Encoder
def png_to_video(image_dir, output_path, fps=24):
    command = [
        "ffmpeg",
        "-framerate", str(fps),
        "-i", os.path.join(image_dir, "img_%d.png"),  # 使用通配符匹配所有 PNG 文件
        "-c:v", "libx264",  # 使用 h264 编码
        "-pix_fmt", "yuv420p",  # 设置像素格式，避免兼容性问题
        output_path
    ]

    try:
        subprocess.run(command, check=True)
        print(f"视频已成功创建：{output_path}")
    except subprocess.CalledProcessError as e:
        print(f"创建视频时出错：{e}")
    except FileNotFoundError:
        print("错误：FFmpeg 未找到。请确保已安装 FFmpeg 并将其添加到系统路径。")
    
def parse_region_mon(region_split):
    mon_id = 1
    if len(region_split) >= 1 and region_split[0]:
        mon_id = int(region_split[0])
    return mon_id

def parse_region(region_split, mon_width, mon_height, fit_pixel=0):
    def get_size(v):
        value_map = { 'd': min(mon_width, mon_height)*3//4, 'w': mon_width, 'h': mon_height, 'f': fit_pixel }
        return value_map[v] if v in value_map else int(v)
    
    width = height = 'f'
    if len(region_split) >= 2 and region_split[0] and region_split[1]:
        width, height = region_split[0], region_split[1]
    width, height = get_size(width), get_size(height)
    
    o1 = o2 = 'c'
    if len(region_split) >= 4 and region_split[2] and region_split[3]:
        o1, o2 = region_split[2], region_split[3]

    def get_offset(o, screen_size, window_size):
        if o.startswith('-'):
            return screen_size - window_size + int(o)
        elif o=='c':
            return (screen_size - window_size) // 2
        else:
            return int(o)
    x, y = get_offset(o1, mon_width, width), get_offset(o2, mon_height, height)
    return width, height, x, y
