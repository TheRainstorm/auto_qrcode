import base64
import os
import argparse
import struct
from pyzbar.pyzbar import decode
from PIL import Image
import multiprocessing
import tqdm
from util import timer

def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes.")
    parser.add_argument("-m", "--mode", default="screen",
                        help="input from screen/dir(only for test)")
    parser.add_argument("-i", "--input-dir", help="The dir containing the images to decode(for test).")
    parser.add_argument("-o", "--output",
                        default="decoded.bin", help="output file path.")
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
    
    def process_image(self, file_path, result_queue):
        # read image
        img = Image.open(file_path)
        
        raw_data = self.decode_qrcode(img)
        
        # parse header
        idx = struct.unpack('i', raw_data[:4])[0]
        data = raw_data[4:]
        result_queue.put((idx, data))
        # print(f'pid {os.getpid()}: file {file_path} image {idx}')
    
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
        
    def input_from_screen(self):
        import mss
        sct = mss.mss()
        mon_id = 2
        mon = sct.monitors[mon_id]
        # The screen part to capture
        # target_width, target_height = 1000, 1000
        target_width, target_height = mon["width"], mon["height"]
        monitor = {
            "top": mon["top"],
            "left": mon["left"],
            "width": target_width,
            "height": target_height,
            "mon": mon_id,
        }
        
        num_chunks = -1
        not_visited = -1
        collected = set()
        i = 0
        tim = timer()
        while not_visited != 0:
            i += 1
            elap = tim.reset()
            print(f"Progress: {len(collected)}/{num_chunks}, one iter: {elap:.2f}s speed: {1/elap if elap else 0:.3f} iter/s \r", end='')
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            raw_data = self.decode_qrcode(img)
            if raw_data is None:
                continue
            idx, num_chunks = struct.unpack('HH', raw_data[:4])
            if not_visited == -1:
                not_visited = num_chunks
                data_list = [b'' for _ in range(num_chunks)]
            if idx not in collected:
                collected.add(idx)
                data_list[idx] = raw_data[4:]
                not_visited -= 1
                # progress
                print(f"Decoded {idx} ")
        self.data_merged = b"".join([d for d in data_list])
        
    def convert(self, output_file, input_dir="", input_mode="screen"):
        tim = timer()
        if input_mode == "screen":
            self.input_from_screen()
        elif input_mode == "dir":
            self.input_from_dir(input_dir)
        else:
            raise ValueError(f"Invalid input mode: {input_mode}")
        
        with open(output_file, 'wb') as f:
            f.write(self.data_merged)
        elap = tim.elapsed()
        print(f"output to {output_file} size {len(self.data_merged)} bytes speed {len(self.data_merged)/elap:.2f} B/s.")

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    i2f = Image2File(args.nproc)
    i2f.convert(args.output, input_mode=args.mode, input_dir=args.input_dir)
