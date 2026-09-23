from pathlib import Path
import unittest

class ServiceTests(unittest.TestCase):
    def test_read_service_publishes_ready_facade_when_unrelated_sidecar_is_unready(self):
        manifest = Path(__file__).with_name('service-vikunja-read.yaml').read_text()
        self.assertIn('publishNotReadyAddresses: true', manifest)

if __name__ == '__main__': unittest.main()
