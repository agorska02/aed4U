"""Minimal XLSX (Office Open XML) writer on the standard library, for the template and demo files.

Supports text, numbers, booleans and dates, simple formulas with a cached value, bold header row, frozen
header, column widths and default column styles, and drop-down lists (data validation). Output is
deterministic (fixed timestamps in the zip), so tests can check that generated files are up to date.
"""

import datetime
import io
import zipfile
from xml.sax.saxutils import escape, quoteattr

# Cell styles (index in cellXfs below)
DEFAULT, HEADER, DATE, TEXT = 0, 1, 2, 3

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
{sheets}
</Types>"""
SHEET_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{MAIN}">
<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F2"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""
EXCEL_EPOCH = datetime.date(1899, 12, 30)
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


class Formula:
    """A formula cell with its cached result (what Excel shows and stores)."""

    def __init__(self, formula, value):
        self.formula = formula
        self.value = value


def column_letter(index):
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


class Sheet:
    def __init__(self, name, rows, widths=None, column_styles=None, header=True, validations=()):
        self.name = name
        self.rows = rows  # list of rows; a row is a list of cell values (None = empty)
        self.widths = widths or {}  # column index -> width in characters
        self.column_styles = column_styles or {}  # column index -> style for cells typed in later
        self.header = header  # bold, frozen first row
        self.validations = validations  # (column index, list formula, error message)


def _cell(ref, value, style, strings):
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>' if style else ""
    if isinstance(value, Formula):
        if isinstance(value.value, str):
            return f'<c r="{ref}"{s} t="str"><f>{escape(value.formula)}</f><v>{escape(value.value)}</v></c>'
        return f'<c r="{ref}"{s}><f>{escape(value.formula)}</f><v>{value.value!r}</v></c>'
    if isinstance(value, bool):
        return f'<c r="{ref}"{s} t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{value!r}</v></c>'
    if isinstance(value, datetime.date):
        return f'<c r="{ref}" s="{DATE}"><v>{(value - EXCEL_EPOCH).days}</v></c>'
    if strings is None:  # inline string
        return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'
    index = strings.setdefault(value, len(strings))
    return f'<c r="{ref}"{s} t="s"><v>{index}</v></c>'


def _sheet_xml(sheet, strings):
    parts = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{MAIN}" xmlns:r="{REL}">']
    if sheet.header:
        parts.append(
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
            'state="frozen"/></sheetView></sheetViews>'
        )
    columns = sorted(set(sheet.widths) | set(sheet.column_styles))
    if columns:
        parts.append("<cols>")
        for index in columns:
            width = sheet.widths.get(index, 14)
            style = sheet.column_styles.get(index)
            style_attr = f' style="{style}"' if style else ""
            parts.append(f'<col min="{index + 1}" max="{index + 1}" width="{width}" customWidth="1"{style_attr}/>')
        parts.append("</cols>")
    parts.append("<sheetData>")
    for number, row in enumerate(sheet.rows, 1):
        cells = []
        for index, value in enumerate(row):
            style = HEADER if sheet.header and number == 1 else sheet.column_styles.get(index, DEFAULT)
            if style == TEXT and isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(value)
            cells.append(_cell(f"{column_letter(index)}{number}", value, style, strings))
        parts.append(f'<row r="{number}">{"".join(cells)}</row>')
    parts.append("</sheetData>")
    if sheet.validations:
        parts.append(f'<dataValidations count="{len(sheet.validations)}">')
        for index, formula, message in sheet.validations:
            letter = column_letter(index)
            parts.append(
                f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" errorTitle="Wartość spoza listy" '
                f'error={quoteattr(message)} sqref="{letter}2:{letter}2000"><formula1>{escape(formula)}</formula1></dataValidation>'
            )
        parts.append("</dataValidations>")
    parts.append("</worksheet>")
    return "".join(parts)


def workbook_bytes(sheets, inline_strings=False):
    strings = None if inline_strings else {}
    sheet_xml = [_sheet_xml(sheet, strings) for sheet in sheets]
    workbook = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>'
        + "".join(f'<sheet name={quoteattr(sheet.name)} sheetId="{i}" r:id="rId{i}"/>' for i, sheet in enumerate(sheets, 1))
        + "</sheets></workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        + f'<Relationship Id="rId{len(sheets) + 1}" Type="{REL}/styles" Target="styles.xml"/>'
        + f'<Relationship Id="rId{len(sheets) + 2}" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
        + "</Relationships>"
    )
    shared = sorted((strings or {}).items(), key=lambda item: item[1])
    shared_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="{MAIN}" count="{len(shared)}" '
        f'uniqueCount="{len(shared)}">'
        + "".join(f'<si><t xml:space="preserve">{escape(text)}</t></si>' for text, _index in shared)
        + "</sst>"
    )
    files = [
        (
            "[Content_Types].xml",
            CONTENT_TYPES.format(
                sheets="\n".join(
                    f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{SHEET_TYPE}"/>'
                    for i in range(1, len(sheets) + 1)
                )
            ),
        ),
        ("_rels/.rels", ROOT_RELS),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", rels),
        ("xl/styles.xml", STYLES),
        ("xl/sharedStrings.xml", shared_xml),
    ] + [(f"xl/worksheets/sheet{i}.xml", xml) for i, xml in enumerate(sheet_xml, 1)]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files:
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()
