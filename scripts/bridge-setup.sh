#!/bin/bash
cp ../bridgeconfig/cbsupervisor.init /etc/init.d/cbsupervisor
chmod +x /etc/init.d/cbsupervisor
update-rc.d cbsupervisor defaults
