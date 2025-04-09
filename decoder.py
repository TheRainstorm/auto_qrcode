import base64
import os
import argparse
import struct
from pyzbar.pyzbar import decode
from PIL import Image
import multiprocessing
import tqdm
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
        "-R", "--region", default="",
        help="Screen_mss: screen region to capture, format: mon_id:width:height:offset_left:offset_top. "
            "mon_id is the monitor id, default 1. "
            "widht/height: int|d|w|h, 'd' means default 3/4*min(w,h). "
            "Offset startwith '-' means from right/bottom, 'c' means center")
    parser.add_argument("-W", "--win-title", help="screen_win32: title of window to capture")
    # L2
    parser.add_argument(
        "-M", "--method", default="qrcode", choices=['qrcode', 'pixelbar', 'cimbar'], help="encoding method"
    )
    # 用于自动计算 region 大小，并非解码需要
    parser.add_argument(
        "-Q", "--qr-version", type=int, default=40, help="QRcode version"
    )
    # pixelbar 还不支持自动识别 box_size，所以需要手动指定
    parser.add_argument(
        "-B", "--qr-box-size", type=float, default=1.5, help="QRcode box size"
    )
    # # L3
    # parser.add_argument(
    #     "-F", "--not-use-fountain-code", dest='use_fountain_code', action='store_false', help="l3 encoding method"
    # )
    parser.add_argument("-n", "--nproc", type=int, default=-1, help="multiprocess")
    return parser

