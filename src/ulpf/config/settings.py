from pathlib import Path
import os
import tomllib
from pydantic import BaseModel, Field, field_validator


import subprocess
import sys


def _detect_physical_cores() -> int:
    """Auto-detect physical CPU cores on the host, with safe logical/fallback detection."""
    try:
        import psutil
        count = psutil.cpu_count(logical=False)
        if count and count > 0:
            return count
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["wmic", "cpu", "get", "NumberOfCores"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            lines = [l.strip() for l in out.splitlines() if l.strip().isdigit()]
            if lines:
                return sum(int(l) for l in lines)
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", "r") as f:
                core_ids = set()
                current_phys = "0"
                for line in f:
                    if line.startswith("physical id"):
                        current_phys = line.split(":")[1].strip()
                    elif line.startswith("core id"):
                        core_id = line.split(":")[1].strip()
                        core_ids.add(f"{current_phys}:{core_id}")
                if core_ids:
                    return len(core_ids)
        except Exception:
            pass

    logical = os.cpu_count() or 2
    return max(1, logical // 2)


def get_recommended_workers(executor_type: str = "process") -> int:
    """Auto-detect recommended workers based on host CPU physical cores."""
    return _detect_physical_cores()


class PipelineConfig(BaseModel):
    extensions_config: str = "config/extensions.yaml"
    mappings_dir: str = "config/mappings"
    output_dir: str = "output"
    output_format: str = "jsonl"
    max_output_file_size_mb: int = 100
    workers: int = 1                # 1=sequential, 0=auto (physical cores), N=explicit
    executor_type: str = "process"  # "process" or "thread" (default: "process")
    batch_size: int = 100           # Batch size for batched multiprocessing (default: 100)
    max_payload_bytes: int = 2097152  # Max event payload size in bytes (default: 2MB guard against DoS)
    max_in_flight_batches: int = 0  # Max concurrent in-flight batches (0=auto: workers*2, >=1=explicit)

    @field_validator("max_in_flight_batches")
    @classmethod
    def validate_max_in_flight(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_in_flight_batches must be >= 0")
        return v





class IngestionConfig(BaseModel):
    default_transport: str = "file"


class WebConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class AIConfig(BaseModel):
    enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "llama3.1:8b"
    fallback_to_mock: bool = True


def is_logforge_root(candidate: Path) -> bool:
    """
    Verify whether a candidate directory belongs to the LogForge repository
    by inspecting signature repository markers.
    """
    if not candidate.is_dir():
        return False
    has_config = (candidate / "config" / "settings.toml").is_file() and (candidate / "config" / "extensions.yaml").is_file()
    has_pyproject = False
    pyproject = candidate / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8")
            if 'name = "ulpf"' in content or "LogForge" in content:
                has_pyproject = True
        except Exception:
            pass
    return has_config or has_pyproject


def find_project_root() -> Path:
    """
    Deterministically discover the LogForge project root directory.

    Order of resolution:
    1. LOGFORGE_PROJECT_ROOT environment variable (validated for existence, directory, and LogForge markers).
    2. Upward traversal from the current module file (__file__).
    3. Current working directory (only if it contains LogForge markers).

    Raises:
        ValueError: If LOGFORGE_PROJECT_ROOT is set but does not exist, is not a directory, or lacks LogForge markers.
        RuntimeError: If LogForge root cannot be deterministically discovered.
    """
    if env_root := os.getenv("LOGFORGE_PROJECT_ROOT"):
        p = Path(env_root).resolve()
        if not p.is_dir():
            raise ValueError(f"LOGFORGE_PROJECT_ROOT='{env_root}' does not exist or is not a directory.")
        if not is_logforge_root(p):
            raise ValueError(f"LOGFORGE_PROJECT_ROOT='{env_root}' is not a valid LogForge repository root (missing markers).")
        return p

    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if is_logforge_root(parent):
            return parent

    cwd = Path.cwd().resolve()
    if is_logforge_root(cwd):
        return cwd

    raise RuntimeError(
        "Could not locate LogForge project root. Neither the module parents, "
        "nor CWD contain LogForge markers (config/settings.toml, pyproject.toml). "
        "Set the LOGFORGE_PROJECT_ROOT environment variable."
    )


class Settings(BaseModel):
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    ai: AIConfig = Field(default_factory=AIConfig)

    def model_post_init(self, __context) -> None:
        """Canonicalize relative pipeline paths to absolute paths anchored at project root."""
        try:
            root = find_project_root()
            for attr in ("extensions_config", "mappings_dir", "output_dir"):
                val = getattr(self.pipeline, attr, None)
                if val and isinstance(val, str):
                    p = Path(val)
                    if not p.is_absolute():
                        setattr(self.pipeline, attr, str((root / p).resolve()))
        except Exception:
            pass

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> "Settings":
        try:
            project_root = find_project_root()
        except RuntimeError:
            project_root = Path.cwd().resolve()

        path: Path | None = None
        if config_path:
            p = Path(config_path)
            if not p.is_absolute():
                if p.exists():
                    p = p.resolve()
                else:
                    p = (project_root / p).resolve()
            else:
                p = p.resolve()

            if p.is_dir():
                path = p / "settings.toml"
            else:
                path = p
        else:
            config_dir_env = os.getenv("LOGFORGE_CONFIG_DIR")
            if config_dir_env:
                candidate = Path(config_dir_env)
                if not candidate.is_absolute():
                    candidate = (project_root / candidate).resolve()
                candidate = candidate / "settings.toml" if candidate.is_dir() else candidate
                if candidate.exists():
                    path = candidate
            else:
                candidate = project_root / "config" / "settings.toml"
                if candidate.exists():
                    path = candidate

        if path and path.exists():
            with open(path, "rb") as f:
                data = tomllib.load(f)
            return cls(**data)

        return cls()

