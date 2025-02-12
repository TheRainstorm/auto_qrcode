import io
import multiprocessing
import os
import shutil
import struct
import math
import argparse
import tqdm
import qrcode


def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes."
    )
    parser.add_argument(
        "-i", "--input", required=True, help="The path to the file to convert."
    )
    parser.add_argument(
        "-o", "--output-dir", default="./out", help="Image output directory."
    )
    parser.add_argument(
        "-n", "--nproc", type=int, default=-1, help="multiprocess encoding"
    )
    return parser


class File2Image:
    def __init__(self, nproc=1):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc

    def encode_qrcode(self, data):
        qr = qrcode.QRCode(
            version=40,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
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

    def convert(self, file_path, output_dir):
        with open(file_path, "rb") as f:
            file_data = f.read()
        print(f"File size: {len(file_data)} bytes.")

        chunk_size = 2953 - 4  # version 40, L error correction
        manager = multiprocessing.Manager()
        result_queue = manager.Queue()
        pool = multiprocessing.Pool(processes=self.nproc)
        num_chunks = math.ceil(len(file_data) / chunk_size)

        for i in range(num_chunks):
            header = struct.pack("i", i)
            chunk_data = header + file_data[i * chunk_size : (i + 1) * chunk_size]
            pool.apply_async(self.process_chunk, (i, chunk_data, result_queue))
        pool.close()

        self.prepare_output_dir(output_dir)

        for i in tqdm.tqdm(range(num_chunks)):
            img_bytes = result_queue.get()
            with open(f"{output_dir}/img_{i}.png", "wb") as f:
                f.write(img_bytes)

        pool.join()

    def prepare_output_dir(self, output_dir):
        if os.path.exists(output_dir):
            remove = input(f"Output directory {output_dir} exists, remove? [y/n]")
            if remove.lower() == "y":
                shutil.rmtree(output_dir)
            else:
                print("Aborted.")
                return
        os.makedirs(output_dir)


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    f2i = File2Image(args.nproc)
    f2i.convert(args.input, args.output_dir)
