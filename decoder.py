import os
import re
import argparse
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
            m = re.match(r"img_(\d+)\.png", file)
            if m:
                file_list.append((int(m.group(1)), file))
        print(f"Found {len(file_list)} images.")
        
        # parallel decode
        data_list = []
        for i,file in file_list:
            # read image
            img = Image.open(os.path.join(input_dir, file))
            data = self.decode_qrcode(img)
            data_list.append((i, data))
        
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
