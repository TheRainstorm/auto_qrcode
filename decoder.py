import base64
import os
import argparse
import struct
from pyzbar.pyzbar import decode
from PIL import Image
import multiprocessing
import tqdm
from util import setup_mss, timer, get_hwnd, getSnapshot

def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes.")
    parser.add_argument("-o", "--output",
                        default="decoded.txt", help="output file path.")
    # 三个参数对应三种模式
    parser.add_argument(
        "-m", "--mode",
        default="screen_win32", choices=['dir', 'screen_mss', 'screen_win32'],
        help="input from dir or screen snapshot."
    )
    parser.add_argument("-i", "--input-dir", default='./out', help="dir: The dir containing the images to decode, use this for testing.")
    parser.add_argument("-r", "--region",
                        help="Screen_mss: screen region to capture, format: mon_id:width:height:offset_left:offset_top. "
                        "mon_id is the monitor id, default 1. Offset startwith '-' means from right/bottom, 'c' means center")
    parser.add_argument("-w", "--win-title", help="screen_win32: title of window to capture")
    parser.add_argument("-n", "--nproc", type=int, default=-1, help="multiprocess")
    return parser

class Image2File:
    def __init__(self, nproc=1):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc

    def decode_qrcode(self, img):
        decoded = decode(img)
        if len(decoded) == 0:
            return None
        data_ = decoded[0].data
        return base64.b32decode(data_)
    
    def parse_img(self, img):
        raw_data = self.decode_qrcode(img)
        if raw_data is None:
            return -1, -1, b''
        idx, num_chunks = struct.unpack('HH', raw_data[:4])
        data = raw_data[4:]
        return idx, num_chunks, data
    
    def process_image(self, file_path, result_queue):
        # read image
        img = Image.open(file_path)
        
        idx, _, data = self.parse_img(img)
        result_queue.put((idx, data))
        # print(f'pid {os.getpid()}: file {file_path} image {idx}')
    
    def convert(self, output_file, mode='screen_win32', input_dir="", region='', win_title=''):
        tim = timer()
        
        if mode=='screen_mss':
            self.input_from_screen(capture_method='mss', region=region)
        elif mode=='screen_win32':
            if not win_title:
                print("win_title must be specified when use screen_win32 mode.")
                exit(1)
            self.input_from_screen(capture_method='win32', win_title=win_title)
        elif mode=='dir':
            self.input_from_dir(input_dir)
        else:
            raise ValueError("No input source specified.")
            
        with open(output_file, 'wb') as f:
            f.write(self.data_merged)
        elap = tim.elapsed()
        print(f"output to {output_file} size {len(self.data_merged)} bytes speed {len(self.data_merged)/elap:.2f} B/s.")

    def input_from_dir(self, input_dir):
        file_list = []
        for file in os.listdir(input_dir):
            if not file.endswith('.png'):
                continue
            file_list.append(file)
        num_images = len(file_list)
        print(f"Found {num_images} images.")
        
        pool = multiprocessing.Pool(processes=self.nproc)
        manager = multiprocessing.Manager()
        result_queue = manager.Queue()
        
        # parallel decode
        for file in file_list:
            pool.apply_async(self.process_image, (os.path.join(input_dir, file), result_queue))
        pool.close()
        
        data_list = [b'' for _ in range(num_images)]
        for i in tqdm.tqdm(range(num_images)):
            idx, data = result_queue.get()
            data_list[idx] = data
        # concat
        self.data_merged = b"".join([d for d in data_list])

    def input_from_screen(self, capture_method, region='', win_title=''):
        if capture_method == 'mss':
            sct, monitor = setup_mss(region)
            def capture_img():
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        else:
            hwnd = get_hwnd(win_title)
            def capture_img():
                return getSnapshot(hwnd)
        
        num_chunks = remained = -1     # 总图片数
        collected = set()   # 记录已经解码的图片
        tim = timer()
        i = 0
        decoded_bytes = 0
        while remained != 0:
            i += 1
            img = capture_img()
            if i==1: img.save("first.png") # write the first image to disk
            
            elap = tim.reset()
            print(f"Progress: {len(collected)}/{num_chunks}, avg speed: {decoded_bytes/tim.since_init():.2f} B/s, one iter: {elap:.2f} s, speed: {1/elap if elap else 0:.3f} iter/s \r", end='')
            
            idx, num_chunks, data = self.parse_img(img)
            if idx == -1:  # parse empty
                continue
            
            if remained == -1:
                remained = num_chunks
                data_list = [b'' for _ in range(num_chunks)]
            if idx not in collected:
                collected.add(idx)
                data_list[idx] = data
                decoded_bytes += len(data)
                remained -= 1
        self.data_merged = b"".join([d for d in data_list])

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    args.win_title = os.getenv('CAPTURE_WINDOW', args.win_title)
    i2f = Image2File(args.nproc)
    i2f.convert(args.output, input_dir=args.input_dir,
                mode=args.mode,
                region=args.region,
                win_title=args.win_title)
