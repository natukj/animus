TOC_SCHEMA_SYS = """You are an expert in data processing, parsing and structuring Markdown text into JSON format. Pay extremely close attention to the instructions and guidelines provided to ensure the output is accurate and well-structured.
"""
TOC_SCHEMA_USER = """I need you to please transform the Table of Contents (ToC) I will provide, in Markdown format, into a structured JSON object. Each line in the ToC will be seperated by a '\\n' character. It is extremely important that you follow the instructions and guidelines below to ensure the output is accurate and well-structured. There can be no mistakes.

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
TOC_ITEMS_USER = """Please format the Table of Contents (ToC) Markdown items into a JSON object. Each line in the ToC will be seperated by a '\\n' character, however some items will span multiple lines. You must output a JSON object according to the following structure:

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
- Do not include any additional information or make any assumptions about the section type, number or title - only use the information provided.
- Do NOT include anything other than ToC items, that include dates, page numbers, compilation numbers, etc.
- If there are no items, please provide an empty JSON object.

Please create a JSON object from the following ToC Markdown lines:

{content}
"""
