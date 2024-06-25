import asyncio
import json
import llm, prompts, utils
import random

def traverse_randomly(tax_data, current_path=[]):
    current_section = find_section_by_path(tax_data, current_path)
    if not current_section:  # No children, end of the path
        return

    utils.print_coloured(" > ".join(current_path), "cyan")
    print("Current Section Titles:")
    for title, _ in current_section:
        utils.print_coloured(title, "yellow")
    
    # Randomly choose one of the child sections to traverse into next
    next_title = random.choice(current_section)[0]
    current_path.append(next_title)
    traverse_randomly(tax_data, current_path)

# initial_sections = find_section_titles(tax_data)
# traverse_randomly(tax_data, [initial_sections[0][0]]) 
# exit()

def find_section_titles(tax_data, search_title=None):
    def search_children(children, search_title):
        for child in children:
            if child['title'] == search_title:
                return [(subchild['title'], subchild['content']) for subchild in child.get('children', [])]
        return []

    if search_title is None:
        return [(section['title'], section['content']) for section in tax_data]
    else:
        for section in tax_data:
            if section['title'] == search_title:
                return [(child['title'], child['content']) for child in section.get('children', [])]
            elif 'children' in section:
                result = search_children(section['children'], search_title)
                if result:
                    return result
        return []
def find_section_by_path(tax_data, path):
    def search_children(children, index):
        for child in children:
            if child['title'] == path[index]:
                # check if this is the last component of the path or continue deeper
                if index + 1 == len(path):
                    return [(subchild['title'], subchild['content']) for subchild in child.get('children', [])]
                else:
                    return search_children(child.get('children', []), index + 1)
        return []
    return search_children(tax_data, 0)

    
with open("/Users/jamesqxd/Documents/norgai-docs/TAX/parsed/final_aus_tax.json", "r") as f:
    tax_data = json.load(f)["contents"]

async def traverse_document(query, tax_data):
    summary = ""
    initial_sections = find_section_titles(tax_data)
    top_titles_arr = [sec[0] for sec in initial_sections]
    top_contents_arr = [top_node[1] for top_node in initial_sections]
    top_titles = "\n".join(top_titles_arr)

    prompt = prompts.TRAVERSAL_USER_INIT.format(query=query, top_titles=top_titles)
    messages = [{"role": "system", "content": prompts.TRAVERSAL_SYS}, {"role": "user", "content": prompt}]

    decision_response = await llm.openai_client_chat_completion_request(messages)
    decision_str = decision_response.choices[0].message.content
    decision = json.loads(decision_str)
    decision_print = decision["title"][0]
    utils.print_coloured(f"traversal agent chose '{decision_print}' from:\n{top_titles}", "green")
    print('\n')

    if decision["action"] == "end":
        return []

    path = [decision["title"][0]]
    current_sections = find_section_by_path(tax_data, path)
    current_content = top_contents_arr[top_titles_arr.index(path[-1])]
    i = 0
    traversed_info = []
    prompt += "\n\nYour traversal path is:"
    while True:
        current_title = path[-1] if path else "You are at the Top Level you can not go back."
        children_titles = "\n".join([title for title, _ in current_sections])
        if not children_titles:
            children_titles = "You are at the bottom level."
        joined_path = " > ".join(path)
        utils.print_coloured(f"Current path: {joined_path}", "cyan")
        user_message = prompts.TRAVERSAL_USER.format(path=" > ".join(path),
                                                     title=current_title,
                                                     content=current_content)
        traversed_info.append(user_message)
        prompt += "\n" + user_message
        prompt_tokens = utils.count_tokens(prompt)
        messages = [{"role": "system", "content": prompts.TRAVERSAL_SYS}, 
                    {"role": "user", "content": prompt + prompts.TRAVERSAL_USER_PLUS.format(children=children_titles, query=query)}]
        decision_response = await llm.openai_client_chat_completion_request(messages)
        decision_str = decision_response.choices[0].message.content
        decision = json.loads(decision_str)
        i += 1
        if decision["action"] == "end" or prompt_tokens > 20000:
            print(f"Ending traversal because decision is {decision['action']} or prompt_tokens is {prompt_tokens}")
            traversed_info_str = "\n".join(traversed_info)
            end_user_message = prompts.TRAVERSAL_USER_END.format(traversed_info=traversed_info_str, query=query)
            messages = [{"role": "system", "content": prompts.TRAVERSAL_SYS}, 
                        {"role": "user", "content": end_user_message}]
            end_response = await llm.openai_client_chat_completion_request(messages, model="gpt-4-turbo", response_format="text")
            summary = end_response.choices[0].message.content
            break
        elif decision["action"] == "next":
            decision_print = decision["title"][0]
            utils.print_coloured(f"traversal agent chose '{decision_print}' from:\n{children_titles}", "green")
            path.append(decision["title"][0])
            current_content = next((content for title, content in current_sections if title == decision["title"][0]), "No Content Found")
            current_sections = find_section_by_path(tax_data, path)
        elif decision["action"] == "back" or not decision["title"]:
            utils.print_coloured(f"traversal agent chose to go back", "green")
            if len(path) > 1:
                path.pop()
                current_sections = find_section_by_path(tax_data, path)
            else:
                path = []
                current_sections = initial_sections
                current_content = ""

    return path, summary

async def main(query):
    result_path, summary = await traverse_document(query, tax_data)
    print("Traversal completed with path:", " > ".join(result_path))
    utils.print_coloured(summary, "green")

# Example usage
query = "What can I claim as a tax deduction as a PAYG employee?"
asyncio.run(main(query))

# async def traverse_section(query, section_titles, path=""):
#     titles = "\n".join([title for title, _ in section_titles])
#     print("Traversing section:", titles)
#     prompt = prompts.TRAVERSAL_USER_INIT.format(query=query, top_titles=titles)
#     messages = [
#         {"role": "system", "content": prompts.TRAVERSAL_SYS},
#         {"role": "user", "content": prompt}
#     ]
#     while True:
#         decision_response = await llm.openai_client_chat_completion_request(messages)
#         decision_str = decision_response.choices[0].message.content
#         decision = json.loads(decision_str)
#         print("Decision:", decision)
#         if decision["action"].lower() == "end":
#             return path
#         elif decision["action"].lower() == "next":
#             next_titles = decision["title"]
#             print("Next titles:", next_titles)
#             next_sections = [(title, find_section_titles(section_titles, title)) for title in next_titles if title]

#             # Prepare the next set of prompts based on LLM decision
#             next_titles_str = "\n".join([title for title, _ in next_sections])
#             next_prompt = prompts.TRAVERSAL_USER.format(path=path, title=next_titles_str, content="")
#             messages.append({"role": "user", "content": next_prompt})

#             # Recursively traverse each next section
#             tasks = [traverse_section(query, section, path + " > " + title) for title, section in next_sections]
#             results = await asyncio.gather(*tasks)
# async def main(query):
#     top_nodes = find_section_titles(tax_dict)
#     results = await asyncio.gather(*[traverse_section(query, top_nodes)])
#     print("Traversal completed with results:", results)

# # Example usage
# query = "What can I claim as a tax deduction if I work from home 100% of the time?"
# asyncio.run(main(query))