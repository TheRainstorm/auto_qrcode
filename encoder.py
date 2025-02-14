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
import numpy as np
import tkinter as tk
from util import *


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
        "-r", "--region", default="",
        help="screen: display region, width:height:offset_left:offset_top. "
            "widht/height: int|d|w|h|f, 'd' means default 3/4*min(w,h). f: QR code fit pixel. "
            "Offset startwith '-' means from right/bottom, 'c' means center"
    )
    parser.add_argument(
        "-n", "--nproc", type=int, default=-1, help="multiprocess encoding"
    )
    parser.add_argument(
        "-Q", "--qr-version", type=int, default=40, help="QRcode version"
    )
    parser.add_argument(
        "-f", "--qr-fit-factor", type=float, default=1.5, help="QRcode fit pixel=(25+4*version+2(border))*fit_factor"
    )
    parser.add_argument(
        "-F", "--fps", type=int, default=10, help="output screen display image fps"
    )
    parser.add_argument(
        "-S", "--sleep", action='store_true', help="sleep 5 seconds to prepare"
    )
    
    return parser

class File2Image:
    def __init__(self, nproc=1, qr_version=40, qr_fit_factor=1.5):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc
        self.qr_version = qr_version
        self.qr_boxsize = 1
        self.qr_border = 1
        self.correction = qrcode.constants.ERROR_CORRECT_L
        self.qr_fit_factor = qr_fit_factor

    def encode_qrcode(self, data_):
        # qrcode 实际编码二进制数据时，实际对数据有要求，需要满足ISO/IEC 8859-1
        # 导致编码和解码后，得到错误数据，解决办法为使用base32编码（损耗6.25%）
        # https://github.com/tplooker/binary-qrcode-tests/tree/master
        data = base64.b32encode(data_)
        qr = qrcode.QRCode(
            version=self.qr_version,
            error_correction=self.correction,
            box_size=self.qr_boxsize,   # in pixels
            border=self.qr_border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        return np.array(img)

    def process_chunk(self, i, chunk_data, result_queue):
        img = self.encode_qrcode(chunk_data)
        # print(f'pid {os.getpid()}: chunk {i}')
        result_queue.put(img)
    
    def get_chunk_size(self):
        qr_maxbytes = qrcode.util.BIT_LIMIT_TABLE[self.correction][self.qr_version]//8
        base32_valid = int(qr_maxbytes/1.0625/1.1)  # 理论计算结果超出限制，除以 1.1 简单修正一下
        print(f"QR code version {self.qr_version} corr: L max bytes: {qr_maxbytes} base32_valid: {base32_valid}")
        return base32_valid - 8  # 8 bytes for header

    def convert(self, file_path, output_mode='screen', output_dir="", fps=10, region=''):
        with open(file_path, "rb") as f:
            file_data = f.read()
        print(f"File size: {len(file_data)} bytes.")

        chunk_size = self.get_chunk_size()
        self.num_chunks = math.ceil(len(file_data) / chunk_size)
        print(f"Chunk size: {chunk_size} bytes, num_chunks: {self.num_chunks}")
        
        manager = multiprocessing.Manager()
        result_queue = manager.Queue()
        pool = multiprocessing.Pool(processes=self.nproc)

        # multiprocessing encoding
        for i in range(self.num_chunks):
            header = struct.pack("II", i, self.num_chunks)
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
            image_ndarry = result_queue.get()
            img = Image.fromarray(image_ndarry)
            img.save(f"{output_dir}/img_{i}.png")
        print(f"Output {self.num_chunks} images to {output_dir}.")

    def output_video(self, result_queue, output_dir, fps=10):
        self.output_file(result_queue, output_dir)
        
        video_path = f"{output_dir}/output.mp4"
        png_to_video(output_dir, video_path, fps=fps)
        print(f"Output to {video_path}.")

    def output_screen(self, result_queue, fps=1, region=''):
        root = tk.Tk()
        fit_pixel = int((self.qr_version * 4 + 21 + 2*self.qr_border) * self.qr_fit_factor) # default times 1.5, version 40 -> 275x275
        width, height, x, y = parse_region(region.split(':'), root.winfo_screenwidth(), root.winfo_screenheight(), fit_pixel=fit_pixel)
        root.overrideredirect(True) # no window border (also no close button)
        root.geometry(f'{width}x{height}+{x}+{y}')
        root.attributes('-topmost', True)
        label = tk.Label(root, borderwidth=0)   # no inner padding
        label.pack(expand=True, fill=tk.BOTH)
        print(f"Display in window[{root.winfo_screenwidth()}x{root.winfo_screenheight()}] {width}x{height}+{x}+{y} fps {fps}")
        
        def quit_app(event):
            if event and event.char in ['q', 'Q', ' '] or\
                (event.keysym == 'c' and event.state & 0x4):  # ctrl+c
                root.destroy()
        root.bind('<Key>', quit_app)
        
        def update_image(label, img):
            label.configure(image=img)
            label.update()
        
        img_tk_list = []
        tim = timer()
        for i in tqdm.tqdm(range(self.num_chunks)):
            tim.reset()
            image_ndarry = result_queue.get()
            img = Image.fromarray(image_ndarry)
            
            # resize image, otherwise label window will be too big
            img_resized = img.resize((width, height), Image.LANCZOS)
        
            img_tk = ImageTk.PhotoImage(img_resized)
            img_tk_list.append(img_tk)
            e = tim.elapsed()
            if e < 1 / fps:
                time.sleep(1 / fps - e)
            update_image(label, img_tk)
        
        def update_image_timer(label, img_tk_list, index=0):
            print(f"current idx: {index}\r", end='')
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
    if args.sleep:
        print("Sleep 5 seconds to prepare...")
        time.sleep(5)
    f2i = File2Image(nproc=args.nproc, qr_version=args.qr_version, qr_fit_factor=args.qr_fit_factor)
    f2i.convert(args.input, output_mode=args.mode,
                output_dir=args.output_dir, region=args.region, fps=args.fps)
