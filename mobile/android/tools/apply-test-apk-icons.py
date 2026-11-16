"""Apply launcher resources to an Apktool --no-src decode of the test APK.

This does not alter DEX, web assets, permissions, server URL, or sign an APK.
The caller must verify the original artifact and rebuilt payload before signing.
"""
from pathlib import Path
import argparse
import re
import shutil
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument('decoded_directory', type=Path)
args = parser.parse_args()
root = args.decoded_directory.resolve()
repo = Path(__file__).resolve().parents[3]
manifest = root / 'AndroidManifest.xml'
metadata = root / 'apktool.yml'
assert manifest.is_file() and metadata.is_file(), 'Expected a decoded APK directory'
ET.register_namespace('android', 'http://schemas.android.com/apk/res/android')
tree = ET.parse(manifest)
assert tree.getroot().get('package') == 'app.daljam.mobile.test', 'Unexpected APK package'
app = tree.getroot().find('application')
assert app is not None
namespace = '{http://schemas.android.com/apk/res/android}'
app.set(namespace + 'icon', '@mipmap/ic_launcher')
app.set(namespace + 'roundIcon', '@mipmap/ic_launcher')
tree.write(manifest, encoding='utf-8', xml_declaration=True)
text = metadata.read_text(encoding='utf-8')
assert re.search(r'^  versionCode: 1$', text, re.M), 'Expected versionCode 1'
text = re.sub(r'^  versionCode: 1$', '  versionCode: 2', text, flags=re.M)
text = re.sub(r'^  versionName: .+$', '  versionName: 0.1.1-icon-test', text, flags=re.M)
metadata.write_text(text, encoding='utf-8')
resources = repo / 'mobile/android/app/src/main/res'
for source in resources.rglob('*'):
    if source.is_file():
        target = root / 'res' / source.relative_to(resources)
        assert not target.exists(), 'Launcher resource already exists: ' + target.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
print('Applied original Daljam launcher artwork and versionCode 2; DEX untouched.')
