#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Open and modify Microsoft Word 2007 docx files (called 'OpenXML' and
'Office OpenXML' by Microsoft)
Part of Python's docx module - http://github.com/mikemaccana/python-docx
LICENSE below:

Copyright (c) 2009-2010 Mike MacCana

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

2022 Modified by Colin Curtain to import docx only.
"""

import html
import logging
import xml.etree.ElementTree as etree
import zipfile


logger = logging.getLogger(__name__)


# All Word prefixes / namespace matches used in document.xml and core.xml.
# LXML does not use prefixes (just the real namespace) , but these
# make it easier to copy Word output more easily.
nsprefixes = {
    'mo': 'http://schemas.microsoft.com/office/mac/office/2008/main',
    'o': 'urn:schemas-microsoft-com:office:office',
    've': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    # Text Content
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'w10': 'urn:schemas-microsoft-com:office:word',
    'wne': 'http://schemas.microsoft.com/office/word/2006/wordml',
    # Drawing
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
    'mv': 'urn:schemas-microsoft-com:mac:vml',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'v': 'urn:schemas-microsoft-com:vml',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    # Properties (core and extended)
    'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'ep': 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    # Content Types
    'ct': 'http://schemas.openxmlformats.org/package/2006/content-types',
    # Package Relationships
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'pr': 'http://schemas.openxmlformats.org/package/2006/relationships',
    # Dublin Core document properties
    'dcmitype': 'http://purl.org/dc/dcmitype/',
    'dcterms': 'http://purl.org/dc/terms/'}


def opendocx(file):
    """ Open a docx file, return a document XML tree and the zipfile. """
    mydoc = zipfile.ZipFile(file)
    xmlcontent = mydoc.read('word/document.xml')
    document = etree.fromstring(xmlcontent)
    return document, mydoc


def _get_default_font_from_styles(zf):
    """Read the default run font from styles.xml (docDefaults / rPrDefault)."""
    ns_w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    try:
        styles_xml = zf.read('word/styles.xml')
    except KeyError:
        return ''
    styles_root = etree.fromstring(styles_xml)
    doc_defaults = styles_root.find(ns_w + 'docDefaults')
    if doc_defaults is None:
        return ''
    rpr_default = doc_defaults.find(ns_w + 'rPrDefault')
    if rpr_default is None:
        return ''
    rpr = rpr_default.find(ns_w + 'rPr')
    if rpr is None:
        return ''
    rfonts = rpr.find(ns_w + 'rFonts')
    if rfonts is None:
        return ''
    return rfonts.get(ns_w + 'ascii', rfonts.get(ns_w + 'hAnsi', '')) or ''


def getdocumenttext(document):
    """ Return the raw text of a document, as a list of paragraphs. """

    paratextlist = []
    # Compile a list of all paragraph (p) elements
    paralist = []
    for element in document.iter():
        # Find p (paragraph) elements
        if element.tag == '{'+nsprefixes['w']+'}p':
            paralist.append(element)
    # Since a single sentence might be spread over multiple text elements, iterate through each
    # paragraph, appending all text (t) children to that paragraphs text.
    for para in paralist:
        paratext = u''
        # Loop through each paragraph
        for element in para.iter():
            # Find t (text) elements
            if element.tag == '{'+nsprefixes['w']+'}t':
                if element.text:
                    paratext = paratext+element.text
            elif element.tag == '{'+nsprefixes['w']+'}tab':
                paratext = paratext + '\t'
        # Add our completed paragraph text to the list of paragraph text
        if not len(paratext) == 0:
            paratextlist.append(paratext)
    return paratextlist


def _build_style_map(zf):
    """Build a dict mapping styleId -> (font_family, font_size_pt) from
    styles.xml, resolving basedOn inheritance."""
    ns_w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    try:
        styles_root = etree.fromstring(zf.read('word/styles.xml'))
    except (KeyError, etree.ParseError):
        return {}
    # First pass: collect all style definitions
    raw = {}
    for style in styles_root.findall(ns_w + 'style'):
        sid = style.get(ns_w + 'styleId', '')
        rPr = style.find(ns_w + 'rPr')
        if rPr is None:
            continue
        rfonts = rPr.find(ns_w + 'rFonts')
        font_family = ''
        if rfonts is not None:
            font_family = rfonts.get(ns_w + 'ascii', '') or ''
        sz = rPr.find(ns_w + 'sz')
        font_size_pt = 0
        if sz is not None:
            try:
                font_size_pt = int(sz.get(ns_w + 'val', '0')) // 2
            except (ValueError, TypeError):
                pass
        basedOn = style.find(ns_w + 'basedOn')
        parent_id = basedOn.get(ns_w + 'val', '') if basedOn is not None else ''
        raw[sid] = {'font': font_family, 'size': font_size_pt, 'parent': parent_id}
    # Second pass: resolve inheritance
    resolved = {}
    # Sort by depth (shortest chain first)
    def _resolve(sid, visited=None):
        if visited is None:
            visited = set()
        if sid in resolved:
            return resolved[sid]
        if sid in visited or sid not in raw:
            return '', 0
        visited.add(sid)
        entry = raw[sid]
        p_font, p_size = _resolve(entry['parent'], visited)
        font = entry['font'] or p_font
        size = entry['size'] if entry['size'] > 0 else p_size
        resolved[sid] = (font, size)
        return font, size

    for sid in raw:
        _resolve(sid)
    return resolved


def getdocumenttext_html(document, zipfile_=None):
    """Return the text of a document as HTML with bold/italic/underline and
    font family / font size / paragraph alignment preserved.

    Inspects <w:rPr> children for <w:b>, <w:i>, <w:u>, <w:rFonts>,
    <w:sz> elements and wraps run text in the corresponding HTML / CSS.
    Also reads <w:pPr><w:jc> for paragraph alignment and <w:pPr><w:pStyle>
    to look up style-based fonts from styles.xml.
    Falls back to document default font from styles.xml when a run
    has no explicit font.
    Returns a full <html><body>…</body></html> string.
    """
    ns_w = '{' + nsprefixes['w'] + '}'
    # Read document defaults and style map
    default_font = ''
    style_map = {}
    if zipfile_ is not None:
        default_font = _get_default_font_from_styles(zipfile_)
        style_map = _build_style_map(zipfile_)
    html_parts = []
    paralist = []
    for element in document.iter():
        if element.tag == ns_w + 'p':
            paralist.append(element)

    for para in paralist:
        line_parts = []

        # ── Paragraph alignment & style lookup ─────────────────────
        ppr = para.find(ns_w + 'pPr')
        align_attr = ''
        para_font = ''
        para_size_pt = 0
        if ppr is not None:
            jc = ppr.find(ns_w + 'jc')
            if jc is not None:
                val = jc.get(ns_w + 'val') or ''
                _align_map = {
                    'left': 'left', 'center': 'center', 'right': 'right',
                    'both': 'justify',
                }
                css_val = _align_map.get(val, '')
                if css_val:
                    align_attr = f' style="text-align:{css_val}"'
            # Look up paragraph style from styles.xml
            pStyle = ppr.find(ns_w + 'pStyle')
            if pStyle is not None:
                sid = pStyle.get(ns_w + 'val', '')
                if sid in style_map:
                    para_font, para_size_pt = style_map[sid]

        # ── Run loop ──────────────────────────────────────────────
        for element in para.iter():
            if element.tag == ns_w + 'r':
                rpr = element.find(ns_w + 'rPr')
                is_bold = False
                is_italic = False
                is_underline = False
                font_family = ''
                font_size_pt = 0
                if rpr is not None:
                    if rpr.find(ns_w + 'b') is not None:
                        is_bold = True
                    if rpr.find(ns_w + 'i') is not None:
                        is_italic = True
                    if rpr.find(ns_w + 'u') is not None:
                        is_underline = True
                    # Font family — try run-level first, then paragraph style,
                    # then document default
                    rfonts = rpr.find(ns_w + 'rFonts')
                    if rfonts is not None:
                        font_family = rfonts.get(ns_w + 'ascii',
                                                  rfonts.get(ns_w + 'hAnsi', '')) or ''
                    if not font_family:
                        font_family = para_font or default_font
                    # Font size in half-points — convert to pt.
                    # Use run-level size if present, otherwise paragraph style size.
                    if font_size_pt == 0 and para_size_pt > 0:
                        font_size_pt = para_size_pt
                    sz = rpr.find(ns_w + 'sz')
                    if sz is not None:
                        try:
                            font_size_pt = int(sz.get(ns_w + 'val', '0')) // 2
                        except (ValueError, TypeError):
                            pass
                # Get run text
                texts = []
                for t in element.iter(ns_w + 't'):
                    if t.text:
                        texts.append(html.escape(t.text))
                if element.find(ns_w + 'tab') is not None:
                    texts.append('&#9;')
                run_text = ''.join(texts)
                if not run_text:
                    continue
                # Build an inline <span> with CSS for font/size
                css_parts = []
                if font_family:
                    # Quote font names with spaces (e.g. "Courier New")
                    if ' ' in font_family:
                        css_parts.append(f"font-family:'{font_family}'")
                    else:
                        css_parts.append(f'font-family:{font_family}')
                if font_size_pt > 0:
                    css_parts.append(f'font-size:{font_size_pt}pt')
                if css_parts:
                    run_text = f'<span style="{"; ".join(css_parts)}">{run_text}</span>'
                if is_bold:
                    run_text = '<b>' + run_text + '</b>'
                if is_italic:
                    run_text = '<i>' + run_text + '</i>'
                if is_underline:
                    run_text = '<u>' + run_text + '</u>'
                line_parts.append(run_text)
        line = ''.join(line_parts)
        if line:
            html_parts.append(f'<p{align_attr}>' + line + '</p>')
    if html_parts:
        return '<html><body>' + '\n'.join(html_parts) + '</body></html>'
    return ''


'''def get_document_text(document):
    """ Return the raw text of a document. """

    text = ""
    # Compile a list of all paragraph (p) elements
    paralist = []
    for element in document.iter():
        #logger.debug(element.text, element.tag, element.get("pStyle"))
        # Find p (paragraph) elements
        if element.tag == '{'+nsprefixes['w']+'}p':
            paralist.append(element)
    # Since a single sentence might be spread over multiple text elements, iterate through each
    # paragraph, appending all text (t) children to that paragraphs text.
    for para in paralist:
        paratext = u''
        # Loop through each paragraph
        for element in para.iter():
            # Find t (text) elements
            if element.tag == '{'+nsprefixes['w']+'}t':
                if element.text:
                    paratext = paratext+element.text
            elif element.tag == '{'+nsprefixes['w']+'}tab':
                paratext = paratext + '\t'
        # Add our completed paragraph text to the list of paragraph text
        if not len(paratext) == 0:
            text += paratext + "\n\n"
    return text'''


'''def contenttypes():
    types = etree.fromstring(
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/conten'
        't-types"></Types>')
    parts = {
        '/word/theme/theme1.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.theme+xml',
        '/word/fontTable.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.wordprocessingml.fontTable+xml',
        '/docProps/core.xml': 'application/vnd.openxmlformats-package.co'
                                  're-properties+xml',
        '/docProps/app.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.extended-properties+xml',
        '/word/document.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.wordprocessingml.document.main+xml',
        '/word/settings.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.wordprocessingml.settings+xml',
        '/word/numbering.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.wordprocessingml.numbering+xml',
        '/word/styles.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.wordprocessingml.styles+xml',
        '/word/webSettings.xml': 'application/vnd.openxmlformats-officedocu'
                                  'ment.wordprocessingml.webSettings+xml'}
    for part in parts:
        types.append(makeelement('Override', nsprefix=None,
                                 attributes={'PartName': part,
                                             'ContentType': parts[part]}))
    # Add support for filetypes
    filetypes = {'gif': 'image/gif',
                 'jpeg': 'image/jpeg',
                 'jpg': 'image/jpeg',
                 'png': 'image/png',
                 'rels': 'application/vnd.openxmlformats-package.relationships+xml',
                 'xml': 'application/xml'}
    for extension in filetypes:
        types.append(makeelement('Default', nsprefix=None,
                                 attributes={'Extension': extension,
                                             'ContentType': filetypes[extension]}))
    return types'''


'''def picture(relationshiplist, picname, picdescription, pixelwidth=None, pixelheight=None, nochangeaspect=True, nochangearrowheads=True):
    """ Take a relationshiplist, picture file name, and return a paragraph containing the image
    and an updated relationshiplist.
    http://openxmldeveloper.org/articles/462.aspx
    # Create an image. Size may be specified, otherwise it will based on the
    # pixel size of image. Return a paragraph containing the picture
    # Copy the file into the media dir """
    
    print("docx.py picture method used")
    media_dir = join(template_dir, 'word', 'media')
    if not os.path.isdir(media_dir):
        os.mkdir(media_dir)
    shutil.copyfile(picname, join(media_dir, picname))

    # Check if the user has specified a size
    if not pixelwidth or not pixelheight:
        # If not, get info from the picture itself
        pixelwidth, pixelheight = Image.open(picname).size[0:2]

    # OpenXML measures on-screen objects in English Metric Units
    # 1cm = 36000 EMUs
    emuperpixel = 12700
    width = str(pixelwidth * emuperpixel)
    height = str(pixelheight * emuperpixel)

    # Set relationship ID to the first available
    picid = '2'
    picrelid = 'rId'+str(len(relationshiplist)+1)
    relationshiplist.append([
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',
        'media/'+picname])

    # There are 3 main elements inside a picture
    # 1. The Blipfill - specifies how the image fills the picture area (stretch, tile, etc.)
    blipfill = makeelement('blipFill', nsprefix='pic')
    blipfill.append(makeelement('blip', nsprefix='a', attrnsprefix='r',
                    attributes={'embed': picrelid}))
    stretch = makeelement('stretch', nsprefix='a')
    stretch.append(makeelement('fillRect', nsprefix='a'))
    blipfill.append(makeelement('srcRect', nsprefix='a'))
    blipfill.append(stretch)

    # 2. The non visual picture properties
    nvpicpr = makeelement('nvPicPr', nsprefix='pic')
    cnvpr = makeelement('cNvPr', nsprefix='pic',
                        attributes={'id': '0', 'name': 'Picture 1', 'descr': picname})
    nvpicpr.append(cnvpr)
    cnvpicpr = makeelement('cNvPicPr', nsprefix='pic')
    cnvpicpr.append(makeelement('picLocks', nsprefix='a',
                    attributes={'noChangeAspect': str(int(nochangeaspect)),
                                'noChangeArrowheads': str(int(nochangearrowheads))}))
    nvpicpr.append(cnvpicpr)

    # 3. The Shape properties
    sppr = makeelement('spPr', nsprefix='pic', attributes={'bwMode': 'auto'})
    xfrm = makeelement('xfrm', nsprefix='a')
    xfrm.append(makeelement('off', nsprefix='a', attributes={'x': '0', 'y': '0'}))
    xfrm.append(makeelement('ext', nsprefix='a', attributes={'cx': width, 'cy': height}))
    prstgeom = makeelement('prstGeom', nsprefix='a', attributes={'prst': 'rect'})
    prstgeom.append(makeelement('avLst', nsprefix='a'))
    sppr.append(xfrm)
    sppr.append(prstgeom)

    # Add our 3 parts to the picture element
    pic = makeelement('pic', nsprefix='pic')
    pic.append(nvpicpr)
    pic.append(blipfill)
    pic.append(sppr)

    # Now make the supporting elements
    # The following sequence is just: make element, then add its children
    graphicdata = makeelement('graphicData', nsprefix='a',
                              attributes={'uri': 'http://schemas.openxmlforma'
                                                 'ts.org/drawingml/2006/picture'})
    graphicdata.append(pic)
    graphic = makeelement('graphic', nsprefix='a')
    graphic.append(graphicdata)

    framelocks = makeelement('graphicFrameLocks', nsprefix='a',
                             attributes={'noChangeAspect': '1'})
    framepr = makeelement('cNvGraphicFramePr', nsprefix='wp')
    framepr.append(framelocks)
    docpr = makeelement('docPr', nsprefix='wp',
                        attributes={'id': picid, 'name': 'Picture 1',
                                    'descr': picdescription})
    effectextent = makeelement('effectExtent', nsprefix='wp',
                               attributes={'l': '25400', 't': '0', 'r': '0',
                                           'b': '0'})
    extent = makeelement('extent', nsprefix='wp',
                         attributes={'cx': width, 'cy': height})
    inline = makeelement('inline', attributes={'distT': "0", 'distB': "0",
                                               'distL': "0", 'distR': "0"},
                         nsprefix='wp')
    inline.append(extent)
    inline.append(effectextent)
    inline.append(docpr)
    inline.append(framepr)
    inline.append(graphic)
    drawing = makeelement('drawing')
    drawing.append(inline)
    run = makeelement('r')
    run.append(drawing)
    paragraph = makeelement('p')
    paragraph.append(run)
    return relationshiplist, paragraph'''


'''def clean(document):
    """ Perform misc cleaning operations on documents.
    Returns cleaned document. """

    newdocument = document
    # Clean empty text and r tags
    for t in ('t', 'r'):
        rmlist = []
        for element in newdocument.iter():
            if element.tag == '{%s}%s' % (nsprefixes['w'], t):
                if not element.text and not len(element):
                    rmlist.append(element)
        for element in rmlist:
            element.getparent().remove(element)
    return newdocument'''


'''def findTypeParent(element, tag):
    """ Finds fist parent of element of the given type
    @param object element: etree element
    @param string the tag parent to search for
    @return object element: the found parent or None when not found
    """

    p = element
    while True:
        p = p.getparent()
        if p.tag == tag:
            return p

    # Not found
    return None'''
