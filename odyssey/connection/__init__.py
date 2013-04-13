#!/usr/bin/env python

import logging

from .auth import authenticate
from . import config
from .ssh import SSH


def connect(cfg=None, **kwargs):
    if cfg is None:
        cfg = config.get()
    if isinstance(cfg, str):
        cfg = config.get(cfg)

    kwargs.update(dict([(k, cfg.get('headnode', k)) for k
                        in cfg.options('headnode')]))
    host = kwargs.pop('host')
    logging.info('Creating SSH connection to %s: %s' % (host, kwargs))
    conn = SSH(host, **kwargs)
    authenticate(conn, cfg)
    return conn
