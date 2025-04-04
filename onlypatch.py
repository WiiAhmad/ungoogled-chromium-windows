#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script to apply patches and domain substitutions to ungoogled-chromium source
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'ungoogled-chromium' / 'utils'))
import domain_substitution
import prune_binaries
import patches
from _common import ENCODING, get_logger
sys.path.pop(0)

_ROOT_DIR = Path(__file__).resolve().parent
_PATCH_BIN_RELPATH = Path('third_party/git/usr/bin/patch.exe')


def main():
    """CLI Entrypoint"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--tarball',
        action='store_true',
        help='Use tarball file paths instead of git paths')
    args = parser.parse_args()

    # Set common variables
    source_tree = _ROOT_DIR / 'build' / 'src'

    # Check if source exists
    if not source_tree.exists():
        get_logger().error('Source tree does not exist. Run update_source.py first.')
        exit(1)

    # Prune binaries
    get_logger().info('Pruning binaries...')
    pruning_list = (_ROOT_DIR / 'ungoogled-chromium' / 'pruning.list') if args.tarball else (_ROOT_DIR / 'pruning.list')
    unremovable_files = prune_binaries.prune_files(
        source_tree,
        pruning_list.read_text(encoding=ENCODING).splitlines()
    )
    if unremovable_files:
        get_logger().error('Files could not be pruned: %s', unremovable_files)
        exit(1)

    # Apply patches
    # First, ungoogled-chromium-patches
    get_logger().info('Applying ungoogled-chromium patches...')
    patches.apply_patches(
        patches.generate_patches_from_series(_ROOT_DIR / 'ungoogled-chromium' / 'patches', resolve=True),
        source_tree,
        patch_bin_path=(source_tree / _PATCH_BIN_RELPATH)
    )
    
    # Then Windows-specific patches
    get_logger().info('Applying Windows-specific patches...')
    patches.apply_patches(
        patches.generate_patches_from_series(_ROOT_DIR / 'patches', resolve=True),
        source_tree,
        patch_bin_path=(source_tree / _PATCH_BIN_RELPATH)
    )

    # Substitute domains
    get_logger().info('Applying domain substitutions...')
    domain_substitution_list = (_ROOT_DIR / 'ungoogled-chromium' / 'domain_substitution.list') if args.tarball else (_ROOT_DIR / 'domain_substitution.list')
    domain_substitution.apply_substitution(
        _ROOT_DIR / 'ungoogled-chromium' / 'domain_regex.list',
        domain_substitution_list,
        source_tree,
        None
    )

    get_logger().info('Patches and domain substitutions applied successfully')


if __name__ == '__main__':
    main()