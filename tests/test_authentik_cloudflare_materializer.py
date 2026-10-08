import ast
import unittest
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER_MANIFEST = (
    REPOSITORY_ROOT
    / "apps"
    / "authentik-blueprints"
    / "cloudflare-group-materializer.yaml"
)


class CloudflareGroupMaterializerTests(unittest.TestCase):
    def test_uses_authentik_queryset_to_exclude_anonymous_user(self):
        manifest = next(yaml.safe_load_all(MATERIALIZER_MANIFEST.read_text(encoding="utf-8")))
        script = manifest["data"]["reconcile.py"]
        tree = ast.parse(script)

        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        referenced_attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

        self.assertIn("exclude_anonymous", called_attributes)
        self.assertNotIn("ANONYMOUS_USER_NAME", referenced_attributes)


if __name__ == "__main__":
    unittest.main()
