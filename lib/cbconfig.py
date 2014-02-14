#!/usr/bin/env python
# cbsupervisor.py
# Copyright (C) ContinuumBridge Limited, 2014 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Peter Claydon
#
# Contains environment for a bridge

import os

CB_BRIDGE_ROOT = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
CB_SOCKET_DIR = CB_BRIDGE_ROOT + "/thisbridge/"
CB_CONFIG_DIR = CB_BRIDGE_ROOT + "/thisbridge/"
CB_SIM_LEVEL = os.getenv('CB_SIM_LEVEL', 0)
CB_NO_CLOUD = os.getenv('CB_NO_CLOUD', False)
CB_CONTROLLER_ADDR = os.getenv('CB_CONTROLLER_ADDR', '54.194.28.63')
#CB_BRIDGE_EMAIL = os.getenv('CB_BRIDGE_EMAIL', 'cde5fb1645e74314a3e6841a4df0828d@continuumbridge.com')
#CB_BRIDGE_PASSWORD = os.getenv('CB_BRIDGE_PASSWORD', 'zqN17m94GftDvNiWNGls+6tyxryCJFWxzWC5hs/fTmF7YXn4i8eogVa/HzwK5fK2')
CB_BRIDGE_EMAIL = os.getenv('CB_BRIDGE_EMAIL', 'noanemail')
CB_BRIDGE_PASSWORD = os.getenv('CB_BRIDGE_PASSWORD', 'notapassword')

print "CB_SIM_LEVEL = ", CB_SIM_LEVEL
print "CB_NO_CLOUD = ", CB_NO_CLOUD
print "CB_CONTROLLER_ADDR = ", CB_CONTROLLER_ADDR
