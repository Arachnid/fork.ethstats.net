import datetime
from eth_rpc_client import Client
from flask import Flask, request, make_response, send_file
import heapq
import json
import logging

from chainstate import config


graph_length=16
app = Flask(__name__)
clients = {nodes[0]: Client(host=nodes[1], port=nodes[2]) for nodes in config.nodes}


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
        if block is None:
            app.logger.debug("Discarded missing block with hash %s", blockhash)
            continue
        block = dict(block)
        block['clients'] = set([clientname])

        blocks[block['hash']] = block
        number = long(block['number'], 16)
        if number > earliest:
            if block['parentHash'] not in blocks:
                frontier.add((clientname, block['parentHash']))
            else:
                blocks[block['parentHash']]['clients'].add(clientname)
            for uncle in block['uncles']:
                if uncle not in blocks:
                    frontier.add((clientname, uncle))
                else:
                    blocks[uncle]['clients'].add(clientname)

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
    for block in blocks.itervalues():
        nodes.append({
            'number': long(block['number'], 16),
            'hash': block['hash'],
            'difficulty': long(block['difficulty'], 16),
            'totalDifficulty': long(block['totalDifficulty'], 16),
            'size': long(block['size'], 16),
            'gasUsed': long(block['gasUsed'], 16),
            'gasLimit': long(block['gasLimit'], 16),
            'parents': [block['parentHash']] + block['uncles'],
            'clients': list(block['clients']),
        })
    return nodes


lastpolled = {}
latest_blocks = {}
def get_latest_block(clientname):
    if clientname not in lastpolled or datetime.datetime.now() - lastpolled[clientname] > datetime.timedelta(seconds=5):
        latest_blocks[clientname] = clients[clientname].get_block_by_number('latest', False)
    return latest_blocks[clientname]


def build_block_info(clientname):
    latest = get_latest_block(clientname)
    return {
        'number': long(latest['number'], 16),
        'hash': latest['hash'],
        'difficulty': long(latest['difficulty'], 16),
        'totalDifficulty': long(latest['totalDifficulty'], 16),
        'name': clientname,
    }
    

def build_block_infos():
    return [build_block_info(clientname) for clientname in clients]


@app.route('/')
def index():
    return send_file('./static/index.html')


@app.route('/blocks')
def blocks(): 
    blockinfos = build_block_infos()
    latest = max(block['number'] for block in blockinfos)
    earliest = max(request.args.get('earliest', latest - 16), latest - 64)
    roots = [(block['name'], block['hash']) for block in blockinfos]
    nodes = build_block_graph(roots, earliest)
    response = make_response(json.dumps({
        'latest': blockinfos,
        'nodes': nodes,
    }, indent=4))
    response.headers['Content-Type'] = 'text/json'
    return response


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
