"""Copy required native libraries with permissions and Debian scan metadata."""
from pathlib import Path
import json
import shutil
import subprocess

EXCLUDED_EXTENSIONS = ('_curses', '_curses_panel', 'readline', '_uuid', '_tkinter')


def dependencies(text):
    if 'not found' in text:
        raise ValueError('Unresolved native runtime dependency: ' + text)
    return {Path(word) for line in text.splitlines() for word in line.strip().split() if word.startswith('/')}


def copy_native(source, root):
    """Preserve loader execution permission and merged-/usr SONAME aliases."""
    target = root/str(source.resolve()).lstrip('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    relative = str(source).lstrip('/')
    if source.parts[1] in {'lib', 'lib64', 'lib32'}:
        relative = 'usr/' + relative
    alias = root/relative
    alias.parent.mkdir(parents=True, exist_ok=True)
    if alias != target:
        shutil.copy2(source, alias)
    return target


def collect(root=Path('/runtime'), local=Path('/usr/local')):
    root.mkdir(exist_ok=False)
    for stem in EXCLUDED_EXTENSIONS:
        for path in (local/'lib/python3.12/lib-dynload').glob(stem+'.*.so'):
            path.unlink()
    shutil.copytree(local, root/'usr/local', symlinks=True)
    # Installation stays in the build/QA stages, never in the application image.
    for path in (root/'usr/local/bin').glob('pip*'):
        path.unlink()
    for path in (root/'usr/local/lib/python3.12/site-packages').glob('pip*'):
        if path.is_dir():
            shutil.rmtree(path)
    packages, copied = set(), set()
    for path in [local/'bin/python3.12', *local.rglob('*.so'), *local.rglob('*.so.*')]:
        if not path.is_file():
            continue
        linked = subprocess.run(['ldd', str(path)], text=True, capture_output=True, timeout=30)
        for source in dependencies(linked.stdout):
            if str(source).startswith('/usr/local/') or source in copied:
                continue
            copy_native(source, root)
            copied.add(source)
            result = subprocess.run(['dpkg-query', '-S', str(source.resolve())], text=True, capture_output=True, timeout=30)
            if result.returncode:
                result = subprocess.run(['dpkg-query', '-S', str(source)], text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise ValueError('OS library lacks package provenance: '+str(source))
            packages.update(row.split(': /')[0] for row in result.stdout.splitlines())
    for package in sorted(packages):
        metadata = subprocess.run(['dpkg-query', '-s', package], check=True, text=True, capture_output=True, timeout=30).stdout
        path = root/'var/lib/dpkg/status.d'/package.replace(':', '_')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(metadata)
        name = package.split(':', 1)[0]
        copyright_file = Path('/usr/share/doc')/name/'copyright'
        if copyright_file.is_file():
            target = root/'usr/share/doc'/name/'copyright'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copyright_file, target)
    print(json.dumps(dict(packages=sorted(packages), libraries=sorted(map(str, copied)))))


if __name__ == '__main__':
    collect()
