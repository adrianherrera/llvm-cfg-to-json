#!/usr/bin/env python3

"""
Analyze a CFG.

Author: Adrian Herrera
"""


from argparse import ArgumentParser, Namespace
from collections import Counter
from pathlib import Path
from typing import List, Optional, Set, Tuple
import json
import logging

import networkx as nx
from networkx.drawing.nx_pydot import write_dot


logger = logging.getLogger(name=__name__)


def parse_args() -> Namespace:
    """Parse command-line arguments."""
    parser = ArgumentParser(description='Analyze CFG(s)')
    parser.add_argument('-o', '--output', metavar='DOT', type=Path,
                        help='Path to output DOT')
    parser.add_argument('cfg', metavar='JSON', nargs='+', type=Path,
                        help='CFG JSON files')
    return parser.parse_args()


def create_cfg_node(mod: str, func: str, bb: str):
    """Name a graph node."""
    return f'{mod}.{func}.{bb}'


def find_callee(modules: List[dict], callee: str) -> Tuple[Optional[str], dict]:
    # TODO optimize
    for mod_data in modules:
        module = mod_data['module']
        for func_data in mod_data['functions']:
            if callee == func_data['name']:
                return module, func_data

    return None, {}


def count_edges(cfg: nx.DiGraph, edge_type: str) -> int:
    """Count edges of a particular type."""
    return sum(1 for _, _, data in cfg.edges(data='type') if data == edge_type)


def get_num_unresolved_calls(cfg: nx.DiGraph) -> int:
    """Determine the number of unresolved function calls in the CFG."""
    return sum(data for _, data in cfg.nodes(data='unresolved_calls') if data)


def get_functions(cfg: nx.DiGraph) -> Set[str]:
    """Get functions."""
    return {data for _, data in cfg.nodes(data='function')}


def main():
    """The main function."""
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)s] %(levelname)s: %(message)s')

    # Turn the CFGs into a networkx graph
    blacklist = set()
    modules = []
    cfg = nx.DiGraph()

    for cfg_path in args.cfg:
        logger.info('Parsing %s...', cfg_path)
        with cfg_path.open() as inf:
            mod_data = json.load(inf)

        modules.append(mod_data)

    # Parse CFG(s)
    for mod_data in modules:
        module = mod_data['module']
        for func_data in mod_data['functions']:
            func = func_data['name']

            if func in blacklist:
                logger.info('Function %s (in %s) is blacklisted. '
                            'Skipping...', func, module)
                continue
            logger.debug('Processing %s (in %s)', func, module)

            # Add basic blocks
            bbs = func_data['blocks']
            if bbs is None:
                bbs = {}

            for label, bb_data in bbs.items():
                node = create_cfg_node(module, func, label)
                start_line = bb_data.get('start_line')
                end_line = bb_data.get('end_line')

                cfg.add_node(node, module=module, function=func,
                             basic_block=label)
                if start_line and end_line:
                    cfg.nodes[node]['start_line'] = start_line
                    cfg.nodes[node]['end_line'] = end_line

            # Add intraprocedural edges
            edges = func_data['edges']
            if edges is None:
                edges = []

            for edge in edges:
                src_bb = create_cfg_node(module, func, edge['src'])
                dst_bb = create_cfg_node(module, func, edge['dst'])
                cfg.add_edge(src_bb, dst_bb, type=edge['type'])

            # Add interprocedural edges
            calls = func_data['calls']
            if calls is None:
                calls = []

            for call in calls:
                # Add forward (call) edge
                #
                # If we don't know anything about the callee function (such as
                # its entry block), skip it
                caller_bb = call['src']
                callee_func = call['dst']

                callee_mod, callee_data = find_callee(modules, callee_func)
                if 'entry' not in callee_data:
                    logger.debug('Callee %s (called from %s) is external. '
                                 'Skipping...', callee_func, caller_bb)
                    continue

                src_bb = create_cfg_node(module, func, caller_bb)
                dst_bb = create_cfg_node(callee_mod, callee_func,
                                         callee_data['entry'])
                cfg.add_edge(src_bb, dst_bb, type=call['type'])

                # Add backward (return) edges
                returns = callee_data['returns']
                if returns is None:
                    logger.debug('Callee %s has no returns', callee_func)
                    returns = []

                for ret_bb in returns:
                    src_bb = create_cfg_node(callee_mod, callee_func, ret_bb)
                    dst_bb = create_cfg_node(module, func, caller_bb)
                    cfg.add_edge(src_bb, dst_bb, type='return')

            # Count unresolved indirect calls and assign them to the CFG nodes
            # that make them
            unresolved_call_count = Counter(func_data.get('unresolved_calls',
                                                          []))
            for bb in unresolved_call_count:
                node = create_cfg_node(module, func, bb)
                cfg.nodes[node]['unresolved_calls'] = unresolved_call_count[bb]

    if args.output:
        write_dot(cfg, args.output)

    # Summarize
    print('num. functions -> %d' % len(get_functions(cfg)))

    print('num. intraprocedural edges -> %d' % count_edges(cfg, 'intra'))
    print('num. direct calls -> %d' % count_edges(cfg, 'call'))
    print('num. returns -> %d' % count_edges(cfg, 'return'))
    print('num. direct edges -> %d' %
          sum(count_edges(cfg, t) for t in ('intra', 'call', 'return')))

    print('num. unresolved edges -> %d' % get_num_unresolved_calls(cfg))


if __name__ == '__main__':
    main()
