#!/bin/bash

live=$(/geth --exec "eth.syncing != false || (Date.now() / 1000 - eth.getBlock('latest').timestamp) < 300" attach)
if [[ $live == "false" ]]; then
	exit 1
else
	exit 0
fi
