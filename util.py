import subprocess
import time
import os
from PIL import Image

class timer():
    def __init__(self):
        self.t0 = time.time()
        self.t0_init = self.t0
    
    def elapsed(self):
        return time.time() - self.t0
    
    def reset(self):
        t1 = time.time()
        elapsed = t1 - self.t0
        self.t0 = t1
        return elapsed
    
    def since_init(self):
        return self.t0 - self.t0_init

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

import mss
def setup_mss(region):
    sct = mss.mss()
    region_split = region.split(':')
    mon_id = 1
    if len(region_split) >= 1 and region_split[0]:
        mon_id = int(region_split[0])
    mon = sct.monitors[mon_id]

    width, height = mon["width"], mon["height"]
    if len(region_split) >= 3 and region_split[1] and region_split[2]:
        width = int(region_split[1])
        height = int(region_split[2])
    
    offset_t = offset_l = 0
    if len(region_split) >= 5 and region_split[3] and region_split[4]:
        offset_t = int(region_split[3])
        offset_l = int(region_split[4])
    
    # The screen part to capture
    monitor = {
        "top": mon["top"] + offset_t,
        "left": mon["left"] + offset_l,
        "width": width,
        "height": height,
        "mon": mon_id,
    }
    print(f"Capture region: {monitor}")
    return sct, monitor
    
# https://stackoverflow.com/a/79254174/9933066
import ctypes, win32con, win32gui
from ctypes import windll, wintypes
from struct import pack, calcsize
import win32gui
user32,gdi32 = windll.user32,windll.gdi32
PW_RENDERFULLCONTENT = 2

def get_hwnd(win_title):
    hwnd = win32gui.FindWindow(None, win_title)
    return hwnd

def getWindowBMAP(hwnd,returnImage=False):
    # get Window size and crop pos/size
    L,T,R,B = win32gui.GetWindowRect(hwnd); W,H = R-L,B-T
    x,y,w,h = (8,8,W-16,H-16) if user32.IsZoomed(hwnd) else (7,0,W-14,H-7)

    # create dc's and bmp's
    dc = user32.GetWindowDC(hwnd)
    dc1,dc2 = gdi32.CreateCompatibleDC(dc),gdi32.CreateCompatibleDC(dc)
    bmp1,bmp2 = gdi32.CreateCompatibleBitmap(dc,W,H),gdi32.CreateCompatibleBitmap(dc,w,h)

    # render dc1 and dc2 (bmp1 and bmp2) (uncropped and cropped)
    obj1,obj2 = gdi32.SelectObject(dc1,bmp1),gdi32.SelectObject(dc2,bmp2) # select bmp's into dc's
    user32.PrintWindow(hwnd,dc1,PW_RENDERFULLCONTENT) # render window to dc1
    gdi32.BitBlt(dc2,0,0,w,h,dc1,x,y,win32con.SRCCOPY) # copy dc1 (x,y,w,h) to dc2 (0,0,w,h)
    gdi32.SelectObject(dc1,obj1); gdi32.SelectObject(dc2,obj2) # restore dc's default obj's

    if returnImage: # create Image from bmp2
        data = ctypes.create_string_buffer((w*4)*h)
        bmi = ctypes.c_buffer(pack("IiiHHIIiiII",calcsize("IiiHHIIiiII"),w,-h,1,32,0,0,0,0,0,0))
        gdi32.GetDIBits(dc2,bmp2,0,h,ctypes.byref(data),ctypes.byref(bmi),win32con.DIB_RGB_COLORS)
        img = Image.frombuffer('RGB',(w,h),data,'raw','BGRX')

    # clean up
    gdi32.DeleteObject(bmp1) # delete bmp1 (uncropped)
    gdi32.DeleteDC(dc1); gdi32.DeleteDC(dc2) # delete created dc's
    user32.ReleaseDC(hwnd,dc) # release retrieved dc

    return (bmp2,w,h,img) if returnImage else (bmp2,w,h)
def getSnapshot(hwnd): # get Window HBITMAP as Image
    hbmp,w,h,img = getWindowBMAP(hwnd,True); gdi32.DeleteObject(hbmp)
    return img