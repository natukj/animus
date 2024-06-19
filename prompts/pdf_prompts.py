TOC_SCHEMA_SYS = """You are an expert in data processing, parsing and structuring Markdown text into JSON format. Pay extremely close attention to the instructions and guidelines provided to ensure the output is accurate and well-structured.
"""
TOC_SCHEMA_USER = """I need you to please transform the Table of Contents (ToC) I will provide, in Markdown format, into a structured JSON object. Each line in the ToC will be separated by '\\n' characters. It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes.

## INSTRUCTIONS
I have split the ToC into multiple parts, and you will be working on the following part:

{dynamic_levels}

You must include each of the above levels in the JSON object.

Here is an example of the JSON structure you need to follow:

{TOC_SCHEMA}

You must follow this structure exactly, making sure to include the correct number of levels and the correct keys for each level. 

## IMPORTANT NOTES
- The lowest level in the JSON hierarchy must ONLY contain the "number" and "title" keys and MUST be the direct children of a parent section.
- A section must NEVER contain an empty "children" list.
- You must include all items in the ToC, at the correct level, and in the correct order.
- Exclude dots, page numbers, and any text not explicitly listed as a ToC item (page numbers are usually at the end of the line).

It is of the upmost importance that the structure is correct and accurate. Failure to do so will result in a loss of trust and confidence in our services. Please do not let this happen.

Please create a JSON object from the following ToC Markdown lines:

{content}
"""
TOC_ITEMS_USER = """Please format the Table of Contents (ToC) Markdown items into a JSON object. Each line in the ToC will be separated by '\\n' characters, however some items will span multiple lines. You must output a JSON object according to the following structure:

{{ "items": [
         {{
               "number": "string (numeric or textual identifier of the section, e.g., '1', '2-5', 'A', '27B')",
               "title": "string (title of the section, without the page number, section type or number)"
         }},
         {{
               "number": "string (numeric or textual identifier of the section, e.g., '1', '2-5', 'A', '27B')",
               "title": "string (title of the section, without the page number, section type or number)"
         }},
         # Add more items as needed
   ]
}}

## IMPORTANT NOTES
- It is EXTREMELY important to not include the page numbers in fields (most likely at the end of the line).
- Do NOT include any additional information or make any assumptions about the section type, number or title - only use the information provided.
- Do NOT include anything other than ToC items, that include dates, page numbers, compilation numbers, etc.
- If there are no items, please provide an empty JSON object.

**Please do NOT include anything other than ToC items, that include dates, page numbers, the document name, compilation numbers, or anything that is not clearly an item in a Table of Contents.**

Please create a JSON object from the following ToC Markdown lines:

{content}
"""
TOC_HIERARCHY_USER_VISION_FUCKKKK = """You will be given the first 2 Table of Contents (ToC) pages in both Markdown format and as images. I need you to determine how many levels of section hierarchy are present in the ToC based on the markdown and visual formatting. This needs to be on a line-by-line basis, where each line is separated by '\\n' characters (in the Markdown text). 

## INSTRUCTIONS
   - The JSON object must be extremely descriptive and comprehensive, as you will be using it to determine the hierarchy levels present in the rest of the ToC. Assume that the beginning of the ToC will be an section enumerated with '1' or 'I', e.g. 'Part 1' or 'Chapter 1', and this is the top level of the hierarchy (nothing before this is part of the ToC).
   - If a section type has the section title on a proceeding line, add an additional entry to the JSON object with the same 'level' as the section type and use "<Level N Section Type> Titles" as the key.
   - Only sections are to be added to the JSON object, not items. The lowest level of hierarchy should (i.e., the most number of '#' characters) must be the section that contains the items in the ToC. Please include this in the description of the section type.
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.

The JSON object should be structured as follows:

      {{
            "<Level 1 Section Type>": {{
                  "level": '#',
                  "description": "(string, verbose description of the section type and how it can be identified in the text)",
                  "lines": "(array of strings, ALL verbatim level 1 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 2 Section Type>": {{
                  "level": '##',
                  "description": "(string, verbose description of the section type and how it can be identified in the text)",
                  "lines": "(array of strings, ALL verbatim level 2 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 3 Section Type>": {{
                  "level": '###',
                  "description": "(string, verbose description of the section type and how it can be identified in the text)",
                  "lines": "(array of strings, ALL verbatim level 3 section lines from the ToC including any enumerations and Markdown formatting)"
            }}
            # Add more levels as needed
      }}

## IMPORTANT NOTES
   - Ignore ALL text before the first section enumerated with '1' or 'I'.
   - The section type should be a descriptive name of the section, e.g., 'Part', 'Chapter', 'Section', 'Subsection', etc.
   - If a section type has the section title on a proceeding line, add an additional entry to the JSON object with the same 'level' as the section type and use "<Level N Section Type> Titles" as the key.
   - The 'level' must always be '#' characters, e.g., '#', '##', '###', etc.
   - The hierarchy, represented by the number of '#' characters in 'level' must be incremented by one for each level of hierarchy and MUST not skip any levels, i.e. # -> ## -> ### etc.
   - Everything in the JSON object must be verbatim from the ToC, including any enumerations and Markdown formatting.
   - The JSON object must include all levels of hierarchy present in the ToC, up to the lowest level that contains the items.

Pay close attention to these specific notes: 
- **If a section type has the section title on a proceeding line, add an additional entry to the JSON object with the same 'level' as the section type and use "<Level N Section Type> Titles" as the key.**
- **Do NOT include any text the proceeds the beginning of the ToC.**

Please format the JSON object as described above, based on the (verbatim) hierarchy levels present in the ToC, here is the Markdown string of the ToC:

{toc_md_string}
"""
TOC_HIERARCHY_USER_VISION_PLUS = """I will provide you with 1-2 pages of a Table of Contents (ToC) in both Markdown format and as images. I need you to create a JSON object that represents the hierarchy of the ToC sections. Each line in the ToC will be separated by '\\n' characters, you must identify the section lines and their respective levels in the hierarchy. Your output must be a JSON object according to the following structure:

{initial_toc_hierarchy_schema}

Pay close attention to the formatting of the examples provided. The sections that you extract from the ToC must follow this formatting exactly. If you are outputting sections with different formatting, you are doing it wrong. Here is an example to guide you:

{example}

Note, there are only {num_levels} levels of hierarchy in the ToC. You must not exceed this number of levels in the JSON object. Please remember to only add sections, not items, to the JSON object. These sections must be verbatim from the ToC Markdown text, including any enumerations and Markdown formatting.

## INSTRUCTIONS
   - Strictly follow the above guide and examples closely to determine the hierarchy levels present in the ToC pages provided.
   - Make sure you include ALL section lines from the ToC, at the appropriate level of hierarchy, in the JSON object.
   - Only sections are to be added to the JSON object, not items. 
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.

Please format the JSON object as described above, based on the hierarchy levels present in the ToC, here is the Markdown text of the ToC:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PLUS_NO = """You will be given Table of Contents (ToC) text in Markdown formatting. I need you to create a JSON object to extract the hierarchy of the ToC sections. This needs to be on a line-by-line basis, where each line is separated by '\\n' characters. Your output must be a JSON object according to the following structure:

