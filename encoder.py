import os
import shutil
import qrcode
import math
import argparse

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
        chunk_size = 4296   # version 40, L error correction
        def generate_qr_code(data):
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

        image_list = []
        for i in range(0, len(data), chunk_size):
            chunk_data = data[i:i + chunk_size]
            img = generate_qr_code(chunk_data)
            
            image_list.append(img)
        return image_list

    def convert(self, file_path, output_dir):
        with open(file_path, 'rb') as f:
            file_data = f.read()
        print(f"File size: {len(file_data)} bytes.")
        image_list = self.encode_qrcode(file_data)
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
