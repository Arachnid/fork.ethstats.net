#!/bin/bash

live=$(/geth --exec "eth.syncing == false" attach)
if [[ $live == "false" ]]; then
	exit 1
else
	exit 0
fi
