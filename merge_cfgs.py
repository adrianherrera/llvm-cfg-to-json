#!/usr/bin/env python3

"""
Merge multiple LLVM CFG JSON files into a single JSON file.

Author: Adrian Herrera
"""


from argparse import ArgumentParser, Namespace
from collections import defaultdict
from pathlib import Path
import json
import logging


def parse_args() -> Namespace:
    """Parse command-line arguments."""
    parser = ArgumentParser(description='Merge multiple LLVM CFG JSON files')
    parser.add_argument('-o', '--out', type=Path, required=True,
                        help='Merged JSON file')
    parser.add_argument('-l', '--log', action='store', default='info',
                        choices={'debug', 'info', 'warning', 'error',
                                 'critical'}, dest='loglevel',
                        help='Logging level')
    parser.add_argument('jsons', nargs='+', type=Path, metavar='JSON',
                        help='Path(s) to JSON CFG files')

    return parser.parse_args()


def main():
    """The main function."""
    args = parse_args()

    # Set the logging level
    numeric_log_level = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(numeric_log_level, int):
        raise ValueError('Invalid log level: %s' % args.loglevel)
    logging.basicConfig(level=numeric_log_level,
                        format='[%(asctime)s] %(levelname)s: %(message)s')

    # Load all of the control flow graphs (CFG)
    all_funcs = defaultdict(dict)
    for json_path in args.jsons:
        if not json_path.is_file():
            logging.warning('%s is not a file. Skipping...', json_path)
            continue

        with json_path.open() as inf:
            mod_data = json.load(inf)
        mod = json_path.stem

        for func, func_data in mod_data.items():
            assert func not in all_funcs[mod]
            all_funcs[mod][func] = func_data

    # Output to JSON
    out_path = args.out
    logging.info('Writing CFG to %s', out_path)
    with out_path.open('w') as outf:
        json.dump(all_funcs, outf)


if __name__ == '__main__':
    main()
