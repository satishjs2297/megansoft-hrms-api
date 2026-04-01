# Templates Directory

This directory contains pre-built resume templates optimized for different regions and hiring requirements.

## Available Templates

### 1. Ford India Template
**File:** `ford-india-resume-template.docx`

**Purpose:** Tailored for Ford India job applications and hiring requirements

**Features:**
- Optimized for Indian resume standards
- Includes company-specific sections for Ford India
- Professional formatting suitable for Indian corporate environment
- Supports all standard resume sections

**Best For:**
- Ford India positions
- India-based candidates
- Regional compliance and standards

**Placeholders Supported:**
- Contact information (name, email, phone, location)
- Professional summary
- Technical skills (categorized)
- Work experience with company, position, dates, responsibilities
- Education details
- Certifications

---

### 2. Ford US Template
**File:** `ford-us-resume-template-v1.docx`

**Purpose:** Tailored for Ford US job applications and hiring requirements

**Features:**
- Optimized for US resume standards
- Includes company-specific sections for Ford US
- Professional formatting suitable for US corporate environment
- Supports all standard resume sections

**Best For:**
- Ford US positions
- US-based candidates
- US compliance and standards

**Placeholders Supported:**
- Contact information (name, email, phone, location)
- Professional summary
- Technical skills (categorized)
- Work experience with company, position, dates, responsibilities
- Education details
- Certifications

---

## Adding New Templates

To add a new template:

1. **Create the template in Microsoft Word or LibreOffice**
   - Use professional formatting
   - Include sections for: name, email, phone, skills, experience, education

2. **Add Jinja2 placeholders**
   - Use `{{ }}` for single values
   - Use `{% for %}...{% endfor %}` for lists
   - Examples:
     ```
     {{ name }}
     {{ email }}
     {% for skill in skills %}
       {{ skill.category }}: {{ skill.skills | join(", ") }}
     {% endfor %}
     ```

3. **Save as DOCX**
   - File → Save As → .docx format
   - Save in this templates directory

4. **Update streamlit_app.py**
   - Add template option to the radio button choices
   - Add template loading logic

5. **Update TEMPLATE_SELECTION.md**
   - Document the new template
   - Add usage instructions

---

## Template Structure

Each template should include these sections (order may vary):

### Header
```
{{ name }}
{{ email }} | {{ phone }} | {{ location }}
```

### Professional Summary (Optional)
```
{{ summary }}
```

### Technical Skills
```
{% for skill in skills %}
{{ skill.category }}: {{ skill.skills | join(", ") }}
{% endfor %}
```

### Professional Experience
```
{% for exp in experience %}
{{ exp.position }} at {{ exp.company }}
{{ exp.start_date }} – {{ exp.end_date }}
{% for desc in exp.description %}
• {{ desc }}
{% endfor %}

{% endfor %}
```

### Education
```
{% for edu in education %}
{{ edu.degree }} in {{ edu.field_of_study }}
{{ edu.institution }}
Graduated: {{ edu.graduation_date }}
{% endfor %}
```

### Certifications (Optional)
```
{% for cert in certifications %}
{{ cert.name }} – {{ cert.issuer }} ({{ cert.date }})
{% endfor %}
```

---

## Template Editing Tips

### In Microsoft Word

1. **Insert placeholders**
   - Type `{{ name }}` where you want the name
   - Type `{{ email }}` where you want the email
   - And so on for other fields

2. **Use loops for lists**
   ```
   {% for skill in skills %}
   {{ skill.category }}: {{ skill.skills | join(", ") }}
   {% endfor %}
   ```

3. **Formatting**
   - Use consistent fonts and sizes
   - Use bullet points for descriptions
   - Add spacing between sections

4. **Save as DOCX**
   - File → Save As
   - Select "Word Document (.docx)"
   - Do NOT save as .doc or .txt

### In LibreOffice Writer

1. **Insert placeholders**
   - Same as Word, type the placeholders directly

2. **Save as DOCX**
   - File → Save As
   - Select "Microsoft Word 2007-2019 (.docx)"

---

## Testing Your Template

1. **Start the Resume Builder**
   ```bash
   streamlit run streamlit_app.py
   ```

2. **Select your template**
   - Upload Custom Template → Select your new template file

3. **Upload a sample resume**
   - Use a test resume to validate

4. **Check output**
   - Review the generated resume
   - Verify all placeholders filled correctly
   - Check formatting looks good

---

## Common Placeholder Mistakes

❌ **Wrong:**
- `{name}` - Missing extra braces
- `${{name}}` - Wrong syntax
- `{{Name}}` - Wrong case (should be lowercase)
- `for skill in skills` - Missing `{% %}` braces

✅ **Correct:**
- `{{ name }}` - Single value
- `{% for skill in skills %}...{% endfor %}` - Loop
- `{{ summary }}` - Lowercase variable names
- `{{ skill.category }}` - Nested properties with dot notation

---

## Available Variables Reference

### Contact Information
- `{{ name }}` - Full name
- `{{ first_name }}` - First name
- `{{ last_name }}` - Last name
- `{{ email }}` - Email address
- `{{ phone }}` - Phone number
- `{{ location }}` - City/location
- `{{ linkedin }}` - LinkedIn URL
- `{{ github }}` - GitHub URL
- `{{ website }}` - Personal website

### Summary
- `{{ summary }}` -Professional summary text

### Lists (use in loops)

**Skills:**
```
{% for skill in skills %}
  {{ skill.category }}
  {{ skill.skills }}     # This is an array, use | join(", ")
{% endfor %}
```

**Experience:**
```
{% for exp in experience %}
  {{ exp.company }}
  {{ exp.position }}
  {{ exp.start_date }}
  {{ exp.end_date }}
  {{ exp.description }}  # This is an array, loop through it
  {{ exp.technologies }} # This is an array
{% endfor %}
```

**Education:**
```
{% for edu in education %}
  {{ edu.institution }}
  {{ edu.degree }}
  {{ edu.field_of_study }}
  {{ edu.graduation_date }}
  {{ edu.gpa }}
{% endfor %}
```

**Certifications:**
```
{% for cert in certifications %}
  {{ cert.name }}
  {{ cert.issuer }}
  {{ cert.date }}
{% endfor %}
```

---

## Template Versioning

Name your templates with versions:
- `ford-us-resume-template-v1.docx` - Version 1
- `ford-us-resume-template-v2.docx` - Version 2 (updated layout)
- `custom-template-v1.docx` - Custom template

---

## Troubleshooting

### "Template not found" error

**Solution:**
1. Make sure file is in `templates/` directory
2. Check exact filename matches in code
3. Verify file permissions allow reading

### "Invalid template" error

**Solution:**
1. Check DOCX file is valid (not corrupted)
2. Verify placeholder syntax is correct
3. Ensure all variables match schema names

### Placeholders not filling

**Solution:**
1. Check spelling of variable names (case-sensitive)
2. Verify data is being extracted by LLM
3. Check for typos in for loops
4. Ensure data exists in structured resume

---

## Support

For template issues or questions, check:
- [TEMPLATE_SELECTION.md](../TEMPLATE_SELECTION.md)
- [TEMPLATE_MAPPING.md](../TEMPLATE_MAPPING.md)
- [streamlit_app.py](../streamlit_app.py) template selection logic
