# Copyright (c) 2012 Spotify AB
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

import subprocess

class InputPipeProcessWrapper(object):
    def __init__(self, command, input_pipe=None):
        self._command = command
        self._input_pipe = input_pipe
        self._process = subprocess.Popen(command,
            stdin=input_pipe,
            stdout=subprocess.PIPE)
        # we want to keep a circular reference to avoid garbage collection
        # when the object is used in, e.g., pipe.read()
        self._process._selfref = self

    def _finish(self):
        if self._input_pipe is not None:
            self._input_pipe.close()
        for line in self:  # exhaust all output...
            pass
        self._process.wait()  # deadlock?
        if self._process.returncode != 0:
            raise RuntimeError('Error reading from pipe. Subcommand exited with non-zero exit status.')

    def close(self):
        self._finish()

    def __del__(self):
        self._finish()

    def __exit__(self, type, value, traceback):
        self._finish()

    def __getattr__(self, name):
        return getattr(self._process.stdout, name)

    def __iter__(self):
        for line in self._process.stdout:
            yield line


class OutputPipeProcessWrapper(object):
    WRITES_BEFORE_FLUSH = 10000

    def __init__(self, command, output_pipe=None):
        self.closed = False
        self._command = command
        self._output_pipe = output_pipe
        self._process = subprocess.Popen(command,
            stdin=subprocess.PIPE,
            stdout=output_pipe)
        self._flushcount = 0

    def write(self, *args, **kwargs):
        self._process.stdin.write(*args, **kwargs)
        self._flushcount += 1
        if self._flushcount == self.WRITES_BEFORE_FLUSH:
            self._process.stdin.flush()
            self._flushcount = 0

    def writeLine(self, line):
        assert '\n' not in line
        self.write(line + '\n')

    def _finish(self):
        """ Closes and waits for subprocess to exit """
        if self._process.returncode is None:
            self._process.stdin.flush()
            self._process.stdin.close()
            self._process.wait()
            self.closed = True

    def __del__(self):
        if not self.closed:
            self.abort()

    def __exit__(self, type, value, traceback):
        if type is None:
            self.close()
        else:
            self.abort()

    def close(self):
        self._finish()
        if self._process.returncode == 0:
            if self._output_pipe is not None:
                self._output_pipe.close()
        else:
            raise RuntimeError('Error when executing command %s' % self._command)

    def abort(self):
        self._finish()

    def __getattr__(self, name):
        return getattr(self._process.stdin, name)


class Format(object):
    """ Interface for format specifications """

    # TODO Move this to spotify.luigi.hdfs
    @classmethod
    def hdfs_reader(cls, path):
        raise NotImplementedError()

    @classmethod
    def pipe_reader(cls, input_pipe):
        raise NotImplementedError()

    # TODO Move this to spotify.luigi.hdfs
    @classmethod
    def hdfs_writer(cls, path):
        raise NotImplementedError()

    @classmethod
    def pipe_writer(cls, output_pipe):
        raise NotImplementedError()


class Gzip(Format):
    @classmethod
    def pipe_reader(cls, input_pipe):
        return InputPipeProcessWrapper(['gunzip'], input_pipe)

    @classmethod
    def pipe_writer(cls, output_pipe):
        return OutputPipeProcessWrapper(['gzip'], output_pipe)