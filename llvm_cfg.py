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


def create_cfg_node(mod, func, identifier):
    """Create a node in the CFG."""
    return '%s.%s.%s' % (mod, func, identifier)


def _find_callee(cfg_dict, callee_func):
    # TODO optimize
    for mod_dict in cfg_dict.values():
        for func, func_dict in mod_dict.items():
            if callee_func == func:
                return func_dict

    return {}


def create_cfg(json_dirs, entry_point='main', entry_module=None,
               blacklist=None):
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

    for json_dir in json_dirs:
        if not os.path.isdir(json_dir):
            raise Exception('Invalid JSON directory `%s`' % json_dir)

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
                logging.info('Function `%s` (in %s) is blacklisted. Skipping',
                             func, func_dict['module'])
                continue
            logging.debug('Processing `%s` (in %s)', func, func_dict['module'])

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
                callee_dict = _find_callee(cfg_dict, callee)
                if 'entry' not in callee_dict:
                    logging.debug('Skipping call to `%s` (from `%s`)', callee,
                                  caller)
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
                    logging.debug('function `%s` (in %s) has no return '
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
