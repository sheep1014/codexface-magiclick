# CodexFace for MagiClick ESP32-S3

[English README](./README.md)

把一只运行 CircuitPython 的 MagiClick ESP32-S3 桌面摆件，改造成一个能显示 Codex 工作状态的表情屏：

- 5 个动态状态表情：`idle`、`working`、`attention`、`blocked`、`off`
- 支持浏览器通过 BLE 连接 Nordic UART 控制
- 支持 USB Serial 作为安装和调试通道
- 自带一个网页管理页，可切状态、发文案、按状态改配色
- 支持 Codex hooks 自动驱动表情变化

![CodexFace 预览](./codex_faces_preview.png)

## 这个仓库里有什么

- `codex_status.py`
  设备端 CircuitPython 主程序，负责屏幕绘制、BLE 和命令处理
- `web/index.html`
  浏览器管理页
- `install_codex_face_to_board.py`
  把主程序和 BLE 依赖写进板子的安装脚本
- `send_codex_face.py`
  通过 USB 串口发送简单命令
- `launch_codex_face_now.py`
  如果板子卡在 REPL，可强制切回 `/app/CodexFace.py`
- `codex_face_hook.py`
  给 Codex hooks 用的轻量串口发送脚本
- `install_codex_hooks.py`
  根据模板自动安装 `~/.codex/hooks.json`
- `codex_hooks_template.json`
  可复用的 Codex hook 模板
- `vendor/circuitpython9/lib/adafruit_ble`
  已内置的 CircuitPython BLE 依赖

## 硬件和软件要求

- 一块运行 CircuitPython 9.x 的 MagiClick S3 / ESP32-S3
- Python 3.9+
- Chrome 或 Edge

先安装本地 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

## 把程序刷进板子

用 USB 连接板子后运行：

```bash
python3 install_codex_face_to_board.py
```

这个脚本会：

- 把 `codex_status.py` 写到板子的 `/app/CodexFace.py`
- 把 BLE 需要的 `.mpy` 文件写到 `/lib/adafruit_ble/...`

对于带启动器的 MagiClick 固件，安装脚本还会尽量自动把“下次启动应用”切到 `/app/CodexFace.py`。

如果 `CIRCUITPY` 盘符是只读的，安装脚本会自动回退到串口 REPL 模式，并尝试把板载文件系统重新挂载为可写后再上传。
如果板子装完后还是停在启动器或 REPL，可以手动执行：

```bash
python3 launch_codex_face_now.py
```

## 打开管理页

运行：

```bash
./serve_web_console.sh
```

然后打开：

- 本机开发用：`http://127.0.0.1:4173`

管理页支持：

- 连接蓝牙
- 连接 USB 串口
- 切换状态
- 发送一行短文案
- 分状态调整 `bg`、`feature`、`accent`、`title`、`warn`、`sweat` 配色

## 浏览器支持和跨电脑直连

这个项目使用的是 `Web Bluetooth` 和 `Web Serial`。

所以要注意：

- 本地开发时，`localhost` 最稳
- 其他电脑想直接通过浏览器蓝牙连接，最好使用 `HTTPS`
- 纯局域网 HTTP，例如 `http://192.168.x.x:4173`，虽然页面能打开，但通常不能正常使用 Web Bluetooth / Web Serial，因为这两个 API 需要安全上下文

参考资料：

- [MDN Web Bluetooth API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Bluetooth_API)
- [MDN Web Serial API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API)
- [Chrome Web Bluetooth 文档](https://developer.chrome.com/docs/capabilities/bluetooth)

如果你希望其他电脑也能直接连接附近的摆件，建议把 `web/` 目录部署到 HTTPS 环境，例如 GitHub Pages、Netlify 或 Vercel。

这个仓库已经自带 GitHub Pages 工作流：

- `.github/workflows/deploy-pages.yml`

仓库公开并启用 Pages 后，就能直接通过 GitHub Pages 的 `https://...` 地址打开管理页。

## 设备命令协议

状态命令：

- `idle`
- `working`
- `attention`
- `blocked`
- `off`

文案命令：

- `text hello`
- `cleartext`

配色命令：

- `palette`
- `palette reset`
- `palette working`
- `palette working reset`
- `palette working bg=#F08F31 feature=#161311 accent=#FFD08B title=#FFF0DE warn=#FFD166 sweat=#A3E6FF`
- `palette bg=#EC7E1D feature=#161311 accent=#A95010 title=#F7C28E warn=#FFD166 sweat=#A3E6FF`
- `color feature #161311`

其他命令：

- `status`
- `ping`

BLE 使用 Nordic UART Service：

- Service UUID: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- RX UUID: `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`
- TX UUID: `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`

## 手动控制示例

```bash
python3 send_codex_face.py idle
python3 send_codex_face.py working
python3 send_codex_face.py --text "Thinking"
python3 send_codex_face.py --clear
python3 launch_codex_face_now.py
```

如果你的板子不在默认串口上，可以先设置：

```bash
export CODEX_FACE_PORT=/dev/cu.usbmodemXXXX
export MAGICLICK_PORT=/dev/cu.usbmodemXXXX
```

## Codex 集成

安装 hook 配置：

```bash
python3 install_codex_hooks.py
```

如果你希望 Codex hooks 通过蓝牙控制摆件，确认 `~/.codex-face.json` 里是：

```json
{
  "transport": "ble",
  "ble_name": "CodexFace",
  "ble_timeout": 8
}
```

Windows 下建议优先只填 `ble_name`，先不要直接抄 macOS 上看到的 BLE UUID。因为：

- macOS/CoreBluetooth 常显示成一串 UUID
- Windows/Bleak 扫描到的通常是 MAC 风格地址，例如 `24:EC:4A:1F:A0:06`
- 本项目现在会先尝试 `ble_address`，失败后自动回退到 `ble_name` 扫描

如果需要排查 Windows BLE，请优先检查：

- 使用 Chrome / Edge
- `~/.codex/hooks/codex_face_hook.log`
- 先关闭网页管理页的蓝牙连接，避免和 Codex hooks 抢设备
- 如果 Windows 上扫描到了正确地址，再把那个地址补回 `~/.codex-face.json`

这个脚本会：

- 把 `codex_face_hook.py` 复制到 `~/.codex/hooks/agent_face_hook.py`
- 根据 `codex_hooks_template.json` 生成 `~/.codex/hooks.json`

默认事件映射如下：

- `SessionStart` -> `idle`
- `UserPromptSubmit` -> `working`
- `PreToolUse` -> `working`
- `PostToolUse` -> `working`
- `PermissionRequest` -> `blocked`
- `PreCompact` -> `attention`
- `Stop` -> `idle`

## 可选：整片 flash 备份

如果你想在折腾前先做一份完整备份，可以运行：

```bash
python3 -m venv .venv-esptool
./.venv-esptool/bin/pip install esptool
./backup_esp32s3.sh
```

备份文件默认会被 git 忽略，不会提交到公开仓库里。

## 推荐的开源发布方式

1. 把这个仓库作为公开仓库发布到 GitHub
2. 启用 GitHub Pages，或者直接使用仓库内置的 Pages workflow
3. 在其他电脑上用 Chrome 或 Edge 打开生成的 `https://...` 地址
4. 点击“连接蓝牙”，连接附近广播为 `CodexFace` 的设备

## 许可证

MIT
