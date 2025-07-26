import string
from ..pxd.utils import ErrorLift
from ..pxd.log   import log



class Error(Exception):
    pass



class Atom(str):

    def __new__(cls, value):
        obj = super().__new__(cls, value)
        obj.string = value
        return obj

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f'Atom({super().__repr__()})'



def parse(input):

    line_number = 1



    # Strip whitespace and single-line comments.

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



    # Recursively parse the s-expression.

    def eat_expr():

        nonlocal input, line_number



        # Look for the start of the next token.

        eat_filler()

        if not input:
            raise Error('Reached end of input while looking for the next token.')



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
                        raise Error(f'On line {line_number}, string is missing ending quote ({quote}).')

                    break



                # Found end of the unquoted symbol.

                if input[0] in string.whitespace + '#()' and quote is None:
                    break



                # Determine if we found the opening/closing quotation.

                found_end_quote = input[0] == quote and value != ''

                if input[0] in ('"', "'") and value == '':
                    quote = input[0]



                # Eat the next character for the symbol.

                value += input[0]
                input  = input[1:]



                # End of symbol if we found the ending quote.

                if found_end_quote:

                    # This is mostly to catch weird quote mismatches.
                    if input and input[0] not in string.whitespace + ')':
                        raise Error(
                            f'On line {line_number}, string should have whitespace or ")" after the ending quote ({quote}).'
                        )

                    break



            # Map the value if possible.

            assert value

            def mapper(value, quote): # TODO This can be exposed to the caller to be customized.

                match value:

                    case 'False' : return False
                    case 'True'  : return True
                    case 'None'  : return None

                    case _:

                        if quote:
                            return value[1:-1]

                        try:
                            return int(value)
                        except ValueError:
                            pass

                        try:
                            return float(value)
                        except ValueError:
                            pass

                return Atom(value) # To indicate that the symbol was unquoted.

            return mapper(value, quote)



    # Parse the input which should just be a single subexpression.

    eat_filler()

    if not input or input[0] != '(':
        raise Error(f'Input should start with the "(" token.')

    result = eat_expr()

    eat_filler()

    if input:
        raise Error(f'On line {line_number}, additional tokens were found; input should just be a single value.')

    return result
