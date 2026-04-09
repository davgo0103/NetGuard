# NetGuard - 網路守衛

自動偵測網路速度，降速時自動切換 MAC 位址的 Windows 系統托盤常駐程式。

針對**每日 MAC 流量限制**的網路環境設計：每個 MAC 到達流量上限後會被降速，切換至其他已註冊的 MAC 即可恢復正常網速。跨日後流量重置，所有 MAC 可重新使用。

## 功能

- 定期測速（使用 speedtest.net 最近伺服器）
- 降速自動切換至下一個可用 MAC
- MAC 池管理：追蹤每個 MAC 的限速狀態，跨日自動重置
- 降速 / 切換成功 / MAC 用完時彈出桌面提示（需手動關閉）
- GUI 設定畫面：管理 MAC 清單與監控參數
- 系統托盤常駐，右鍵選單操作
- 開機自動啟動（寫入登錄檔 `HKCU\...\Run`）
- 自動要求管理員權限（UAC）

## 系統需求

- Windows 10 / 11
- 管理員權限（修改 MAC 需要）
- 網卡需支援自訂 MAC 位址
- MAC 位址需事先在組織中註冊（未註冊的 MAC 無法上網）

## 快速開始

### 方法一：直接使用 exe

1. 執行 `dist\NetGuard.exe`（會自動要求管理員權限）
2. 首次啟動會彈出**設定畫面**，輸入組織已註冊的 MAC 位址
3. 設定完成後自動常駐在系統托盤

### 方法二：從原始碼執行

```bash
# 安裝依賴
pip install -r requirements.txt

# 啟動（會自動要求管理員權限）
python net_guard.py
```

### 方法三：自行打包

```bash
# 安裝依賴 + 打包成 exe
build.bat
# 輸出: dist\NetGuard.exe
```

## 設定

首次啟動會自動開啟 GUI 設定畫面。之後可從托盤右鍵選單開啟。

也可直接編輯 `config.json`：

```json
{
    "speed_threshold_mbps": 50,
    "check_interval_seconds": 120,
    "cooldown_seconds": 60,
    "adapter_name": "auto",
    "log_file": "net_guard.log",
    "max_log_size_mb": 5,
    "auto_start": true,
    "daily_reset_hour": 0,
    "mac_list": [
        "0C9D9218AAC4",
        "0C9D9218AAC5",
        "0C9D9218AAC6"
    ],
    "mac_pool_file": "mac_pool.json"
}
```

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `speed_threshold_mbps` | 低於此速度判定為降速 (Mbps) | `50` |
| `check_interval_seconds` | 測速間隔 (秒) | `120` |
| `cooldown_seconds` | MAC 切換後的冷卻時間 (秒) | `60` |
| `adapter_name` | 網卡名稱，`auto` 為自動偵測 | `"auto"` |
| `auto_start` | 是否開機自動啟動 | `true` |
| `mac_list` | 已註冊的 MAC 位址清單 | `[]` |

## 系統托盤選單

| 選項 | 說明 |
|------|------|
| 暫停 / 恢復監控 | 暫停或恢復自動測速與切換 |
| 立即切換 MAC | 手動觸發切換至下一個可用 MAC |
| 恢復原始 MAC | 移除自訂 MAC，還原為硬體原始位址 |
| 開機自動啟動 | 勾選 / 取消開機常駐 |
| 設定 | 開啟 GUI 設定畫面 |
| 開啟日誌 | 開啟 `net_guard.log` |
| 結束 | 停止監控並退出程式 |

## 托盤圖示顏色

| 顏色 | 狀態 |
|------|------|
| 綠色 | 網速正常 |
| 黃色 | 測速中 / 正在切換 MAC |
| 紅色 | 降速 / 無網路 / MAC 已全部用完 |
| 灰色 | 監控已暫停 |

## 運作流程

```
啟動 → 等待 10 秒 → 測速
                      ↓
              速度 >= 閾值 → 正常（綠色）→ 等待下次測速
                      ↓
              速度 < 閾值 → 標記目前 MAC 為限速
                      ↓
              從 MAC 池取得下一個可用 MAC
                      ↓
          有可用 MAC → 修改登錄檔 → 重啟網卡 → 彈窗通知
                      ↓
          全部用完 → 等待跨日重置（00:00）→ 彈窗通知
```

## 專案結構

```
├── net_guard.py       # 主程式（托盤、控制器、入口）
├── mac_changer.py     # MAC 位址切換（登錄檔 + 網卡重啟）
├── mac_pool.py        # MAC 池管理（輪替、跨日重置）
├── speed_test.py      # 網速偵測（speedtest.net）
├── settings_gui.py    # GUI 設定畫面（tkinter）
├── config.json        # 設定檔
├── mac_pool.json      # MAC 使用記錄（自動產生）
├── requirements.txt   # Python 依賴
├── build.bat          # PyInstaller 打包腳本
└── install.bat        # 快速安裝依賴
```

## 注意事項

- 每次切換 MAC 會有約 **7 秒短暫斷線**（停用→啟用網卡 + DHCP 重新取得 IP）
- MAC 位址必須是組織已註冊的，未註冊的 MAC 無法上網
- 程式使用 `speedtest.net` 測速，每次測速約消耗 10~40 MB 流量
- 日誌檔自動輪替，最大 5 MB x 3 個備份
