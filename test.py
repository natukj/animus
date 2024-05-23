from parser.pdf_parser import PDFParser
import asyncio
import json
from thefuzz import process

async def main_run():
    parser = PDFParser()

    md_levels = {'Chapter': '#', 'Part': '##', 'Division': '###', 'Subdivision': '####', 'Guide': '####', 'Operative provisions': '####', 'General': '####'}
    
    level_info_list = await parser.run_find_levels_from_json_path(f"master_toc.json")
    with open("content.md", "r") as f:
        content_md_lines = f.readlines()

    content_md_section_lines = [(line.strip(), idx) for idx, line in enumerate(content_md_lines) if line.startswith('#')]

    formatted_section_names = []
    for level_info in level_info_list:
        section_type, number, title = level_info
        if not section_type:
            section_match = None
        else:
            section_match = process.extractOne(section_type, md_levels.keys(), score_cutoff=95)
        if section_match:
            matched_section = section_match[0]
            md_level = md_levels[matched_section]
        else:
            max_level = max(md_levels.values(), key=len)
            md_level = max_level

        if section_type and number and title:
            section_name = f'{section_type} {number} {title}'
        elif not number:
            if section_type in title:
                section_name = title
            else:
                section_name = f'{section_type} {title}'
        else:
            section_name = section_type
        
        formatted_section_names.append(f"{md_level} {section_name}")

    start_lines = []
    remaining_content_md_section_lines = content_md_section_lines[:]

    for i, formatted_section_name in enumerate(formatted_section_names):
        matches = process.extractBests(formatted_section_name, [line for line, _ in remaining_content_md_section_lines], score_cutoff=80, limit=10)
        if matches:
            highest_score = max(matches, key=lambda x: x[1])[1]
            highest_score_matches = [match for match in matches if match[1] == highest_score]
            # select the highest score with the lowest index
            matched_line = min(highest_score_matches, key=lambda x: next(idx for line, idx in remaining_content_md_section_lines if line == x[0]))[0]
            start_line_idx = next(idx for line, idx in remaining_content_md_section_lines if line == matched_line)
            
            remaining_content_md_section_lines = [item for item in remaining_content_md_section_lines if item[1] > start_line_idx]
            
            start_line = content_md_lines[start_line_idx].strip()
            md_level, md_section_name = formatted_section_name.split(' ', 1)
            start_lines.append((formatted_section_names[i], start_line, start_line_idx))
            print(f"Matched {md_section_name} to {start_line} at idx: {start_line_idx}")
        else:
            print(f"Could not match {formatted_section_names[i].strip().lstrip('#').strip()}")
            print(f"Remaining: {remaining_content_md_section_lines}")

    # for section, start, idx in start_lines:
    #     print(f"Section: {section}\nStart Line: {start} at idx: {idx}\n")

    # section_name_embeddings = model.encode(formatted_section_names, convert_to_tensor=True)
    # md_section_line_embeddings = model.encode([line[0] for line in content_md_section_lines], convert_to_tensor=True)
    # remaining_md_section_line_embeddings = md_section_line_embeddings
    
    # start_lines = []
    # used_indices = set()
    # for i, section_name_embedding in enumerate(section_name_embeddings):
    #     matchs = util.semantic_search(section_name_embedding.unsqueeze(0), remaining_md_section_line_embeddings, score_function=util.cos_sim, top_k=3)
    #     highest_score = max(match['score'] for match in matchs[0])
    #     highest_score_matches = [match for match in matchs[0] if match['score'] == highest_score]
    #     start_idx = min(match['corpus_id'] for match in highest_score_matches if match['corpus_id'] not in used_indices)
    #     used_indices.add(start_idx)
    #     start_line_idx = content_md_section_lines[start_idx][1]
    #     start_line = content_md_lines[start_line_idx].strip()
    #     start_lines.append((formatted_section_names[i], start_line, start_line_idx))
    #     print(f"Matched {formatted_section_names[i]} to {start_line} at idx:({start_idx}) {start_line_idx}")

    #     remaining_md_section_line_embeddings = torch.cat([remaining_md_section_line_embeddings[:start_line_idx], remaining_md_section_line_embeddings[start_line_idx + 1:]], dim=0)

    # for section, start, idx in start_lines:
    #     print(f"Section: {section}\nStart Line: {start} at idx: {idx}\n")
    
    # matches = util.semantic_search(section_name_embeddings, md_section_line_embeddings, score_function=util.cos_sim, top_k=10)
    # start_end_lines = []
    # used_indices = set()
    
    # for i, match_list in enumerate(matches):
    #     for match in match_list:
    #         start_idx = match['corpus_id']
    #         if start_idx not in used_indices:
    #             start_line_idx = content_md_section_lines[start_idx][1]
    #             start_line = content_md_lines[start_line_idx].strip()
    #             start_end_lines.append((formatted_section_names[i], start_line, start_line_idx))
    #             used_indices.add(start_idx)
    #             break

    # # Sort by the index to ensure correct order
    # start_end_lines.sort(key=lambda x: x[2])

    # # Output start lines for each section
    # for section, start, idx in start_end_lines:
    #     print(f"Section: {section}\nStart Line: {start} at idx: {idx}\n")
    # print(f"{len(match_list)} remaining sections unmatched")

asyncio.run(main_run())
