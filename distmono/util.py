from pathlib import PosixPath
import sys
import shlex
import subprocess
import os


class Shell:
    def cmdlist(self, cmd):
        if not cmd:
            raise ValueError('cmd cannot be empty')

        if isinstance(cmd, str):
            return shlex.split(cmd)

        if isinstance(cmd, (list, tuple)):
            return [str(s) for s in cmd]

        raise ValueError('cmd must be a str, list or tuple')

    def run(self, cmd, **kwargs):
        if kwargs.get('shell'):
            # With shell=True, output won't redirect to stdout
            raise ValueError('Please call call_shell()')

        cmd = self.cmdlist(cmd)
        print_cmd = kwargs.pop('print_cmd', True)

        if print_cmd:
            info = ['$', subprocess.list2cmdline(cmd)]

            if kwargs.get('capture_output'):
                info.append(' # output captured')

            self.print(' '.join(info))

        if 'check' not in kwargs:
            kwargs['check'] = True

        if 'encoding' not in kwargs:
            kwargs['encoding'] = self.encoding

        return subprocess.run(cmd, **kwargs)

    @property
    def encoding(self):
        return sys.stdout.encoding or 'utf8'

    def output(self, cmd, **kwargs):
        kwargs['capture_output'] = True
        return self.run(cmd, **kwargs).stdout

    def print(self, msg, **kwargs):
        if 'flush' not in kwargs:
            kwargs['flush'] = True

        error = kwargs.pop('error', False)

        if error:
            kwargs['file'] = sys.stderr

        print(str(msg), **kwargs)

    def chdir(self, work_dir):
        from os import path as osp

        class ChdirContext:
            def __init__(self):
                self.orig_dir = os.getcwd()
                cd(work_dir)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                cd(self.orig_dir)

        def cd(work_dir):
            orig_dir = os.getcwd()

            if not osp.samefile(orig_dir, work_dir):
                self.print(f'$ cd {str(work_dir)!r}')
                os.chdir(work_dir)

        return ChdirContext()

    def temp_dir(self, *, memory=False, prefix=None, suffix=None):
        import shutil
        import tempfile

        class TempDirPath(PosixPath):
            def __enter__(path):
                return path

            def __exit__(path, exc_type, exc_val, exc_tb):
                shutil.rmtree(path)

        parent_dir = self._temp_parent_dir(memory=memory)
        path = tempfile.mkdtemp(dir=parent_dir, prefix=prefix, suffix=suffix)
        return TempDirPath(path)

    def _temp_parent_dir(self, *, memory):
        if memory:
            return PosixPath('/run/shm')

        tmp_dir = self.app_tmp_dir
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir

    def temp_file(self, *, memory=False, prefix=None, suffix=None):
        import tempfile

        class TempFilePath(PosixPath):
            def __enter__(path):
                return path

            def __exit__(path, exc_type, exc_val, exc_tb):
                os.remove(path)

        parent_dir = self._temp_parent_dir(memory=memory)
        fd, path = tempfile.mkstemp(dir=parent_dir, prefix=prefix, suffix=suffix)
        return TempFilePath(path)


sh = Shell()