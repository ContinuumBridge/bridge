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

CB_BRIDGE_ROOT = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
CB_HOME = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '../..'))
CB_SOCKET_DIR = CB_BRIDGE_ROOT + "/../thisbridge/"
CB_CONFIG_DIR = CB_BRIDGE_ROOT + "/../thisbridge/"
CB_SIM_LEVEL = os.getenv('CB_SIM_LEVEL', 0)
CB_NO_CLOUD = os.getenv('CB_NO_CLOUD', False)
CB_CONTROLLER_ADDR = os.getenv('CB_CONTROLLER_ADDR', '54.194.28.63')
CB_BRIDGE_EMAIL = os.getenv('CB_BRIDGE_EMAIL', 'noanemail')
CB_BRIDGE_PASSWORD = os.getenv('CB_BRIDGE_PASSWORD', 'notapassword')
CB_LOGGING_LEVEL = getattr(logging, 'DEBUG')
CB_LOGFILE = CB_CONFIG_DIR + 'bridge.log'
