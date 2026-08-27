# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

This code is modified from the stack overflow entry:
https://stackoverflow.com/questions/328356/extracting-text-from-html-file-using-python

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

from html.parser import HTMLParser
from html.entities import name2codepoint
import re
import logging

logger = logging.getLogger(__name__)


class _HTMLToText(HTMLParser):
    """ Convert HTML to text. """

    def __init__(self):

        HTMLParser.__init__(self)
        self._buf = []
        self.hide_output = False

    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'br', 'li', 'h1', 'h2', 'h3') and not self.hide_output:
            self._buf.append('\n')
        elif tag in ('script', 'style'):
            self.hide_output = True

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            self._buf.append('\n')

    def handle_endtag(self, tag):
        if tag == 'p':
            self._buf.append('\n')
        elif tag in ('script', 'style'):
            self.hide_output = False

    def handle_data(self, text):
        if text and not self.hide_output:
            self._buf.append(re.sub(r'\s+', ' ', text))

    def handle_entityref(self, name):
        if name in name2codepoint and not self.hide_output:
            c = chr(name2codepoint[name])
            self._buf.append(c)

    def handle_charref(self, name):
        if not self.hide_output:
            n = int(name[1:], 16) if name.startswith('x') else int(name)
            self._buf.append(chr(n))

    def get_text(self):
        return re.sub(r' +', ' ', ''.join(self._buf))


def html_to_text(html):
    """
    Given a piece of HTML, return the plain text it contains.
    This handles entities and char refs, but not javascript and stylesheets.
    """
    parser = _HTMLToText()
    try:
        parser.feed(html)
        parser.close()
    except Exception as e:  # HTMLParseError:
        logger.debug(str(e))
        pass
    return parser.get_text()


def _parse_css_rules(style_text):
    """Extract a dict mapping selector -> dict of property:value from CSS text.

    Handles tag selectors (``body``, ``h1``, ``p``) and class selectors
    (``.headerstyle``).  Ignores pseudo-classes and complex selectors.
    """
    rules = {}
    # Remove comments
    style_text = re.sub(r'/\*.*?\*/', '', style_text, flags=re.DOTALL)
    # Match each rule block: selector { ... }
    for match in re.finditer(
            r'([^}]+?)\s*\{([^}]+)\}',
            style_text,
            re.DOTALL):
        sel = match.group(1).strip()
        # Only handle simple tag and class selectors
        if re.match(r'^[a-zA-Z0-9_.-]+$', sel) and ':' not in sel:
            declarations = match.group(2)
            props = {}
            for prop_match in re.finditer(
                    r'([\w-]+)\s*:\s*([^;}]+)',
                    declarations):
                key = prop_match.group(1).strip()
                val = prop_match.group(2).strip()
                props[key] = val
            if props:
                rules[sel] = props
    return rules


def _apply_inline_style(tag_text, rules):
    """Apply matching CSS rules as inline ``style=""`` on an opening tag.

    ``tag_text`` is the raw ``<tag ...>`` string.  Returns the same tag
    with CSS properties from matching tag and class selectors merged into
    the ``style`` attribute.
    """
    # Extract tag name
    tag_match = re.match(r'<(\w+)', tag_text)
    if not tag_match:
        return tag_text
    tag_name = tag_match.group(1).lower()

    # Collect applicable properties
    props = {}
    # Tag selector (e.g. body, h1, p)
    if tag_name in rules:
        props.update(rules[tag_name])
    # Class selectors
    classes = re.findall(r'class\s*=\s*["\']([^"\']+)["\']', tag_text)
    for cls in sum((c.split() for c in classes), []):
        key = '.' + cls
        if key in rules:
            props.update(rules[key])

    if not props:
        return tag_text

    # Build inline CSS string
    inline_css = '; '.join(f'{k}: {v}' for k, v in props.items())

    # Merge with existing style attribute
    style_match = re.search(r'style\s*=\s*["\']([^"\']*)["\']', tag_text)
    if style_match:
        existing = style_match.group(1)
        if existing and not existing.endswith(';'):
            existing += ';'
        merged = existing + inline_css
        return tag_text[:style_match.start()] + f'style="{merged}"' + tag_text[style_match.end():]
    else:
        # Insert style before closing >
        if tag_text.endswith('/>'):
            return tag_text.replace('/>', f' style="{inline_css}"/>', 1)
        else:
            return tag_text.replace('>', f' style="{inline_css}">', 1)


