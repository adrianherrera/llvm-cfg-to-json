#!/usr/bin/env python
#
# Author: Adrian Herrera
#
# Calculate useful statistics of an LLVM control flow graph
#


from __future__ import print_function

import argparse
import logging
import os

import networkx as nx
from networkx.drawing.nx_pydot import write_dot
import pydot

from llvm_cfg import create_cfg


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
    return len(max(sink_paths, key=len)) + 1


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
    cfg, entry_pts = create_cfg(json_dir, args.entry, args.module)

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
    for entry_node in entry_pts:
        if entry_node not in cfg:
            logging.warning('Entry point `%s` does not exist in the CFG. '
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
        print('`%s` stats' % entry_node)
        print('  num. basic blocks: %d' % num_bbs)
        print('  num. edges: %d' % num_edges)
        print('  num. indirect calls: %d' % num_indirect_calls)
        print('  eccentricity from `%s`: %d' % (entry_node, eccentricity))
        print('  longest path from `%s`: %s' % (entry_node, longest_path))


if __name__ == '__main__':
    main()
