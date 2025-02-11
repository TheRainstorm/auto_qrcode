import io
import os
import shutil
import struct
import math
import argparse
from PIL import Image
import tqdm

def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes.")
    parser.add_argument("-i", "--input", required=True, help="The path to the file to convert.")
    parser.add_argument("-o", "--output-dir", 
                        default="./out", help="Image output directory.")
    return parser

class File2Image:
    def __init__(self):
        pass

    def encode_qrcode(self, data):
        import qrcode
        qr = qrcode.QRCode(
            version=40,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        return img

    def convert(self, file_path, output_dir):
        with open(file_path, 'rb') as f:
            file_data = f.read()
        print(f"File size: {len(file_data)} bytes.")
        
        chunk_size = 2953-4   # version 40, L error correction
        image_list = []
        
        for i in tqdm.tqdm(range(0, len(file_data), chunk_size)):
            # add header to chunk data
            header = struct.pack('i', i)
            chunk_data = header + file_data[i:i + chunk_size]
            img = self.encode_qrcode(chunk_data)
            image_list.append(img)
        print(f"Generated {len(image_list)} images.")
        
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)
        
        for i, img in enumerate(image_list):
            img.save(f"{output_dir}/img_{i}.png")

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    f2i = File2Image()
    f2i.convert(args.input, args.output_dir)
