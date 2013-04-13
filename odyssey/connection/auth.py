#!/usr/bin/env python

import getpass

import onetimepass


def get_token(cfg):
    s = cfg.get('auth', 'secret')
    if s == '':
        t = getpass.getpass('OAuth Token:')
    else:
        t = onetimepass.get_totp(s)
    return t


def get_password(cfg):
    p = cfg.get('auth', 'password')
    if p == '':
        p = getpass.getpass('RC Password:')
    return p


def wait_until(prompt, ssh, max_fails):
    s = ''
    fails = 0
    while prompt not in s:
        l = ssh.readline()
        if l == '':
            fails += 1
            if fails > max_fails:
                raise Exception("Failed to read '%s'" % prompt)
        s += l


def authenticate(ssh, cfg, wait=True, max_read_fails=10):
    p = get_password(cfg)
    if wait:
        # TODO define prompts in cfg
        wait_until('Password:', ssh, max_read_fails)
    ssh.sendline(p)
    if wait:
        wait_until('Verification code:', ssh, max_read_fails)
    t = get_token(cfg)
    ssh.sendline(str(t))
