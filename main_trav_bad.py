import json
import asyncio
import llm, prompts, utils
import pandas as pd
import copy
import ast

tax_df_path = "ztest_tax_output/processed_tax_data.csv"

df = pd.read_csv(tax_df_path)

# add depths
df['depth'] = df['path'].str.count('/')

LLM_CHOICE = "claude"

async def traverse_branch(current_path, current_depth, path_stack, memory_paths, searched_paths, query, i):
    inst_prompt = prompts.TRAVERSAL_USER_INST_CLAUDE
    content = ""
    while len(memory_paths) < 5:
        paths = utils.get_subpaths(df, current_path)
        utils.print_coloured(f"Current path: {current_path} (Memory: {len(memory_paths)})", "yellow")
        if current_path:
            content, references = utils.get_content_and_references(df, current_path)
        
        subpath_options = utils.get_subpath_options(paths, current_depth)
        
        if i == 0:
            formatted_prompt = inst_prompt + prompts.TRAVERSAL_USER_INST_CLAUDE_INIT.format(query=query, subpath_options=subpath_options)
            i = 1
        else:
            formatted_prompt = inst_prompt + prompts.TRAVERSAL_USER_MEMORY_CLAUDE.format(memory_paths="\n".join(memory_paths), searched_paths="\n".join(searched_paths)) + prompts.TRAVERSAL_USER_INST_CLAUDE_PLUS.format(current_path=current_path, content=content, subpath_options=subpath_options, query=query)
            #print(prompts.TRAVERSAL_USER_MEMORY_CLAUDE.format(memory_paths="\n".join(memory_paths), searched_paths="\n".join(searched_paths)))

        messages = [{"role": "user", "content": formatted_prompt}]
        result = await llm.claude_client_chat_completion_request(messages)
        claude_thoughts = utils.extract_between_tags("thinking", result, strip=True)
        #utils.print_coloured(claude_thoughts, "cyan")
        claude_action = utils.extract_between_tags("action", result, strip=True)
        utils.print_coloured(claude_action, "green")
        claude_traverse = utils.extract_between_tags("traverse", result, strip=True)
        utils.print_coloured(claude_traverse, "yellow")
        claude_save = utils.extract_between_tags("save", result, strip=True)
        utils.print_coloured(claude_save, "magenta")
        
        searched_paths.add(current_path)

        if claude_action.lower() == 'traverse':
            try:
                traverse_options = ast.literal_eval(claude_traverse)
            except (ValueError, SyntaxError):
                utils.print_coloured("Failed to parse traverse options as list", "red")
                try:
                    traverse_options = json.loads(claude_traverse)
                except json.JSONDecodeError:
                    utils.print_coloured("Failed to parse traverse options as JSON", "red")
                    traverse_options = [option.strip().strip('[]') for option in claude_traverse.split(',')]
                    traverse_options = [option for option in traverse_options if option]
            traverse_options = [str(option) for option in traverse_options]
            utils.print_coloured(f"Traverse options: {traverse_options}", "green")
            
            if len(traverse_options) > 1:
                tasks = [
                    traverse_branch(
                        paths[int(option) - 1] if option.isdigit() and 1 <= int(option) <= len(paths) else current_path,
                        current_depth + 1 if option.isdigit() and 1 <= int(option) <= len(paths) else current_depth,
                        copy.deepcopy(path_stack),
                        memory_paths,
                        searched_paths,
                        query,
                        1
                    ) for option in traverse_options
                ]
                await asyncio.gather(*tasks)
                break
            
            elif traverse_options:
                choice = traverse_options[0].strip()
                if choice.startswith('r'):
                    ref_index = int(choice[1:]) - 1
                    if ref_index < len(references):
                        new_path = utils.find_path_by_self_ref(df, references[ref_index])
                        if new_path:
                            path_stack.append(current_path)
                            current_path = new_path
                            utils.print_coloured(f"Traversing to reference {ref_index + 1}: {current_path}", "green")
                            current_depth = df[df['path'] == current_path]['depth'].iloc[0]
                elif choice.isdigit() and 1 <= int(choice) <= len(paths):
                    path_stack.append(current_path)
                    current_path = paths[int(choice) - 1]
                    utils.print_coloured(f"Traversing to subpath {choice}: {current_path}", "green")
                    current_depth += 1
        elif claude_action.lower() == 'back':
            if path_stack:
                current_path = path_stack.pop()
                utils.print_coloured(f"Going back to path: {current_path}", "red")
                
                # Use .loc instead of .iloc and add error handling
                matching_rows = df[df['path'] == current_path]
                if not matching_rows.empty:
                    current_depth = matching_rows['depth'].iloc[0]
                else:
                    utils.print_coloured(f"Warning: Could not find depth for path {current_path}. Setting depth to 0.", "yellow")
                    current_depth = 0
            else:
                utils.print_coloured(f"Cannot go back further. Already at the root {current_path}.", "yellow")
                current_path = current_path
                current_depth = 0
                    # if path_stack:
            #     current_path = path_stack.pop()
            #     utils.print_coloured(f"Going back to path: {current_path}", "red")
            #     current_depth = df[df['path'] == current_path]['depth'].iloc[0]
        elif claude_action.lower() == 'end':
            utils.print_coloured(claude_thoughts, "red")
            break

        if claude_save.lower() == 'true':
            memory_paths.add(current_path)
            utils.print_coloured(f"Added {current_path} to memory", "cyan")
        else:
            searched_paths.add(current_path)
            utils.print_coloured(f"Added {current_path} to searched paths", "magenta")

    return memory_paths, searched_paths

async def main_trav():
    current_path = ""
    current_depth = 0
    path_stack = []
    memory_paths = set()
    searched_paths = set()
    query = "What can I claim as a tax deduction as a PAYG employee?"
    
    final_memory_paths, final_searched_paths = await traverse_branch(current_path, current_depth, path_stack, memory_paths, searched_paths, query, 0)

    print("Traversal complete.")
    memory_content = ""
    for path in final_memory_paths:
        memory_content += utils.get_content(df, path)
    # print("\nSearched paths:")
    # for path in final_searched_paths:
    #     print(path)
    formatted_answer_prompt = prompts.TRAVERSAL_USER_ANSWER_CLAUDE.format(query=query, memory_content=memory_content)
    messages = [{"role": "user", "content": formatted_answer_prompt}]
    result = await llm.claude_client_chat_completion_request(messages)
    utils.print_coloured(result, "yellow")
    claude_thinking_answer = utils.extract_between_tags("thinking", result, strip=True)
    utils.print_coloured(claude_thinking_answer, "cyan")
    claude_answer = utils.extract_between_tags("answer", result, strip=True)
    utils.print_coloured(claude_answer, "green")

asyncio.run(main_trav())
