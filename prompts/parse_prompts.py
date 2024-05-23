TOC_HIERARCHY_SYS_PROMPT = """You are an expert in data processing, parsing and structuring text into JSON format. Always remember to follow the instructions and guidelines provided, ensuring that the output is accurate and well-structured."""
TOC_HIERARCHY_SCHEMA_TEMPLATE = {
    "<Level 1 Section Type>": "#",
    "<Level 2 Section Type>": "##",
    "<Level 3 Section Type>": "###",
    "<Level 4 Section Type>": "####",
    "<Level 5 Section Type>": "#####",
    "<Level 6 Section Type>": "######"
}
TOC_HIERARCHY_USER_PROMPT = """You are tasked with creating a JSON dictionary that maps each unique hierarchical section type to the corresponding number of '#' characters used to denote its level in the Table of Contents (ToC). You will be given a Markdown string ToC and you must return a structured JSON object according to the following instructions:

**Instructions:**
1. **Inclusions:**
   - You must include every single unique hierarchical section type that appears in the Table of Contents and is prefixed with a number of '#' characters.
   - Only include section types that are in the Table of Contents (eg. 'Chapter', 'Part', 'Section', etc.)
   
2. **Exclusions:**
   - You must NOT include the enumeration of the hierarchical section types. Include only the base section type (e.g., 'Chapter', 'Part', 'Section', etc.)
   - Exclude 'Contents' or 'Table of Contents' as they are not part of the hierarchy.
   
3. **Comprehensiveness:**
   - Ensure all levels of hierarchy (represented by varying numbers of '#' characters) are considered.
   - Each level must be mapped to the exact number of '#' characters used to denote it in the markdown text.

4. **Example Format:**
   - Use the following example format for the dictionary:

{TOC_HIERARCHY_SCHEMA_TEMPLATE}

## Table of Contents Markdown Text:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PROMPT_OG = """You are tasked with creating a JSON dictionary that maps each major unique hierarchical section type to the corresponding number of '#' characters used to denote its level in the Table of Contents (ToC). You will be given a Markdown string ToC and you must return a structured JSON object according to the following instructions:

**Instructions:**
1. **Inclusions:**
   - You must include every single unique hierarchical section type that appears in the Table of Contents and is prefixed with a number of '#' characters.
   - Only include section types that are REPEATED in the Table of Contents, unless they are the Top Level.
   - Only include major section types that are appear throughout the ToC, not specific or granular types.
   
2. **Exclusions:**
   - You must NOT include the enumeration of the hierarchical section types. Include only the base section type, e.g., 'Chapter', 'Part', 'Section', etc.
   - Exclude 'Contents' or 'Table of Contents' as they are not part of the hierarchy.
   - Exclude any standalone section types that are not repeated in the ToC.
   - Exclude section types that are too specific or granular, focusing only on the main hierarchical levels.
   
3. **Comprehensiveness:**
   - Ensure all levels of hierarchy (represented by varying numbers of '#' characters) are considered.
   - Each level must be mapped to the exact number of '#' characters used to denote it in the markdown text.
   - Include all REPEATED section types regardless of their position in the hierarchy.
   - Include the Top Level section type even if it is not repeated.
   - The JSON object must be minimal and contain only the major section types that are used throughout the ToC.

4. **Example Format:**
   - Use the following example format for the dictionary:

{TOC_HIERARCHY_SCHEMA_TEMPLATE}

## Table of Contents Markdown Text:

{toc_md_string}
"""
TOC_SCHEMA_SYS_PROMPT = """You are working for the Australian Tax Office (ATO), the Australian Government's principal revenue collection agency. Your task is to transform the Table of Contents (ToC) from the Income Tax Assessment Act, provided in Markdown format, into a structured JSON object according to the following guidelines:

**Instructions:**
1. **Section Hierarchy:** You must identify the hierarchical level of each section. Each "section" key in the ToC text is prefixed by a series of "#" symbols that correspond to their hierarchical level.
2. **Section Types:** The ToC contains sections of various types, such as: {section_types}. These must be standalone sections in the JSON object.
2. **Multiple Sections at the Same Level:** Sections sharing the same number of "#" symbols must be placed at the same hierarchical level within the JSON object.
3. **Missing Section Numbers:** If a section lacks a numeric identifier, set the "number" value to an empty string ("").
4. **No Empty Sections:** The "section" key must never be an empty string.
5. **Lowest Level Formatting:** The lowest level in the JSON hierarchy must only contain the "number" and "title" keys. These levels have no "#" prefix in the ToC.

**Exclusions:**
- Exclude dots, page numbers, and any text not explicitly listed as a ToC item.

**JSON Format:**
Please format the ToC into a JSON structure as outlined below:

{TOC_SCHEMA}
"""
TOC_SCHEMA_SYS_PROMPT_PLUS = """You are working for the Australian Tax Office (ATO), the Australian Government's principal revenue collection agency. Your task is to transform the Table of Contents (ToC) from the Income Tax Assessment Act, provided in Markdown format, into a structured JSON object according to the following guidelines:

**Instructions:**
1. **Section Hierarchy:** You must identify the hierarchical level of each section. Each "section" key in the ToC text is prefixed by a series of "#" symbols that correspond to their hierarchical level.
2. **Section Types:** The ToC contains sections of various types, such as: {section_types}. These must be standalone sections in the JSON object.
2. **Multiple Sections at the Same Level:** Sections sharing the same number of "#" symbols must be placed at the same hierarchical level within the JSON object.
3. **Missing Section Numbers:** If a section lacks a numeric identifier, set the "number" value to an empty string ("").
4. **No Empty Sections:** The "section" key must never be an empty string.
5. **Lowest Level Formatting:** The lowest level in the JSON hierarchy must only contain the "number" and "title" keys. These levels have no "#" prefix in the ToC.

**Exclusions:**
- Exclude dots, page numbers, and any text not explicitly listed as a ToC item.

**Split Sections:** 
The following section has been split into multiple parts: 
- The current section is: {chapter_title}
- The current child section is: {part_title}

**JSON Format:**
Please format the ToC into a JSON structure as outlined below:

{TOC_SCHEMA}
"""
TOC_SECTION_TEMPLATE = {
    "section": "string (section type, e.g., 'Chapter', 'Part', 'Section')",
    "number": "string (numeric or textual identifier of the section, e.g., '1', '2-5', 'A', '27B')",
    "title": "string (title of the section, without the page number, section type or number)"
}
TOC_SECTION_USER_PROMPT = """Please format the following line from the Table of Contents (ToC) into a JSON object according to the following structure:

**JSON Format:**

{TOC_SECTION_TEMPLATE}

## Important Note:
- Do not include the '#' characters in the JSON object.
- Do not include the page numbers in the "title" field (most likely at the end of the line).

## ToC Line:

{toc_line}
"""