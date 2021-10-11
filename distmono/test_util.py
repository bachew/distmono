from os import path as osp
from subprocess import CalledProcessError
from distmono.util import sh
import os
import pytest


class TestCmdlist:
    def test_string(self):
        assert sh.cmdlist('echo string') == ['echo', 'string']

    def test_list(self):
        assert sh.cmdlist(['echo', 'list']) == ['echo', 'list']

    def test_tuple(self):
        assert sh.cmdlist(('echo', 'list')) == ['echo', 'list']

    def test_list_non_str(self):
        assert sh.cmdlist(['tail', '-n', 100, 'log']) == ['tail', '-n', '100', 'log']

    def test_empty(self):
        with pytest.raises(ValueError, match='cmd cannot be empty'):
            sh.cmdlist(None)

        with pytest.raises(ValueError, match='cmd cannot be empty'):
            sh.cmdlist('')

        with pytest.raises(ValueError, match='cmd cannot be empty'):
            sh.cmdlist([])

    def test_invalid(self):
        with pytest.raises(ValueError, match='cmd must be a str, list or tuple'):
            sh.cmdlist(sh)


class TestRun:
    def test_run(self, tmpdir):
        tmpfile = tmpdir / 'file'
        assert not tmpfile.exists()
        res = sh.run(['touch', tmpfile.strpath])
        assert res.returncode == 0
        assert tmpfile.exists()

    def test_invalid_command(self):
        with pytest.raises(CalledProcessError):
            sh.run(['ls', '--invalid-option'])

    def test_no_check(self):
        res = sh.run(['ls', '--invalid-option'], check=False)
        assert res.returncode != 0


def test_output():
    assert sh.output(['echo', 'ho']) == 'ho\n'
    assert sh.output('echo hi') == 'hi\n'


class TestChdir:
    def test_direct(self, tmpdir):
        cwd = os.getcwd()
        try:
            sh.chdir(tmpdir.strpath)
            assert tmpdir.samefile(os.getcwd())
        finally:
            sh.chdir(cwd)
            assert osp.samefile(os.getcwd(), cwd)

    def test_context(self, tmpdir):
        cwd = os.getcwd()

        with sh.chdir(tmpdir.strpath):
            assert tmpdir.samefile(os.getcwd())

        assert osp.samefile(os.getcwd(), cwd)
