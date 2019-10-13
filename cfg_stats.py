#!/usr/bin/env python
#
# Author: Adrian Herrera
#
# Determine the eccentricity of an LLVM control flow graph
#


from __future__ import print_function

import argparse
from collections import defaultdict
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


def create_node(mod, func, identifier):
    return '%s.%s.%s' % (mod, func, identifier)


def find_callee(cfg_dict, callee_func):
    # TODO optimize
    for mod_dict in cfg_dict.values():
        for func, func_dict in mod_dict.items():
            if callee_func == func:
                return func_dict

    return {}


def main():
    args = parse_args()

    json_dir = args.json_dir
    if not os.path.isdir(json_dir):
        raise Exception('Invalid JSON directory `%s`' % json_dir)

    # Load all of the control flow graphs (CFG)

    cfg_dict = defaultdict(dict)
    entry_pts = []
    num_indirect_calls = 0

    for json_path in glob.glob(os.path.join(json_dir, 'cfg.*.json')):
        with open(json_path, 'r') as json_file:
            data = json.load(json_file)

            # Build the CFG
            mod = data['module']
            func = data.pop('function')
            cfg_dict[mod][func] = data

            # Collect other interesting stats
            if func == args.entry:
                entry_pts.append((mod, func))
            num_indirect_calls += data.pop('indirect_calls')

    # Turn the CFGs into a networkx graph

    # Blacklist the following functions
    blacklist = set()

    cfg = nx.DiGraph()

    # Add intraprocedural edges
    for mod, mod_dict in cfg_dict.items():
        for func, func_dict in mod_dict.items():
            if func in blacklist:
                continue

            # JSON nodes may be `none`
            if not func_dict.get('nodes'):
                continue

            # Insert a node into the CFG with the module and function as
            # attributes
            for node in func_dict['nodes']:
                cfg.add_node(create_node(mod, func, node), module=mod,
                             function=func)

            # JSON edges may be `none`
            if not func_dict.get('edges'):
                continue

            # Add intraprocedural edges
            for edge in func_dict['edges']:
                cfg.add_edge(create_node(mod, func, edge['src']),
                             create_node(mod, func, edge['dst']))

    # Add interprocedural edges
    for mod, mod_dict in cfg_dict.items():
        for func, func_dict in mod_dict.items():
            # JSON calls may be `none`
            if not func_dict.get('calls'):
                continue

            for call in func_dict['calls']:
                # Add forward edge
                #
                # If we don't know anything about the callee function (such as
                # its entry block), skip it
                callee = call['dst']
                callee_dict = find_callee(cfg_dict, callee)
                if 'entry' not in callee_dict:
                    continue

                cfg.add_edge(create_node(mod, func, call['src']),
                             create_node(callee_dict['module'], callee,
                                         callee_dict['entry']))

                # Add backward edges (if they exist)
                #
                # JSON returns may be `none`
                if not callee_dict.get('returns'):
                    continue

                for ret in callee_dict['returns']:
                    cfg.add_edge(create_node(mod, callee, ret),
                                 create_node(mod, func, call['src']))

    # Output to DOT
    if args.dot:
        print('Writing to cfg.dot...')
        write_dot(cfg, 'cfg.dot')
        print()

    # Depending on how the target was compiled and the CFGToJSON pass run, there
    # may be multiple entry points (e.g., multiple driver programs, each with
    # their own main function).
    #
    # Thus, iterate over each entry point and reduce the CFG to only those nodes
    # reachable from the entry point. This allows us to calculate eccentricity,
    # because the CFG is now connected.
    for entry_mod, entry_func in entry_pts:
        entry_node = create_node(entry_mod, entry_func,
                                 cfg_dict[entry_mod][entry_func]['entry'])

        descendants = nx.descendants(cfg, entry_node)
        descendants.add(entry_node)
        reachable_cfg = cfg.copy()
        reachable_cfg.remove_nodes_from(n for n in cfg if n not in descendants)

        num_bbs = reachable_cfg.number_of_nodes()
        num_edges = reachable_cfg.size()
        eccentricity = nx.eccentricity(reachable_cfg, v=entry_node)

        print('`%s.%s` stats' % (entry_mod, entry_func))
        print('  num. basic blocks: %d' % num_bbs)
        print('  num. edges: %d' % num_edges)
        print('  eccentricity from `%s`: %d' % (entry_node, eccentricity))
        print()


if __name__ == '__main__':
    main()
