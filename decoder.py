import base64
import os
import argparse
import struct
from pyzbar.pyzbar import decode
from PIL import Image
import multiprocessing
import tqdm
from pixelbar import PixelBar
from util import *
from pywirehair import decoder as wirehair_decoder

def get_parser():
    parser = argparse.ArgumentParser(
        description="Convert a file to a series of QR codes.")
    parser.add_argument("-o", "--output",
                        default="out.txt", help="output file path.")
    # 从目录或者屏幕截图中获取数据
    parser.add_argument(
        "-m", "--mode",
        default="screen_dxcam", choices=['dir', 'screen_mss', 'screen_dxcam', 'screen_win32'],
        help="input from dir or screen snapshot."
    )
    parser.add_argument("-i", "--input-dir", default='./out', help="dir: The dir containing the images to decode, use this for testing.")
    parser.add_argument(
        "-r", "--region", default="",
        help="Screen_mss: screen region to capture, format: mon_id:width:height:offset_left:offset_top. "
            "mon_id is the monitor id, default 1. "
            "widht/height: int|d|w|h, 'd' means default 3/4*min(w,h). "
            "Offset startwith '-' means from right/bottom, 'c' means center")
    parser.add_argument("-w", "--win-title", help="screen_win32: title of window to capture")
    # L2
    parser.add_argument(
        "-M", "--method", default="qrcode", choices=['qrcode', 'pixelbar'], help="encoding method"
    )
    # pixelbar 还不支持自动识别 boxsize，所以需要手动指定
    parser.add_argument(
        "-B", "--qr-box-size", type=int, default=20, help="QRcode box size"
    )
    # L3
    parser.add_argument(
        "--not-use-fountain-code", dest='use_fountain_code', action='store_false', help="l3 encoding method"
    )
    parser.add_argument("-n", "--nproc", type=int, default=-1, help="multiprocess")
    return parser

