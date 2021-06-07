"""
Generate networkx-based control-flow graph based on the LLVM `CFGToJSON` pass.

Author: Adrian Herrera
"""


__all__ = ['create_cfg']


from collections import defaultdict, Counter
from pathlib import Path
from typing import Optional, Sequence, Set, Tuple
import json
import logging

import networkx as nx


def create_cfg_node(mod: str, func: str, identifier: str) -> str:
    """Create a node in the CFG."""
    return f'{mod}.{func}.{identifier}'


def find_callee(cfg_dict: dict, callee_func: str) -> dict:
    # TODO optimize
    for mod_dict in cfg_dict.values():
        for func, func_dict in mod_dict.items():
            if callee_func == func:
                return func_dict

    return {}


def create_cfg(jsons: Sequence[Path], entry_point: str = 'main',
               entry_module: Optional[str] = None,
               blacklist: Optional[Set[str]] = None) -> Tuple[nx.DiGraph, Set[str]]:
    """
    Create an interprocedural control-flow graph from a directory of JSON files
    created by the `CFGToJSON` LLVM pass.

    Returns a tuple containing:

    1. The CFG
    2. A list of entry nodes into the CFG
    """
    cfg_dict = defaultdict(dict)
    entry_nodes = set()

    if not blacklist:
        blacklist = set()

    for json_path in jsons:
        if not json_path.is_file():
            logging.warning('%s is not a file. Skipping...', json_path)
            continue

        logging.debug('Parsing module %s', json_path)
        with json_path.open() as inf:
            mod_data = json.load(inf)

        # Build the CFG dictionary
        mod = json_path.stem
        for func, func_data in mod_data.items():
            cfg_dict[mod][func] = func_data

    # Turn the CFGs into a networkx graph
    cfg = nx.DiGraph()

    for mod, mod_dict in cfg_dict.items():
        for func, func_dict in mod_dict.items():
            if func in blacklist:
                logging.info('Function %s (in %s) is blacklisted. '
                             'Skipping...', func, func_dict['module'])
                continue
            logging.debug('Processing %s (in %s)', func, func_dict['module'])

            # Add nodes
            nodes = func_dict.get('nodes')
            if nodes is None:
                nodes = {}

            for label, data in nodes.items():
                node = create_cfg_node(mod, func, label)
                start_line = data['start_line']
                end_line = data['end_line']
                size = data['size']

                cfg.add_node(node, module=mod, function=func)
                if start_line and end_line:
                    cfg.nodes[node]['start_line'] = start_line
                    cfg.nodes[node]['end_line'] = end_line
                    cfg.nodes[node]['size'] = size

            # Add intraprocedural edges
            edges = func_dict.get('edges')
            if edges is None:
                edges = []

            for edge in edges:
                src_node = create_cfg_node(mod, func, edge['src'])
                dst_node = create_cfg_node(mod, func, edge['dst'])
                cfg.add_edge(src_node, dst_node)

                if func == entry_point and \
                        (entry_module is None or mod == entry_module) and \
                        cfg.in_degree(src_node) == 0:
                    entry_nodes.add(src_node)

            # Add interprocedural edges
            calls = func_dict.get('calls')
            if calls is None:
                calls = []

            for call in calls:
                # Add forward (call) edge
                #
                # If we don't know anything about the callee function (such as
                # its entry block), skip it
                caller = call['src']
                callee = call['dst']
                callee_dict = find_callee(cfg_dict, callee)
                if 'entry' not in callee_dict:
                    logging.debug('Callee %s (called from %s) is external. '
                                  'Skipping...', callee, caller)
                    continue

                src_node = create_cfg_node(mod, func, caller)
                dst_node = create_cfg_node(callee_dict['module'], callee,
                                           callee_dict['entry'])
                cfg.add_edge(src_node, dst_node)

                if func == entry_point and \
                        (entry_module is None or mod == entry_module) and \
                        cfg.in_degree(src_node) == 0:
                    entry_nodes.add(src_node)

                # Add backward (return) edges
                returns = callee_dict.get('returns')
                if returns is None:
                    logging.debug('Function %s (in %s) has no return '
                                  'instruction(s)', callee,
                                  callee_dict['module'])
                    returns = []

                for ret in returns:
                    src_node = create_cfg_node(mod, callee, ret)
                    dst_node = create_cfg_node(mod, func, call['src'])
                    cfg.add_edge(src_node, dst_node)

            # Count indirect calls and assign them to the nodes that make them
            indirect_calls = func_dict.get('indirect_calls')
            if indirect_calls is None:
                indirect_calls = []

            indirect_call_count = Counter(indirect_calls)
            for n in indirect_call_count:
                node = create_cfg_node(mod, func, n)
                if node not in cfg:
                    cfg.add_node(node)
                cfg.nodes[node]['indirect_calls'] = indirect_call_count[n]

    return cfg, list(entry_nodes)
