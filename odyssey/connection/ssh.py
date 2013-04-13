#!/usr/bin/env python

from . import command


class SSH(command.Command):
    def __init__(self, host, cmd=None, args=['-q'], timeout=0.1, connect=True):
        self.host = host
        self.cmd = None
        self.args = args
        command.Command.__init__(self, timeout=timeout)
        if connect:
            self.connect()

    def _build_command(self):
        cmd = command.which('ssh') if self.cmd is None else self.cmd
        args = [self.host, ]
        args += self._parse_args()
        return cmd, args

    def _parse_args(self):
        if isinstance(self.args, str):
            self.args = self.args.split()
        return self.args

    def connect(self):
        return self.run(*self._build_command())
