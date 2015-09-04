#!/usr/bin/env python
# cbupgrade.py
# Copyright (C) ContinuumBridge Limited, 2015 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
"""
This script is executed when a bridge is upgraded.
It is included in the bridge_clone that has just been downloaded and called
by the previous version of the bridge while it is still running.
"""
ModuleName = "Upgrader"
import logging
import subprocess
import os
CB_LOGFILE = "/var/log/cbridge.log"

logging.basicConfig(filename=CB_LOGFILE,level=logging.DEBUG,format='%(asctime)s %(levelname)s: %(message)s')
try:
    subprocess.call(["cp", "../../bridge_clone/scripts/cb", "/usr/bin/cb"])
    subprocess.call(["cp", "../../bridge_clone/scripts/cbridge", "/etc/init.d/cbridge"])
    subprocess.call(["update-rc.d", "-f", "ntp", "remove"])
    subprocess.call(["pkill", "ntpd"])
    subprocess.call(["cp", "../../bridge_clone/scripts/fstab", "/etc/fstab"])
    subprocess.call(["cp", "../../bridge_clone/scripts/UpdateXMLs.sh", "/opt/z-way-server/ZDDX/UpdateXMLs.sh"])
    subprocess.call(["cd /opt/z-way-server/ZDDX;" "./UpdateXMLs.sh"])
    if not os.path.exists("../../bridge_clone/node_modules"):
        subprocess.call(["cp", "-r", "../../bridge/node_modules", "../../bridge_clone/node_modules"])
        logging.info("%s Copied old node_modules", ModuleName)
    else:
        logging.info("%s New node_modules", ModuleName)
    logging.info("%s Upgrade script run successfully", ModuleName)
    exit(0)
except Exception as ex:
    logging.warning("%s Problem running upgrade script", ModuleName)
    logging.warning("%s Exception: %s %s", ModuleName, type(ex), str(ex.args))
    exit(1)
