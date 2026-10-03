"""The trusted popup bridge is explicit, serialized and fail-closed."""

import threading
import unittest

from projectmapper.adapters.approval import ApprovalBroker
from projectmapper.adapters.session import ApprovalRequest


class ApprovalBrokerTests(unittest.TestCase):
    def request(self):
        return ApprovalRequest("text.save", "mcp", "Save file?", "Save a.py?",
                               ("C:/project/a.py",), "-old\n+new")

    def call_with(self, display):
        stop = threading.Event()
        broker = ApprovalBroker(timeout_seconds=10, display=display)
        server = threading.Thread(target=broker.serve, args=(stop,))
        server.start()
        try:
            result = broker(self.request())
            return result
        finally:
            stop.set()
            server.join(timeout=2)
            self.assertFalse(server.is_alive())

    def test_only_an_explicit_true_decision_approves_and_exact_request_is_shown(self):
        seen = []

        def display(request, timeout):
            seen.append((request, timeout))
            return True

        self.assertTrue(self.call_with(display))
        self.assertEqual(seen, [(self.request(), 10)])

    def test_deny_timeout_and_popup_failure_all_deny(self):
        for display in (lambda _request, _timeout: False,
                        lambda _request, _timeout: None,
                        lambda _request, _timeout: (_ for _ in ()).throw(RuntimeError("UI error"))):
            with self.subTest(display=display):
                self.assertFalse(self.call_with(display))

    def test_approval_arriving_after_deadline_is_denied(self):
        stop = threading.Event()
        broker = ApprovalBroker(timeout_seconds=0.02,
                                display=lambda *_: (threading.Event().wait(0.05) or True))
        server = threading.Thread(target=broker.serve, args=(stop,))
        server.start()
        try:
            self.assertFalse(broker(self.request()))
        finally:
            stop.set()
            server.join(timeout=2)
            self.assertFalse(server.is_alive())

    def test_main_loop_stop_releases_queued_request_as_denied(self):
        stop = threading.Event()
        broker = ApprovalBroker(timeout_seconds=10, display=lambda *_: self.fail("stopped broker displayed a request"))
        result = []
        caller = threading.Thread(target=lambda: result.append(broker(self.request())))
        caller.start()
        for _ in range(100):
            if not broker._requests.empty():
                break
            caller.join(timeout=0.01)
        self.assertFalse(result)
        stop.set()
        server = threading.Thread(target=broker.serve, args=(stop,))
        server.start()
        server.join(timeout=2)
        caller.join(timeout=2)
        self.assertFalse(server.is_alive())
        self.assertFalse(caller.is_alive())
        self.assertEqual(result, [False])


if __name__ == "__main__":
    unittest.main()
