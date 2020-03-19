#!/usr/bin/env python
#
# Author: Adrian Herrera
#
# Calculate useful statistics of an LLVM control flow graph
#


from __future__ import print_function

import argparse
from collections import defaultdict, Counter
import glob
import logging
import json
import os

import networkx as nx
from networkx.drawing.nx_pydot import write_dot
import pydot


def parse_args():
    parser = argparse.ArgumentParser(description='Calculate statistics of an '
                                                 'LLVM CFG')
    parser.add_argument('json_dir',
                        help='Path to directory containing JSON CFGs')
    parser.add_argument('--dot', action='store_true', required=False,
                        help='Generate DOT file')
    parser.add_argument('-e', '--entry', action='store', required=False,
                        default='main',
                        help='Program entry point (function name)')
    parser.add_argument('-m', '--module', action='store', required=False,
                        help='Module name containing the entry point')
    parser.add_argument('-l', '--log', action='store', default='info',
                        choices={'debug', 'info', 'warning', 'error',
                                 'critical'}, dest='loglevel',
                        help='Logging level')
    parser.add_argument('-s', '--stats', action='store_true', default=False,
                        help='Print statistics at the end')

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


def get_num_indirect_calls(graph):
    indirect_call_counts = (count for _, count in
                            graph.nodes(data='indirect_calls') if count)
    return sum(indirect_call_counts)


def get_longest_path(graph, node):
    #
    # Algorithm:
    #
    #  1. Get a list of nodes that don't have any out-going edges ("sinks")
    #  2. Get a list of loop-free paths from the entry node to every sink
    #  3. Get the length of the maximum path from the entry node to a sink
    #
    sinks = (n for n, out_degree in graph.out_degree() if out_degree == 0)
    sink_paths = (path for sink in sinks
                  for path in nx.all_simple_paths(graph, node, sink))
    return len(max(sink_paths, key=lambda p: len(p))) + 1


def main():
    args = parse_args()

    # Check that the input directory is valid
    json_dir = args.json_dir
    if not os.path.isdir(json_dir):
        raise Exception('Invalid JSON directory `%s`' % json_dir)

    # Set the logging level
    numeric_log_level = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(numeric_log_level, int):
        raise ValueError('Invalid log level: %s' % args.loglevel)
    logging.basicConfig(level=numeric_log_level)

    # Load all of the control flow graphs (CFG)

    cfg_dict = defaultdict(dict)
    entry_pts = []

    for json_path in glob.glob(os.path.join(json_dir, 'cfg.*.json')):
        logging.debug('Parsing `%s`', json_path)
        with open(json_path, 'r') as json_file:
            data = json.load(json_file)

            # Build the CFG
            mod = data['module']
            func = data.pop('function')
            cfg_dict[mod][func] = data

            # Collect other interesting stats
            if func == args.entry and \
                    (args.module is None or mod == args.module):
                logging.debug('New entry point `%s` in module %s', func, mod)
                entry_pts.append((mod, func))

    # Turn the CFGs into a networkx graph

    # Blacklist the following functions
    blacklist = set()

    cfg = nx.DiGraph()

    for mod, mod_dict in cfg_dict.items():
        for func, func_dict in mod_dict.items():
            if func in blacklist:
                logging.info('Function `%s` is blacklisted. Skipping', func)
                continue

            # Add intraprocedural edges
            edges = func_dict.get('edges')
            if edges is None:
                edges = []

            for edge in edges:
                src = create_node(mod, func, edge['src'])
                cfg.add_edge(src, create_node(mod, func, edge['dst']))
                cfg.nodes[src]['module'] = mod
                cfg.nodes[src]['function'] = func

            # Add interprocedural edges
            calls = func_dict.get('calls')
            if calls is None:
                calls = []

            for call in calls:
                # Add forward (call) edge
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

                # Add backward (return) edges
                returns = callee_dict.get('returns')
                if returns is None:
                    logging.debug('function `%s` has no return instruction(s)',
                                  callee)
                    returns = []

                for ret in returns:
                    cfg.add_edge(create_node(mod, callee, ret),
                                 create_node(mod, func, call['src']))

            # Count indirect calls and assign them to the nodes that make them
            indirect_calls = func_dict.get('indirect_calls')
            if indirect_calls is None:
                indirect_calls = []

            indirect_call_count = Counter(indirect_calls)
            for n in indirect_call_count:
                node = create_node(mod, func, n)
                if node not in cfg:
                    cfg.add_node(node)
                cfg.nodes[node]['indirect_calls'] = indirect_call_count[n]

    # Output to DOT
    if args.dot:
        logging.info('Writing CFG to cfg.dot')
        write_dot(cfg, 'cfg.dot')

    if not args.stats:
        return

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

        if entry_node not in cfg:
            logging.warn('Entry point `%s` does not exist in the CFG. '
                         'Skipping...', entry_node)
            continue

        descendants = nx.descendants(cfg, entry_node)
        descendants.add(entry_node)
        reachable_cfg = cfg.copy()
        reachable_cfg.remove_nodes_from(n for n in cfg if n not in descendants)

        num_bbs = reachable_cfg.number_of_nodes()
        num_edges = reachable_cfg.size()
        num_indirect_calls = get_num_indirect_calls(reachable_cfg)
        eccentricity = nx.eccentricity(reachable_cfg, v=entry_node)
        longest_path = get_longest_path(reachable_cfg, entry_node)

        print()
        print('`%s.%s` stats' % (entry_mod, entry_func))
        print('  num. basic blocks: %d' % num_bbs)
        print('  num. edges: %d' % num_edges)
        print('  num. indirect calls: %d' % num_indirect_calls)
        print('  eccentricity from `%s`: %d' % (entry_node, eccentricity))
        print('  longest path from `%s`: %s' % (entry_node, longest_path))


if __name__ == '__main__':
    main()
