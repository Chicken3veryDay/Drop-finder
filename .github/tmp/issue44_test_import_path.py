from pathlib import Path

path = Path('tests/test_product_detail_reliability.py')
text = path.read_text(encoding='utf-8')
old = '''import unittest

from scripts import autonomous_worker_v4 as production
from scripts import product_detail_reliability as detail_reliability
from scripts import autonomous_merge
'''
new = '''import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for module_name in tuple(sys.modules):
    if module_name == "multi_product" or module_name.startswith("multi_product."):
        del sys.modules[module_name]
try:
    sys.path.remove(str(SCRIPTS))
except ValueError:
    pass
sys.path.insert(0, str(SCRIPTS))

import autonomous_merge
import autonomous_worker_v4 as production
import product_detail_reliability as detail_reliability
'''
if text.count(old) != 1:
    raise SystemExit('unexpected issue 44 test import anchor')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
