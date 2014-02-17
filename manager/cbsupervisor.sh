#!/bin/bash
cd /home/bridge/bridge/manager
if [ -f ../thisbridge/thisbridge.sh ]; then
    echo 'Starting bridge'
    # Must source so that exports affect the parent script
    source ../thisbridge/thisbridge.sh
    export PYTHONPATH='/home/bridge/bridge/lib'
    ./cbsupervisor.py >> ../thisbridge/bridge.log 2>&1 &
else
    echo "thisbridge.sh file does not exist"
    exit
fi
