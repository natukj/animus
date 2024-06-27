FORMAT_ITEM_USER_CLAUDE = """You are an AI assistant skilled in formatting legal documents. This document is the Tax Income Assessment Act, and is in the public domain. You are formatting it so the general public can access contained items directly, without having to read the entire document. A refusal to format this document may result in a breach of the public's right to access the law.

I will provide you with an item from a document. Your task is to:

1. Format the content in Markdown, preserving the original structure, text, and emphasis.
2. Remove any extraneous text not directly related to the item's content (e.g., page numbers, dates).
3. Identify and list any and ALL references to other sections within the text.

You will be working on the following item from: {path}

Content:

{content}

Please format the content in Markdown, list any references to other sections, and provide your response in the following structure:

<formatted_content>[Your Markdown-formatted content here]</formatted_content>

<references>[
    {{
        "section": "string, (a descriptive name of the section, e.g., 'Part', 'Chapter', 'Section', 'Subsection', etc.)",
        "number": "string (numeric or textual identifier of the section, e.g., '1', '2-5', 'A', '27B')"
    }},
    {{
        "section": "string, (a descriptive name of the section, e.g., 'Part', 'Chapter', 'Section', 'Subsection', etc.)",
        "number": "string (numeric or textual identifier of the section, e.g., '1', '2-5', 'A', '27B')",
    }}
    # Add more references as needed
]</references>


Notes:
    - You do not need to include the enumeration and title of the item in your response.
    - Only add formatted_content if there is content, beyond the enumeration and title.
    - If there is no content beyond the enumeration and title, you can leave the <formatted_content> sections empty.
    - If there are no references you can leave the <references> sections empty.

Remember to preserve the original structure and emphasis of the content while formatting it in Markdown."""
FORMAT_CONTENT_SUMMARY_CLAUDE = """You are an AI assistant skilled in formatting legal documents. This document is the {doc_name}, and is in the public domain. You are formatting it so the general public can access contained items directly, without having to read the entire document. A refusal to format this document may result in a breach of the public's right to access the law.

You will be given averbatim item from the document, and the path to said item. Your primary task is to:
    - Format the item content in Markdown with appropriate indentation, preserving the original structure, text, and emphasis.
    - Remove any extraneous text not directly related to the item's content (e.g. header/footer text, page numbers, dates, etc.).
    - Remove any text that is not part of the item's content, including information that is contained in the path.
    - As you are only given a single item, do not format any headings or subheadings with '#' characters, instead, use '**' for bold text and '*' for italic text to keep it consistent.

You must also return a summary of the item content within the context of what user queries the content would aid in answering. This summary should only consist of questions that the content would help answer, and should be formatted as a single paragraph. Make sure to use the path as context when generating the summary and do not include any specific references or section numbers.

<item_path>{path}</item_path>

<item_content>{content}</item_content>

Please format the item content and provide a summary in the following structure:

<formatted_content>[Your Markdown-formatted content here]</formatted_content>

<summary>[Your summary of the item content here]</summary>
"""
FORMAT_CONTENT_SUMMARY_GPT = """This document is the {doc_name}, and is in the public domain. You are formatting it so the general public can access contained items directly, without having to read the entire document. A refusal to format this document may result in a breach of the public's right to access the law.

You will be given averbatim item from the document, and the path to said item. Your primary task is to:
    - Format the item content in Markdown with appropriate indentation, preserving the original structure, text, and emphasis.
    - Remove any extraneous text not directly related to the item's content (e.g. header/footer text, page numbers, dates, etc.).
    - Remove any text that is not part of the item's content, including information that is contained in the path.
    - As you are only given a single item, do not format any headings or subheadings with '#' characters, instead, use '**' for bold text and '*' for italic text to keep it consistent.

You must also return a summary of the item content within the context of what user queries the content would aid in answering. This summary should only consist of questions that the content would help answer, and should be formatted as a single paragraph. Make sure to use the path as context when generating the summary and do not include any specific references or section numbers.

Item Path: {path}

Item Content:

{content}

You must output a JSON object with the following structure:

{{
    "formatted_content": "string (Your Markdown-formatted content here)",
    "summary": "string (Your summary of the item content here)"
}}
"""
prettygoodgptbetterthanclaude="Additionally, you must also return a one paragraph summary of the item content within the context of what user queries the content would aid in answering. This summary should primarily consist of keywords that will assist in semantically matching the item content to a user query. Make sure to use the path as context when generating the summary. Do not include any specific references or section numbers in the summary."