def clean_html_for_display(raw_html):
    """Clean HTML for safe display in QTextEdit / QTextDocument.

    * Removes <script>, <style>, <head>, <meta>, <link> elements and their
      contents, but **inlines** CSS rules from <style> blocks into the
      elements' ``style=""`` attributes first, so that tag-based and
      class-based formatting (font-family, font-size, color, etc.) is
      preserved by QTextEdit.
    * Keeps all formatting tags: <b>, <i>, <u>, <p>, <br>,
      <h1>-<h6>, <ul>, <ol>, <li>, <blockquote>, <em>, <strong>, <span>,
      <div>, <pre>, <code>, <hr>, <table>, <tr>, <td>, <th>, <thead>,
      <tbody>, <a>, <img>, <center>, <font>, and inline ``style=""``
      attributes.

    Returns a well-formed HTML string wrapped in <html><body>…</body></html>.
    """
    # 1. Extract and parse CSS from <style> blocks
    css_rules = {}
    for style_match in re.finditer(
            r'<style[^>]*>(.*?)</style>',
            raw_html,
            re.IGNORECASE | re.DOTALL):
        style_content = style_match.group(1)
        css_rules.update(_parse_css_rules(style_content))

    # 2. Strip scripts, styles, head, meta, link (but keep body content)
    cleaned = re.sub(
        r'<script[^>]*>.*?</script>',
        '',
        raw_html,
        flags=re.IGNORECASE | re.DOTALL
    )
    # We remove the content of style tags but we might want to keep style blocks
    # that are inside body? For now, remove all style blocks.
    cleaned = re.sub(
        r'<style[^>]*>.*?</style>',
        '',
        cleaned,
        flags=re.IGNORECASE | re.DOTALL
    )
    cleaned = re.sub(r'<head[^>]*>.*?</head>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'<meta[^>]*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<link[^>]*>', '', cleaned, flags=re.IGNORECASE)

    # 3. Inline CSS rules into tag style attributes
    if css_rules:
        # Find all opening tags and apply matching rules
        def _inline_tag(m):
            return _apply_inline_style(m.group(0), css_rules)
        cleaned = re.sub(r'<[a-zA-Z][^>]*?(?:/>|>)', _inline_tag, cleaned)

    # 3b. Ensure bare <h1>-<h6> headings get a visible size even when the
    # source HTML does not style them (Qt's HTML renderer gives <h1> only
    # bold, no larger font). Only apply when the tag has no font-size yet.
    _HEADING_SIZES = {'h1': '24pt', 'h2': '20pt', 'h3': '17pt',
                      'h4': '14pt', 'h5': '12pt', 'h6': '10pt'}
    def _ensure_heading_size(m):
        tag = m.group(0)
        tag_name = re.match(r'<(\w+)', tag).group(1).lower()
        size = _HEADING_SIZES.get(tag_name)
        if size is None:
            return tag
        if re.search(r'font-size\s*:', tag, re.IGNORECASE):
            return tag
        if 'style="' in tag:
            return tag.replace('style="', f'style="font-size: {size}; ', 1)
        return tag[:-1] + f' style="font-size: {size};">'
    cleaned = re.sub(
        r'<h[1-6][^>]*>',
        _ensure_heading_size,
        cleaned,
        flags=re.IGNORECASE)

    # 3c. Preserve runs of 2+ spaces (and leading spaces) in text content:
    # QTextDocument collapses multiple regular spaces when rendering HTML, so
    # transcripts/indented text would lose their alignment. Convert such runs
    # to &nbsp; (Qt renders them back as normal spaces in toPlainText), but
    # only in TEXT nodes - never inside tags (attribute values) and never in
    # <pre>/<textarea> where whitespace is already significant.
    # Split into tags and text segments; keep tags intact.
    _segments = re.split(r'(<[^>]+>)', cleaned)
    _in_pre = False
    for _si in range(len(_segments)):
        _seg = _segments[_si]
        if _seg.startswith('<'):
            # Track pre/textarea open/close so we skip their content.
            _m = re.match(r'<(/)?(pre|textarea)\b', _seg, re.IGNORECASE)
            if _m:
                if _m.group(1):
                    _in_pre = False
                else:
                    _in_pre = True
            continue
        if _in_pre or not _seg:
            continue
        # Convert runs of 2+ spaces (and leading spaces at segment start).
        _segments[_si] = re.sub(
            r'(?:^| ) +',
            lambda mm: '&nbsp;' * len(mm.group(0)),
            _seg)
    cleaned = ''.join(_segments)
    # 4. Ensure it's wrapped in a basic document structure
    if not cleaned.strip().lower().startswith('<html'):
        cleaned = '<html><body>' + cleaned + '</body></html>'
    return cleaned


def text_to_html(text):
    """ Convert the given text to html, wrapping what looks like URLs with <a> tags,
    converting newlines to <br> tags and converting confusing chars into html
    entities.
    """
    def f(mo):
        t = mo.group()
        if len(t) == 1:
            return {'&': '&amp;', "'": '&#39;', '"': '&quot;', '<': '&lt;', '>': '&gt;'}.get(t)
        return '<a href="%s">%s</a>' % (t, t)
    return re.sub(r'https?://[^] ()"\';]+|[&\'"<>]', f, text)
