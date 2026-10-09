from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree
from docx import Document


ROOT = Path(__file__).resolve().parents[1]
SOURCE_TEMPLATE = ROOT / "templates" / "ford-india-resume-template.docx"
TEMPLATE = ROOT / "templates" / "ford-india-resume-template-enhanced.docx"
TMP = Path(tempfile.gettempdir()) / "ford-india-resume-template.updated.docx"

doc = Document(SOURCE_TEMPLATE)
paragraphs = doc.paragraphs
target = next(p for p in paragraphs if p.text == "{% for exp in experience %}")
target.insert_paragraph_before(
    "{% if career_gaps %}Career Gaps: {% for gap in career_gaps %}{{gap}}{% if not loop.last %}; {% endif %}{% endfor %}{% endif %}"
)

block = [
    "Employer:  {{exp.company}}",
    "Client:  {{exp.client_name}}",
    "Role:  {{exp.position}}",
    "Start Date/ End Date / Duration: {{exp.start_date}} - {{exp.end_date}}",
    "Responsibilities:",
    "{%- for resp in exp.responsibilites %}",
    "{{resp}}",
    "{%- endfor %}",
]
for paragraph, text in zip(paragraphs[60:68], block):
    paragraph.text = text
    paragraph.paragraph_format.space_after = 0
    paragraph.paragraph_format.space_before = 0
    if text in block[:5]:
        for run in paragraph.runs:
            run.bold = True

education_block = [
    "{%- for edu in education %}",
    "{{ edu.degree }}",
    "Duration of Study:",
    "{{ edu.start_date }} - {{ edu.end_date }}",
    "Final Degree, Course of Study, and University Name: {{ edu.degree }} in {{ edu.field_of_study }} from {{ edu.institution }}{% if not loop.last %}{{ \"\\n\" }}{% endif %}",
    "{%- endfor %}",
]
for paragraph, text in zip(paragraphs[9:15], education_block):
    paragraph.text = text
    paragraph.paragraph_format.space_after = 0
    paragraph.paragraph_format.space_before = 0

doc.save(TMP)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
with ZipFile(TMP) as source, ZipFile(TEMPLATE, "w", ZIP_DEFLATED) as destination:
    for item in source.infolist():
        data = source.read(item.filename)
        if item.filename == "word/document.xml":
            root = etree.fromstring(data)
            for text_node in root.xpath(".//w:t", namespaces=NS):
                paragraph = text_node.getparent()
                while paragraph is not None and paragraph.tag != f"{{{W_NS}}}p":
                    paragraph = paragraph.getparent()
                if "candidate_photo" in (text_node.text or "") and paragraph is not None:
                    ppr = paragraph.find(f"{{{W_NS}}}pPr")
                    if ppr is None:
                        ppr = etree.Element(f"{{{W_NS}}}pPr")
                        paragraph.insert(0, ppr)
                    jc = ppr.find(f"{{{W_NS}}}jc")
                    if jc is None:
                        jc = etree.SubElement(ppr, f"{{{W_NS}}}jc")
                    jc.set(f"{{{W_NS}}}val", "center")
                for old, new in {
                    "CDSID:": "i. CDSID:",
                    "Supervisor:": "ii. Supervisor:",
                    "Duration of the Project:": "iii. Duration of the Project:",
                    "Exit reason:": "iv. Exit reason:",
                }.items():
                    if old in (text_node.text or ""):
                        text_node.text = text_node.text.replace(old, new)
                        if paragraph is not None:
                            ppr = paragraph.find(f"{{{W_NS}}}pPr")
                            if ppr is None:
                                ppr = etree.Element(f"{{{W_NS}}}pPr")
                                paragraph.insert(0, ppr)
                            ind = ppr.find(f"{{{W_NS}}}ind")
                            if ind is None:
                                ind = etree.SubElement(ppr, f"{{{W_NS}}}ind")
                            ind.set(f"{{{W_NS}}}left", "0")
                            ind.set(f"{{{W_NS}}}firstLine", "0")
                            jc = ppr.find(f"{{{W_NS}}}jc")
                            if jc is None:
                                jc = etree.SubElement(ppr, f"{{{W_NS}}}jc")
                            jc.set(f"{{{W_NS}}}val", "left")
                            if not paragraph.xpath("./w:r/w:tab", namespaces=NS):
                                first_run = paragraph.find(f"{{{W_NS}}}r")
                                tab_run = etree.Element(f"{{{W_NS}}}r")
                                etree.SubElement(tab_run, f"{{{W_NS}}}tab")
                                if first_run is not None:
                                    paragraph.insert(paragraph.index(first_run), tab_run)
                                else:
                                    paragraph.append(tab_run)
            data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
        destination.writestr(item, data)

TMP.unlink()
