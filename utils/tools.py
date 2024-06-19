import sys
import base64
import tiktoken
import fitz
from typing import Dict, Any, Callable
from termcolor import colored

def print_coloured(text, color, attrs=None):
    """
    Print text in the terminal with specified color and attributes.

    Args:
    text (str): The text to print.
    color (str): The color to use. Options include 'grey', 'red', 'green', 'yellow', 'blue',
                 'magenta', 'cyan', and 'white'.
    attrs (list of str, optional): List of attributes. Options include 'bold', 'dark', 
                                   'underline', 'blink', 'reverse', 'concealed'.
    """
    print(colored(text, color, attrs=attrs))

def count_tokens(text: str, encoding_name: str = "o200k_base") -> int:
    """
    count the number of tokens in the given text using the specified encoding.
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens

def encode_page_as_base64(page: fitz.Page, xzoom: float = 2.0, yzoom: float = 1.0) -> str:
    # NOTE gpt-4o found (2, 1) to be the clearest zoom values
    pix = page.get_pixmap(matrix=fitz.Matrix(xzoom, yzoom))
    return base64.b64encode(pix.tobytes()).decode('utf-8')

def message_template_vision(user_prompt: str, *images: str) -> Dict[str, Any]:
    message_template = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt}
                ] + [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}
                    for image in images[:30]  # limit to the first 30 images think gpt4o will only take 39
                ]
            }
        ]
    return message_template

def is_correct(prompt: str = "Is this correct? (Y/n): ", confirmation_value: str = 'y', error_message: str = "fml", exit_on_error: bool = True):
    user_input = input(prompt).strip().lower()
    if user_input != confirmation_value.lower():
        print_coloured(error_message, "red")
        if exit_on_error:
            sys.exit()