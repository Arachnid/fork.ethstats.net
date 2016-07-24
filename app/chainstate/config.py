nodes_debug = {
    'Hard fork': {
    	'host': 'localhost',
    	'port': 8546,
    	'explorer': "https://etherscan.io/block/%s",
    },
    'Non-fork': {
    	'host': 'localhost',
    	'port': 8547,
    	'explorer': "http://classic.aakilfernandes.com/#/block/%s",
    },
}

nodes_prod = {
    'Hard fork': {
    	'name': 'Hard fork',
    	'host': 'geth-fork',
    	'port': 8545,
    	'explorer': "https://etherscan.io/block/%s",
    },
    'Non-fork': {
    	'host': 'geth-nofork',
    	'port': 8545,
    	'explorer': "http://classic.aakilfernandes.com/#/block/%s",
    }
}
