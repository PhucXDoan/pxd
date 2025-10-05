import string



################################################################################################################################
#
# Default routine for conversions of S-expression symbols to Python values.
#



class Unquoted(str):
    pass



def default_mapping(value, quote):



    # Some direct substituations.

    match value:
        case 'False' : return False
        case 'True'  : return True
        case 'None'  : return None



    # Attempting to parse as an integer.

    try:
        return int(value)
    except ValueError:
        pass



    # Attempting to parse as a float.

    try:
        return float(value)
    except ValueError:
        pass



    # Symbols that are quoted with backticks are to be evaluated literally.
    # e.g:
    # >
    # >    (a b `2 + 2` c d)
    # >    (a b    4    c d)
    # >

    if quote == '`':
        return eval(value[1:-1], {}, {})



    # Other quoted symbols will just be a Python string.

    if quote:
        return value[1:-1]



    # We indicate that the symbol was unquoted.

    return Unquoted(value)



################################################################################################################################
#
# The S-expression parser itself.
#

def parse_sexp(input, mapping = default_mapping):



    # Strip whitespace and single-line comments.

    line_number = 1

    def eat_filler():

        nonlocal input, line_number

        while True:



            # Reached end of input.

            if not input:
                break



            # Keep track of current line number.

            if input[0] == '\n':
                line_number += 1



            # Strip whitespace.

            if input[0] in string.whitespace:
                input = input[1:]



            # Strip single-line comment.

            elif input[0] == '#':
                input        = '\n'.join(input.split('\n', maxsplit = 1)[1:])
                line_number += 1



            # We're at the next token!

            else:
                break



    # Recursively parse the S-expression.

    def eat_expr():

        nonlocal input, line_number



        # Look for the start of the next token.

        eat_filler()

        if not input:
            raise SyntaxError('Reached end of input while looking for the next token.')



        # Parse subexpression.

        if input[0] == '(':

            input = input[1:]



            # Get each element.

            values = []

            while True:

                eat_filler()

                if input and input[0] == ')':
                    break
                else:
                    values += [eat_expr()]



            # Found the end of the subexpression.

            input = input[1:]

            return tuple(values)



        # Parse symbol.

        else:

            value = ''
            quote = None # TODO Escaping.

            while True:



                # At the end of the input or line.

                if not input or input[0] == '\n':

                    if quote is not None:
                        raise SyntaxError(f'On line {line_number}, string is missing ending quote ({quote}).')

                    break



                # Found end of the unquoted symbol.

                # TODO Should something like "unconnected-(U1-PE2-Pad1)"
                #      be parsed as ('unconnected-', ('U1-PE2-Pad1',))
                #      or as ('unconnected-(U1-PE2-Pad1)')?

                if input[0] in string.whitespace + '#' and quote is None:
                    break



                # Determine if we found the opening/closing quotation.

                found_end_quote = input[0] == quote and value != ''

                if input[0] in ('"', "'", '`') and value == '':
                    quote = input[0]



                # Eat the next character for the symbol.

                value += input[0]
                input  = input[1:]



                # End of symbol if we found the ending quote.

                if found_end_quote:

                    # This is mostly to catch weird quote mismatches.
                    if input and input[0] not in string.whitespace + ')':
                        raise SyntaxError(
                            f'On line {line_number}, string should have whitespace or ")" after the ending quote ({quote}).'
                        )

                    break



            # Map the value if possible.

            assert value

            return mapping(value, quote)



    # Parse the input which should just be a single subexpression.

    eat_filler()

    if not input or input[0] != '(':
        raise SyntaxError(f'Input should start with the "(" token.')

    result = eat_expr()

    eat_filler()

    if input:
        raise SyntaxError(f'On line {line_number}, additional tokens were found; input should just be a single value.')

    return result
