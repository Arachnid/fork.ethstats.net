import datetime
from eth_rpc_client import Client
from flask import Flask
import heapq
from jinja2 import Environment, PackageLoader
import json
import logging

from chainstate import config


graph_length=16
app = Flask(__name__)
clients = {nodes[0]: Client(host=nodes[1], port=nodes[2]) for nodes in config.nodes}
env = Environment(loader=PackageLoader('chainstate', 'templates'))


lastpolled = {}
latest_blocks = {}
def build_block_info(clientname):
    if clientname not in lastpolled or datetime.datetime.now() - lastpolled[clientname] > datetime.timedelta(seconds=5):
        latest_blocks[clientname] = clients[clientname].get_block_by_number('latest', False)
    latest = latest_blocks[clientname]
    return {
        'number': long(latest['number'], 16),
        'hash': latest['hash'],
        'difficulty': long(latest['difficulty'], 16),
        'totalDifficulty': long(latest['totalDifficulty'], 16),
    }
    

def build_block_infos():
    return {clientname: build_block_info(clientname) for clientname in clients}


block_hash_heap = []
block_hash_cache = {}
def get_block_by_hash(clientname, h):
    if h not in block_hash_cache:
        app.logger.debug("Fetching block not in cache: %s", h)
        block = clients[clientname].get_block_by_hash(h)
        block_hash_cache[h] = block
        if block is not None:
            heapq.heappush(block_hash_heap, (long(block['number'], 16), h))
    return block_hash_cache[h]


def find_ancestors(roots, earliest):
    blocks = {}
    frontier = set(roots)
    while frontier:
        clientname, blockhash = frontier.pop()
        block = get_block_by_hash(clientname, blockhash)
        if block is None: continue

        blocks[block['hash']] = block
        number = long(block['number'], 16)
        if number > earliest:
            if block['parentHash'] not in blocks:
                frontier.add((clientname, block['parentHash']))
            for uncle in block['uncles']:
                if uncle not in blocks:
                    frontier.add((clientname, uncle))

    # Clean up the cache
    while True:
        blocknum, blockhash = block_hash_heap[0]
        if blocknum >= earliest: break
        heapq.heappop(block_hash_heap)
        del block_hash_cache[blockhash]

    return blocks


def build_block_graph(roots, earliest):
    blocks = find_ancestors(roots, earliest)
    nodes = []
    edges = []
    for block in blocks.itervalues():
        nodes.append({
            'number': long(block['number'], 16),
            'hash': block['hash'],
            'difficulty': long(block['difficulty'], 16),
            'totalDifficulty': long(block['totalDifficulty'], 16),
            'size': long(block['size'], 16),
            'gasUsed': long(block['gasUsed'], 16),
            'gasLimit': long(block['gasLimit'], 16),
        })
        if block['parentHash'] in blocks:
            edges.append((block['parentHash'], block['hash']))
        for uncle in block['uncles']:
            if uncle in blocks:
                edges.append((uncle, block['hash']))
    return nodes, edges


@app.route('/')
def index():
    template = env.get_template('index.html')
    blockinfos = build_block_infos()
    latest = max(block['number'] for block in blockinfos.values())
    nodes, edges = build_block_graph(
        [(clientname, block['hash']) for clientname, block in blockinfos.iteritems()],
        latest - graph_length)
    return template.render(blockinfos=blockinfos, nodes=json.dumps(nodes), edges=json.dumps(edges), latest=latest)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
