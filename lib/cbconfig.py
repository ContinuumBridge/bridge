#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
# Contains environment for a bridge

import os
import logging

def str2bool(v):
      return v.lower() in ("yes", "true", "t", "1")

CB_BRIDGE_ROOT = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
CB_HOME = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '../..'))
CB_SOCKET_DIR = CB_HOME + "/thisbridge/"
CB_CONFIG_DIR = CB_HOME + "/thisbridge/"
CB_MANAGER_EXIT = CB_CONFIG_DIR + "/manager_exit"
CB_SIM_LEVEL = os.getenv('CB_SIM_LEVEL', '0')
CB_NO_CLOUD = str2bool(os.getenv('CB_NO_CLOUD', 'False'))
CB_CONTROLLER_ADDR = os.getenv('CB_CONTROLLER_ADDR', '54.194.28.63')
CB_BRIDGE_EMAIL = os.getenv('CB_BRIDGE_EMAIL', 'noanemail')
CB_BRIDGE_PASSWORD = os.getenv('CB_BRIDGE_PASSWORD', 'notapassword')
CB_LOGGING_LEVEL = getattr(logging, os.getenv('CB_LOG_ENVIRONMENT', 'INFO'))
CB_LOGFILE = CB_CONFIG_DIR + 'bridge.log'
CB_DEV_BRIDGE = str2bool(os.getenv('CB_DEV_BRIDGE', 'False'))
CB_WLAN_TEST = str2bool(os.getenv('CB_WLAN_TEST', 'False'))
CB_GET_SSID_TIMEOUT = int(os.getenv('CB_GET_SSID_TIMEOUT', '300'))
CB_ZWAVE_BRIDGE = str2bool(os.getenv('CB_ZWAVE_BRIDGE', 'False'))
