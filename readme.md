

打算做一个类似 cambar 的项目，将文件自动转换成一系列二维码，自动播放，接收端自动扫描，并转换回文件。

和 cambar 使用手机摄像头扫描不同，本项目针对通过远程桌面访问目标机器的场景。由于不需要通过物理摄像头信道，因此单个二维码编码的信息可以远高于 cambar。

为了简单起见，暂时不自己设计二维码编码方案，而是使用现有的

- qrcode: 114 维时，有 1KB左右
- cambar：7KB


## 依赖

```shell
apt install zbar-tools  # python pyzbar need

pip install -r requirements.txt
```

Windows pip install pyzbar 后仍然无法运行，报错找不到 libiconv.dll，见 https://github.com/NaturalHistoryMuseum/pyzbar/issues/161#issuecomment-2294826987

尝试了卸载重装、python 版本从 3.12 降低为 3.8、下载 pyzbar whl 包（zip文件）解压复制 dll 均无法解决。最后解决办法是下载安装 VC2013 运行库：https://www.microsoft.com/en-US/download/details.aspx?id=40784


