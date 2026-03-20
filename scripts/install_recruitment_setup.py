import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = PROJECT_ROOT / "venv"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
ENV_FILE = PROJECT_ROOT / ".env"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"


def _venv_python() -> Path:
    if sys.platform.startswith("win"):
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _run(cmd: list[str], step_name: str) -> None:
    print(f"[setup] {step_name}: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)


def main() -> int:
    try:
        if not VENV_DIR.exists():
            _run([sys.executable, "-m", "venv", str(VENV_DIR)], "创建虚拟环境")
        else:
            print("[setup] 跳过创建虚拟环境：venv 已存在")

        venv_python = _venv_python()
        if not venv_python.exists():
            print(f"error venv_python_not_found path={venv_python}")
            return 1

        if REQUIREMENTS.exists():
            _run(
                [str(venv_python), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
                "安装 Python 依赖",
            )
        else:
            print(f"error requirements_not_found path={REQUIREMENTS}")
            return 1

        _run(
            [str(venv_python), "-m", "playwright", "install", "chromium"],
            "安装 Playwright Chromium",
        )

        if not ENV_FILE.exists():
            if not ENV_EXAMPLE.exists():
                print(f"error env_example_not_found path={ENV_EXAMPLE}")
                return 1
            shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
            print("[setup] 已创建 .env（来源 .env.example）")
        else:
            print("[setup] 跳过创建 .env：文件已存在")

        print("ready setup_installed")
        print("next 请在 .env 填写 OPENAI_API_KEY / LLM_BASE_URL / LLM_MODEL")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"error setup_failed step_command={exc.cmd} exit_code={exc.returncode}")
        return 1
    except Exception as exc:
        print(f"error setup_failed reason={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
