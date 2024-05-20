IS_THIS_JSON_CORRECT = """You are tasked with checking the work of a colleague who was tasked with:

{SYSTEM_PROMPT}

Your colleague was given this information:

{USER_PROMPT}

Your colleague's response was:

{RESPONSE_JSON}

You must response with a JSON Object that indicates whether your colleague's response is correct or incorrect according to the following guidelines:

**Incorrect:**
If the response is incorrect, you must provide the correct JSON Object.

**Correct:**
If the response is correct, you must provide an empty JSON Object."""