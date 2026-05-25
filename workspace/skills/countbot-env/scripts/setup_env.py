"""
CountBot 环境检测与自动创建脚本。

在所有技能 Python 脚本执行前运行，确保环境可用。

用法:
    python workspace/skills/countbot-env/scripts/setup_env.py

输出:
    conda:COUNTBOT_EXISTS  — conda + CountBot 环境已就绪
    conda:CREATED           — conda + 已新建 CountBot 环境
    conda:CREATE_FAILED     — conda 存在但环境创建失败
    NO_CONDA                — 系统没有 conda
"""

import os
import subprocess
import sys
from pathlib import Path


def _run(cmd, timeout=30, **kwargs):
    """运行命令并返回 CompletedProcess。"""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, **kwargs)


def check_conda() -> bool:
    cmd = "where conda" if sys.platform == "win32" else "which conda"
    try:
        return _run(cmd).returncode == 0
    except Exception:
        return False


def check_env_exists(env_name: str = "CountBot") -> bool:
    try:
        r = _run("conda env list")
        return env_name in r.stdout
    except Exception:
        return False


PIP_CACHE_FLAG = "--no-cache-dir"


def _pip_install(project_root, req):
    """在 CountBot 环境中 pip install。"""
    try:
        r = _run(
            f'conda run -n CountBot pip install -r "{project_root / req}" {PIP_CACHE_FLAG} -i https://mirrors.aliyun.com/pypi/simple/',
            timeout=300,
        )
        return r.returncode == 0, r.stderr.strip()[-300:]
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def ensure_packages(project_root) -> bool:
    """检查关键包是否安装，未安装则自动补装。"""
    check_cmd = "conda run -n CountBot python -c \"import requests; print('OK')\""
    try:
        r = _run(check_cmd, timeout=30)
        if r.returncode == 0 and "OK" in r.stdout:
            return True
    except Exception:
        pass

    print("环境存在但缺少依赖包，正在安装...")
    req_files = ["requirements_countbot.txt", "requirements.txt"]
    for req in req_files:
        if (project_root / req).exists():
            ok, err = _pip_install(project_root, req)
            if ok:
                return True
            print(f"从 {req} 安装失败: {err}")
            return False
    print("未找到 requirements.txt 或 requirements_countbot.txt")
    return False


def create_env(project_root: Path) -> bool:
    """创建 CountBot conda 环境。优先用 environment.yml，否则用 requirements.txt。"""
    yml = project_root / "environment.yml"

    if yml.exists():
        print("发现 environment.yml，正在创建环境...")
        try:
            r = _run(f'conda env create -f "{yml}"', timeout=600)
            if r.returncode == 0:
                # 创建成功后安装依赖
                ensure_packages(project_root)
                return True
            print(f"environment.yml 创建失败: {r.stderr.strip()[-200:]}")
            return False
        except subprocess.TimeoutExpired:
            print("创建超时（>10分钟）")
            return False

    # 回退：创建空环境 + pip install
    print("未找到 environment.yml, 使用 conda create + pip install...")
    try:
        r = _run("conda create -n CountBot python=3.10 -y", timeout=120)
        if r.returncode != 0:
            print(f"conda create 失败: {r.stderr.strip()[-200:]}")
            return False
    except subprocess.TimeoutExpired:
        print("conda create 超时")
        return False

    # 安装依赖
    ensure_packages(project_root)
    return True


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    os.chdir(project_root)

    if not check_conda():
        print("NO_CONDA")
        sys.exit(0)

    if check_env_exists():
        if ensure_packages(project_root):
            print("conda:COUNTBOT_EXISTS")
        else:
            print("conda:COUNTBOT_EXISTS")
            print("依赖安装失败，部分功能可能受限，请手动执行: conda run -n CountBot pip install -r requirements_countbot.txt")
        sys.exit(0)

    print("conda:ENV_NOT_FOUND")
    print("正在自动创建 CountBot 环境...")
    if create_env(project_root):
        print("conda:CREATED")
    else:
        print("conda:CREATE_FAILED")
        print("请手动创建: conda create -n CountBot python=3.10 && pip install -r requirements.txt")