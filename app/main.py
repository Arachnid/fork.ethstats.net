import datetime
from eth_rpc_client import Client
from flask import Flask, request, make_response, send_file
import heapq
import json
import logging

from chainstate import config


graph_length = 16
block_interval_average_len = 500
cache_duration = 3600
cache_blocks = 1000
fork_total_difficulty = 39490902020018959982l
app = Flask(__name__)


def get_nodes():
    if app.debug:
        return config.nodes_debug
    else:
        return config.nodes_prod


clients = {}
def get_client(name):
    if len(clients) == 0:
        clients.update({name: Client(host=node['host'], port=node['port']) for name, node in get_nodes().iteritems()})
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
            app.logger.debug("Fetching block not in cache: %s", h)
            block = self.client.get_block_by_hash(h)
            self.block_hash_cache[h] = block
            if block is not None:
                self.block_number_cache[int(block['number'], 16)] = block
                ts = long(block['timestamp'], 16)
                self.latest = max(self.latest, ts)

                self.tidy_heap()
                heapq.heappush(self.block_hash_heap, (ts, h, int(block['number'], 16)))
        return self.block_hash_cache[h]

    def get_block_by_number(self, num):
        if num not in self.block_number_cache:
            app.logger.debug("Fetching block not in cache: %d", num)
            block = self.client.get_block_by_number(int(num))
            self.block_number_cache[num] = block
            if block is not None:
                self.block_hash_cache[block['hash']] = block
                ts = long(block['timestamp'], 16)
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

            ts = long(block['timestamp'], 16)
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
    for block in blocks.itervalues():
        nodes.append({
            'number': long(block['number'], 16),
            'timestamp': long(block['timestamp'], 16),
            'hash': block['hash'],
            'difficulty': long(block['difficulty'], 16),
            'totalDifficulty': long(block['totalDifficulty'], 16),
            'size': long(block['size'], 16),
            'gasUsed': long(block['gasUsed'], 16),
            'gasLimit': long(block['gasLimit'], 16),
            'parents': [block['parentHash']] + block['uncles'],
        })
    nodes.sort(key=lambda node: node['number'])
    return nodes


lastpolled = {}
latest_blocks = {}
def get_latest_block(clientname):
    if clientname not in lastpolled or datetime.datetime.now() - lastpolled[clientname] > datetime.timedelta(seconds=5):
        latest_blocks[clientname] = get_client(clientname).get_block_by_number('latest', False)
    return latest_blocks[clientname]


def build_block_info(clientname):
    latest = get_latest_block(clientname)
    latestNumber = long(latest['number'], 16)
    latestTimestamp = long(latest['timestamp'], 16)

    earlier = get_fetcher(clientname).get_block_by_number(latestNumber - block_interval_average_len)
    earlierTimestamp = long(earlier['timestamp'], 16)

    difficulty = long(latest['difficulty'], 16)
    blockInterval = (latestTimestamp - earlierTimestamp) / float(block_interval_average_len)
    hashRate = difficulty / blockInterval

    return {
        'number': latestNumber,
        'timestamp': latestTimestamp,
        'hash': latest['hash'],
        'shortHash': latest['hash'][:10],
        'difficulty': difficulty,
        'totalDifficulty': long(latest['totalDifficulty'], 16) - fork_total_difficulty,
        'blockInterval': "%.1f" % (blockInterval,),
        'hashRate': "%.1f" % (hashRate / 1000000000),
        'name': clientname,
        'explore': get_nodes()[clientname]['explorer'] % (latest['hash'],),
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
    response = make_response(json.dumps({
        'latest': blockinfos,
        'nodes': nodes,
    }, indent=4))
    response.headers['Content-Type'] = 'text/json'
    return response


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
