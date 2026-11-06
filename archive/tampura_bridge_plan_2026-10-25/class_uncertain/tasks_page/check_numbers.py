"""List numbers on the page's visible text that do not occur in sources/."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
body = re.sub(r'<style.*?</style>', '', html, flags=re.S)
text = re.sub(r'<[^>]+>', ' ', body)
srcs = ''.join(open(os.path.join(HERE, 'sources', f), encoding='utf-8').read()
               for f in ('TAMPURA_TASKS_SURVEY.md', 'no_fit_case.md'))
nums = sorted(set(re.findall(r'(?<![\w.])\d+(?:\.\d+)?', text)), key=float)
missing = [n for n in nums if not re.search(r'(?<![\d.])' + re.escape(n) + r'(?![\d])', srcs)]
print('numbers on page:', len(nums))
print('not found verbatim in sources:', missing)
