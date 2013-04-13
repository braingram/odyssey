#!/usr/bin/env python

import io

import cconfig

base = """
[auth]
secret:
password:

[headnode]
host: odyssey
args[list]: ['-q', ]
timeout[float]: 0.1
"""


def get(local=None):
    local = [] if local is None else [local, ]
    local.append('odyssey.ini')
    return cconfig.TypedConfig(
        base=base, user='.odyssey/odyssey.ini', local=local)
