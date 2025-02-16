
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

## Credits

- https://github.com/sz3/libcimbar
- https://github.com/ra1nty/DXcam
- https://github.com/catid/wirehair
- https://github.com/sz3/pywirehair