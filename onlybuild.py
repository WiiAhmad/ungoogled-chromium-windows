#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script to build ungoogled-chromium
"""

import sys
import time
import argparse
import os
import subprocess
import ctypes
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'ungoogled-chromium' / 'utils'))
from _common import ENCODING, get_logger
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent


def _get_vcvars_path(name='64'):
    """
    Returns the path to the corresponding vcvars*.bat path

    As of VS 2017, name can be one of: 32, 64, all, amd64_x86, x86_amd64
    """
    vswhere_exe = '%ProgramFiles(x86)%\\Microsoft Visual Studio\\Installer\\vswhere.exe'
    result = subprocess.run(
        '"{}" -prerelease -latest -property installationPath'.format(vswhere_exe),
        shell=True,
        check=True,
        stdout=subprocess.PIPE,
        universal_newlines=True)
    vcvars_path = Path(result.stdout.strip(), 'VC/Auxiliary/Build/vcvars{}.bat'.format(name))
    if not vcvars_path.exists():
        raise RuntimeError(
            'Could not find vcvars batch script in expected location: {}'.format(vcvars_path))
    return vcvars_path


def _run_build_process(*args, **kwargs):
    """
    Runs the subprocess with the correct environment variables for building
    """
    # Add call to set VC variables
    cmd_input = ['call "%s" >nul' % _get_vcvars_path()]
    cmd_input.append('set DEPOT_TOOLS_WIN_TOOLCHAIN=0')
    cmd_input.append(' '.join(map('"{}"'.format, args)))
    cmd_input.append('exit\n')
    subprocess.run(('cmd.exe', '/k'),
                   input='\n'.join(cmd_input),
                   check=True,
                   encoding=ENCODING,
                   **kwargs)


def _run_build_process_timeout(*args, timeout):
    """
    Runs the subprocess with the correct environment variables for building
    """
    # Add call to set VC variables
    cmd_input = ['call "%s" >nul' % _get_vcvars_path()]
    cmd_input.append('set DEPOT_TOOLS_WIN_TOOLCHAIN=0')
    cmd_input.append(' '.join(map('"{}"'.format, args)))
    cmd_input.append('exit\n')
    with subprocess.Popen(('cmd.exe', '/k'), encoding=ENCODING, stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) as proc:
        proc.stdin.write('\n'.join(cmd_input))
        proc.stdin.close()
        try:
            proc.wait(timeout)
            if proc.returncode != 0:
                raise RuntimeError('Build failed!')
        except subprocess.TimeoutExpired:
            print('Sending keyboard interrupt')
            for _ in range(3):
                ctypes.windll.kernel32.GenerateConsoleCtrlEvent(1, proc.pid)
                time.sleep(1)
            try:
                proc.wait(10)
            except:
                proc.kill()
            raise KeyboardInterrupt


def _setup_rust_toolchain(source_tree):
    """Setup Rust toolchain for build"""
    HOST_CPU_IS_64BIT = sys.maxsize > 2**32
    RUST_DIR_DST = source_tree / 'third_party' / 'rust-toolchain'
    RUST_DIR_SRC64 = source_tree / 'third_party' / 'rust-toolchain-x64'
    RUST_DIR_SRC86 = source_tree / 'third_party' / 'rust-toolchain-x86'
    RUST_DIR_SRCARM = source_tree / 'third_party' / 'rust-toolchain-arm'
    RUST_FLAG_FILE = RUST_DIR_DST / 'INSTALLED_VERSION'
    
    # Check if already setup
    if RUST_FLAG_FILE.exists():
        get_logger().info('Rust toolchain already set up')
        return
        
    get_logger().info('Setting up Rust toolchain...')
    
    # Directories to copy from source to target folder
    DIRS_TO_COPY = ['bin', 'lib']

    # Loop over all source folders
    for rust_dir_src in [RUST_DIR_SRC64, RUST_DIR_SRC86, RUST_DIR_SRCARM]:
        # Loop over all dirs to copy
        for dir_to_copy in DIRS_TO_COPY:
            # Copy bin folder for host architecture
            if (dir_to_copy == 'bin') and (HOST_CPU_IS_64BIT != (rust_dir_src == RUST_DIR_SRC64)):
                continue

            # Create target dir
            target_dir = RUST_DIR_DST / dir_to_copy
            if not os.path.isdir(target_dir):
                os.makedirs(target_dir)

            # Loop over all subfolders of the rust source dir
            for cp_src in rust_dir_src.glob(f'*/{dir_to_copy}/*'):
                cp_dst = target_dir / cp_src.name
                if cp_src.is_dir():
                    shutil.copytree(cp_src, cp_dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(cp_src, cp_dst)

    # Generate version file
    with open(RUST_FLAG_FILE, 'w') as f:
        subprocess.run([source_tree / 'third_party' / 'rust-toolchain-x64' / 'rustc' / 'bin' / 'rustc.exe', '--version'], stdout=f)


def _setup_build_config(source_tree, x86=False, arm=False):
    """Setup build configuration"""
    # Create output directory
    build_dir = source_tree / 'out' / 'Default'
    build_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if build configuration already exists
    if (build_dir / 'args.gn').exists():
        get_logger().info('Build configuration already set up')
        return
        
    get_logger().info('Setting up build configuration...')
    
    # Output args.gn
    gn_flags = (_ROOT_DIR / 'ungoogled-chromium' / 'flags.gn').read_text(encoding=ENCODING)
    gn_flags += '\n'
    windows_flags = (_ROOT_DIR / 'flags.windows.gn').read_text(encoding=ENCODING)
    if x86:
        windows_flags = windows_flags.replace('x64', 'x86')
    elif arm:
        windows_flags = windows_flags.replace('x64', 'arm64')
    gn_flags += windows_flags
    (build_dir / 'args.gn').write_text(gn_flags, encoding=ENCODING)


def main():
    """CLI Entrypoint"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--x86',
        action='store_true',
        help='Target x86 architecture')
    parser.add_argument(
        '--arm',
        action='store_true',
        help='Target ARM64 architecture')
    parser.add_argument(
        '--ci',
        action='store_true',
        help='CI mode - build with timeout and package')
    parser.add_argument(
        '--skip-gn',
        action='store_true',
        help='Skip GN bootstrap and generation')
    parser.add_argument(
        '--skip-bindgen',
        action='store_true',
        help='Skip bindgen build')
    args = parser.parse_args()

    # Set common variables
    source_tree = _ROOT_DIR / 'build' / 'src'

    # Check if source exists
    if not source_tree.exists():
        get_logger().error('Source tree does not exist. Run update_source.py first.')
        exit(1)

    # Setup Rust toolchain
    _setup_rust_toolchain(source_tree)

    # Setup build configuration
    _setup_build_config(source_tree, args.x86, args.arm)

    # Enter source tree to run build commands
    os.chdir(source_tree)

    # Run GN bootstrap
    if not args.skip_gn and not os.path.exists('out\\Default\\gn.exe'):
        get_logger().info('Running GN bootstrap...')
        _run_build_process(
            sys.executable, 'tools\\gn\\bootstrap\\bootstrap.py', '-o', 'out\\Default\\gn.exe',
            '--skip-generate-buildfiles')

        # Run gn gen
        get_logger().info('Running GN gen...')
        _run_build_process('out\\Default\\gn.exe', 'gen', 'out\\Default', '--fail-on-unused-args')

    # Build bindgen
    if not args.skip_bindgen and not os.path.exists('third_party\\rust-toolchain\\bin\\bindgen.exe'):
        get_logger().info('Building bindgen...')
        _run_build_process(
            sys.executable,
            'tools\\rust\\build_bindgen.py')

    # Run ninja
    get_logger().info('Running ninja build...')
    if args.ci:
        _run_build_process_timeout('third_party\\ninja\\ninja.exe', '-C', 'out\\Default', 'chrome',
                                'chromedriver', 'mini_installer', timeout=3.5*60*60)
        # package
        get_logger().info('Packaging build...')
        os.chdir(_ROOT_DIR)
        subprocess.run([sys.executable, 'package.py'])
    else:
        _run_build_process('third_party\\ninja\\ninja.exe', '-C', 'out\\Default', 'chrome',
                        'chromedriver', 'mini_installer')

    get_logger().info('Build completed successfully')


if __name__ == '__main__':
    main()