class Image2File:
    def __init__(self, method='qrcode', nproc=1, qr_box_size=None, use_fountain_code=True):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc
        self.method = method
        self.pb = PixelBar()
        # self.pb = PixelBar(self.qr_version, box_size=self.qr_boxsize, border_size=self.qr_border, pixel_bits=8)
        self.qr_box_size = qr_box_size
        self.use_fountain_code = use_fountain_code
        self.dec = None

    def decode_qrcode(self, img):
        decoded = decode(img)
        if len(decoded) == 0:
            return None
        data_ = decoded[0].data
        return base64.b32decode(data_)
    
    def get_l3_pkt_from_l2(self, img):
        '''l2_pkt ->l3_pkt'''
        if self.method == 'qrcode':
            raw_data = self.decode_qrcode(img)
        elif self.method == 'pixelbar':
            raw_data = self.pb.decode(img, box_size=self.qr_box_size)
        else:
            raise ValueError("No encoding method specified.")
        return raw_data
    
    def parse_l3_pkt(self, l3_pkt):
        idx, num_chunks = struct.unpack('II', l3_pkt[:8])
        data = l3_pkt[8:]
        return idx, num_chunks, data

    def parse_l3_pkt_fountain_code(self, l3_pkt):
        idx, file_data_size = struct.unpack('II', l3_pkt[:8])
        l3_pl_raw = l3_pkt[8:]
        l3_pl_size = len(l3_pl_raw)
        if not self.dec:
            self.dec = wirehair_decoder(file_data_size, l3_pl_size)
        l3_pl = self.dec.decode(idx, l3_pl_raw)
        return idx, file_data_size, l3_pl
        
    def parse_img(self, img):
        raw_data = self.get_l3_pkt_from_l2(img)
        if raw_data is None:
            return -1, -1, b''
        idx, num_chunks = struct.unpack('II', raw_data[:8])
        data = raw_data[8:]
        return idx, num_chunks, data
    
    def process_image(self, file_path, result_queue):
        # read image
        img = Image.open(file_path)
        
        idx, _, data = self.parse_l3_pkt(self.get_l3_pkt_from_l2(img))
        result_queue.put((idx, data))
        # print(f'pid {os.getpid()}: file {file_path} image {idx}')
    
    def convert(self, output_file, mode='screen_win32', input_dir="", region='', win_title=''):
        tim = timer()
        
        if mode=='screen_mss':
            self.input_from_screen(capture_method='mss', region=region)
        elif mode=='screen_dxcam':
            self.input_from_screen(capture_method='dxcam', region=region)
        elif mode=='screen_win32':
            if not win_title:
                print("win_title must be specified when use screen_win32 mode.")
                exit(1)
            self.input_from_screen(capture_method='win32', win_title=win_title)
        elif mode=='dir':
            if self.use_fountain_code:
                print("Fountain code not supported in dir mode for now.")
                exit(1)
            self.input_from_dir(input_dir)
        else:
            raise ValueError("No input source specified.")
            
        with open(output_file, 'wb') as f:
            f.write(self.data_merged)
        elap = tim.elapsed()
        print(f"output to {output_file} size: {len(self.data_merged)}B elpased: {elap:.0f}s speed {len(self.data_merged)/elap:.2f} B/s.")

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
            import mss
            region_split = region.split(':')
            sct = mss.mss()
            mon_id = parse_region_mon(region_split)
            mon = sct.monitors[mon_id]
            width, height, x, y = parse_region(region_split[1:], mon["width"], mon["height"])
            
            # The screen part to capture
            monitor = {
                "left": mon["left"] + x,
                "top": mon["top"] + y,
                "width": width,
                "height": height,
                "mon": mon_id,
            }
            print(f"Screen: {mon_id}[{mon["width"]}x{mon["height"]}], Capture region: {width}x{height}+{x}+{y}")
            
            def capture_img():
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        elif capture_method == 'dxcam':
            import dxcam
            region_split = region.split(':')
            mon_id = parse_region_mon(region_split) - 1 # 0 based
            camera = dxcam.create(output_idx=mon_id, output_color="RGB")
            width, height, x, y = parse_region(region_split[1:], camera.width, camera.height)
            region = (x, y, x + width, y + height)
            print(f"Screen: {mon_id+1}[{camera.width}x{camera.height}], Capture region: {width}x{height}+{x}+{y}")
            
            camera.start(target_fps=60, region=region)
            def capture_img():
                frame = camera.get_latest_frame()
                # frame = camera.grab(region=region)
                return Image.fromarray(frame)
        else:
            hwnd = get_hwnd(win_title)
            def capture_img():
                return getSnapshot(hwnd)
        
        img = capture_img()
        img.save("first.png") # write the first image to disk
        
        if self.use_fountain_code:
            tim = timer()
            collected_idx = set()
            idx = file_data_size = l3_pl_size = num_chunks = -1
            unrecv = True
            progress = tqdm.tqdm(leave=False, mininterval=0.33, bar_format='{desc}')
            while True:
                img = capture_img()
                elap = tim.reset()
                if unrecv:  # 未接收到数据
                    progress.set_description(f"Recv speed: {len(collected_idx)*l3_pl_size/tim.since_init():.2f} B/s {1/elap:.3f}fps")
                else:
                    progress.set_description(f"Recv speed: {len(collected_idx)*l3_pl_size/tim.since_init():.2f} B/s")
                    progress.update()
                l3_pkt = self.get_l3_pkt_from_l2(img)
                if l3_pkt is None:
                    continue
                idx, file_data_size, l3_pl = self.parse_l3_pkt_fountain_code(l3_pkt)
                if unrecv:  # 第一次接收到数据
                    unrecv = False
                    tim = timer()   # 重置时钟
                    l3_pl_size = len(l3_pkt) - 8
                    num_chunks = (file_data_size + l3_pl_size - 1)// l3_pl_size
                    progress.close()
                    progress = tqdm.tqdm(total=num_chunks, leave=True, mininterval=0.33)
                collected_idx.add(idx)
                if l3_pl is not None:
                    print()
                    break
            progress.close()
            self.data_merged = l3_pl
        else:
            num_chunks = remained = -1     # 总图片数
            collected = set()   # 记录已经解码的图片
            decoded_bytes = 0
            max_idx = -1
            tim = timer()
            while remained != 0:
                img = capture_img()
                elap = tim.reset()
                print(f"max: {max_idx:5d}{' ' if max_idx<= len(collected) else 'M'} len/tot: {len(collected):>5d}/{num_chunks:<5d} speed: {decoded_bytes/tim.since_init():.2f} B/s each iter: {elap:.2f}s speed: {1/elap:.3f}fps \r", end='')
                
                idx, num_chunks, data = self.parse_img(img)
                if idx == -1:  # parse empty
                    continue
                
                if remained == -1:
                    tim = timer()
                    remained = num_chunks
                    data_list = [b'' for _ in range(num_chunks)]
                if idx not in collected:
                    collected.add(idx)
                    data_list[idx] = data
                    decoded_bytes += len(data)
                    max_idx = max(max_idx, idx)
                    remained -= 1
            print()
            self.data_merged = b"".join([d for d in data_list])
        if capture_method == 'dxcam':
            camera.stop()

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    args.win_title = os.getenv('CAPTURE_WINDOW', args.win_title)
    i2f = Image2File(nproc=args.nproc, method = args.method, qr_box_size=args.qr_box_size)
    i2f.convert(args.output,
                mode=args.mode,
                input_dir=args.input_dir,
                region=args.region,
                win_title=args.win_title)
