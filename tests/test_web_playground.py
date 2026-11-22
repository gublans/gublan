"""tests for the online playground in web/: the site builds, lists only files that exist, and gublan's checker and
javascript translator work without pygame or pyopengl, the way they run in the browser."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))

import build_site  # noqa: E402


class PlaygroundSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.site, cls.manifest = build_site.build(os.path.join(cls.temp.name, "site"))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_page_files_are_there(self):
        for name in ["index.html", "playground.js", "playground.css", "bridge.py", "logo.png", ".nojekyll"]:
            self.assertTrue(os.path.isfile(os.path.join(self.site, name)), name)

    def test_manifest_lists_real_files(self):
        for name in self.manifest["python"]:
            self.assertTrue(os.path.isfile(os.path.join(self.site, "gublan", name)), name)
        for example in self.manifest["examples"]:
            self.assertTrue(os.path.isfile(os.path.join(self.site, example["file"])), example["file"])
        self.assertIn("runtimes/gublan_runtime.js", self.manifest["python"])

    def test_version_matches_the_studio(self):
        from studio.version import VERSION
        self.assertEqual(self.manifest["version"], VERSION)

    def test_3d_examples_are_marked(self):
        marked = {example["file"]: example["web"] for example in self.manifest["examples"]}
        self.assertFalse(marked["examples/shapes_3d.gubl"])
        self.assertTrue(marked["examples/hello.gubl"])

    def test_bridge_works_without_pygame_or_opengl(self):
        # a fresh python with only the site's files, like pyodide: bridge.py must stand in for pygame and opengl
        script = (
            "import sys, json; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]); import bridge; "
            "print(json.dumps([json.loads(bridge.translate('use colors\\nprint hi {1 + 2}\\n')), "
            "json.loads(bridge.check('if 1 = 1\\nprint hi\\n')), "
            "json.loads(bridge.translate('if 1 = 1\\n'))]))"
        )
        done = subprocess.run([sys.executable, "-I", "-c", script, os.path.join(self.site, "gublan"), self.site],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        good, problems, bad = json.loads(done.stdout)
        self.assertTrue(good["ok"], good)
        self.assertIn("G.start(main", good["code"])
        self.assertEqual(problems[0]["line"], 1)
        self.assertFalse(bad["ok"])


if __name__ == "__main__":
    unittest.main()
