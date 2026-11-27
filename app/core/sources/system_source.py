"""app/sources/system_source.py — 电脑系统硬件资源与网络速率数据源

本地高频无网络数据源：
实时采集 CPU 占用与核数、内存已用与总量、磁盘已用与总量、
以及实时网络上下行速率 (↑ 上传 / ↓ 下载)。

优先采用 Windows 原生 kernel32/iphlpapi ctypes API 0 依赖无损采集，
显式声明 64 位 argtypes / restype，若环境装有 psutil 则作为辅助兼容通道。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
from typing import Any

from app.core.tiles import make_tile

from . import SourceInfo, register

# ==================== Win32 API 显式声明 ====================
_kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

_kernel32.GetSystemTimes.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
_kernel32.GetSystemTimes.restype = wintypes.BOOL

_kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.c_void_p]
_kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL

_kernel32.GetDiskFreeSpaceExW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(ctypes.c_ulonglong),
]
_kernel32.GetDiskFreeSpaceExW.restype = wintypes.BOOL

_iphlpapi = ctypes.WinDLL("iphlpapi.dll", use_last_error=True)
_iphlpapi.GetIfTable2.argtypes = [ctypes.c_void_p]
_iphlpapi.GetIfTable2.restype = wintypes.DWORD
_iphlpapi.FreeMibTable.argtypes = [ctypes.c_void_p]
_iphlpapi.FreeMibTable.restype = None

# TCP 连接表查询 (用于定位吃带宽进程)
_iphlpapi.GetExtendedTcpTable.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.BOOL,
    wintypes.ULONG,
    ctypes.c_int,
    wintypes.ULONG,
]
_iphlpapi.GetExtendedTcpTable.restype = wintypes.DWORD

_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_IF_ROW2(ctypes.Structure):
    _fields_ = [
        ("InterfaceLuid", ctypes.c_uint64),
        ("InterfaceIndex", wintypes.DWORD),
        ("InterfaceGuid", ctypes.c_byte * 16),
        ("Alias", ctypes.c_wchar * 257),
        ("Description", ctypes.c_wchar * 257),
        ("PhysicalAddressLength", wintypes.DWORD),
        ("PhysicalAddress", ctypes.c_byte * 32),
        ("PermanentPhysicalAddress", ctypes.c_byte * 32),
        ("Mtu", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TunnelType", wintypes.DWORD),
        ("MediaType", wintypes.DWORD),
        ("PhysicalMediumType", wintypes.DWORD),
        ("AccessType", wintypes.DWORD),
        ("DirectionType", wintypes.DWORD),
        ("InterfaceAndOperStatusFlags", wintypes.BYTE),
        ("OperStatus", wintypes.DWORD),
        ("AdminStatus", wintypes.DWORD),
        ("MediaConnectState", wintypes.DWORD),
        ("NetworkGuid", ctypes.c_byte * 16),
        ("ConnectionType", wintypes.DWORD),
        ("TransmitLinkSpeed", ctypes.c_uint64),
        ("ReceiveLinkSpeed", ctypes.c_uint64),
        ("InOctets", ctypes.c_uint64),
        ("InUcastPkts", ctypes.c_uint64),
        ("InNUcastPkts", ctypes.c_uint64),
        ("InDiscards", ctypes.c_uint64),
        ("InErrors", ctypes.c_uint64),
        ("InUnknownProtos", ctypes.c_uint64),
        ("InUcastOctets", ctypes.c_uint64),
        ("InMulticastOctets", ctypes.c_uint64),
        ("InBroadcastOctets", ctypes.c_uint64),
        ("OutOctets", ctypes.c_uint64),
        ("OutUcastPkts", ctypes.c_uint64),
        ("OutNUcastPkts", ctypes.c_uint64),
        ("OutDiscards", ctypes.c_uint64),
        ("OutErrors", ctypes.c_uint64),
        ("OutUcastOctets", ctypes.c_uint64),
        ("OutMulticastOctets", ctypes.c_uint64),
        ("OutBroadcastOctets", ctypes.c_uint64),
        ("OutQLen", ctypes.c_uint64),
    ]


class MIB_IF_TABLE2(ctypes.Structure):
    _fields_ = [
        ("NumEntries", wintypes.DWORD),
        ("Table", MIB_IF_ROW2 * 1),
    ]


# ==================== 状态缓存与初始化 ====================
_LAST_CPU_TIMES: tuple[int, int, int] | None = None
_LAST_NET_SAMPLE: tuple[float, int, int] | None = None
_LATEST_NET_SPEED: tuple[float, float] = (0.0, 0.0)  # (speed_up, speed_down)


def _prime_cpu_times() -> None:
    global _LAST_CPU_TIMES
    idle = ctypes.c_ulonglong(0)
    kernel = ctypes.c_ulonglong(0)
    user = ctypes.c_ulonglong(0)
    if _kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        _LAST_CPU_TIMES = (idle.value, kernel.value, user.value)


_prime_cpu_times()


def _format_speed(bps: float) -> str:
    """将每秒字节数转换为可读速率字符串。"""
    if bps < 1024.0:
        return f"{int(bps)} B/s"
    elif bps < 1024.0 * 1024.0:
        kb = bps / 1024.0
        return f"{kb:.1f} KB/s" if kb < 100.0 else f"{int(round(kb))} KB/s"
    elif bps < 1024.0 * 1024.0 * 1024.0:
        mb = bps / (1024.0 * 1024.0)
        return f"{mb:.1f} MB/s" if mb < 100.0 else f"{int(round(mb))} MB/s"
    else:
        gb = bps / (1024.0 * 1024.0 * 1024.0)
        return f"{gb:.2f} GB/s"


def _sample_network_octets_native() -> tuple[int, int]:
    """通过 Windows 原生 GetIfTable2 采集当前活跃网卡的 In/Out 累计字节数。"""
    pTable = ctypes.c_void_p()
    ret = _iphlpapi.GetIfTable2(ctypes.byref(pTable))
    if ret != 0 or not pTable:
        return 0, 0
    try:
        pStruct = ctypes.cast(pTable, ctypes.POINTER(MIB_IF_TABLE2))
        n = pStruct.contents.NumEntries
        if n <= 0:
            return 0, 0

        class FULL_TABLE(ctypes.Structure):
            _fields_ = [
                ("NumEntries", wintypes.DWORD),
                ("Table", MIB_IF_ROW2 * n),
            ]

        full_table = ctypes.cast(pTable, ctypes.POINTER(FULL_TABLE)).contents
        total_in = 0
        total_out = 0
        for i in range(n):
            row = full_table.Table[i]
            if row.Type != 24 and row.OperStatus == 1:
                total_in += int(row.InOctets)
                total_out += int(row.OutOctets)
        return total_in, total_out
    finally:
        _iphlpapi.FreeMibTable(pTable)


def get_network_metrics() -> tuple[float, float]:
    """计算实时网络上传速率 (bps) 与下载速率 (bps)。"""
    global _LAST_NET_SAMPLE, _LATEST_NET_SPEED
    now = time.monotonic()
    tot_in, tot_out = _sample_network_octets_native()

    if _LAST_NET_SAMPLE is None:
        _LAST_NET_SAMPLE = (now, tot_in, tot_out)
        _LATEST_NET_SPEED = (0.0, 0.0)
        return _LATEST_NET_SPEED

    last_ts, last_in, last_out = _LAST_NET_SAMPLE
    dt = max(0.2, now - last_ts)

    d_in = max(0, tot_in - last_in) if tot_in >= last_in else 0
    d_out = max(0, tot_out - last_out) if tot_out >= last_out else 0

    speed_down = d_in / dt
    speed_up = d_out / dt
    _LAST_NET_SAMPLE = (now, tot_in, tot_out)
    _LATEST_NET_SPEED = (speed_up, speed_down)
    return _LATEST_NET_SPEED


# ==================== 系统核心硬件指标采集 ====================
def _get_system_metrics_native() -> tuple[float, float, float, float, float, float, float, float]:
    """通过 Windows 原生 ctypes 获取：
    (cpu_pct, mem_pct, mem_used_gb, mem_total_gb, disk_pct, disk_free_gb, disk_used_gb, disk_total_gb)
    """
    global _LAST_CPU_TIMES

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    _kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))

    mem_total_gb = stat.ullTotalPhys / (1024**3)
    mem_avail_gb = stat.ullAvailPhys / (1024**3)
    mem_used_gb = max(0.0, mem_total_gb - mem_avail_gb)
    mem_pct = float(stat.dwMemoryLoad)

    free_bytes = ctypes.c_ulonglong(0)
    total_bytes = ctypes.c_ulonglong(0)
    sys_drive = os.environ.get("SystemDrive", "C:") + "\\"
    _kernel32.GetDiskFreeSpaceExW(
        sys_drive,
        ctypes.byref(free_bytes),
        ctypes.byref(total_bytes),
        None,
    )
    disk_total_gb = total_bytes.value / (1024**3) if total_bytes.value > 0 else 1.0
    disk_free_gb = free_bytes.value / (1024**3)
    disk_used_gb = max(0.0, disk_total_gb - disk_free_gb)
    disk_pct = max(0.0, min(100.0, (disk_used_gb / disk_total_gb) * 100.0))

    idle = ctypes.c_ulonglong(0)
    kernel = ctypes.c_ulonglong(0)
    user = ctypes.c_ulonglong(0)
    _kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    curr_times = (idle.value, kernel.value, user.value)

    if _LAST_CPU_TIMES is None:
        _LAST_CPU_TIMES = curr_times
        cpu_pct = 15.0
    else:
        d_idle = curr_times[0] - _LAST_CPU_TIMES[0]
        d_kernel = curr_times[1] - _LAST_CPU_TIMES[1]
        d_user = curr_times[2] - _LAST_CPU_TIMES[2]
        _LAST_CPU_TIMES = curr_times
        total_time = d_kernel + d_user
        if total_time > 0:
            cpu_pct = max(0.0, min(100.0, (1.0 - (d_idle / total_time)) * 100.0))
        else:
            cpu_pct = 10.0

    return (
        cpu_pct,
        mem_pct,
        mem_used_gb,
        mem_total_gb,
        disk_pct,
        disk_free_gb,
        disk_used_gb,
        disk_total_gb,
    )


def get_system_metrics() -> tuple[float, float, float, float, float, float, float, float]:
    """获取系统指标，优先 psutil，回退 Windows 原生 API。"""
    try:
        import psutil

        cpu_pct = float(psutil.cpu_percent(interval=None))
        vm = psutil.virtual_memory()
        mem_pct = float(vm.percent)
        mem_used_gb = vm.used / (1024**3)
        mem_total_gb = vm.total / (1024**3)

        sys_drive = os.environ.get("SystemDrive", "C:") + "\\"
        du = psutil.disk_usage(sys_drive)
        disk_pct = float(du.percent)
        disk_free_gb = du.free / (1024**3)
        disk_used_gb = du.used / (1024**3)
        disk_total_gb = du.total / (1024**3)
        return (
            cpu_pct,
            mem_pct,
            mem_used_gb,
            mem_total_gb,
            disk_pct,
            disk_free_gb,
            disk_used_gb,
            disk_total_gb,
        )
    except ImportError:
        return _get_system_metrics_native()


def hardware_usage_color(ratio: float) -> str:
    """根据硬件使用率返回色彩：正常科技蓝，>75% 橙，>88% 红。"""
    if ratio > 0.88:
        return "#FF3B30"
    if ratio > 0.75:
        return "#FF9500"
    return "#0A84FF"


def get_top_network_processes(limit: int = 3) -> list[dict[str, Any]]:
    """通过 GetExtendedTcpTable 与进程快照扫描当前最活跃的网络连接进程 (TOP 3)。"""
    try:
        size = wintypes.DWORD(0)
        # AF_INET = 2, TCP_TABLE_OWNER_PID_ALL = 5
        _iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), True, 2, 5, 0)
        if size.value == 0:
            return []
        buf = ctypes.create_string_buffer(size.value)
        if _iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), True, 2, 5, 0) != 0:
            return []

        num_entries = wintypes.DWORD.from_buffer_copy(buf[:4]).value
        row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
        pid_counts: dict[int, int] = {}
        for i in range(num_entries):
            offset = 4 + i * row_size
            if offset + row_size > size.value:
                break
            row = MIB_TCPROW_OWNER_PID.from_buffer_copy(buf[offset:offset + row_size])
            pid = row.dwOwningPid
            if pid > 4:
                pid_counts[pid] = pid_counts.get(pid, 0) + 1

        if not pid_counts:
            return []

        # TH32CS_SNAPPROCESS = 0x00000002
        h = _kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        proc_names: dict[int, str] = {}
        if h and h != wintypes.HANDLE(-1).value:
            try:
                pe = PROCESSENTRY32W()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                if _kernel32.Process32FirstW(h, ctypes.byref(pe)):
                    while True:
                        proc_names[pe.th32ProcessID] = pe.szExeFile
                        if not _kernel32.Process32NextW(h, ctypes.byref(pe)):
                            break
            finally:
                _kernel32.CloseHandle(h)

        aggregated: dict[str, int] = {}
        for pid, count in pid_counts.items():
            name = proc_names.get(pid) or f"PID {pid}"
            aggregated[name] = aggregated.get(name, 0) + count

        sorted_procs = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
        return [{"name": name, "connections": count} for name, count in sorted_procs[:limit]]
    except Exception:
        return []


@register(
    SourceInfo(
        id="system",
        title="电脑系统硬件监控 (CPU / 内存 / 磁盘 / 实时网速)",
        description="实时采集 CPU 占用、物理内存、系统盘空间及网络实时上下行速率",
        kind="local",
        default_interval_sec=2,
        min_interval_sec=1,
        needs_credentials=False,
    )
)
def fetch_system_tiles(cfg: dict[str, Any], timeout: float = 2.0) -> list[dict[str, Any]]:
    """采集系统核心硬件与实时网络速率，返回 3 个标准 Tile。"""
    (
        cpu_pct,
        mem_pct,
        mem_used_gb,
        mem_total_gb,
        disk_pct,
        disk_free_gb,
        disk_used_gb,
        disk_total_gb,
    ) = get_system_metrics()

    cpu_count = os.cpu_count() or 8
    speed_up, speed_down = get_network_metrics()

    up_str = _format_speed(speed_up)
    down_str = _format_speed(speed_down)

    top_net_procs = []
    # 当检测到上下行速率 > 5MB/s 时，自动触发 TCP 活跃进程扫描
    if (speed_up + speed_down) > 5 * 1024 * 1024:
        top_net_procs = get_top_network_processes(3)

    probe_extra = {
        "net_up_str": up_str,
        "net_down_str": down_str,
        "speed_up": speed_up,
        "speed_down": speed_down,
        "top_net_procs": top_net_procs,
        "cpu_count": cpu_count,
        "mem_used_gb": mem_used_gb,
        "mem_total_gb": mem_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_free_gb": disk_free_gb,
    }

    r_cpu = max(0.0, min(1.0, cpu_pct / 100.0))
    r_mem = max(0.0, min(1.0, mem_pct / 100.0))
    r_disk = max(0.0, min(1.0, disk_pct / 100.0))

    t_cpu = make_tile(
        id="system:cpu",
        source="system",
        name="CPU",
        ratio=r_cpu,
        center_text=f"{int(round(cpu_pct))}%",
        sub_text=f"{cpu_count}核",
        color=hardware_usage_color(r_cpu),
        kind="ring",
        **probe_extra,
    )

    t_mem = make_tile(
        id="system:mem",
        source="system",
        name="RAM",
        ratio=r_mem,
        center_text=f"{int(round(mem_pct))}%",
        sub_text=f"{mem_used_gb:.1f}G",
        color=hardware_usage_color(r_mem),
        kind="ring",
        mem_detail=f"{mem_used_gb:.1f}G / {mem_total_gb:.0f}G",
        **probe_extra,
    )

    t_disk = make_tile(
        id="system:disk",
        source="system",
        name="Disk",
        ratio=r_disk,
        center_text=f"{int(round(disk_pct))}%",
        sub_text=f"余{disk_free_gb:.0f}G",
        color=hardware_usage_color(r_disk),
        kind="ring",
        disk_detail=f"{disk_used_gb:.0f}G / {disk_total_gb:.0f}G",
        **probe_extra,
    )

    return [t_cpu, t_mem, t_disk]
