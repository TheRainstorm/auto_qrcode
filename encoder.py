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
from pixelbar import PixelBar
from util import *
from pywirehair import encoder as wirehair_encoder

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
        "-R", "--region", default="",
        help="screen: display region, width:height:offset_left:offset_top. "
            "widht/height: int|d|w|h|f, 'd' means default 3/4*min(w,h). f: QR code fit pixel. "
            "Offset startwith '-' means from right/bottom, 'c' means center"
    )
    # L2
    parser.add_argument(
        "-M", "--method", default="qrcode", choices=['qrcode', 'pixelbar'], help="encoding method"
    )
    parser.add_argument(
        "-Q", "--qr-version", type=int, default=40, help="QRcode version"
    )
    parser.add_argument(
        "-B", "--qr-box-size", type=float, default=1.5, help="QRcode pixels=(21+4*version+2(border))*box_size, When use screen output, can be float. "
    )
    # L3
    parser.add_argument(
        "-F", "--not-use-fountain-code", dest='use_fountain_code', action='store_false', help="l3 encoding method"
    )
    # misc
    parser.add_argument(
        "-n", "--nproc", type=int, default=-1, help="multiprocess encoding"
    )
    parser.add_argument(
        "-f", "--fps", type=int, default=60, help="output screen display image fps"
    )
    
    return parser