class Image2File:
    def __init__(self, method='qrcode', nproc=1, qr_box_size=1.5, qr_version=40):
        if nproc <= 0:
            self.nproc = multiprocessing.cpu_count() - 1
        else:
            self.nproc = nproc
        self.method = method
        self.pb = None
        self.qr_box_size = qr_box_size
        self.use_fountain_code = False
        self.dec = None
        # 仅用于自动计算 region
        self.qr_version = qr_version
        self.qr_border = 1
        self.cb = None  # cimbar

    def decode_qrcode(self, img):
        decoded = decode(img)
        if len(decoded) == 0:
            return None
        data_ = decoded[0].data
        return base64.b32decode(data_)
    
    def get_l3_pkt_from_l2(self, img):
        '''l2_pkt ->l3_pkt'''
        if self.method == 'qrcode':
            l2_pkt = self.decode_qrcode(img)
        elif self.method == 'pixelbar':
            if not self.pb:
                from pixelbar import PixelBar
                self.pb = PixelBar()
            l2_pkt = self.pb.decode(img, box_size=int(self.qr_box_size))
        elif self.method == 'cimbar':
            if not self.cb:
                import cimbar
                self.cb = cimbar.Cimbar()
            l2_pkt = self.cb.decode(img)
        else:
            raise ValueError("No encoding method specified.")
        if l2_pkt is None:
            return None
        l2_header = l2_pkt[0]
        if l2_header == 1:
            self.use_fountain_code = True
        
        return l2_pkt[1:]
    
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
    
    def process_image(self, file_path, result_queue):
        # not fountain code, decoding process
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
            print(f"mode: {mode} input_dir: {input_dir}")
            self.input_from_dir(input_dir)
        else:
            raise ValueError("No input source specified.")
            
        with open(output_file, 'wb') as f:
            f.write(self.data_merged)
        elap = tim.elapsed()
        print(f"output to {output_file} size: {len(self.data_merged)}B elpased: {elap:.0f}s speed {len(self.data_merged)/elap:.2f} B/s.")
        print(f"MD5: {md5sum(output_file)}")

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
        # for file in file_list:
        #     self.process_image(os.path.join(input_dir, file), result_queue)
        
        data_list = [b'' for _ in range(num_images)]
        for i in tqdm.tqdm(range(num_images)):
            idx, data = result_queue.get()
            data_list[idx] = data
        # concat
        self.data_merged = b"".join([d for d in data_list])

    def input_from_screen(self, capture_method, region='', win_title=''):
        fit_pixel = int((self.qr_version * 4 + 21 + 2*self.qr_border) * self.qr_box_size) # default 1.5, version 40 -> 275x275, can be distinguished
        if capture_method == 'mss':
            import mss
            region_split = region.split(':')
            sct = mss.mss()
            mon_id = parse_region_mon(region_split)
            mon = sct.monitors[mon_id]
            width, height, x, y = parse_region(region_split[1:], mon["width"], mon["height"], fit_pixel=fit_pixel)
            
            # The screen part to capture
            monitor = {
                "left": mon["left"] + x,
                "top": mon["top"] + y,
                "width": width,
                "height": height,
                "mon": mon_id,
            }
            print(f'Screen: {mon_id}[{mon["width"]}x{mon["height"]}], Capture region: {width}x{height}+{x}+{y}')
            
            def capture_img():
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        elif capture_method == 'dxcam':
            import dxcam
            region_split = region.split(':')
            mon_id = parse_region_mon(region_split) - 1 # 0 based
            camera = dxcam.create(output_idx=mon_id, output_color="RGB")
            width, height, x, y = parse_region(region_split[1:], camera.width, camera.height, fit_pixel=fit_pixel)
            region = (x, y, x + width, y + height)
            print(f"Screen: {mon_id+1}[{camera.width}x{camera.height}], Capture region: {width}x{height}+{x}+{y}")
            
            camera.start(target_fps=60, region=region)
            def capture_img():
                frame = camera.get_latest_frame()
                # frame = camera.grab(region=region)
                return Image.fromarray(frame)
        else:
            from util_decode import get_hwnd, getSnapshot
            hwnd = get_hwnd(win_title)
            def capture_img():
                return getSnapshot(hwnd)
        
        # get first pkt
        tim = timer()
        progress = tqdm.tqdm(leave=False, mininterval=0.33, bar_format='{desc}')
        while True:
            img = capture_img()
            elap = tim.reset()
            l3_pkt = self.get_l3_pkt_from_l2(img)       #set self.use_fountain_code
            if l3_pkt is None: # 未接收到数据
                progress.set_description(f"capture {1/elap:.3f}fps")
                continue
            print(f"L3 mode: {'fountain code' if self.use_fountain_code else 'normal'}")
            img.save("first.png") # write the first image to disk
            progress.close()
            break
        
        if self.use_fountain_code:
            tim = timer()
            collected_idx = set()
            idx = file_data_size = l3_pl_size = num_chunks = -1
            unrecv = True
            progress = tqdm.tqdm(leave=False, mininterval=0.33, bar_format='{desc}')
            while True:
                img = capture_img()
                elap = tim.reset()
                l3_pkt = self.get_l3_pkt_from_l2(img)
                if l3_pkt is None: # 未接收到数据
                    progress.set_description(f"speed: {len(collected_idx)*l3_pl_size/tim.since_init():.2f} B/s {1/elap:.3f}fps")
                    continue
                idx, file_data_size, l3_pl = self.parse_l3_pkt_fountain_code(l3_pkt)
                if idx not in collected_idx:
                    progress.set_description(f"Idx: {idx} speed: {len(collected_idx)*l3_pl_size/tim.since_init():.2f} B/s")
                    progress.update()
                    collected_idx.add(idx)
                if unrecv:  # 第一次接收到数据
                    unrecv = False
                    tim = timer()   # 重置时钟
                    l3_pl_size = len(l3_pkt) - 8
                    num_chunks = (file_data_size + l3_pl_size - 1)// l3_pl_size
                    progress.close()
                    progress = tqdm.tqdm(total=num_chunks, leave=True, mininterval=0.33)
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
                
                l3_pkt = self.get_l3_pkt_from_l2(img)
                if l3_pkt is None:
                    continue
                idx, num_chunks, data = self.parse_l3_pkt(l3_pkt)
                
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
    i2f = Image2File(nproc=args.nproc, method = args.method, qr_box_size=args.qr_box_size, qr_version=args.qr_version)
    i2f.convert(args.output,
                mode=args.mode,
                input_dir=args.input_dir,
                region=args.region,
                win_title=args.win_title)
