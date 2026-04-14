"""
MAC 位址切換模組
透過 Windows 登錄檔修改網卡 MAC 位址，並重新啟用網卡。
需要管理員權限執行。
"""

import random
import re
import subprocess
import winreg
import logging
import time

logger = logging.getLogger("NetGuard")

# 網卡類別的登錄檔路徑
ADAPTER_REG_PATH = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"

# subprocess 隱藏視窗旗標
_CREATE_NO_WINDOW = 0x08000000


def _run_cmd(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    """執行外部指令，隱藏視窗，安全處理 stdout/stderr。"""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
    )


def generate_random_mac() -> str:
    """產生隨機的本地管理 MAC 位址。"""
    first_byte = random.randint(0x00, 0xFF)
    first_byte = (first_byte | 0x02) & 0xFE
    mac_bytes = [first_byte] + [random.randint(0x00, 0xFF) for _ in range(5)]
    return "".join(f"{b:02X}" for b in mac_bytes)


def get_adapter_list() -> list[dict]:
    """取得所有網路卡資訊列表。"""
    adapters = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ADAPTER_REG_PATH)
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
                if not re.match(r"^\d{4}$", subkey_name):
                    continue
                subkey_path = f"{ADAPTER_REG_PATH}\\{subkey_name}"
                subkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path, 0, winreg.KEY_READ)
                try:
                    driver_desc = winreg.QueryValueEx(subkey, "DriverDesc")[0]
                except FileNotFoundError:
                    driver_desc = ""
                try:
                    net_cfg_id = winreg.QueryValueEx(subkey, "NetCfgInstanceId")[0]
                except FileNotFoundError:
                    net_cfg_id = ""
                try:
                    current_mac = winreg.QueryValueEx(subkey, "NetworkAddress")[0]
                except FileNotFoundError:
                    current_mac = ""
                adapters.append({
                    "subkey_name": subkey_name,
                    "subkey_path": subkey_path,
                    "driver_desc": driver_desc,
                    "net_cfg_id": net_cfg_id,
                    "current_mac": current_mac,
                })
                winreg.CloseKey(subkey)
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError as e:
        logger.error(f"無法讀取網卡登錄檔: {e}")
    return adapters


