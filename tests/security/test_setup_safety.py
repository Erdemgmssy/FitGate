"""No Django runtime, Docker writes or database connections are needed."""
import ast
import importlib.util
import secrets
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]

class SetupSafetyTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('local_postgres',ROOT/'backend/tools/local_postgres.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def test_existing_env_or_backup_configuration_never_calls_docker(self):
        for name in ['.env.fastapi','backups/postgres-docker.env']:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
                with patch.object(self.module.subprocess,'run') as run,self.assertRaises(SystemExit):self.module.preflight(root)
                run.assert_not_called()

    def test_existing_container_or_volume_never_writes_configuration(self):
        for existing_container in [True,False]:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                replies=[SimpleNamespace(returncode=0,stdout='npipe://local',stderr=''),SimpleNamespace(returncode=0,stdout='ready',stderr=''),
                    SimpleNamespace(returncode=0 if existing_container else 1,stdout='',stderr='Error: No such object')]
                if not existing_container:replies.append(SimpleNamespace(returncode=0,stdout='',stderr=''))
                with patch.object(self.module.shutil,'which',return_value='docker'),patch.dict(self.module.os.environ,{'DOCKER_HOST':''}),patch.object(self.module.subprocess,'run',side_effect=replies),self.assertRaises(SystemExit):self.module.preflight(root)
                self.assertEqual(list(root.iterdir()),[])

    def test_missing_or_remote_docker_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(self.module.shutil,'which',return_value=None),self.assertRaises(SystemExit):self.module.preflight(Path(directory))
            with patch.object(self.module.shutil,'which',return_value='docker'),patch.dict(self.module.os.environ,{'DOCKER_HOST':'tcp://remote:2375'}),self.assertRaises(SystemExit):self.module.preflight(Path(directory))

    def test_fresh_install_preflight_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            replies=[SimpleNamespace(returncode=0,stdout='npipe://local',stderr=''),SimpleNamespace(returncode=0,stdout='ready',stderr=''),
                SimpleNamespace(returncode=1,stdout='',stderr='Error: No such object'),SimpleNamespace(returncode=1,stdout='',stderr='Error: no such volume')]
            with patch.object(self.module.shutil,'which',return_value='docker'),patch.dict(self.module.os.environ,{'DOCKER_HOST':''}),patch.object(self.module.subprocess,'run',side_effect=replies) as run:self.module.preflight(root)
            self.assertEqual(list(root.iterdir()),[]);self.assertEqual(run.call_count,4)

    def test_closed_engine_or_unexpected_inspect_error_never_writes(self):
        for failed_engine in [True,False]:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                replies=[SimpleNamespace(returncode=0,stdout='npipe://local',stderr=''),
                    SimpleNamespace(returncode=1 if failed_engine else 0,stdout='',stderr='')]
                if not failed_engine:replies.append(SimpleNamespace(returncode=1,stdout='',stderr='permission denied'))
                with patch.object(self.module.shutil,'which',return_value='docker'),patch.dict(self.module.os.environ,{'DOCKER_HOST':''}),patch.object(self.module.subprocess,'run',side_effect=replies),self.assertRaises(SystemExit):self.module.preflight(root)
                self.assertEqual(list(root.iterdir()),[])

    def test_legacy_seed_has_no_literal_password_and_prompt_validates(self):
        if not (ROOT/'backend/gym').exists():
            for name in ['backend/config','backend/manage.py','backend/serve.py',
                         'backend/requirements-django-backup.txt','backend/requirements.lock.txt']:
                self.assertFalse((ROOT/name).exists(),name)
            return
        tree=ast.parse((ROOT/'backend/gym/management/commands/seed_demo.py').read_text(encoding='utf-8-sig'))
        passwords=[key.value for node in ast.walk(tree) if isinstance(node,ast.Call) for key in node.keywords if key.arg=='password']
        self.assertEqual(len(passwords),2)
        self.assertTrue(all(isinstance(node,ast.Call) and node.func.id=='_password' for node in passwords))
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_password')
        prompt=Mock();namespace={'getpass':SimpleNamespace(getpass=prompt),'CommandError':ValueError}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'legacy-password-validation','exec'),namespace)
        value=secrets.token_urlsafe(18);prompt.side_effect=[value,value]
        self.assertEqual(namespace['_password']('admin'),value)
        for values in [('', ''),('short','short'),(value,value+'x')]:
            prompt.side_effect=values
            with self.assertRaises(ValueError):namespace['_password']('staff')

    def test_current_runtime_has_no_legacy_import_or_automatic_seed(self):
        for path in (ROOT/'backend/app').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) and not node.level else []
                self.assertFalse(any(m.split('.')[0] in ['django','gym','config'] for m in modules),str(path))
        for name in ['FitGate-Launcher.ps1','start-backend.ps1','start-frontend.ps1','start-bridge.ps1']:
            value=(ROOT/name).read_text(encoding='utf-8-sig')
            self.assertNotIn('demo_seed',value);self.assertNotIn('seed_demo',value);self.assertNotIn('manage.py',value)

if __name__=='__main__':unittest.main()
