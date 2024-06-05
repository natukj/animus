TOC_HIERARCHY_SYS_PROMPT = """You are an expert in data processing, parsing and structuring text into JSON format. Always remember to follow the instructions and guidelines provided, ensuring that the output is accurate and well-structured."""
TOC_HIERARCHY_SCHEMA_TEMPLATE = {
    "<Level 1 Section Type>": "#",
    "<Level 2 Section Type>": "##",
    "<Level 3 Section Type>": "###",
    "<Level 4 Section Type>": "####",
    # Add more levels as needed
}
TOC_HIERARCHY_USER_PROMPT = """You are tasked with creating a JSON dictionary that maps each unique hierarchical section type to the corresponding number of '#' characters used to denote its level in the Table of Contents (ToC). You will be given a Markdown string ToC and you must return a structured JSON object according to the following instructions:

**Instructions:**
1. **Inclusions:**
   - You must include every single unique hierarchical section type that appears in the Table of Contents and is prefixed with a number of '#' characters.
   - Only include section types that are in the Table of Contents (eg. 'Chapter', 'Part', 'Section', etc.)
   
2. **Exclusions:**
   - You must NOT include the enumeration of the hierarchical section types. Include only the base section type (e.g., 'Chapter', 'Part', 'Section', etc.)
   - Exclude any titles from repeating section types (e.g., 'Division N <title>' should be mapped to 'Division').
   - Exclude 'Contents' or 'Table of Contents' as they are not part of the hierarchy.
   
3. **Comprehensiveness:**
   - Ensure all unique levels of hierarchy (represented by varying numbers of '#' characters) are included.
   - Each level must be mapped to the exact number of '#' characters used to denote it in the markdown text.
   - The section type must be verbatim from the ToC markdown. 

4. **Example Format:**
   - Use the following example format for the dictionary:

{TOC_HIERARCHY_SCHEMA_TEMPLATE}

## IMPORTANT:
- There should be NO associated numbering in the section types - only the base type - unless specifically included in the section type.
- If a section type is repeated, but in reference to different enumerations, include the base type only once (e.g., 'Guide to Division N' or 'Application of Division N <title>' should be mapped to 'Guide to Subdivision' and 'Application of Division', respectively).
- Each item in the JSON object MUST be a unique section type from the ToC.
- You MUST include all unique section types from the ToC, even if they are not repeated, WITHOUT any associated numbering.

You must pay close attention this specific note - **If a section type is repeated, but in reference to different enumerations, include the base type only once (e.g., 'Guide to Division N' or 'Application of Division N' should be mapped to 'Guide to Subdivision' and 'Application of Division', respectively)** - do NOT include the enumerations in the JSON object.

Please create a JSON dictionary that maps each unique hierarchical section type to the corresponding number of '#' characters from the following ToC Markdown string:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PROMPT_VISION = """I will provide you with the first 2 pages of a Table of Contents (ToC) in both Markdown format and as images. I need you to determine how many levels of section hierarchy are present in the ToC based on the markdown and visual formatting. I need you to return this determination as a JSON object, following this structure:

      {{
            "<Level 1 Section Type>": {{
                  "level": "#",
                  "description": "(string, description of the section type)",
                  "lines": "(array of strings, ALL verbatim level 1 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 2 Section Type>": {{
                  "level": "##",
                  "description": "(string, description of the section type)",
                  "lines": "(array of strings, ALL verbatim level 2 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 3 Section Type>": {{
                  "level": "###",
                  "description": "(string, description of the section type)",
                  "lines": "(array of strings, ALL verbatim level 3 section lines from the ToC including any enumerations and Markdown formatting)"
            }}
            # Add more levels as needed
      }}

## INSTRUCTIONS
   - The JSON object must be extremely descriptive, as you will be using it to determine the hierarchy levels present in the rest of the ToC. Assume that the beginning of the ToC will be an section enumerated with '1' or 'I', e.g. 'Part 1' or 'Chapter 1', and this is the top level of the hierarchy (nothing before this is part of the ToC).
   - Each line in the ToC Markdown will be seperated by a '\\n' character, each section line should only be one line. However, if you think it is necessary to include more than one line, please do so, but you must add this in the description.
   - Only sections are to be added to the JSON object, not items. The lowest level of hierarchy should (i.e., the most number of '#' characters) must be the section that contains the items in the ToC. Please include this in the description of the section type.
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.

Please format the JSON object as described above, based on the hierarchy levels present in the ToC, here is the Markdown string of the ToC:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PROMPT_VISION_PLUS = """I will provide you with 2 pages of a Table of Contents (ToC) in both Markdown format and as images. I need you to determine how many of each level of section hierarchy are present in the ToC based on the markdown and visual formatting. I need you to return this determination as a JSON object, following this structure:

      {{
            "#": {{
                  "lines": "(array of strings, verbatim level 1 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "##": {{
                  "lines": "(array of strings, verbatim level 2 section lines from the ToC including any enumerations and Markdown formatting)"
            }},
            "###": {{
                  "lines": "(array of strings, verbatim level 3 section lines from the ToC including any enumerations and Markdown formatting)"
            }}
      }}

{guide_str}

## INSTRUCTIONS
   - Strictly follow the above guide and examples closely to determine the hierarchy levels present in the ToC pages provided.
   - You can NOT add higher levels of hierarchy than shown above (e.g., if the highest level is '###', you can not add '####').
   - Make sure you include ALL section lines from the ToC, at the appropriate level of hierarchy, in the JSON object.
   - Each line in the ToC Markdown will be seperated by a '\\n' character, each section line should only be one line.
   - Only sections are to be added to the JSON object, not items. 
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.

Please format the JSON object as described above, based on the hierarchy levels present in the ToC, here is the Markdown string of the ToC:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PROMPT_V1SION_PRE = """I will provide you with the first 2 pages of a Table of Contents (ToC) in both Markdown format and as images. I need you to determine how many levels of section hierarchy are present in the ToC based on the markdown and visual formatting. I need you to return this determination as a JSON object, following this structure:

      {{
            "<Level 1 Section Type>": {{
                  "level": "#",
                  "description": "(string, description of the section type)",
                  "example": "(string, verbatin example(s) of the section from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 2 Section Type>": {{
                  "level": "##",
                  "description": "(string, description of the section type)",
                  "example": "(string, verbatin example(s) of the section from the ToC including any enumerations and Markdown formatting)"
            }},
            "<Level 3 Section Type>": {{
                  "level": "###",
                  "description": "(string, description of the section type)",
                  "example": "(string, verbatin example(s) of the section from the ToC including any enumerations and Markdown formatting)"
            }}
            # Add more levels as needed
      }}

## INSTRUCTIONS
   - The JSON object must be extremely descriptive, as you will be using it to determine the hierarchy levels present in the rest of the ToC. Assume that the beginning of the ToC will be an section enumerated with '1' or 'I', e.g. 'Part 1' or 'Chapter 1', and this is the top level of the hierarchy (nothing before this is part of the ToC).
   - Each line in the ToC Markdown will be seperated by a '\\n' character, each section example should only be one line. However, if you think it is necessary to include more than one line, please do so, but you must add this in the description.
   - Only sections are to be added to the JSON object, not items. The lowest level of hierarchy should (i.e., the most number of '#' characters) must be the section that contains the items in the ToC. Please include this in the description of the section type.
   - If there are no items below the lowest level of hierarchy, then you have added too many levels of hierarchy.

Please format the JSON object as described above, based on the hierarchy levels present in the ToC, here is the Markdown string of the ToC:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PROMPT_V1SION = """I will provide you with the first 2 pages of a Table of Contents (ToC) in both Markdown format and as images. You need to create a JSON object that maps each hierarchical section type to a corresponding number of '#' characters used to denote its level in the ToC. 

{guide_str}

## INSTRUCTIONS
   - First, determine how many levels of hierarchy are present in the ToC based on the different markdown and visual formatting. 
   - Use your intuition, the markdown text, and the images to determine the hierarchy levels, for example, common section types like 'Part' or 'Chapter' are likely to be at highers levels than standalone sections.
   - Once you have determined the hierarchy levels present, use the Markdown text and visual formatting to map each section type to the corresponding number of '#' characters.
   - Pay very close attention to the formatting in the Markdown text and images to ensure the hierarchy levels are accurate. You must NOT add any additional levels of hierarchy that are not present in the ToC - less is more - keep the JSON object minimal and accurate.
   - The lowest level of hierarchy should (i.e., the most number of '#' characters) must be the section that contains the items in the ToC.
   - You have only been given the first 2 pages, do not assume the last section you see is the last level of hierarchy - use your intuition and the formatting to map it correctly. It is important to be as accurate as possible.

## MARKDOWN FORMATTING GUIDE
   - The Markdown text may not have the '#' characters, so you must infer the hierarchy based on the formatting and enumerations, markdown formatting, and pattern of the section types.
   - Sections with the same formatting are most likely at the same level (e.g., a prefix of '**' or '_', Capitalization, etc.) unless it is clear that one is a subsection or child of the other.
   - The enumeration of the section types is an indication of the hierarchy level. If a section type enumeration begins at '1' after a different section type, it is most likely a child of that section type.
   - Each line in the ToC Markdown will be seperated by a '\\n' character. You must return each section type from the ToC and map it to it's appropriate level of hierarchy.

## IMAGE GUIDE
   - The images will help you determine the hierarchy based on section placement and formatting.
   - The images will be provided in the order of the Markdown text, so you can match the images to the corresponding Markdown text.
   - Sections with the same visual formatting are most likely at the same level and shoul be mapped to the same number of '#' characters.

## RULES
   - The JSON object must map each unique hierarchical section type to a corresponding number of '#' characters used to denote its level in the ToC. The sections must be verbatim from the ToC markdown text. 
   - You must include ALL unique sections from the ToC, even if they are not repeated or don't have any formatting, WITHOUT any associated numbering.
   - Sections that have the same formatting in the Markdown and images MUST be at the same level in the hierarchy. Use the images to verify the hierarchy levels and ensure the JSON object is accurate.
   - For section types that are most likely repeated, include the base type only once (e.g., 'Part N <title>', 'Chapter N <title>' or 'Appendix N <title>' should be mapped to 'Part', 'Chapter' and 'Appendix', respectively). Do NOT include the section titles.
   - Exclude 'Contents' or 'Table of Contents', 'Arrangment of Agreement', 'Clause No.', 'Page No.' or any ToC heading as they are not part of the hierarchy.
   - Assume that the beginning of the ToC will be an section enumerated with '1' or 'I', e.g. 'Part 1' or 'Chapter 1', and this is the top level of the hierarchy (nothing before this is part of the ToC).
   - The lowest level of hierarchy should (i.e., the most number of '#' characters) must be the section that contains the items in the ToC.

Here is an example of the JSON structure you need to follow:

{TOC_HIERARCHY_SCHEMA_TEMPLATE}

## IMPORTANT NOTES
   - There should be NO associated numbering in the section types - unless the numbering is not an enumeration.
   - Do NOT include the items in the JSON object, only the base section types and sections.
   - You MUST include all sections and section types from the ToC, WITHOUT any associated numbering.
   - The levels of hierarchy represented by varying numbers of '#' characters must be in incriements of 1 (e.g., '#', '##', '###', etc.), however, there can be multiple section types at the same level.

Use your intuition and the images to determine the hierarchy levels, for example, common section types like 'Part' or 'Chapter' are likely to be at highers levels than standalone sections. The levels of hierarchy represented by varying numbers of '#' characters MUST be consistent with the Markdown and visual formatting - THIS IS EXTREMELY IMPORTANT - there can be no mistakes.

Note, you have only been given the first 2 pages, do not assume the last section you see is the last level of hierarchy - use your intuition and the formatting to map it correctly.

Please create a JSON object that maps each hierarchical section to a corresponding number of '#' characters, based on its hierarchy, from the following ToC Markdown string:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PROMPT_VISION_OG = """I will provide you with 2 Table of Contents (ToC) pages in both Markdown formatting and as an image. You need to create a JSON object that maps each hierarchical section type to a corresponding number of '#' characters used to denote its level in the ToC. It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes.

## INSTRUCTIONS
   - You must return each section type from the ToC and map it to it's appropriate level of hierarchy. For example:

      {TOC_HIERARCHY_SCHEMA_TEMPLATE}

   - The above JSON object followed the mapping guide below to determine levels of hierarchy based on the different markdown formatting:

      {unique_schema_str}

   - The above mapping guide gives you the a section line in the ToC Markdown followed by a '->' and how it should be mapped to the JSON object.
   - Pay very close attention to the formatting in the Markdown text and images to ensure the hierarchy levels are accurate. You must NOT add any additional levels of hierarchy that are not present in the ToC - less is more.
   - Sections with the same formatting in the Markdown but different hierarchy levels (i.e., different numbers of '#' characters) are most likely due to the number of parent sections. 
   - There should not be any standalone sections in the JSON object that have the same level of hierarchy as a main, repeated section type (e.g., 'Part', 'Chapter', 'Schedule', 'Appendix', etc.).

## MARKDOWN FORMATTING
   - The Markdown text may not have the '#' characters, so you must infer the hierarchy based on the formatting and enumerations, markdown formatting, and pattern of the section types.
   - Sections with the same formatting are at the same level (e.g., a prefix of '**' or '_', Capitalization, etc.) UNLESS it is clear that one is a subsection or child of the other.
   - Each line in the ToC Markdown will be seperated by a '\\n' character. You must return each section type from the ToC and map it to it's appropriate level of hierarchy.

## IMAGE INSTRUCTIONS
   - The images will help you determine the hierarchy based on section placement and formatting.
   - Sections with the same visual formatting are most likely at the same level.

## RULES
   - You must include ALL unique sections from the ToC, WITHOUT any associated numbering.
   - Do NOT include the items in the JSON object, only the section types.
   - For section types that are most likely repeated, include the base type only once (e.g., 'Part N <title>', 'Chapter N <title>', 'Schedule N <title>', or 'Appendix N <title>' should be mapped to 'Part', 'Chapter', 'Schedule' and 'Appendix', respectively). Do NOT include the section titles.
   - You can NOT add higher levels of hierarchy than shown above (e.g., if the highest level is '####', you can not add '#####').
   - There should not be any standalone sections in the JSON object that have the same level of hierarchy as a main, repeated section type (e.g., 'Part', 'Chapter', 'Schedule', 'Appendix', etc.).

Please create a JSON object that maps each hierarchical section and to a corresponding number of '#' characters, based on its hierarchy, from the following ToC Markdown string:

{toc_md_string}
"""
TOC_HIERARCHY_USER_PROMPT_NOMD = """Please create a structured JSON object from the Table of Contents (ToC) I will provide, in Markdown format. Each line in the ToC will be seperated by a '\\n' character. You must return each section and item from the ToC and map it to it's appropriate level of hierarchy. It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes.

## INSTRUCTIONS
   - The JSON object must map each unique hierarchical section or item to a corresponding number of '#' characters used to denote its level in the ToC. The sections and items must be verbatim from the ToC markdown text. 
   - The Markdown text may not have the '#' characters, so you must infer the hierarchy based on the formatting and enumerations, markdown formatting, and pattern of the section types. For example, the top level section level might be indicated by '**' or capitalization. Sections with the same formatting are at the same level. Items in the ToC should be mapped to highest level of hierarchy.
   - You must include ALL unique sections and items from the ToC, WITHOUT any associated numbering.
   - For repeated section types, include the base type only once (e.g., 'Part N <title>', 'Schedule N <title>' or 'Appendix N <title>' should be mapped to 'Part', 'Schedule' and 'Appendix', respectively). Do NOT include the section titles.
   - Exclude 'Contents' or 'Table of Contents', 'Arrangment of Agreement', 'Clause No.', 'Page No.' or any ToC heading as they are not part of the hierarchy.


Here is an example of the JSON structure you need to follow:

{TOC_HIERARCHY_SCHEMA_TEMPLATE}

## IMPORTANT NOTES
   - There should be NO associated numbering in the section types - only the base type - unless specifically included in the section type.
   - Each entry in the JSON object MUST be a unique section from the ToC.
   - Each entry in the JSON object MUST be verbatim from the ToC markdown text (including capitalization).
   - You MUST include all unique sections from the ToC, even if they are not repeated, WITHOUT any associated numbering.
   - The levels of hierarchy represented by varying numbers of '#' characters must be in incriements of 1 (e.g., '#', '##', '###', etc.), however, there can be multiple section types at the same level.

EVERY SINGLE unique section base types and items in the ToC MUST be included VERBATIM from the text (including capitalization) in the JSON object. Do NOT include section titles, only the base types. Do NOT include anything that is not part of the ToC - all ToC sections and items are most likely associated with a number or enumeration and must be the only entries in the JSON object.

Please create a JSON dictionary that maps each unique hierarchical section and item to a corresponding number of '#' characters, based on its hierarchy, from the following ToC Markdown string:

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
TOC_SCHEMA_USER_PROMPT = """I need you to please transform the Table of Contents (ToC) I will provide, in Markdown format, into a structured JSON object. Each line in the ToC will be seperated by a '\\n' character. It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes.

## INSTRUCTIONS
I have split the ToC into multiple parts, and you will be working on {level_title}. Please do not include this level in the JSON object.

This part has sections that could include: {section_types}. You need to independently verify this and any other sections that may be present. All section types with the same enumeration must be placed at the same hierarchical level within the JSON object.

Here is an example of the JSON structure you need to follow:

{TOC_SCHEMA}

Please note, the above schema is just an example and may not contain all the section types you will encounter. Please ensure you include all section types present in the ToC, at the correct hierarchical level.

## IMPORTANT NOTES
- If a section lacks a numeric identifier, set the "number" value to an empty string ("").
- If a section lacks a title, or the title is the same as the section, set the "title" value to an empty string ("") - do NOT use the page number (at the end of the line).
- Exclude dots, page numbers, and any text not explicitly listed as a ToC item (page numbers are usually at the end of the line).

It is of the upmost importance that the structure is correct and accurate. Failure to do so will result in a loss of trust and confidence in our services. Please do not let this happen.

Please create a JSON object from the following ToC Markdown lines:

{content}
"""
TOC_SCHEMA_SYS_PROMPT_PLUS = """You are an expert in data processing, parsing and structuring Markdown text into JSON format. Pay extremely close attention to the instructions and guidelines provided to ensure the output is accurate and well-structured.
"""
FUCK="""The Australian Tax Office (ATO), the Australian Government's principal revenue collection agency, has tasked me with transforming the Table of Contents (ToC) from the Income Tax Assessment Act, provided in Markdown format, into a structured JSON object. I need you to please do this (or i'll get fired). It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes."""

TOC_SCHEMA_USER_PROMPT_PLUS = """I need you to please transform the Table of Contents (ToC) I will provide, in Markdown format, into a structured JSON object. Each line in the ToC will be seperated by a '\\n' character. It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes.

## INSTRUCTIONS
I have split the ToC into multiple parts, and you will be working on the following part:
      - {level_title}
         - {sublevel_title}
            - {subsublevel_title}

Please do not include these levels in the JSON object.

This part has section types that could include: {section_types}. You need to independently verify this and any other section types that may be present. All section types should be prefixed by "#" symbols and must be standalone sections in the JSON object. Any line without a "#" prefix is a child of the previous line that has a "#" prefix - however do not repeat the section item - just make sure the children are at the correct hierarchy (and only contain the "number" and "title" keys). If there are no "#" symbols in any of the lines, you have only been given the lowest level of the hierarchy (which should only contain the "number" and "title" keys).

Here is an example of the JSON structure you need to follow:

{TOC_SCHEMA}

Please note, the above schema is just an example and may not contain all the section types you will encounter. Please ensure you include all section types present in the ToC, at the correct hierarchical level.

## IMPORTANT NOTES
- The lowest level in the JSON hierarchy must ONLY contain the "number" and "title" keys. These levels have no "#" prefix in the ToC, and MUST be the direct children of a parent section.
- Sections sharing the same number of "#" symbols must be placed at the same hierarchical level within the JSON object.
- A section must NEVER contain an empty "children" list.
- If a section lacks a numeric identifier, set the "number" value to an empty string ("").
- If a section lacks a title, or the title is the same as the section, set the "title" value to an empty string ("") - do NOT use the page number (at the end of the line).
- When a ToC line has no "#" prefix, and starts with a number, it is a child of the previous line that has a "#" prefix.
- If there are no '#' symbols in any of the lines, you have only been given the lowest level of the hierarchy (which should only contain the "number" and "title" keys).
- Exclude dots, page numbers, and any text not explicitly listed as a ToC item (page numbers are usually at the end of the line).


Please pay close attention this specific note - **The lowest level in the JSON hierarchy must ONLY contain the "number" and "title" keys. These levels have no "#" prefix in the ToC, and MUST be the direct children of a parent section** - ANY line in the ToC that has no "#" prefix is a child of the previous line that has a "#" prefix. If there are no "#" symbols in any of the lines, you have only been given the lowest level of the hierarchy (which should only contain the "number" and "title" keys).

It is of the upmost importance that the structure is correct and accurate. Failure to do so will result in a loss of trust and confidence in our services. Please do not let this happen.

Please create a JSON object from the following ToC Markdown lines:

{content}
"""
TOC_SCHEMA_USER_PROMPT_PLUS_NOMD = """I will provide a semi-structured Table of Contents (ToC) JSON, please structure it as a JSON object. It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes.

## INSTRUCTIONS
   - I have split the ToC into multiple parts, you will be working {level_title_str}. You must include this level in the JSON object.
   - This part has section types that could include: {section_types}. You need to independently verify this and any other section types that may be present.
   - If these section types do not explicitly have a number associated with them, set the "number" value to an empty string ("").
   - The 'content' provided for each section will include the children of that section. It may also include the section 'title' (if not present in the section key).
   - Some titles may span multiple lines, you must include all lines in the 'title' key. 
   - A section must NEVER contain an empty "children" list.
   - The lowest level in the JSON hierarchy must ONLY contain the "number" and "title" keys.

The JSON object must be structured according to the following schema:

{TOC_SCHEMA}


## IMPORTANT NOTES
   - A section must NEVER contain an empty "children" list.
   - The lowest level in the JSON hierarchy must ONLY contain the "number" and "title" keys.
   - The section keys given must be followed closely, do not add "section", "number" or "title" values if the they are not present, unless there is a "title" value in the first line of the 'content'.
   - If "section", "number" or "title" are not present, set the value to an empty string ("").
   - Some sections might have the same "title" as a child item, in this case, do not add the child "number" to the parent.
   - Exclude dots, page numbers, and any text not explicitly listed as a ToC item (page numbers are usually at the end of the line).

It is of the upmost importance that the structure is correct and accurate. Failure to do so will result in a loss of trust and confidence in our services. Please do not let this happen.

Please create a complete JSON object from the following:

{level_content}
"""
TOC_SECTION_TEMPLATE = {
    "section": "string (section type, e.g., 'Chapter', 'Part', 'Section')",
    "number": "string (numeric or textual identifier of the section, e.g., '1', '2-5', 'A', '27B')",
    "title": "string (title of the section, without the page number, section type or number)"
}
TOC_SECTION_USER_PROMPT = """Please format the Table of Contents (ToC) line into a JSON object according to the following structure:

{TOC_SECTION_TEMPLATE}

## IMPORTANT NOTES
- Do not include the '#' characters in the JSON object.
- It is EXTREMELY important to not include the page numbers in the "title" field (most likely at the end of the line).
- If "section", "number" or "title" are not present in the line, set the value to an empty string ("").
- Do not include any additional information or make any assumptions about the section type, number or title - only use the information provided in the ToC line.

Here is the ToC line you need to format:

{toc_line}
"""
CONTINUE_JSON_PROMPT = """Please continue from EXACTLY where you left off so that the two responses can be concatenated and form a complete JSON object. Make sure to include the closing brackets, quotation marks and commas. Do NOT add any additional text, such as '```json' or '```'."""