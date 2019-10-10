#!/usr/bin/env python


from __future__ import print_function

import argparse
import glob
import json
import os

import networkx as nx
from networkx.drawing.nx_pydot import write_dot
import pydot


def parse_args():
    parser = argparse.ArgumentParser(description='Calculate the eccentricity '
                                                 'of an LLVM CFG')
    parser.add_argument('json_dir',
                        help='Path to directory containing JSON CFGs')
    parser.add_argument('--dot', action='store_true', required=False,
                        help='Generate DOT file')
    parser.add_argument('-e', '--entry', action='store', required=False,
                        default='main', help='Alternative entry point')

    return parser.parse_args()


def main():
    args = parse_args()

    json_dir = args.json_dir
    if not os.path.isdir(json_dir):
        raise Exception('Invalid JSON directory `%s`' % json_dir)

    # Load all of the control flow graphs (CFG)

    cfg_dict = {}
    for json_path in glob.glob(os.path.join(json_dir, 'cfg.*.json')):
        with open(json_path, 'r') as json_file:
            data = json.load(json_file)
            func = data.pop('function')
            cfg_dict[func] = data

    # Turn the CFGs into a networkx graph

    # Blacklist the following functions
    blacklist = set()

    cfg = nx.DiGraph()

    # Add intraprocedural edges
    for func, func_dict in cfg_dict.items():
        if func in blacklist:
            continue

        # JSON edges may be `none`
        if not func_dict.get('edges'):
            continue

        for edge in func_dict['edges']:
            cfg.add_edge('%s.%s' % (func, edge['src']),
                         '%s.%s' % (func, edge['dst']))

    # Add interprocedural edges
    for func, func_dict in cfg_dict.items():
        # JSON calls may be `none`
        if not func_dict.get('calls'):
            continue

        for call in func_dict['calls']:
            # Add forward edge
            #
            # If we don't know anything about the callee function (such as
            # its entry block), skip it
            callee = call['dst']
            callee_dict = cfg_dict.get(callee, {})
            if 'entry' not in callee_dict:
                continue

            cfg.add_edge('%s.%s' % (func, call['src']),
                         '%s.%s' % (callee, callee_dict['entry']))

            # Add backward edges (if they exist)
            #
            # JSON returns may be `none`
            if not callee_dict.get('returns'):
                continue

            for ret in callee_dict['returns']:
                cfg.add_edge('%s.%s' % (callee, ret),
                             '%s.%s' % (func, call['src']))

    # Output to DOT
    if args.dot:
        print('Writing to cfg.dot...')
        write_dot(cfg, 'cfg.dot')

    # The resulting CFG will probably not be strongly connected. So split the
    # CFG into weakly-connected components and find the one with our given entry
    # point
    sub_cfg = None
    entry_node = 'main.%s' % cfg_dict[args.entry]['entry']
    for wcc in nx.weakly_connected_component_subgraphs(cfg):
        if entry_node in wcc:
            sub_cfg = wcc
            break

    if not sub_cfg:
        raise Exception('Could not find CFG with entry point `%s`' % args.entry)

    entry_eccentricity = nx.eccentricity(sub_cfg, v=entry_node)
    print('eccentricity from `%s`: %d' % (entry_node, entry_eccentricity))


if __name__ == '__main__':
    main()
