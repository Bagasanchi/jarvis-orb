import ast
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


class PublicConfigTests(unittest.TestCase):
    def load_config(self, directory, **overrides):
        environment = {k: v for k, v in os.environ.items() if not k.startswith('JARVIS_')}
        environment.update(JARVIS_DATA_DIR=directory, **overrides)
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(Path(__file__).resolve().parents[1] / 'config.example.py'))

    def test_public_install_has_no_bundled_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.load_config(directory)['LLM_API_KEY'], '')

    def test_environment_overrides_private_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'credentials.json').write_text(json.dumps({'cloud_api_key': 'fixture-value'}))
            self.assertEqual(self.load_config(directory, JARVIS_CLOUD_API_KEY='environment-value')['LLM_API_KEY'], 'environment-value')

    def test_malformed_private_file_uses_empty_default(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'credentials.json').write_text('[]')
            self.assertEqual(self.load_config(directory)['LLM_API_KEY'], '')

    def test_source_config_has_no_literal_api_key(self):
        path = Path(__file__).resolve().parents[1] / 'jarvis' / 'config.py'
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'LLM_API_KEY' for t in node.targets):
                self.assertFalse(isinstance(node.value, ast.Constant) and bool(node.value.value))
