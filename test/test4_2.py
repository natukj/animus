from pydantic import BaseModel, ValidationError
from typing import Union, Any, Optional, Dict, Tuple, List, NewType
import json
import asyncio
import base64
from fastapi import UploadFile
import fitz
import re
import uuid
import pathlib
from collections import Counter, defaultdict
from thefuzz import process  
import llm, prompts, utils
from deepdiff import DeepDiff
import copy

"""COMPLEX ATYPICAL"""
def compare_schemas(original, corrected):
    # Compare dictionaries
    diff = DeepDiff(original, corrected, ignore_order=True)
    return diff

def encode_page_as_base64(page: fitz.Page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 1))
    return base64.b64encode(pix.tobytes()).decode('utf-8')

pages = list(range(0, 59))
#grouped_pages = [pages[i:i+2] for i in range(0, len(pages), 2)]
grouped_pages = [pages[:2]] + [pages[i:i+4] for i in range(2, len(pages), 4)]

doc = fitz.open("/Users/jamesqxd/Documents/norgai-docs/ACTS/ukCOMPANIESACT2006.pdf")
async def main_run():
    # toc_file_path = "toc.md"
    # with open(toc_file_path, "r") as f:
    #     toc_md_str = f.read()
    # toc_md_lines = [line.strip() for line in toc_md_str.split("\n") if line.strip()]
    # section_lines = [line for line in toc_md_lines if not re.match(r'^\s*\d+[\s\.].*', line)]
    # toc_md_toc_section_str = "\n".join(section_lines)
    # with open("uk_toc_section.md", "w") as f:
    #     f.write(toc_md_toc_section_str)
    # exit()
    #toc_section_list = utils.to_markdownOG(doc=doc, pages=pages, page_chunks=True)
    with open("uk_toc_section_list.json", "r") as f:
        toc_section_list = json.load(f)

    individual_page_texts = {page: toc_section_list[pages.index(page)].get("text", "") for page in pages}
    grouped_pages_text = {tuple(group): [individual_page_texts[page] for page in group] for group in grouped_pages}
    end_pages = []
    end_pages_text = ""
    appendix_break = False
    for group in list(reversed(grouped_pages)):
        remaining_group_pages = []
        for page in reversed(group):
            page_text = individual_page_texts[page]
            if any(keyword in page_text.lower() for keyword in ['schedule', 'appendix', 'appendices']) and not appendix_break:
                end_pages.append(page)
                print(f"Appendix/Schedule Page: {page}")
                end_pages_text += page_text
            else:
                appendix_break = True
                remaining_group_pages.insert(0, page)
        #         remaining_group_pages.append(page)
        # remaining_group_pages = list(reversed(remaining_group_pages))
        remaining_group_text = "".join(individual_page_texts[page] for page in remaining_group_pages)
        if remaining_group_pages:
            grouped_pages_text[tuple(remaining_group_pages)] = remaining_group_text
            if tuple(remaining_group_pages) != tuple(group):
                del grouped_pages_text[tuple(group)]
        else:
            del grouped_pages_text[tuple(group)]

    grouped_end_pages_text = {tuple(end_pages): end_pages_text} if end_pages else {}

    # for group, text in grouped_end_pages_text.items():
    #     print(f"END Pages {group}: {len(text)}")
    # save_json = {}
    for i, (group, text) in enumerate(grouped_pages_text.items()):
        print(f"Pages({i}) {group}: {len(text)}")
        # pages_key = f"{group[0]}-{group[-1]}"
        # save_json[pages_key] = text
    
    # with open ("uk2_page_texts.json", "w") as f:
    #     json.dump(save_json, f, indent=2)
    # exit()
    # group, text = list(grouped_pages_text.items())[3]
    # print(f"Pages {group}: {len(text)}")

    #pathlib.Path("toc.md").write_bytes(toc_md_str.encode())
    # for k in grouped_pages_text.keys():
    #     if len(k) == 2:
    #         a,b = k
    #     else:
    #         a = k[0]
    #         b = ""
    #     print(f"Pages {a} to {b}:\n{len(grouped_pages_text[k])}")
    #     pathlib.Path(f"vol9({k}).md").write_bytes(grouped_pages_text[k].encode())

    async def process_page(page_nums_and_text: tuple, prior_schema: dict = None, example: str = None):
        page_nums, toc_md_toc_section_str = page_nums_and_text
        if not prior_schema:
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_VISION.format(toc_md_string=toc_md_toc_section_str)
        else:
            USER_PROMPT = prompts.TOC_HIERARCHY_USER_VISION_PLUS.format(initial_toc_hierarchy_schema=json.dumps(prior_schema, indent=4), example=example, num_levels=len(prior_schema), toc_md_string=toc_md_toc_section_str)
        if not example:
            page = doc[page_nums[0]]
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encode_page_as_base64(page)}",
                            },
                        }
                    ]
                }
            ]
            if len(page_nums) > 1:
                for next_page_num in page_nums[1:]:
                    next_page = doc[next_page_num]
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encode_page_as_base64(next_page)}",
                            },
                        }
                    )
        else:
            # toc_md_lines = toc_md_toc_section_str.split("\n")
            # section_lines = [line for line in toc_md_lines if not re.match(r'^\s*\d+[\s\.].*', line)]
            # toc_md_toc_section_str_re = "\n".join(section_lines)
            messages = [
                    {"role": "system", "content": prompts.TOC_HIERARCHY_SYS_PROMPT},
                    {"role": "user", "content": prompts.TOC_HIERARCHY_USER_PLUS.format(initial_toc_hierarchy_schema=json.dumps(prior_schema, indent=2), example=example, num_levels=len(prior_schema), toc_md_string=toc_md_toc_section_str)}
                ]
            messages_copy = copy.deepcopy(messages)
            #utils.print_coloured(f"{json.dumps(messages, indent=2)}", "yellow")
        while True:
            if not prior_schema:
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o")
            else:
                utils.print_coloured(f"{len(messages)} messages", "magenta")
                response = await llm.openai_client_chat_completion_request(messages, model="gpt-4o", temperature=0)
            try:
                message_content = response.choices[0].message.content
                toc_hierarchy_schema = json.loads(message_content)
                if not prior_schema:
                    utils.print_coloured(f"{json.dumps(toc_hierarchy_schema, indent=2)}", "yellow")
                    return toc_hierarchy_schema
                else:
                    levels_str = ""
                    for level, content in toc_hierarchy_schema.items():
                        levels_str += f"\n\n{level}:\n"
                        for line in content["lines"]:
                            levels_str += f"{line}\n"
                    utils.print_coloured(levels_str, "green")
                    validation_messages = messages_copy + [
                        {"role": "assistant", "content": json.dumps(toc_hierarchy_schema, indent=2)},
                        {"role": "user", "content": prompts.IS_THIS_JSON_CORRECT.format(levels_str=levels_str)}
                    ]
                    # for message in validation_messages:
                    #     if message["role"] == "user":
                    #         utils.print_coloured(f"{message['content'][:300]}", "blue")
                    #     else:
                    #         utils.print_coloured(f"{message['content'][:300]}", "magenta")
                    check_response = await llm.openai_client_chat_completion_request(validation_messages, model="gpt-4o", temperature=0)
                    check_content = check_response.choices[0].message.content
                    is_correct_dict = json.loads(check_content)
                    utils.print_coloured(is_correct_dict["is_correct"], "yellow")
                    # utils.print_coloured(f"{page_nums}:{json.dumps(toc_hierarchy_schema, indent=2)}", "yellow")
                    if isinstance(is_correct_dict["is_correct"], str):
                        is_correct_dict["is_correct"] = is_correct_dict["is_correct"].lower() == "true"
                    if is_correct_dict["is_correct"]:
                        utils.print_coloured(f"{page_nums}:{json.dumps(toc_hierarchy_schema, indent=2)}", "cyan")
                        return toc_hierarchy_schema 
                    else:
                        why_wrong = is_correct_dict.get("reason", None)
                        if why_wrong:
                            messages = messages_copy + [
                                {"role": "assistant", "content": json.dumps(toc_hierarchy_schema, indent=2)},
                                {"role": "user", "content": why_wrong + "\n\nPlease provide the correct JSON Object."}
                            ]
                            for message in messages:
                                if message["role"] == "user":
                                    utils.print_coloured(f"{message['content'][:300]}", "blue")
                                else:
                                    utils.print_coloured(f"{message['content'][:300]}", "magenta")
                            utils.print_coloured(f"{page_nums}: {why_wrong}", "red")
                            utils.print_coloured(f"{page_nums}:{json.dumps(toc_hierarchy_schema, indent=2)}", "red")
                            fuck_this = [
                                {"role": "system", "content": "You are an expert in correcting JSON Objects."},
                                {"role": "user", "content": f"I have this JSON:\n\n{json.dumps(toc_hierarchy_schema, indent=2)}" + why_wrong + "\n\nPlease provide the corrected JSON Object."}
                            ]
                            fuck_this_response = await llm.openai_client_chat_completion_request(fuck_this, model="gpt-4o", temperature=0)
                            fuck_this_content = fuck_this_response.choices[0].message.content
                            fuck_this_dict = json.loads(fuck_this_content)
                            utils.print_coloured(f"{page_nums}:{json.dumps(fuck_this_dict, indent=2)}", "green")
                        else:
                            continue

                #return toc_hierarchy_schema
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {e}")
                print(f"Message content: {message_content}")
                print("Retrying...")
                continue
            except Exception as e:
                print(f"Error: {e}")
                print("Retrying...")
                continue
                
    # group, text = next(iter(grouped_pages_text.items()))
    # print(f"Pages {group}: {len(text)}")
    # print(type(text))   
    # for group, text in grouped_end_pages_text.items():
    #     print(f"END Pages {group}: {len(text)}")
    #appendix_schema = await process_page(next(iter(grouped_end_pages_text.items())))
    # appendix_toc_hierarchy_schema = {}
    # for details in appendix_schema.values():
    #     level = details["level"]
    #     lines = details["lines"]
    #     for line in lines:
    #         appendix_toc_hierarchy_schema[line] = level
    # utils.print_coloured(json.dumps(appendix_toc_hierarchy_schema, indent=2), "green")
    prior_schema = {
        "Part": {
            "level": "#",
            "description": "Top-level section representing major divisions of the document",
            "lines": [
            "**PART 1**",
            "**PART 2**",
            "**PART 3**"
            ]
        },
        "Part Titles": {
            "level": "#",
            "description": "Titles of the top-level sections",
            "lines": [
            "GENERAL INTRODUCTORY PROVISIONS",
            "COMPANY FORMATION",
            "A COMPANY\u2019S CONSTITUTION"
            ]
        },
        "Chapter": {
            "level": "##",
            "description": "Second-level section representing subdivisions within parts",
            "lines": [
            "**CHAPTER 1**",
            "**CHAPTER 2**",
            "**CHAPTER 3**",
            "**CHAPTER 4**"
            ]
        },
        "Chapter Titles": {
            "level": "##",
            "description": "Titles of the second-level sections",
            "lines": [
            "INTRODUCTORY",
            "ARTICLES OF ASSOCIATION",
            "RESOLUTIONS AND AGREEMENTS AFFECTING A COMPANY\u2019S CONSTITUTION",
            "MISCELLANEOUS AND SUPPLEMENTARY PROVISIONS"
            ]
        },
        "Section": {
            "level": "###",
            "description": "Third-level section representing specific topics within chapters, containing items",
            "lines": [
            "_Companies and Companies Acts_",
            "_Types of company_",
            "_General_",
            "_Requirements for registration_",
            "_Registration and its effect_",
            "_General_",
            "_Alteration of articles_",
            "_Supplementary_",
            "_Statement of company\u2019s objects_"
            ]
        }
        }
    
    #appendix_schema = await process_page(next(iter(grouped_end_pages_text.items())))
    # appendix_schema, prior_schema = await asyncio.gather(
    #     process_page(next(iter(grouped_end_pages_text.items()))),
    #     process_page(next(iter(grouped_pages_text.items())))
    # )
    #utils.print_coloured(f"Appendix Schema: {json.dumps(appendix_schema, indent=2)}", "green")
    initial_toc_hierarchy_schema = {}
    for details in prior_schema.values():
        level = details["level"]
        description = details["description"]
        lines = details["lines"]
        if level not in initial_toc_hierarchy_schema:
            initial_toc_hierarchy_schema[level] = {
            "lines": f"(array of strings (verbatim), {description} Include any enumerations and Markdown formatting, e.g., {', '.join(lines)})"
            }
        else:
            current_description = initial_toc_hierarchy_schema[level]["lines"]
            new_description = f"{description} Include any enumerations and Markdown formatting, e.g., {', '.join(lines)}"
            initial_toc_hierarchy_schema[level]["lines"] = f"{current_description[:-1]} and/or {new_description})"
    #guide_str = json.dumps(initial_toc_hierarchy_schema, indent=2)
    utils.print_coloured(json.dumps(initial_toc_hierarchy_schema, indent=2), "green")
    _, text = next(iter(grouped_pages_text.items()))
    initial_toc_md_lines = text.split("\n")
    found_flags = {key: False for key in prior_schema.keys()}
    levels = {details["level"]: key for key, details in prior_schema.items()}
    found_lines = {level: [] for level in levels}
    first_idx = None
    last_idx = None
    for idx, line in enumerate(initial_toc_md_lines):
        for section, details in prior_schema.items():
            if line in details["lines"]:
                found_flags[section] = True
                found_lines[details["level"]].append((line, idx))

                if first_idx is None or idx < first_idx:
                    first_idx = idx
                if last_idx is None or idx > last_idx:
                    last_idx = idx
                if all(found_flags.values()):
                    break
        if all(found_flags.values()):
            break
    example_substring = '\n'.join(initial_toc_md_lines[first_idx:last_idx + 1])
    example = f"<example_text>\n{example_substring}\n</example_text>\n\n"
    for key, lines in found_lines.items():
        example += f"\nFrom the above text the {key} key sections are:\n\n"
        for line, idx in lines:
            example += f"{line} (at line {idx})\n"
            utils.print_coloured(f"{line} (at line {idx})", "cyan")
    example += "\n\nIt is EXTREMELY important to read the following instructions carefully before proceeding:\n\n"
    for level, lines in initial_toc_hierarchy_schema.items():
        trimmed_lines = lines['lines']
        if trimmed_lines.startswith("(array of strings (verbatim), ") and trimmed_lines.endswith(")"):
            trimmed_lines = trimmed_lines[len("(array of strings (verbatim), "):-1]
        example += f"\t- the {level} key is {trimmed_lines}\n"
    #example += "\n\nI have tried to remove all the ToC items in the ToC Markdown text below to make it easier for you to focus on the structure of the ToC. However, there may be some remaining text from the items that spanned multiple lines, so please make sure to identify and ignore these.\n\n"
    # for i in range(0, 5):
    #     print(f"Sleeping for {5-i} seconds...")
    #     await asyncio.sleep(1)
    # toc_hierarchy_schemas = await asyncio.gather(
    #     *[
    #         process_page(page_nums, prior_schema=initial_toc_hierarchy_schema, example=example)
    #         for page_nums in list(grouped_pages_text.items())
    #     ]
    # )
    # exit()
    entry = list(grouped_pages_text.items())[7]

    toc_hierarchy_schemas = await asyncio.gather(
        process_page(entry, prior_schema=initial_toc_hierarchy_schema, example=example)
    )
    exit()
    # # combine groups
    # items = list(grouped_pages_text.items())[1:]
    # grouped_pairs = [(items[i], items[i+1]) for i in range(0, len(items), 2)]
    # combined_grouped_pages_text = {}
    # for pair in grouped_pairs:
    #     pages_pair = pair[0][0] + pair[1][0]
    #     text_pair = pair[0][1] + pair[1][1]
    #     combined_grouped_pages_text[tuple(pages_pair)] = text_pair
    # if len(items) % 2 != 0:
    #     last_item = items[-1]
    #     combined_grouped_pages_text[last_item[0]] = last_item[1]
    # # for pages_range, text in combined_grouped_pages_text.items():
    # #     print(f"Combined Pages: {pages_range}, Combined Text: {len(text)}...")
    # toc_hierarchy_schemas = await asyncio.gather(
    #     *[
    #         process_page(page_nums, prior_schema=initial_toc_hierarchy_schema, example=example)
    #         for page_nums in list(combined_grouped_pages_text.items())
    #     ]
    # )

    combined_toc_hierarchy_schema = {}
    for details in prior_schema.values():
        for line in details["lines"]:
            if line not in combined_toc_hierarchy_schema:
                combined_toc_hierarchy_schema[line] = details["level"]
    for details in appendix_schema.values():
        for line in details["lines"]:
            if line not in combined_toc_hierarchy_schema:
                combined_toc_hierarchy_schema[line] = details["level"]
    for schema in toc_hierarchy_schemas:
        for level, content in schema.items():
            for line in content["lines"]:
                if line not in combined_toc_hierarchy_schema:
                    combined_toc_hierarchy_schema[line] = level

    ordered_items = sorted(combined_toc_hierarchy_schema.items(), key=lambda x: x[1].count('#'))
    ordered_dict = dict(ordered_items)
    utils.print_coloured(f"{json.dumps(ordered_dict, indent=4)}", "green")
    with open("uuk_toc_hierarchy_schema.json", "w") as f:
        json.dump(ordered_dict, f, indent=2)
        
    
asyncio.run(main_run())