{initial_toc_hierarchy_schema}

Pay close attention to the descriptions of each key above. The sections that you extract from the ToC must follow this exactly. There are only {num_levels} levels of hierarchy in the ToC. You must not exceed this number of levels in the JSON object. Please remember to only add sections, NOT items, to the JSON object. These sections must be verbatim from the ToC Markdown text, including any enumerations and Markdown formatting.

Here is some example Markdown text (from this document ToC) and extracted sections to guide you:

{example}

## INSTRUCTIONS
   - Strictly follow the above guide and examples closely to determine the hierarchy levels present in the ToC pages provided.
   - Make sure to include ALL section lines from the ToC, at the appropriate level of hierarchy, in the JSON object.
   - Only sections are to be added to the JSON object, not items. 
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.
   - You are not guaranteed to have every level present in the given text so you must use the example text formatting to assist you in assigning the section hierarchy correctly.
   - READ THE DESCRIPTIONS IN THE PROVIDED JSON OBJECT CAREFULLY.

Please format the JSON object as described above, based on the hierarchy levels present in the ToC, from the following ToC Markdown text:

{toc_md_string}
"""
TOC_HIERARCHY_USER_VISION_APPENDIX = """You will be given Table of Contents (ToC) Appendix page(s) in both Markdown format and as images. I need you to determine how many levels of section hierarchy are present in the ToC based on the markdown and visual formatting. 

