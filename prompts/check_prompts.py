IS_THIS_JSON_CORRECTFUCK = """Please evaluate if the values in the JSON Object below are correctly assigned:

{toc_hierarchy_schema}

It must follow this schema:

    {{
        "#": {{
                "lines": "(array of strings)"
        }},
        "##": {{
                "lines": "(array of strings)"
        }},
        "###": {{
                "lines": "(array of strings)"
        }}
    }}

Here is guide as to what the keys should contain:

{prior_schema}

Your ONLY job is to ensure that the JSON Object values are correctly assigned. Your are not evaluating the values themselves, ONLY whether those values are in the correct keys. 

Your primary focus should be based on the following criteria:

- The values are correctly assigned to the keys based on the examples and descriptions provided.
- They do NOT need to be in the correct order.
- Not all keys need to have values.
- You are NOT evaluating the values themselves, ONLY whether those values are in the correct keys.
- Make NO assumptions about the text your colleague was working with - ONLY evaluate the value placement in the JSON Object.

Make NO assumptions about the text - ONLY evaluate the value placement in the JSON Object.

{{
    "is_correct": (Boolean, True if the JSON Object is correct, False if it is incorrect),
    "reasoning": (String, a brief explanation of why the JSON Object is correct or incorrect)
}}
"""
IS_THIS_JSON_CORRECT = """Can you please double check your response to verify that the sections are correctly assigned to the right level of hierarchy? 

If is extremely important that each section is correctly assigned to the correct level of hierarchy. Have some faith in your response and only return False if you are certain that the values are incorrectly assigned.

Respond with a JSON Object following:

{{
    "is_correct": (Boolean, True if the JSON Object is correct, False if it is incorrect),
    "reason": (String (optional), a message to yourself detailing why the JSON Object is incorrect and the corrections that need to be made),
}}

Only respond with a "reason" key if you believe there is an error in your response. The reason should detail the corrections that need to be made and begin with "The JSON Object is incorrect because...". You must be explicit in your reasoning and provide which exact sections are incorrectly assigned and where they should be assigned instead. Below is a list of the sections and their corresponding levels of hierarchy in your response:
{levels_str}
"""