#!/usr/bin/env python

import errno
import fcntl
import os
import pty
import resource
import select
import signal
import struct
import sys
import termios
import time


class Timeout(Exception):
    pass


class Command(object):
    def __init__(self, cmd="", args=[], timeout=0.1):
        self.pid = None
        self.child_fd = -1

        self.closed = True
        self.terminated = True
        self.flag_eof = False
        self.status = None
        self.exitstatus = None
        self.signalstatus = None

        self.timeout = timeout
        self.delaybeforesend = 0.05
        self.delayafterclose = 0.1
        self.delayafterterminate = 0.1

        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        self.STDIN_FILENO = pty.STDIN_FILENO
        self.STDOUT_FILENO = pty.STDOUT_FILENO
        self.STDERR_FILENO = pty.STDERR_FILENO

        if cmd != "":
            self.run(cmd, args)

    def run(self, cmd, args=[]):
        self.pid, self.child_fd = pty.fork()
        if self.pid == 0:
            self.child_fd = sys.stdout.fileno()
            self.setwinsize(24, 80)
            if len(args) == 0 or args[0] != cmd:
                args.insert(0, cmd)
            os.execv(cmd, args)
        self.closed = False
        self.terminated = False

    def close(self, force=False):
        if not self.closed:
            self.flush()
            os.close(self.child_fd)
            time.sleep(self.delayafterclose)
            if self.isalive():
                if not self.terminate(force):
                    raise Exception('Could not terminate child process')
                max_fd = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
                for i in range(3, max_fd):
                    try:
                        os.close(i)
                    except OSError:
                        pass
            self.child_fd = -1
            self.closed = True

    def flush(self):
        pass

    def fileno(self):
        return self.child_fd

    def isattry(self):
        return os.isatty(self.child_fd)

    # echo...

    def read_nonblocking(self, size=1, timeout=-1):
        if timeout == -1:
            timeout = self.timeout
        if self.closed:
            raise Exception('I/O operation on closed file')

        if not self.isalive():
            r, w, e = self.__select([self.child_fd], [], [], 0)
            if not r:
                self.flag_eof = True
                raise EOFError('EOF encountered during read')

        r, w, e = self.__select([self.child_fd], [], [], timeout)

        if not r:
            if not self.isalive():
                self.flag_eof = True
                raise EOFError('EOF encountered during read')
            else:
                raise Timeout("read timed out")

        if self.child_fd in r:
            try:
                s = os.read(self.child_fd, size)
            except OSError as E:
                self.flag_eof = True
                raise EOFError('EOF encountered during read: %s' % E)
            if s == '':
                self.flag_eof = True
                raise EOFError('EOF encountered, blank read')
            return s
        raise Exception("unexpected state encountered")

    def read(self, size=-1):
        return self.read_nonblocking(size)

    def readline(self, delimiter='\r\n', maxchars=100):
        s = ""
        while len(s) < maxchars:
            try:
                s += self.read(1)
                if len(s) > len(delimiter) and \
                        s[-len(delimiter):] == delimiter:
                    break
            except Timeout:
                break
        return s

    def readlines(self):
        pass

    def write(self, s):
        self.send(s)

    def writelines(self, lines):
        for l in lines:
            self.write(l)

    def send(self, s):
        time.sleep(self.delaybeforesend)
        return os.write(self.child_fd, s.encode("utf-8"))

    def sendline(self, s=''):
        return self.send(s + os.linesep)

    def sendcontrol(self, char):
        char = char.lower()
        a = ord(char)
        if a >= 97 and a <= 122:
            a = a - ord('a') + 1
            return self.send(chr(a))
        d = {'@': 0, '`': 0,
             '[': 27, '{': 27,
             '\\': 28, '|': 28,
             ']': 29, '}': 29,
             '^': 30, '~': 30,
             '_': 31,
             '?': 127}
        if char not in d:
            return 0
        return self.send(chr(d[char]))

    # sendeof, sendintr

    def eof(self):
        return self.flag_eof

    def terminate(self, force=False):
        if not self.isalive():
            return True
        try:
            self.kill(signal.SIGHUP)
            time.sleep(self.delayafterterminate)
            if not self.isalive():
                return True
            self.kill(signal.SIGCONT)
            time.sleep(self.delayafterterminate)
            if not self.isalive():
                return True
            self.kill(signal.SIGINT)
            time.sleep(self.delayafterterminate)
            if not self.isalive():
                return True
            if force:
                self.kill(signal.SIGKILL)
                time.sleep(self.delayafterterminate)
                if not self.isalive():
                    return True
                else:
                    return False
            return False
        except OSError as e:
            # I think there are kernel timing issues that sometimes cause
            # this to happen. I think isalive() reports True, but the
            # process is dead to the kernel.
            # Make one last attempt to see if the kernel is up to date.
            time.sleep(self.delayafterterminate)
            if not self.isalive():
                return True
            else:
                return False

    def wait(self):
        if self.isalive():
            pid, status = os.waitpid(self.pid, 0)
        else:
            raise Exception('Cannot wait for dead child process.')
        self.exitstatus = os.WEXITSTATUS(status)
        if os.WIFEXITED(status):
            self.status = status
            self.exitstatus = os.WEXITSTATUS(status)
            self.signalstatus = None
            self.terminated = True
        elif os.WIFSIGNALED(status):
            self.status = status
            self.exitstatus = None
            self.signalstatus = os.WTERMSIG(status)
            self.terminated = True
        elif os.WIFSTOPPED(status):
            # You can't call wait() on a child process in the stopped state.
            raise Exception('Called wait() on a stopped child ' +
                    'process. This is not supported. Is some other ' +
                    'process attempting job control with our child pid?')
        return self.exitstatus

    def isalive(self):
        if self.terminated:
            return False

        if self.flag_eof:
            # This is for Linux, which requires the blocking form
            # of waitpid to # get status of a defunct process.
            # This is super-lame. The flag_eof would have been set
            # in read_nonblocking(), so this should be safe.
            waitpid_options = 0
        else:
            waitpid_options = os.WNOHANG

        try:
            pid, status = os.waitpid(self.pid, waitpid_options)
        except OSError as e:
            # No child processes
            if e[0] == errno.ECHILD:
                raise Exception('isalive() encountered condition ' +
                        'where "terminated" is 0, but there was no child ' +
                        'process. Did someone else call waitpid() ' +
                        'on our process?')
            else:
                raise e
        if pid == 0:
            try:
                ### os.WNOHANG) # Solaris!
                pid, status = os.waitpid(self.pid, waitpid_options)
            except OSError as e:
                # This should never happen...
                if e[0] == errno.ECHILD:
                    raise Exception('isalive() encountered condition ' +
                            'that should never happen. There was no child ' +
                            'process. Did someone else call waitpid() ' +
                            'on our process?')
                else:
                    raise e
            if pid == 0:
                return True
        if pid == 0:
            return True

        if os.WIFEXITED(status):
            self.status = status
            self.exitstatus = os.WEXITSTATUS(status)
            self.signalstatus = None
            self.terminated = True
        elif os.WIFSIGNALED(status):
            self.status = status
            self.exitstatus = None
            self.signalstatus = os.WTERMSIG(status)
            self.terminated = True
        elif os.WIFSTOPPED(status):
            raise Exception('isalive() encountered condition ' +
                    'where child process is stopped. This is not ' +
                    'supported. Is some other process attempting ' +
                    'job control with our child pid?')
        return False

    def kill(self, sig):
        if self.isalive():
            os.kill(self.pid, sig)

    def setwinsize(self, rows, cols):
        TIOCSWINSZ = getattr(termios, 'TIOCSWINSZ', -2146929561)
        if TIOCSWINSZ == 2148037735:
            # Same bits, but with sign.
            TIOCSWINSZ = -2146929561
        # Note, assume ws_xpixel and ws_ypixel are zero.
        s = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(self.fileno(), TIOCSWINSZ, s)

    def __select(self, iwtd, owtd, ewtd, timeout=None):
        if timeout is not None:
            end_time = time.time() + timeout
        while True:
            try:
                return select.select(iwtd, owtd, ewtd, timeout)
            except select.error as e:
                if e[0] == errno.EINTR:
                    # if we loop back we have to subtract the
                    # amount of time we already waited.
                    if timeout is not None:
                        timeout = end_time - time.time()
                        if timeout < 0:
                            return([], [], [])
                else:
                    # something else caused the select.error, so
                    # this actually is an exception.
                    raise


def which(cmd):
    for p in os.environ['PATH'].split(os.pathsep):
        fn = os.path.join(p, cmd)
        if os.access(fn, os.X_OK):
            return fn
    raise Exception("Failed to find command: %s in path %s" % cmd,
                    os.environ['PATH'])