The JSON object should be structured as follows:

      {{
            "<Level 1 Section Type>": {{
                  "level": "#",
                  "description": "(string, verbose description of the section type and how it can be identified in the text)",
                  "lines": "(array of strings, ALL verbatim level 1 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 2 Section Type>": {{
                  "level": "##",
                  "description": "(string, verbose description of the section type and how it can be identified in the text",
                  "lines": "(array of strings, ALL verbatim level 2 section lines from the ToC including any enumerations and Markdown formatting)"
            }}
            # Add more levels as needed
      }}

## IMPORTANT NOTES
   - The section type should be a descriptive name of the section, e.g., 'Schedule', 'Appendix', 'Part', etc.
   - Everything in the JSON object must be verbatim from the ToC, including any enumerations and Markdown formatting.

**Please IGNORE any text above the first Schedule or Appendix section.**

Please format the JSON object as described above, based on the (verbatim) hierarchy levels present in the ToC, here is the Markdown string of the ToC:

{toc_md_string}
"""
FUCK = """I will provide you with pages of a Table of Contents (ToC) in Markdown format. I need you to create a JSON object that represents the hierarchy of the ToC sections. Each line in the ToC will be separated by '\\n' characters, you must identify the section lines and their respective levels in the hierarchy. Your output must be a JSON object according to the following structure:

{initial_toc_hierarchy_schema}

Pay close attention to the formatting of the examples provided. The sections that you extract from the ToC must follow this formatting exactly. If you are outputting sections with different formatting, you are doing it wrong. Here is an example to guide you:

{example}

Note, there are only {num_levels} levels of hierarchy in the ToC. You must not exceed this number of levels in the JSON object. Please remember to only add sections, not items, to the JSON object. These sections must be verbatim from the ToC Markdown text, including any enumerations and Markdown formatting.

## INSTRUCTIONS
   - Strictly follow the above guide and examples closely to determine the hierarchy levels present in the ToC pages provided.
   - Make sure to include ALL section lines from the ToC, at the appropriate level of hierarchy, in the JSON object.
   - Only sections are to be added to the JSON object, not items. 
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.
   - You are not guaranteed to have every level present in the given text so you must use the example text formatting to assist you in assigning the section hierarchy correctly.
   - READ THE DESCRIPTIONS IN THE PROVIDED JSON OBJECT CAREFULLY.

Please format the JSON object as described above, based on the hierarchy levels present in the ToC, here is the Markdown text of the ToC:

{toc_md_string}"""
TOC_HIERARCHY_USER_PLUS = """You will be given Table of Contents (ToC) text in Markdown formatting. I need you to create a JSON object to extract each section in the ToC according to their the hierarchy. This needs to be on a line-by-line basis, where each line is separated by '\\n' characters. Your output must be a JSON object according to the following structure:

{prior_schema_template}

Here is some example Markdown text (from this document ToC) and the desired JSON object to guide you:

{example}

Pay close attention to the descriptions and formatting in the examples provided. The sections that you extract from the ToC must follow this exactly. You must not exceed {num_levels} number of levels in the JSON object. Please remember to only add sections, NOT items, to the JSON object. These sections must be verbatim from the ToC Markdown text, including any enumerations and Markdown formatting.

## INSTRUCTIONS
   - Strictly follow the above guide and examples closely to determine the hierarchy levels present in the ToC pages provided.
   - Make sure to include ALL section lines from the ToC, at the appropriate level of hierarchy, in the JSON object.
   - You must include ALL section lines from the ToC, even if they are repeated.
   - Only sections are to be added to the JSON object, not items. 
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.
   - You are not guaranteed to have every level present in the given text so you must use the example text formatting and example JSON to assist you in assigning the section hierarchy correctly.

Pay close attention to these specific notes: 
   - **Do NOT include any items in the JSON object, only sections.** 
   - **Do NOT include ANYTHING other than the section lines from the ToC, this includes dates, page numbers, the document name, compilation numbers, or anything that is not clearly a section in a Table of Contents.**
   
Please format the JSON object as described above, based on the hierarchy levels present in the ToC, from the following ToC Markdown text:

{toc_md_string}
"""
TOC_HIERARCHY_USER_VISION = """You will be given the first 2 Table of Contents (ToC) pages in both Markdown format and as images. I need you to determine how many levels of section hierarchy are present in the ToC based on the markdown and visual formatting. This needs to be on a line-by-line basis, where each line is separated by '\\n' characters (in the Markdown text). 

## INSTRUCTIONS
   - The JSON object must be extremely descriptive and comprehensive, as you will be using it to determine the hierarchy levels present in the rest of the ToC. Assume that the beginning of the ToC will be an section enumerated with '1' or 'I', e.g. 'Part 1' or 'Chapter 1', and this is the top level of the hierarchy (nothing before this is part of the ToC).
   - If a section type has the section title on a proceeding line, add an additional entry to the JSON object with the same 'level' as the section type and use "<Level N Section Type> Titles" as the key.
   - The 'level' must always be '#' characters, e.g., '#', '##', '###', etc, and must be incremented by one for each level of hierarchy.
   - Only sections are to be added to the JSON object, not items. The lowest level of hierarchy should (i.e., the most number of '#' characters) must be the section that contains the items in the ToC. Please include this in the description of the section type.
   - The section lines MUST be verbatim from the ToC text, including any enumerations and Markdown formatting.
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.

The JSON object should be structured as follows:

      {{
            "<Level 1 Section Type>": {{
                  "level": '#',
                  "description": "(string, verbose description of the section type and how it can be identified in the text)",
                  "lines": "(array of strings, ALL verbatim level 1 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 2 Section Type>": {{
                  "level": '##',
                  "description": "(string, verbose description of the section type and how it can be identified in the text)",
                  "lines": "(array of strings, ALL verbatim level 2 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 3 Section Type>": {{
                  "level": '###',
                  "description": "(string, verbose description of the section type and how it can be identified in the text)",
                  "lines": "(array of strings, ALL verbatim level 3 section lines from the ToC including any enumerations and Markdown formatting)"
            }}
            # Add more levels as needed
      }}

## IMPORTANT NOTES
   - The section type should be a descriptive name of the section, e.g., 'Part', 'Chapter', 'Section', 'Subsection', etc.
   - If a section type has the section title on a proceeding line, add an additional entry to the JSON object with the same 'level' as the section type and use "<Level N Section Type> Titles" as the key.
   - The hierarchy, represented by the number of '#' characters in 'level' must be incremented by one for each level of hierarchy and MUST not skip any levels, i.e. # -> ## -> ### etc.
   - Everything in the JSON object must be verbatim from the ToC, including any enumerations and Markdown formatting.
   - The JSON object must include all levels of hierarchy present in the ToC, up to the lowest level that contains the items.

Pay close attention to these specific notes: 
- **If a section type has the section title on a proceeding line, add an additional entry to the JSON object with the same 'level' as the section type and use "<Level N Section Type> Titles" as the key.**
- **Do NOT include any text the proceeds the beginning of the ToC.**
- **Do NOT include any items in the JSON object, only sections.**

Please format the JSON object as described above, based on the (verbatim) hierarchy levels present in the ToC, here is the Markdown string of the ToC:

{toc_md_string}
"""