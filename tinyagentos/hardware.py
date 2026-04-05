# tinyagentos/hardware.py
from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class CpuInfo:
    arch: str = ""
    model: str = ""
    cores: int = 0
    soc: str = ""


@dataclass
class NpuInfo:
    type: str = "none"      # rknpu | hailo | coral | qualcomm | none
    device: str = ""
    tops: int = 0
    cores: int = 0


@dataclass
class GpuInfo:
    type: str = "none"      # nvidia | amd | mali | intel | none
    model: str = ""
    vram_mb: int = 0
    vulkan: bool = False
    cuda: bool = False
    rocm: bool = False


@dataclass
class DiskInfo:
    total_gb: int = 0
    free_gb: int = 0
    type: str = ""           # emmc | sd | nvme | ssd | hdd


@dataclass
class OsInfo:
    distro: str = ""
    version: str = ""
    kernel: str = ""


@dataclass
class HardwareProfile:
    cpu: CpuInfo = field(default_factory=CpuInfo)
    ram_mb: int = 0
    npu: NpuInfo = field(default_factory=NpuInfo)
    gpu: GpuInfo = field(default_factory=GpuInfo)
    disk: DiskInfo = field(default_factory=DiskInfo)
    os: OsInfo = field(default_factory=OsInfo)

    @property
    def profile_id(self) -> str:
        arch = "arm" if self.cpu.arch in ("aarch64", "armv7l") else "x86"
        if self.npu.type != "none":
            accel = "npu"
        elif self.gpu.cuda:
            accel = "cuda"
        elif self.gpu.rocm:
            accel = "rocm"
        elif self.gpu.vulkan:
            accel = "vulkan"
        else:
            accel = "cpu"
        ram_gb = max(1, self.ram_mb // 1024)
        return f"{arch}-{accel}-{ram_gb}gb"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["profile_id"] = self.profile_id
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> HardwareProfile:
        data = json.loads(path.read_text())
        data.pop("profile_id", None)
        return cls(
            cpu=CpuInfo(**data.get("cpu", {})),
            ram_mb=data.get("ram_mb", 0),
            npu=NpuInfo(**data.get("npu", {})),
            gpu=GpuInfo(**data.get("gpu", {})),
            disk=DiskInfo(**data.get("disk", {})),
            os=OsInfo(**data.get("os", {})),
        )


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def _detect_cpu() -> CpuInfo:
    arch = platform.machine()
    cores = 0
    model = ""
    soc = ""
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        for line in cpuinfo.split("\n"):
            if line.startswith("processor"):
                cores += 1
            if "model name" in line.lower() or "hardware" in line.lower():
                model = line.split(":")[-1].strip()
        # Detect SoC for ARM
        dt_model = Path("/proc/device-tree/model")
        if dt_model.exists():
            soc_str = dt_model.read_text().strip("\x00").lower()
            if "rk3588" in soc_str:
                soc = "rk3588"
            elif "rk3576" in soc_str:
                soc = "rk3576"
            elif "bcm2712" in soc_str:
                soc = "bcm2712"
    except OSError:
        pass
    if not cores:
        import os
        cores = os.cpu_count() or 1
    return CpuInfo(arch=arch, model=model, cores=cores, soc=soc)


def _detect_ram() -> int:
    try:
        meminfo = Path("/proc/meminfo").read_text()
        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return kb // 1024
    except OSError:
        pass
    return 0


def _detect_npu() -> NpuInfo:
    # Rockchip RKNPU
    if Path("/dev/rknpu").exists():
        cores = 3  # RK3588 default
        return NpuInfo(type="rknpu", device="/dev/rknpu", tops=6, cores=cores)
    # Hailo
    for p in Path("/dev").glob("hailo*"):
        return NpuInfo(type="hailo", device=str(p), tops=26, cores=1)
    # Google Coral
    for p in Path("/dev").glob("apex_*"):
        return NpuInfo(type="coral", device=str(p), tops=4, cores=1)
    return NpuInfo()


def _detect_gpu() -> GpuInfo:
    gpu = GpuInfo()
    lspci = _run(["lspci"])
    if "NVIDIA" in lspci.upper():
        gpu.type = "nvidia"
        for line in lspci.split("\n"):
            if "NVIDIA" in line.upper() and ("VGA" in line or "3D" in line):
                gpu.model = line.split(":")[-1].strip()
                break
        # Check CUDA
        gpu.cuda = shutil.which("nvidia-smi") is not None
        # Check Vulkan
        gpu.vulkan = gpu.cuda  # NVIDIA cards with drivers have Vulkan
    elif "AMD" in lspci.upper() and "VGA" in lspci.upper():
        gpu.type = "amd"
        for line in lspci.split("\n"):
            if "AMD" in line.upper() and "VGA" in line:
                gpu.model = line.split(":")[-1].strip()
                break
        gpu.rocm = Path("/opt/rocm").exists()
        gpu.vulkan = gpu.rocm
    else:
        # Check for integrated Mali (ARM)
        drm_path = Path("/sys/class/drm")
        if drm_path.exists():
            for card in drm_path.glob("card*/device/driver"):
                driver = card.resolve().name if card.exists() else ""
                if "mali" in driver.lower() or "panfrost" in driver.lower():
                    gpu.type = "mali"
                    gpu.model = "Mali (integrated)"
                    break
    # Check Vulkan availability
    if not gpu.vulkan and shutil.which("vulkaninfo"):
        result = _run(["vulkaninfo", "--summary"])
        if "GPU" in result and "ERROR" not in result:
            gpu.vulkan = True
    return gpu


def _detect_disk() -> DiskInfo:
    try:
        import shutil as sh
        usage = sh.disk_usage("/")
        total_gb = usage.total // (1024 ** 3)
        free_gb = usage.free // (1024 ** 3)
    except OSError:
        total_gb = 0
        free_gb = 0
    # Detect storage type
    dtype = ""
    lsblk = _run(["lsblk", "-dno", "NAME,ROTA,TRAN"])
    for line in lsblk.split("\n"):
        parts = line.split()
        if len(parts) >= 2:
            rota = parts[1] if len(parts) > 1 else "1"
            tran = parts[2] if len(parts) > 2 else ""
            if "nvme" in tran:
                dtype = "nvme"
                break
            elif "mmc" in parts[0]:
                dtype = "emmc" if "mmcblk" in parts[0] else "sd"
                break
            elif rota == "0":
                dtype = "ssd"
                break
            elif rota == "1":
                dtype = "hdd"
    return DiskInfo(total_gb=total_gb, free_gb=free_gb, type=dtype)


def _detect_os() -> OsInfo:
    distro = ""
    version = ""
    try:
        for line in Path("/etc/os-release").read_text().split("\n"):
            if line.startswith("ID="):
                distro = line.split("=", 1)[1].strip('"')
            elif line.startswith("VERSION_ID="):
                version = line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    kernel = platform.release()
    return OsInfo(distro=distro, version=version, kernel=kernel)


def detect_hardware() -> HardwareProfile:
    """Detect all hardware and return a profile."""
    return HardwareProfile(
        cpu=_detect_cpu(),
        ram_mb=_detect_ram(),
        npu=_detect_npu(),
        gpu=_detect_gpu(),
        disk=_detect_disk(),
        os=_detect_os(),
    )


def get_hardware_profile(cache_path: Path) -> HardwareProfile:
    """Load cached hardware profile, or detect and cache if missing."""
    if cache_path.exists():
        return HardwareProfile.load(cache_path)
    profile = detect_hardware()
    profile.save(cache_path)
    return profile
