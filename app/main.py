import datetime
import web3

from web3 import Web3, HTTPProvider 
from flask import Flask, request, make_response, send_file
import heapq
import json
import logging
import hexbytes
from chainstate import config


graph_length = 16
block_interval_average_len = 500
cache_duration = 3600
cache_blocks = 1000
fork_total_difficulty = 8352655385330519099922
app = Flask(__name__)


def get_nodes():
    if app.debug:
        return config.nodes_debug
    else:
        return config.nodes_prod


clients = {}
def get_client(name):
    if len(clients) == 0:
        clients.update({name: Web3(Web3.HTTPProvider(node['url'])) for name, node in get_nodes().items()})
#        clients.update({name: Client(host=node['host'], port=node['port']) for name, node in get_nodes().iteritems()})
    return clients[name]


class BlockFetcher(object):
    def __init__(self, client, cache_duration=3600, cache_blocks=1000):
        self.cache_duration = cache_duration
        self.cache_blocks = cache_blocks
        self.client = client
        self.block_hash_heap = []
        self.block_hash_cache = {}
        self.block_number_cache = {}
        self.latest = 0

    def get_block_by_hash(self, h):
        if h not in self.block_hash_cache:
            if type(h) == hexbytes.HexBytes:
                h = h.hex()
            app.logger.debug("Fetching block not in cache: %s", h)
            block = self.client.eth.getBlock(h)
            self.block_hash_cache[h] = block
            if block is not None:
                self.block_number_cache[block['number']] = block
                ts = block['timestamp']
                self.latest = max(self.latest, ts)

                self.tidy_heap()
                heapq.heappush(self.block_hash_heap, (ts, h, block['number']))
        return self.block_hash_cache[h]

    def get_block_by_number(self, num):
        if num not in self.block_number_cache:
            app.logger.debug("Fetching block not in cache: %d", num)
            block = self.client.eth.getBlock(int(num))
            self.block_number_cache[num] = block
            if block is not None:
                self.block_hash_cache[block['hash']] = block
                ts = block['timestamp']
                self.latest = max(self.latest, ts)

                self.tidy_heap()
                heapq.heappush(self.block_hash_heap, (ts, block['hash'], num))
        return self.block_number_cache[num]

    def tidy_heap(self):
        while len(self.block_hash_heap) > self.cache_blocks and self.block_hash_heap[0][0] < self.latest - self.cache_duration:
            blockts, blockhash, blocknum = heapq.heappop(self.block_hash_heap)
            del block_number_cache[blocknum]
            del block_hash_cache[blockhash]


fetchers = {}
def get_fetcher(name):
    if len(fetchers) == 0:
        fetchers.update({name: BlockFetcher(get_client(name), cache_duration, cache_blocks) for name in get_nodes()})
    return fetchers[name]


def find_ancestors(roots, earliest):
    blocks = {}
    for clientname, roothash in roots:
        frontier = set([roothash])
        while frontier:
            blockhash = frontier.pop()
            block = get_fetcher(clientname).get_block_by_hash(blockhash)
            if block is None:
                app.logger.debug("Discarded missing block with hash %s", blockhash)
                continue

            block = dict(block)
            blocks[block['hash']] = block

            ts = block['timestamp']
            if ts >= earliest:
                if block['parentHash'] not in blocks:
                    frontier.add(block['parentHash'])
                for uncle in block['uncles']:
                    if uncle not in blocks:
                        frontier.add(uncle)

    return blocks


def build_block_graph(roots, earliest):
    blocks = find_ancestors(roots, earliest)
    nodes = []
    for (h, block) in blocks.items():
        nodes.append({
            'number': block['number'],
            'timestamp': block['timestamp'],
            'hash': block['hash'].hex(),
            'difficulty': block['difficulty'],
            'totalDifficulty': block['totalDifficulty'],
            'size': block['size'],
            'gasUsed': block['gasUsed'],
            'gasLimit': block['gasLimit'],
            'parents': [block['parentHash'].hex()] + [u.hex() for u in block['uncles']],
        })
    nodes.sort(key=lambda node: node['number'])
    return nodes


lastpolled = {}
latest_blocks = {}
def get_latest_block(clientname):
    if clientname not in lastpolled or datetime.datetime.now() - lastpolled[clientname] > datetime.timedelta(seconds=5):
        latest_blocks[clientname] = get_client(clientname).eth.getBlock('latest', False)
    return latest_blocks[clientname]


def build_block_info(clientname):
    latest = get_latest_block(clientname)
#    latestNumber = int(latest['number'], 16)
    latestNumber = int(latest['number'])    
    latestTimestamp = latest['timestamp']

    earlier = get_fetcher(clientname).get_block_by_number(latestNumber - block_interval_average_len)
    earlierTimestamp = earlier['timestamp']

    difficulty = latest['difficulty']
    blockInterval = (latestTimestamp - earlierTimestamp) / float(block_interval_average_len)
    hashRate = difficulty / blockInterval

    return {
        'number': latestNumber,
        'timestamp': latestTimestamp,
        'hash': latest['hash'].hex(),
        'shortHash': latest['hash'].hex()[:10],
        'difficulty': difficulty,
        'totalDifficulty': latest['totalDifficulty'] - fork_total_difficulty,
        'blockInterval': "%.1f" % (blockInterval,),
        'hashRate': "%.1f" % (hashRate / 1000000000),
        'name': clientname,
        'explore': get_nodes()[clientname]['explorer'] % (latest['hash'].hex(),),
    }
    

def build_block_infos():
    infos = [build_block_info(name) for name in get_nodes()]
    max_difficulty = float(max(info['difficulty'] for info in infos))
    max_total_difficulty = max(info['totalDifficulty'] for info in infos)
    for info in infos:
        info['difficulty'] = "%.2f" % (100 * info['difficulty'] / float(max_difficulty),)
        info['totalDifficulty'] = "%.2f" % (100 * info['totalDifficulty'] / float(max_total_difficulty),)
    return infos


@app.route('/')
def index():
    return send_file('./static/index.html')


@app.route('/blocks')
def blocks(): 
    blockinfos = build_block_infos()
    latest = max(block['timestamp'] for block in blockinfos)
    earliest = max(int(request.args.get('since', latest - 300)), latest - cache_duration)
    roots = [(block['name'], block['hash']) for block in blockinfos]
    nodes = build_block_graph(roots, earliest)
    #app.logger.debug(blockinfos)
    #app.logger.debug(nodes)
    response = make_response(json.dumps({
        'latest': blockinfos,
        'nodes': nodes,
    }, indent=4))
    response.headers['Content-Type'] = 'text/json'
    return response


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