class File2Image:
    def __init__(self, method='qrcode', nproc=1, qr_version=40, qr_box_size=1.5, use_fountain_code=True):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc
        self.method = method
        self.qr_version = qr_version
        self.correction = qrcode.constants.ERROR_CORRECT_L
        self.qr_box_size = qr_box_size
        self.qr_border = 1
        self.pb = PixelBar(self.qr_version, box_size=int(self.qr_box_size), border_size=self.qr_border, pixel_bits=8)
        self.use_fountain_code = use_fountain_code   # 不断产生新的编码块，直到解码成功
        
    def encode_qrcode(self, data_):
        # qrcode 实际编码二进制数据时，实际对数据有要求，需要满足ISO/IEC 8859-1
        # 导致编码和解码后，得到错误数据，解决办法为使用base32编码（损耗6.25%）
        # https://github.com/tplooker/binary-qrcode-tests/tree/master
        data = base64.b32encode(data_)
        qr = qrcode.QRCode(
            version=self.qr_version,
            error_correction=self.correction,
            box_size=int(self.qr_box_size),   # in pixels
            border=self.qr_border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        return img
    
    def encode_pixelbar(self, data):
        return self.pb.encode(data)

    def get_l2_pl_size(self):
        if self.method == 'qrcode':
            qr_maxbytes = qrcode.util.BIT_LIMIT_TABLE[self.correction][self.qr_version]//8
            base32_valid = int(qr_maxbytes/1.0625/1.1)  # 理论计算结果超出限制，除以 1.1 简单修正一下
            print(f"QR code version {self.qr_version} corr: L max bytes: {qr_maxbytes} base32_valid: {base32_valid}")
            return base32_valid
        else:
            return self.pb.max_data_size
        
    def mk_l2_pkt(self, l3_pkt):
        if self.method == 'qrcode':
            img = self.encode_qrcode(l3_pkt)
        else:
            img = self.encode_pixelbar(l3_pkt)
        return np.array(img)

    def get_l3_pl_size(self, l2_pl_size):
        # if self.use_fountain_code:
        return l2_pl_size - 8
    
    def mk_l3_pkt(self, idx, num_chunks, data):
        header = struct.pack("II", idx, num_chunks)
        return header + data
    def mk_l3_pkt_fountain_code(self, idx, file_data_size, data):
        header = struct.pack("II", idx, file_data_size)
        return header + data
        
    def output_l2_pkt_to_queue(self, i, l3_pkt, result_queue):
        # print(f'pid {os.getpid()}: chunk {i}')
        result_queue.put(self.mk_l2_pkt(l3_pkt))
    
    def output_l2_pkt_to_queue_fountain_code(self, pid, nproc, file_data, l3_pl_size, result_queue):
        enc = wirehair_encoder(file_data, l3_pl_size)
        i = pid # interleave 到每个进程
        while True:
            while result_queue.qsize() > 240:
                time.sleep(0.1)
            
            l3_pl = enc.encode(i)
            l3_pkt = self.mk_l3_pkt_fountain_code(i, len(file_data), l3_pl)
            i += nproc
            result_queue.put(self.mk_l2_pkt(l3_pkt))
    
    def convert(self, file_path, output_mode='screen', output_dir="", fps=10, region=''):
        with open(file_path, "rb") as f:
            file_data = f.read()
        print(f"File size: {len(file_data)} bytes.")

        l2_pl_size = self.get_l2_pl_size()
        print(f"L2 payload size: {l2_pl_size} bytes.")
        l3_pl_size = self.get_l3_pl_size(l2_pl_size)
        print(f"L3 payload size: {l3_pl_size} bytes.")
        
        self.num_chunks = math.ceil(len(file_data) / l3_pl_size)
        print(f"num_chunks(l3_pkt_num): {self.num_chunks}")
        
        manager = multiprocessing.Manager()
        result_queue = manager.Queue()

        # 采用生产者和消费者模型，生产者输出 l2_pkt 到队列
        # 主进程输出 l2_pkt 到文件/视频/屏幕
        if self.use_fountain_code:
            producers = []
            # use one process now, TODO: use multiple processes encoding
            for pid in range(self.nproc):
                process = multiprocessing.Process(target=self.output_l2_pkt_to_queue_fountain_code, args=(pid, self.nproc, file_data, l3_pl_size, result_queue))
                process.start()
                producers.append(process)
        else:
            pool = multiprocessing.Pool(processes=self.nproc)
            # multiprocessing encoding
            for i in range(self.num_chunks):
                l3_pkt = self.mk_l3_pkt(i, self.num_chunks, file_data[i * l3_pl_size : (i + 1) * l3_pl_size])
                pool.apply_async(self.output_l2_pkt_to_queue, (i, l3_pkt, result_queue))
            pool.close()

        try:
            if output_mode == 'dir':
                if self.use_fountain_code:
                    print("Fountain code not support dir mode for now.")
                    exit(1)
                self.output_file(result_queue, output_dir)
            elif output_mode == 'video':
                if self.use_fountain_code:
                    print("Fountain code not support video mode for now.")
                    exit(1)
                self.output_video(result_queue, output_dir, fps=fps)
            elif output_mode == 'screen':
                self.output_screen(result_queue, fps=fps, region=region)
            else:
                raise ValueError(f"Invalid output mode: {output_mode}")
        except KeyboardInterrupt:
            print("KeyboardInterrupt")
        finally:
            if self.use_fountain_code:
                for p in producers:
                    p.terminate()  # 确保所有子进程被正确终止

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
        fit_pixel = int((self.qr_version * 4 + 21 + 2*self.qr_border) * self.qr_box_size) # default 1.5, version 40 -> 275x275, can be distinguished
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
        
        if self.use_fountain_code:
            tim = timer()
            i = 0
            progress = tqdm.tqdm(total=self.num_chunks, leave=True, mininterval=0.33, position=0)
            while True:
                tim.reset()
                image_ndarry = result_queue.get()
                img = Image.fromarray(image_ndarry)
                
                # resize image, otherwise label window will be too big
                img_resized = img.resize((width, height), Image.NEAREST)

                progress.update()
                img_tk = ImageTk.PhotoImage(img_resized)
                e = tim.elapsed()
                if e < 1 / fps:
                    time.sleep(1 / fps - e)
                update_image(label, img_tk)
                i += 1
        else:
            img_tk_list = []
            tim = timer()
            for i in tqdm.tqdm(range(self.num_chunks)):
                tim.reset()
                image_ndarry = result_queue.get()
                img = Image.fromarray(image_ndarry)
                
                # resize image, otherwise label window will be too big
                img_resized = img.resize((width, height), Image.NEAREST)
            
                img_tk = ImageTk.PhotoImage(img_resized)
                if self.use_fountain_code: img_tk_list.append(img_tk)
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
    f2i = File2Image(method=args.method, qr_version=args.qr_version, qr_box_size=args.qr_box_size,
                     use_fountain_code=args.use_fountain_code, nproc=args.nproc)
    f2i.convert(args.input, output_mode=args.mode,
                output_dir=args.output_dir, region=args.region, fps=args.fps)
