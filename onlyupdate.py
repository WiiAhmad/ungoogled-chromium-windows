#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script to update or download ungoogled-chromium source code
"""

import sys
import argparse
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'ungoogled-chromium' / 'utils'))
import downloads
from _common import ENCODING, ExtractorEnum, get_logger
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent


def _make_tmp_paths():
    """Creates TMP and TEMP variable dirs so ninja won't fail"""
    tmp_path = Path(os.environ['TMP'])
    if not tmp_path.exists():
        tmp_path.mkdir()
    tmp_path = Path(os.environ['TEMP'])
    if not tmp_path.exists():
        tmp_path.mkdir()


def main():
    """CLI Entrypoint"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--disable-ssl-verification',
        action='store_true',
        help='Disables SSL verification for downloading')
    parser.add_argument(
        '--7z-path',
        dest='sevenz_path',
        default='_use_registry',
        help=('Command or path to 7-Zip\'s "7z" binary. If "_use_registry" is '
              'specified, determine the path from the registry. Default: %(default)s'))
    parser.add_argument(
        '--winrar-path',
        dest='winrar_path',
        default='_use_registry',
        help=('Command or path to WinRAR\'s "winrar.exe" binary. If "_use_registry" is '
              'specified, determine the path from the registry. Default: %(default)s'))
    parser.add_argument(
        '--tarball',
        action='store_true',
        help='Download chromium source from tarball instead of git')
    parser.add_argument(
        '--x86',
        action='store_true',
        help='Target x86 architecture')
    parser.add_argument(
        '--arm',
        action='store_true',
        help='Target ARM64 architecture')
    args = parser.parse_args()

    # Set common variables
    source_tree = _ROOT_DIR / 'build' / 'src'
    downloads_cache = _ROOT_DIR / 'build' / 'download_cache'

    # Setup environment
    source_tree.mkdir(parents=True, exist_ok=True)
    downloads_cache.mkdir(parents=True, exist_ok=True)
    _make_tmp_paths()

    # Extractors
    extractors = {
        ExtractorEnum.SEVENZIP: args.sevenz_path,
        ExtractorEnum.WINRAR: args.winrar_path,
    }

    # Prepare source folder
    if args.tarball:
        # Download chromium tarball
        get_logger().info('Downloading chromium tarball...')
        download_info = downloads.DownloadInfo([_ROOT_DIR / 'ungoogled-chromium' / 'downloads.ini'])
        downloads.retrieve_downloads(download_info, downloads_cache, None, True, args.disable_ssl_verification)
        try:
            downloads.check_downloads(download_info, downloads_cache, None)
        except downloads.HashMismatchError as exc:
            get_logger().error('File checksum does not match: %s', exc)
            exit(1)

        # Unpack chromium tarball
        get_logger().info('Unpacking chromium tarball...')
        downloads.unpack_downloads(download_info, downloads_cache, None, source_tree, extractors)
    else:
        # Clone sources
        target_platform = 'win32' if args.x86 else 'win-arm64' if args.arm else 'win64'
        get_logger().info(f'Cloning sources for {target_platform}...')
        subprocess.run([
            sys.executable, 
            str(Path('ungoogled-chromium', 'utils', 'clone.py')), 
            '-o', 'build\\src', 
            '-p', target_platform
        ], check=True)

    # Retrieve windows downloads
    get_logger().info('Downloading required files...')
    download_info_win = downloads.DownloadInfo([_ROOT_DIR / 'downloads.ini'])
    downloads.retrieve_downloads(download_info_win, downloads_cache, None, True, args.disable_ssl_verification)
    try:
        downloads.check_downloads(download_info_win, downloads_cache, None)
    except downloads.HashMismatchError as exc:
        get_logger().error('File checksum does not match: %s', exc)
        exit(1)

    # Unpack downloads
    DIRECTX = source_tree / 'third_party' / 'microsoft_dxheaders' / 'src'
    ESBUILD = source_tree / 'third_party' / 'devtools-frontend' / 'src' / 'third_party' / 'esbuild'
    if DIRECTX.exists():
        import shutil
        shutil.rmtree(DIRECTX)
        DIRECTX.mkdir()
    if ESBUILD.exists():
        import shutil
        shutil.rmtree(ESBUILD)
        ESBUILD.mkdir()
    get_logger().info('Unpacking downloads...')
    downloads.unpack_downloads(download_info_win, downloads_cache, None, source_tree, extractors)

    get_logger().info('Source update completed successfully')


if __name__ == '__main__':
    main()