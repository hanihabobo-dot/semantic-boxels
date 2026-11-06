"""Self-check of index.html: parse, tag balance, img srcs, banned characters and words, img size."""
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
VOID = {'meta', 'link', 'img', 'br', 'hr', 'input', 'source'}


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.imgs, self.ids, self.hrefs = [], [], [], set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'img':
            self.imgs.append(a.get('src'))
        if tag == 'a':
            self.hrefs.append(a.get('href'))
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append(f'unexpected </{tag}> at {self.getpos()}, open: {self.stack[-1] if self.stack else None}')
            return
        self.stack.pop()


p = P()
p.feed(src)
p.close()
print('tag errors:', p.errors or 'none')
print('unclosed:', p.stack or 'none')
missing = [s for s in p.imgs if not os.path.isfile(os.path.join(HERE, s))]
print('img srcs:', len(p.imgs), 'missing:', missing or 'none')
bad_anchor = [h for h in p.hrefs if h and h.startswith('#') and h[1:] not in p.ids]
print('broken in-page links:', bad_anchor or 'none')
print('external links:', sorted({h for h in p.hrefs if h and not h.startswith('#')}))
for name, ch in (('em dash', '—'), ('en dash', '–')):
    print(name, 'count:', src.count(ch))
for f in ('img/MANIFEST.md',):
    t = open(os.path.join(HERE, f), encoding='utf-8').read()
    print(f, 'em/en dashes:', t.count('—') + t.count('–'))
print('"faithful" count:', len(re.findall('faithful', src, re.I)))
print('emoji-range chars:', len(re.findall('[\U0001F300-\U0001FAFF☀-➿]', src)))
print('unverified tags:', src.count('class="tag unv"'), 'measured tags:', src.count('class="tag meas"'))
imgdir = os.path.join(HERE, 'img')
pngs = [f for f in os.listdir(imgdir) if f.endswith('.png')]
total = sum(os.path.getsize(os.path.join(imgdir, f)) for f in pngs)
print('img/ pngs:', len(pngs), 'total bytes:', total)
unused = sorted(set('img/' + f for f in pngs) - set(p.imgs))
print('pngs not used on page:', unused or 'none')
print('html bytes:', len(src.encode('utf-8')))
