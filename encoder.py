import argparse
import os
import subprocess
import multiprocessing
import time
import tqdm
import base64
import io
import struct
import math
import qrcode.util
import qrcode
from PIL import Image, ImageTk
import tkinter as tk
from util import timer, png_to_video


def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes."
    )
    parser.add_argument(
        "-i", "--input", required=True, help="The path to the file to convert."
    )
    parser.add_argument(
        "-m", "--mode",
        default="screen", choices=['dir', 'video', 'screen'],
        help="output to dir/video/screen(display in window)"
    )
    parser.add_argument(
        "-o", "--output-dir", default="./out", help="dir/video: output image/video directory"
    )
    parser.add_argument(
        "-r", "--region", default="80:80:-0:-0",
        help="screen: display region, width:height:offset_left:offset_top. "
            "widht/height 'd' means default 3/4 screen size. Offset startwith '-' means from right/bottom, 'c' means center"
    )
    parser.add_argument(
        "-n", "--nproc", type=int, default=-1, help="multiprocess encoding"
    )
    parser.add_argument(
        "-Q", "--qr-version", type=int, default=40, help="QRcode version"
    )
    parser.add_argument(
        "-F", "--fps", type=int, default=10, help="output screen display image fps"
    )
    
    return parser

class File2Image:
    def __init__(self, nproc=1, qr_version=40):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc
        self.qr_version = qr_version
        self.qr_boxsize = 4
        self.correction = qrcode.constants.ERROR_CORRECT_L

    def encode_qrcode(self, data_):
        # qrcode 实际编码二进制数据时，实际对数据有要求，需要满足ISO/IEC 8859-1
        # 导致编码和解码后，得到错误数据，解决办法为使用base32编码（损耗6.25%）
        # https://github.com/tplooker/binary-qrcode-tests/tree/master
        data = base64.b32encode(data_)
        qr = qrcode.QRCode(
            version=self.qr_version,
            error_correction=self.correction,
            box_size=self.qr_boxsize,   # in pixels
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        # 将图像保存为字节流
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def process_chunk(self, i, chunk_data, result_queue):
        img_bytes = self.encode_qrcode(chunk_data)
        # print(f'pid {os.getpid()}: chunk {i}')
        result_queue.put(img_bytes)
    
    def get_chunk_size(self):
        qr_maxbytes = qrcode.util.BIT_LIMIT_TABLE[self.correction][self.qr_version]//8
        base32_valid = int(qr_maxbytes/1.0625/1.1)  # 理论计算结果超出限制，除以 1.1 简单修正一下
        print(f"QR code version {self.qr_version} corr: L max bytes: {qr_maxbytes} base32_valid: {base32_valid}")
        return base32_valid - 4  # 4 bytes for header

    def convert(self, file_path, output_mode='screen', output_dir="", fps=10, region=''):
        with open(file_path, "rb") as f:
            file_data = f.read()
        print(f"File size: {len(file_data)} bytes.")

        chunk_size = self.get_chunk_size()
        self.num_chunks = math.ceil(len(file_data) / chunk_size)
        
        manager = multiprocessing.Manager()
        result_queue = manager.Queue()
        pool = multiprocessing.Pool(processes=self.nproc)

        # multiprocessing encoding
        for i in range(self.num_chunks):
            header = struct.pack("HH", i, self.num_chunks)
            chunk_data = header + file_data[i * chunk_size : (i + 1) * chunk_size]
            pool.apply_async(self.process_chunk, (i, chunk_data, result_queue))
        pool.close()

        if output_mode == 'dir':
            self.output_file(result_queue, output_dir)
        elif output_mode == 'video':
            self.output_video(result_queue, output_dir, fps=fps)
        elif output_mode == 'screen':
            self.output_screen(result_queue, fps=fps, region=region)
        else:
            raise ValueError(f"Invalid output mode: {output_mode}")

    def output_file(self, result_queue, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
        for i in tqdm.tqdm(range(self.num_chunks)):
            img_bytes = result_queue.get()

            with open(f"{output_dir}/img_{i}.png", "wb") as f:
                f.write(img_bytes)
        print(f"Output {self.num_chunks} images to {output_dir}.")

    def output_video(self, result_queue, output_dir, fps=10):
        self.output_file(result_queue, output_dir)
        
        video_path = f"{output_dir}/output.mp4"
        png_to_video(output_dir, video_path, fps=fps)
        print(f"Output to {video_path}.")

    def output_screen(self, result_queue, fps=1, region=''):
        region_split = region.split(':')
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        width = height = min(screen_width, screen_height) * 3 // 4
        if len(region_split) >= 2 and region_split[0] and region_split[1]:
            if region_split[0] != 'd':  # default
                width = int(region_split[0])
                height = int(region_split[1])
        
        o1 = o2 = 'c'
        if len(region_split) >= 2 and region_split[2] and region_split[3]:
            o1 = region_split[2]
            o2 = region_split[3]
        def get_offset(o, screen_size, window_size):
            if o.startswith('-'):
                return screen_size - window_size + int(o)
            elif o=='c':
                return (screen_size - window_size) // 2
            else:
                return int(o)
            
        root.overrideredirect(True) # no window border (also no close button)
        root.geometry(f'{width}x{height}+{get_offset(o1, screen_width, width)}+{get_offset(o2, screen_height, height)}')
        root.attributes('-topmost', True)
        label = tk.Label(root, borderwidth=0)   # no inner padding
        label.pack(expand=True, fill=tk.BOTH)
        
        def quit_app(event):
            if event and event.char in ['q', 'Q', ' '] or\
                (event.keysym == 'c' and event.state & 0x4):  # ctrl+c
                root.destroy()
        root.bind('<Key>', quit_app)
        
        def update_image(label, img):
            label.img = img
            label.configure(image=img)
            label.update()
        
        img_tk_list = []
        tim = timer()
        for i in tqdm.tqdm(range(self.num_chunks)):
            img_bytes = result_queue.get()
            img = Image.open(io.BytesIO(img_bytes))
            
            # resize image, otherwise label window will be too big
            img_resized = img.resize((width, height), Image.LANCZOS)
        
            img_tk = ImageTk.PhotoImage(img_resized)
            img_tk_list.append(img_tk)
            e = tim.reset()
            if e < 1 / fps:
                time.sleep(1 / fps - e)
            update_image(label, img_tk)
        
        def update_image_timer(label, img_tk_list, index=0):
            label.configure(image=img_tk_list[index])
            label.img = img_tk_list[index]
            next_index = (index + 1) % len(img_tk_list)
            root.after(int(1000 / fps), update_image_timer, label, img_tk_list, next_index)
        
        # display repeatly
        update_image_timer(label, img_tk_list)
        try:
            root.mainloop()
        except KeyboardInterrupt:
            root.destroy()
    
if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    f2i = File2Image(args.nproc, args.qr_version)
    f2i.convert(args.input, output_mode=args.mode,
                output_dir=args.output_dir, region=args.region, fps=args.fps)
