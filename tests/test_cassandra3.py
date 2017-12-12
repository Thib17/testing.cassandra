# -*- coding: utf-8 -*-

import os
import sys
import signal
import cassandra.cluster as cassandra_cluster
import tempfile
import testing.cassandra3
from mock import patch
from time import sleep
from shutil import rmtree

if sys.version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest


class TestCassandra(unittest.TestCase):

    def setUp(self):
        self.cluster = self.session = None

    def tearDown(self):
        self._shutdown()

    def _connect(self, cassandra):
        if not self.cluster:
            self.cluster = cassandra_cluster.Cluster(
                **cassandra.connection_params()
            )
        if not self.session:
            self.session = self.cluster.connect()
        return self.session

    def _shutdown(self):
        if self.session is not None:
            self.session.shutdown()
            self.session = None
        if self.cluster is not None:
            self.cluster.shutdown()
            self.cluster = None

    def test_basic(self):
        # start cassandra server
        cassandra = testing.cassandra3.Cassandra()
        self.assertIsNotNone(cassandra)
        self.assertEqual(cassandra.server_list(),
                         ['127.0.0.1:%d' % cassandra.cassandra_yaml['rpc_port']])

        # connect to cassandra
        session = self._connect(cassandra)
        self.assertIsNotNone(session)

        # shutting down
        pid = cassandra.server_pid
        self.assertTrue(cassandra.is_alive())

        cassandra.stop()
        sleep(1)

        self.assertFalse(cassandra.is_alive())
        with self.assertRaises(OSError):
            os.kill(pid, 0)  # process is down

    def test_stop(self):
        # start cassandra server
        cassandra = testing.cassandra3.Cassandra()
        self.assertTrue(os.path.exists(cassandra.base_dir))
        self.assertTrue(cassandra.is_alive())

        # call stop()
        cassandra.stop()
        self.assertFalse(os.path.exists(cassandra.base_dir))
        self.assertFalse(cassandra.is_alive())

        # call stop() again
        cassandra.stop()
        self.assertFalse(os.path.exists(cassandra.base_dir))
        self.assertFalse(cassandra.is_alive())

        # delete cassandra object after stop()
        del cassandra

    def test_with_cassandra(self):
        with testing.cassandra3.Cassandra() as cassandra:
            self.assertIsNotNone(cassandra)

            # connect to cassandra
            conn = self._connect(cassandra)
            self.assertIsNotNone(conn)
            self.assertTrue(cassandra.is_alive())

        self.assertFalse(cassandra.is_alive())

    def test_multiple_cassandra(self):
        cassandra1 = testing.cassandra3.Cassandra()
        cassandra2 = testing.cassandra3.Cassandra()
        self.assertNotEqual(cassandra1.server_pid, cassandra2.server_pid)

        self.assertTrue(cassandra1.is_alive())
        self.assertTrue(cassandra2.is_alive())

    @patch("testing.cassandra3.find_cassandra_home")
    def test_cassandra_is_not_found(self, find_cassandra_home):
        find_cassandra_home.side_effect = RuntimeError

        with self.assertRaises(RuntimeError):
            testing.cassandra3.Cassandra()

    def test_fork(self):
        cassandra = testing.cassandra3.Cassandra()
        if os.fork() == 0:
            del cassandra
            cassandra = None
            os.kill(os.getpid(), signal.SIGTERM)  # exit tests FORCELY
        else:
            os.wait()
            sleep(1)
            self.assertTrue(cassandra.is_alive())  # process is alive (delete mysqld obj in child does not effect)

    def test_stop_on_child_process(self):
        cassandra = testing.cassandra3.Cassandra()
        if os.fork() == 0:
            cassandra.stop()
            os.kill(cassandra.server_pid, 0)  # process is alive (calling stop() is ignored)
            os.kill(os.getpid(), signal.SIGTERM)  # exit tests FORCELY
        else:
            os.wait()
            sleep(1)
            self.assertTrue(cassandra.is_alive())  # process is alive (calling stop() in child is ignored)

    def test_copy_data_from(self):
        try:
            tmpdir = tempfile.mkdtemp()

            # create new database
            with testing.cassandra3.Cassandra(base_dir=tmpdir) as cassandra:
                session = self._connect(cassandra)
                session.execute('CREATE TABLE IF NOT EXISTS test.hello (k INT, PRIMARY KEY(k))')
                session.execute('INSERT INTO test.hello (k) VALUES(1)')

            self._shutdown()
            # flushing MemTable (commit log) to SSTable
            with testing.cassandra3.Cassandra(base_dir=tmpdir) as cassandra:
                pass

            # create another database from first one
            data_dir = os.path.join(tmpdir, 'data')
            with testing.cassandra3.Cassandra(copy_data_from=data_dir) as cassandra:
                session = self._connect(cassandra)
                results = list(session.execute('SELECT k FROM test.hello'))

                self.assertEqual(1, results[0].k)
        finally:
            rmtree(tmpdir)

    def test_skipIfNotInstalled_found(self):
        @testing.cassandra3.skipIfNotInstalled
        def testcase():
            pass

        self.assertEqual(False, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(False, hasattr(testcase, '__unittest_skip_why__'))

    @patch("testing.cassandra3.find_cassandra_home")
    def test_skipIfNotInstalled_notfound(self, find_cassandra_home):
        find_cassandra_home.side_effect = RuntimeError

        @testing.cassandra3.skipIfNotInstalled
        def testcase():
            pass

        self.assertEqual(True, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(True, hasattr(testcase, '__unittest_skip_why__'))
        self.assertEqual(True, testcase.__unittest_skip__)
        self.assertEqual("Cassandra not found", testcase.__unittest_skip_why__)

    def test_skipIfNotInstalled_with_args_found(self):
        cassandra_home = testing.cassandra3.find_cassandra_home()
        path = os.path.join(cassandra_home, 'bin', 'cassandra')

        @testing.cassandra3.skipIfNotInstalled(path)
        def testcase():
            pass

        self.assertEqual(False, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(False, hasattr(testcase, '__unittest_skip_why__'))

    def test_skipIfNotInstalled_with_args_notfound(self):
        @testing.cassandra3.skipIfNotInstalled("/path/to/anywhere")
        def testcase():
            pass

        self.assertEqual(True, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(True, hasattr(testcase, '__unittest_skip_why__'))
        self.assertEqual(True, testcase.__unittest_skip__)
        self.assertEqual("Cassandra not found", testcase.__unittest_skip_why__)

    def test_skipIfNotFound_found(self):
        @testing.cassandra3.skipIfNotFound
        def testcase():
            pass

        self.assertEqual(False, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(False, hasattr(testcase, '__unittest_skip_why__'))

    @patch("testing.cassandra3.find_cassandra_home")
    def test_skipIfNotFound_notfound(self, find_cassandra_home):
        find_cassandra_home.side_effect = RuntimeError

        @testing.cassandra3.skipIfNotFound
        def testcase():
            pass

        self.assertEqual(True, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(True, hasattr(testcase, '__unittest_skip_why__'))
        self.assertEqual(True, testcase.__unittest_skip__)
        self.assertEqual("Cassandra not found", testcase.__unittest_skip_why__)
