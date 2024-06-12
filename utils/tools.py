import base64
import tiktoken

def count_tokens(text: str, encoding_name: str = "o200k_base") -> int:
    """
    count the number of tokens in the given text using the specified encoding.
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens