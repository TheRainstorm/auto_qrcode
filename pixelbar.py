import numpy as np
from PIL import Image

class PixelBar:
    def __init__(self, version=40, box_size=1, border_size=1, pixel_bits=8):
        box = 21 + 4*version + 2*border_size
        width = height = box * box_size
        self.width = width
        self.height = height
        self.width_data_box = width//box_size - 2*border_size
        self.height_data_box = height//box_size - 2*border_size
        self.box_size = box_size
        self.border_size = border_size

        self.pixel_bits = pixel_bits # 8 or 16
        self.mode = 1 if pixel_bits == 8 else 2
        self.max_data_size = self.width_data_box * self.height_data_box * self.mode

    def _mode1_encode(self, data):
        """3-3-2 编码模式"""
        pixels = []
        for byte in data:
            r = (byte >> 5) & 0x07   # 高3位
            g = (byte >> 2) & 0x07   # 中3位
            b = byte & 0x03          # 低2位
            
            # 使用每个通道的高位保存数据（不容易失真）
            r = (r << 5)
            g = (g << 5)
            b = (b << 6)
            pixels.append((r, g, b))
        return pixels

    def _mode2_encode(self, data):
        """5-(3,3)-5 编码模式"""
        pixels = []
        if len(data) % 2 != 0:
            data += b'\x00'  # 补零处理
        for i in range(0, len(data), 2):
            word = (data[i] << 8) | data[i+1]
            
            r = (word >> 11) & 0x1F   # 高5位
            g = (word >> 5)  & 0x3F   # 中6位
            b = word & 0x1F           # 低5位
            
            r = (r << 3)
            g = (g << 2)
            b = (b << 3)
            pixels.append((r, g, b))
        return pixels

    def encode(self, data):
        # 数据长度校验
        if len(data) > self.max_data_size:
            raise ValueError(f"数据过大，最大支持 {self.max_data_size} 字节")
        
        # 选择编码模式
        if self.mode == 1:
            pixels = self._mode1_encode(data)
        elif self.mode == 2:
            pixels = self._mode2_encode(data)
        else:
            raise ValueError("不支持的编码模式")

        # 生成图像矩阵
        B, b, w, h = self.box_size, self.border_size, self.width_data_box, self.height_data_box
        # arr = np.zeros((self.height+2*b, self.width+2*b, 3), dtype=np.uint8)
        arr = np.full(((h+2*b)*B, (w+2*b)*B, 3), 255, dtype=np.uint8)
        for p in range(len(pixels)):
            y, x = divmod(p, w)
            if y < h:
                # for i in range(B):
                #     for j in range(B):
                #         arr[y*B+i, x*B+j] = pixels[p]
                arr[(y+b)*B:(y+1+b)*B, (x+b)*B:(x+1+b)*B] = pixels[p]
        
        img = Image.fromarray(arr)
        # return img.resize((self.width, self.height), Image.NEAREST)
        return img

    def decode(self, img, box_size=None, mode=1):
        border_size = 1
        width, height = img.size
        # img = img.resize((width//box_size, height//box_size), Image.NEAREST)
        arr = np.array(img)
        
        # detect box size
        def pixels_are_equal(pixel1, pixel2, rtol=10, atol=10):
            return np.allclose(pixel1, pixel2, rtol=rtol, atol=atol)
        def gcd(a, b):
            while b:
                a, b = b, a % b
            return a
        if not box_size:
            count = {}
            for i in range(0, height, height//3):
                j = 0
                while j < width-1:
                    k = j
                    while k+1 < width and pixels_are_equal(arr[i, k], arr[i, k+1]):
                        k += 1
                    count[k-j+1] = count.get(k-j+1, 0) + 1
                    j = k + 1
            sorted_count = sorted(count.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_count) < 3:
                box_size = sorted_count[0][0]
            else:
                box_size = gcd(sorted_count[2][0], gcd(sorted_count[0][0], sorted_count[1][0]))
            
        B = box_size
        # 检查是否有效
        # 检查边框 
        if not np.all(arr[0:B, :] >=128):
            return None
        
        b = border_size
        w, h = img.size
        w, h = w//B, h//B
        width_data_box, height_data_box = w - 2*b, h - 2*b
        pixels = []
        for y in range(height_data_box):
            for x in range(width_data_box):
                pixels.append(arr[(y + b)*B + B//2, (x + b)*B + B//2])

        # 选择编码模式
        if mode == 1:
            data = self._mode1_decode(pixels)
        elif mode == 2:
            data = self._mode2_decode(pixels)
        else:
            raise ValueError("不支持的编码模式")
        return bytes(data)
    
    def _mode1_decode(self, pixels):
        data = []
        for r, g, b in pixels:
            r = (r >> 5) & 0x07 # byte 高3位
            g = (g >> 5) & 0x07 # byte 中3位
            b = (b >> 6) & 0x03 # byte 低2位
            data.append((r << 5) | (g << 2) | b)
        return data
    def _mode2_decode(self, pixels):
        data = []
        for r, g, b in pixels:
            r = (r >> 3) & 0x1F # byte1 高5位
            g = (g >> 2) & 0x3F # byte1 低3位, byte2 高3位
            g1, g2 = g >> 3, g & 0x07
            b = (b >> 3) & 0x1F # byte2 低5位
            data.append((r << 3) | g1)
            data.append((g2 <<5) | b)
        return data

if __name__ == "__main__":
    pb = PixelBar(version=1, box_size=20, pixel_bits=8)
    
    with open('pixelbar.py', 'rb') as f:
        test_data = f.read()
    test_data = test_data[:pb.max_data_size]
    
    img = pb.encode(test_data)
    img.show()
    img.save('pixelbar.png')
    
    data = pb.decode(img)
    print(data == test_data)
    print(f"test data size {len(test_data)}: {test_data[:20]}")
    print(f"decoded data size {len(data)}: {data[:20]}")
    
    import struct
    img = Image.open('first.png')
    print(img.size)
    raw_data = pb.decode(img, box_size=20)
    print(f"raw data size: {len(raw_data)}")
    idx, num_chunks = struct.unpack('II', raw_data[:8])
    data = raw_data[8:]
    print(idx, num_chunks)
    print(data[:20])
    
    img = pb.encode(raw_data)
    img.show()
