import base64
import os
import argparse
import struct
from pyzbar.pyzbar import decode
from PIL import Image
import multiprocessing
import tqdm

def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes.")
    parser.add_argument("-i", "--input-dir", required=True, help="The dir containing the images to decode.")
    parser.add_argument("-o", "--output", 
                        default="decoded.bin", help="output file path.")
    parser.add_argument(
        "-n", "--nproc", type=int, default=-1, help="multiprocess"
    )
    return parser

class Image2File:
    def __init__(self, nproc=1):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc

    def decode_qrcode(self, img):
        decoded = decode(img)
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
        
    def convert(self, input_dir, output_file):
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
        pool.join()
        # concat
        data_merged = b"".join([d for d in data_list])
        
        with open(output_file, 'wb') as f:
            f.write(data_merged)
        print(f"output to {output_file} size {len(data_merged)} bytes.")

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    i2f = Image2File(args.nproc)
    i2f.convert(args.input_dir, args.output)
