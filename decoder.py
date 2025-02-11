import os
import re
import argparse
import struct
from pyzbar.pyzbar import decode
from PIL import Image


def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes.")
    parser.add_argument("-i", "--input-dir", required=True, help="The dir containing the images to decode.")
    parser.add_argument("-o", "--output", 
                        default="decoded.bin", help="output file path.")
    return parser

class Image2File:
    def __init__(self):
        pass

    def decode_qrcode(self, img):
        decoded = decode(img)
        return decoded[0].data

    def convert(self, input_dir, output_file):
        file_list = []
        for file in os.listdir(input_dir):
            if not file.endswith('.png'):
                continue
            file_list.append(file)
        print(f"Found {len(file_list)} images.")
        
        # parallel decode
        data_list = []
        for file in file_list:
            # read image
            img = Image.open(os.path.join(input_dir, file))
            raw_data = self.decode_qrcode(img)
            # parse header
            idx = struct.unpack('i', raw_data[:4])[0]
            data = raw_data[4:]
            data_list.append((idx, data))
        
        # concat
        data_list.sort(key=lambda x: x[0])
        data_merged = b"".join([d for i,d in data_list])
        
        with open(output_file, 'wb') as f:
            f.write(data_merged)
        print(f"output to {output_file} size {len(data_merged)} bytes.")

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    i2f = Image2File()
    i2f.convert(args.input_dir, args.output)