def find_active_adapter(adapter_name: str = "auto") -> dict | None:
    """尋找目前使用中的實體網路卡（自動排除 VPN / 虛擬網卡）。"""
    adapters = get_adapter_list()
    if not adapters:
        return None

    if adapter_name != "auto":
        for a in adapters:
            if adapter_name.lower() in a["driver_desc"].lower():
                return a
        return None

    # 優先：找到有 default gateway（實際上網）的實體網卡
    try:
        result = _run_cmd([
            "powershell", "-NoProfile", "-Command",
            # 取得 default route 的 InterfaceIndex，再查對應的 NetAdapter
            "$idx = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
            "| Sort-Object RouteMetric | Select-Object -First 1).ifIndex; "
            "if ($idx) { Get-NetAdapter -InterfaceIndex $idx -ErrorAction SilentlyContinue "
            "| ForEach-Object { \"$($_.InterfaceGuid)|$($_.Name)|$($_.InterfaceDescription)\" } }"
        ])
        if result.stdout and result.stdout.strip():
            parts = result.stdout.strip().split("|", 2)
            gw_guid = parts[0].strip("{}").lower() if parts else ""
            gw_name = parts[1] if len(parts) > 1 else ""
            gw_desc = parts[2] if len(parts) > 2 else ""
            if gw_guid:
                for a in adapters:
                    if a["net_cfg_id"].strip("{}").lower() == gw_guid:
                        logger.info(f"自動選擇網卡 (default gateway): {gw_name} ({gw_desc})")
                        return a
    except Exception as e:
        logger.warning(f"Default gateway 偵測失敗: {e}")

    # 次選：所有 Up 的實體網卡（HardwareInterface=true 排除 VPN / VM）
    active_guids: list[str] = []
    try:
        result = _run_cmd([
            "powershell", "-NoProfile", "-Command",
            "Get-NetAdapter | Where-Object {"
            "$_.Status -eq 'Up' -and $_.HardwareInterface -eq $true"
            "} | Select-Object -Property InterfaceGuid, Name, InterfaceDescription | "
            "ForEach-Object { \"$($_.InterfaceGuid)|$($_.Name)|$($_.InterfaceDescription)\" }"
        ])
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split("|", 2)
                guid = parts[0].strip("{}") if parts else ""
                name = parts[1] if len(parts) > 1 else ""
                desc = parts[2] if len(parts) > 2 else ""
                if guid:
                    logger.debug(f"偵測到實體網卡: {name} ({desc}) [{guid}]")
                    active_guids.append(guid.lower())
    except Exception as e:
        logger.warning(f"PowerShell 偵測實體網卡失敗: {e}")

    # 若 HardwareInterface 過濾有結果，用它匹配登錄檔
    if active_guids:
        for guid in active_guids:
            for a in adapters:
                if a["net_cfg_id"].strip("{}").lower() == guid:
                    logger.info(f"自動選擇網卡: {a['driver_desc']}")
                    return a

    # Fallback：取得所有 Up 的網卡，但用黑名單過濾掉虛擬 / VPN
    logger.debug("HardwareInterface 過濾無結果，fallback 到關鍵字過濾")
    try:
        result = _run_cmd([
            "powershell", "-NoProfile", "-Command",
            "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
            "Select-Object -Property InterfaceGuid | "
            "ForEach-Object { $_.InterfaceGuid }"
        ])
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                guid = line.strip().strip("{}")
                for a in adapters:
                    if a["net_cfg_id"].strip("{}").lower() == guid.lower():
                        if _is_virtual_adapter(a["driver_desc"]):
                            logger.debug(f"跳過虛擬/VPN 網卡: {a['driver_desc']}")
                            continue
                        logger.info(f"自動選擇網卡 (fallback): {a['driver_desc']}")
                        return a
    except Exception as e:
        logger.warning(f"PowerShell fallback 偵測失敗: {e}")

    # 最後 fallback：常見實體網卡關鍵字
    for a in adapters:
        desc = a["driver_desc"].lower()
        if any(kw in desc for kw in ["wi-fi", "wifi", "wireless", "ethernet", "realtek", "intel"]):
            if not _is_virtual_adapter(a["driver_desc"]):
                logger.info(f"自動選擇網卡 (keyword fallback): {a['driver_desc']}")
                return a

    return adapters[0] if adapters else None


# 已知的虛擬 / VPN 網卡關鍵字（小寫比對）
_VIRTUAL_ADAPTER_KEYWORDS = [
    "vpn", "virtual", "tap-", "tap ", "tun ", "wireguard", "warp",
    "hyper-v", "vmware", "virtualbox", "vbox", "loopback",
    "bluetooth", "miniport", "wan miniport", "teredo",
    "6to4", "isatap", "fortinet", "forticlient", "juniper",
    "cisco anyconnect", "pangp", "palo alto", "softether",
    "nordlynx", "proton", "surfshark", "express",
    "windscribe", "mullvad", "openvpn",
]


def _is_virtual_adapter(driver_desc: str) -> bool:
    """根據驅動描述判斷是否為虛擬 / VPN 網卡。"""
    desc = driver_desc.lower()
    return any(kw in desc for kw in _VIRTUAL_ADAPTER_KEYWORDS)


def get_adapter_interface_name(net_cfg_id: str) -> str | None:
    """根據 NetCfgInstanceId 取得介面名稱（如「乙太網路」、「Wi-Fi」）。
    使用 PowerShell Get-NetAdapter 取得正確的介面名稱。
    """
    try:
        guid = net_cfg_id.strip("{}")
        result = _run_cmd([
            "powershell", "-NoProfile", "-Command",
            f"Get-NetAdapter | Where-Object {{$_.InterfaceGuid -eq '{{{guid}}}'}} | "
            "Select-Object -ExpandProperty Name"
        ])
        if result.stdout and result.stdout.strip():
            name = result.stdout.strip()
            logger.info(f"偵測到介面名稱: {name}")
            return name
    except Exception as e:
        logger.warning(f"取得介面名稱失敗: {e}")

    # fallback: 嘗試用 netsh
    try:
        result = _run_cmd(["netsh", "interface", "show", "interface"])
        if result.stdout:
            for line in result.stdout.splitlines():
                # 格式: "已啟用  已連線  專用  乙太網路"
                parts = line.split()
                if len(parts) >= 4:
                    # 最後一個欄位是介面名稱（可能含空格）
                    pass
    except Exception:
        pass

    return None


