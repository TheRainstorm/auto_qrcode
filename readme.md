
打算做一个类似 [libcimbar](https://github.com/sz3/libcimbar) 的项目，将文件自动转换成一系列二维码，自动播放，接收端自动扫描，并转换回文件。

和 libcimbar 使用手机摄像头扫描不同，本项目针对通过远程桌面访问目标机器的场景。由于不需要通过物理摄像头信道，因此单个二维码编码的信息可以远高于 libcimbar。

为了简单起见，暂时不自己设计二维码编码方案，而是使用现有的

- qrcode: version 40 （181x181 个 box），低（L）纠错，传输二进制数据，有 2 KB 左右
- libcimbar：单张图片 7 KB 左右

## TODO

- [x] 编码器使用多进程，编码 qrcode 输出 fps 可以达到 60 fps
- [x] 使用 dxcam 截屏，截屏速度不再是瓶颈（>120fps）
- [x] 使用 pywin32 支持捕获指定后台窗口
- [x] 使用喷泉码方案（wirehair），解决因为单个图片丢失需要多轮扫描的问题（encoder 播放图片速度小于 10fps 才能基本保证不丢失，实际接收速率>20fps（包含q rcode 解码时间））
- [ ] wirehair 多进程下编解码
- [ ] 更高效的编码方案，代替现有的 qrcode

目前基于二维码能达到 25KB/s，不如 libcimbar 的 106 KB/s。

## 依赖

```shell
pip install -r requirements.txt

# linux 下需要安装 zbar
apt install zbar-tools  # python pyzbar need
```

Windows pip install pyzbar 后仍然无法运行，报错找不到 libiconv.dll，见 https://github.com/NaturalHistoryMuseum/pyzbar/issues/161#issuecomment-2294826987

尝试了卸载重装、python 版本从 3.12 降低为 3.8、下载 pyzbar whl 包（zip文件）解压复制 dll 均无法解决。最后解决办法是下载安装 VC2013 运行库：https://www.microsoft.com/en-US/download/details.aspx?id=40784

## 使用

tiny qrcode
```shell
$ python encoder.py -i encoder.py -r 80:80:-0:-0 -Q 7 -F 30
File size: 7577 bytes.
QR code version 8 corr: L max bytes: 194 base32_valid: 165
100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 48/48 [00:02<00:00, 16.67it/s] 

$ python decoder.py -m screen_dxcam -r 2:80:80:-0:-0
Screen: 1, Capture region: (1840, 1000, 1920, 1080)
output to decoded.txt size 7140 bytes speed 886.99 B/s.s, speed: 39.001 iter/s
```

```shell
$ python encoder.py -i /e/virtio-win-gt-x64.msi -F 20
File size: 4885504 bytes.
QR code version 40 corr: L max bytes: 2956 base32_valid: 2529
Chunk size: 2521 bytes, num_chunks: 1938
Display in window[1920x1080] 274x274+823+403 fps 20

$ python decoder.py -m screen_dxcam -r 1:550:550
output to decoded.txt size 4885504 bytes speed 21534.02 B/s.r: 0.04s speed: 25.634fps  # 2 loop, peak at 40KB/s
```

```
# QR code 74KB/s (fountain code)
python encoder.py -i r200KB.bin -Q 40 -B 1.5 -f 60
python decoder.py -Q 40 -B 3 -R 1
```

Usage:
```
$ python encoder.py -h
usage: encoder.py [-h] -i INPUT [-m {dir,video,screen}] [-o OUTPUT_DIR] [-R REGION] [-M {qrcode,pixelbar}] [-Q QR_VERSION] [-B QR_box_size] [-F] [-n NPROC] [-f FPS]

Convert a file to a series of QR codes.

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        The path to the file to convert.
  -m {dir,video,screen}, --mode {dir,video,screen}
                        output to dir/video/screen(display in window)
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        dir/video: output image/video directory
  -R REGION, --region REGION
                        screen: display region, width:height:offset_left:offset_top. widht/height: int|d|w|h|f, 'd' means default 3/4*min(w,h). f: QR code fit pixel. Offset startwith '-' means from right/bottom, 'c' means center
  -M {qrcode,pixelbar}, --method {qrcode,pixelbar}
                        encoding method
  -Q QR_VERSION, --qr-version QR_VERSION
                        QRcode version
  -B QR_box_size, --qr-box-size QR_box_size
                        QRcode pixels=(21+4*version+2(border))*box_size, When use screen output, can be float.
  -F, --not-use-fountain-code
                        l3 encoding method
  -n NPROC, --nproc NPROC
                        multiprocess encoding
  -f FPS, --fps FPS     output screen display image fps
```

```
$ python decoder.py -h
usage: decoder.py [-h] [-o OUTPUT] [-m {dir,screen_mss,screen_dxcam,screen_win32}] [-i INPUT_DIR] [-R REGION] [-W WIN_TITLE] [-M {qrcode,pixelbar}] [-B QR_box_size] [-F] [-n NPROC]

Convert a file to a series of QR codes.

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        output file path.
  -m {dir,screen_mss,screen_dxcam,screen_win32}, --mode {dir,screen_mss,screen_dxcam,screen_win32}
                        input from dir or screen snapshot.
  -i INPUT_DIR, --input-dir INPUT_DIR
                        dir: The dir containing the images to decode, use this for testing.
  -R REGION, --region REGION
                        Screen_mss: screen region to capture, format: mon_id:width:height:offset_left:offset_top. mon_id is the monitor id, default 1. widht/height: int|d|w|h, 'd' means default 3/4*min(w,h). Offset startwith '-' means
                        from right/bottom, 'c' means center
  -W WIN_TITLE, --win-title WIN_TITLE
                        screen_win32: title of window to capture
  -M {qrcode,pixelbar}, --method {qrcode,pixelbar}
                        encoding method
  -B QR_box_size, --qr-box-size QR_box_size
                        QRcode box size
  -F, --not-use-fountain-code
                        l3 encoding method
  -n NPROC, --nproc NPROC
                        multiprocess
```

## Credits

- https://github.com/sz3/libcimbar
- https://github.com/ra1nty/DXcam
- https://github.com/catid/wirehair
- https://github.com/sz3/pywirehair