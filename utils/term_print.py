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
