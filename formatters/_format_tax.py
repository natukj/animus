import os
import json
import re
import utils

# directory = "/Users/jamesqxd/Documents/norgai-docs/TAX/parsed"
# def extract_number(filename):
#     match = re.search(r'\d+', filename)
#     return int(match.group()) if match else 0


# files = [f for f in os.listdir(directory) if f.endswith(".json")]
# sorted_files = sorted(files, key=extract_number)

# with open(os.path.join(directory, sorted_files[0]), "r") as f:
#     contents = json.load(f)
# for filename in sorted_files[1:]:
#     file_path = os.path.join(directory, filename)
#     print(f"Processing {file_path}")
#     with open(file_path, "r") as f:
#         new_contents = json.load(f)
#     for new_item in new_contents["contents"]:
#         title = new_item.get("title")
#         existing_item = next((item for item in contents["contents"] if item.get("title") == title), None)
        
#         if existing_item:
#             existing_item["children"].extend(new_item["children"])
#         else:
#             contents["contents"].append(new_item)

# with open(os.path.join(directory, "final_aus_tax.json"), "w") as f:
#     json.dump(contents, f, indent=4)
# exit()
def get_all_titles(item, depth=0, title_string=""):
    title_string += "\t" * depth + item.get("title") + "\n"
    if "children" in item:
        for child in item["children"]:
            title_string = get_all_titles(child, depth + 1, title_string)
    return title_string
def create_title_dict(item, title_dict=None):
    if title_dict is None:
        title_dict = {}
    title = item.get("title")
    title_dict[title] = {}
    if "children" in item:
        for child in item["children"]:
            title_dict[title].update(create_title_dict(child))
    return title_dict


directory = "/Users/jamesqxd/Documents/norgai-docs/TAX/parsed/final_aus_tax.json"
with open(directory) as f:
    data = json.load(f)

contents = data["contents"]

all_titles = ""
title_dict = {}
for item in contents:
    all_titles += get_all_titles(item)
    title_dict.update(create_title_dict(item))

# print(all_titles)
# print(utils.count_tokens(all_titles))
with open("/Users/jamesqxd/Documents/norgai-docs/TAX/parsed/final_aus_tax_titles.json", "w") as f:
    json.dump(title_dict, f, indent=4)