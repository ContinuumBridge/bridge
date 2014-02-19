#!/bin/bash
# Runs cbsupervisor with local bridge controller & outputs to shell rather than log file
cd /home/bridge/bridge/manager
if [ -f ../thisbridge/thisbridge.sh ]; then
    echo 'Starting bridge'
    # Must source so that exports affect the parent script
    source ../thisbridge/thisbridge.sh
    export PYTHONPATH='/home/bridge/bridge/lib'
    CB_NO_CLOUD='True' ./cbsupervisor.py
else
    echo "thisbridge.sh file does not exist"
    exit
fi
