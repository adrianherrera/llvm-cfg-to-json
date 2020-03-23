"""
Generate networkx-based control-flow graph based on the LLVM `CFGToJSON` pass.

Author: Adrian Herrera
"""

from collections import defaultdict, Counter
import glob
import json
import logging
import os

import networkx as nx


def _create_node(mod, func, identifier):
    """Create a node in the CFG."""
    return '%s.%s.%s' % (mod, func, identifier)


def _find_callee(cfg_dict, callee_func):
    # TODO optimize
    for mod_dict in cfg_dict.values():
        for func, func_dict in mod_dict.items():
            if callee_func == func:
                return func_dict

    return {}


def create_cfg(json_dir, entry_point='main', entry_module=None, blacklist=None):
    """
    Create an interprocedural control-flow graph from a directory of JSON files
    created by the `CFGToJSON` LLVM pass.

    Returns a tuple containing:

    1. The CFG
    2. A list of entry nodes into the CFG
    """
    cfg_dict = defaultdict(dict)
    entry_pts = []

    if not blacklist:
        blacklist = set()

    for json_path in glob.glob(os.path.join(json_dir, 'cfg.*.json')):
        logging.debug('Parsing `%s`', json_path)
        with open(json_path, 'r') as json_file:
            data = json.load(json_file)

            # Build the CFG dictionary
            mod = data['module']
            func = data.pop('function')
            cfg_dict[mod][func] = data

    # Turn the CFGs into a networkx graph
    cfg = nx.DiGraph()

    for mod, mod_dict in cfg_dict.items():
        for func, func_dict in mod_dict.items():
            if func in blacklist:
                logging.info('Function `%s` is blacklisted. Skipping', func)
                continue

            # Add nodes
            nodes = func_dict.get('nodes')
            if nodes is None:
                nodes = {}

            for label, data in nodes.items():
                node = _create_node(mod, func, label)
                cfg.add_node(node, module=mod, function=func,
                             start_line=data['start_line'],
                             end_line=data['end_line'])

            # Add intraprocedural edges
            edges = func_dict.get('edges')
            if edges is None:
                edges = []

            for edge in edges:
                src = _create_node(mod, func, edge['src'])
                cfg.add_edge(src, _create_node(mod, func, edge['dst']))

                if func == entry_point and \
                        (entry_module is None or mod == entry_module):
                    entry_pts.append(src)

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
                callee_dict = _find_callee(cfg_dict, callee)
                if 'entry' not in callee_dict:
                    continue

                cfg.add_edge(_create_node(mod, func, call['src']),
                             _create_node(callee_dict['module'], callee,
                                          callee_dict['entry']))

                # Add backward (return) edges
                returns = callee_dict.get('returns')
                if returns is None:
                    logging.debug('function `%s` has no return instruction(s)',
                                  callee)
                    returns = []

                for ret in returns:
                    cfg.add_edge(_create_node(mod, callee, ret),
                                 _create_node(mod, func, call['src']))

            # Count indirect calls and assign them to the nodes that make them
            indirect_calls = func_dict.get('indirect_calls')
            if indirect_calls is None:
                indirect_calls = []

            indirect_call_count = Counter(indirect_calls)
            for n in indirect_call_count:
                node = _create_node(mod, func, n)
                if node not in cfg:
                    cfg.add_node(node)
                cfg.nodes[node]['indirect_calls'] = indirect_call_count[n]

    return cfg, entry_pts