def set_mac_address(adapter: dict, new_mac: str) -> bool:
    """在登錄檔中設定新的 MAC 位址。"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            adapter["subkey_path"],
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "NetworkAddress", 0, winreg.REG_SZ, new_mac)
        winreg.CloseKey(key)
        logger.info(f"已設定 MAC: {new_mac} -> {adapter['driver_desc']}")
        return True
    except OSError as e:
        logger.error(f"設定 MAC 失敗: {e}")
        return False


def restart_adapter(adapter: dict) -> bool:
    """停用再啟用網卡以套用新的 MAC。"""
    iface_name = get_adapter_interface_name(adapter["net_cfg_id"])
    if not iface_name:
        logger.error(f"無法取得介面名稱 (GUID: {adapter['net_cfg_id']})")
        # 最後嘗試用 PowerShell Restart-NetAdapter（用描述名）
        return _restart_via_powershell(adapter)

    logger.info(f"正在重啟網卡: {iface_name}")
    try:
        result = _run_cmd(["netsh", "interface", "set", "interface", iface_name, "disabled"])
        if result.returncode != 0:
            logger.warning(f"netsh disable 失敗: {result.stderr.strip()}")
            return _restart_via_powershell(adapter)

        time.sleep(1)

        result = _run_cmd(["netsh", "interface", "set", "interface", iface_name, "enabled"])
        if result.returncode != 0:
            logger.warning(f"netsh enable 失敗: {result.stderr.strip()}")
            return False

        time.sleep(3)
        logger.info("網卡已重新啟用")
        return True
    except subprocess.TimeoutExpired:
        logger.error("重啟網卡逾時")
        return False


def _restart_via_powershell(adapter: dict) -> bool:
    """用 PowerShell Restart-NetAdapter 重啟網卡（備用方案）。"""
    guid = adapter["net_cfg_id"].strip("{}")
    logger.info(f"嘗試使用 PowerShell 重啟網卡 (GUID: {guid})")
    try:
        result = _run_cmd([
            "powershell", "-NoProfile", "-Command",
            f"Restart-NetAdapter -InterfaceDescription '{adapter['driver_desc']}' -Confirm:$false"
        ], timeout=30)
        if result.returncode == 0:
            time.sleep(5)
            logger.info("PowerShell 重啟網卡成功")
            return True
        else:
            logger.error(f"PowerShell 重啟失敗: {result.stderr.strip()}")
            return False
    except Exception as e:
        logger.error(f"PowerShell 重啟異常: {e}")
        return False


def change_mac(adapter_name: str = "auto") -> tuple[bool, str, str]:
    """執行完整的 MAC 切換流程。"""
    adapter = find_active_adapter(adapter_name)
    if not adapter:
        logger.error("找不到可用的網路卡")
        return False, "", ""

    old_mac = adapter.get("current_mac", "原始")
    new_mac = generate_random_mac()

    logger.info(f"切換 MAC: {old_mac} -> {new_mac} ({adapter['driver_desc']})")

    if not set_mac_address(adapter, new_mac):
        return False, old_mac, new_mac

    if not restart_adapter(adapter):
        return False, old_mac, new_mac

    return True, old_mac, new_mac


def restore_original_mac(adapter_name: str = "auto") -> bool:
    """移除自訂 MAC，恢復原始硬體 MAC。"""
    adapter = find_active_adapter(adapter_name)
    if not adapter:
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            adapter["subkey_path"],
            0,
            winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, "NetworkAddress")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        logger.info("已移除自訂 MAC")
        return restart_adapter(adapter)
    except OSError as e:
        logger.error(f"恢復 MAC 失敗: {e}")
        return False
