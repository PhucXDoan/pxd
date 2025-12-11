#! /usr/bin/env python3

import sys, logging, pathlib
import prompter



class RootFormatter(logging.Formatter):

    def format(self, record):



        message = super().format(record)



        # The `table` property allows for a
        # simple, justified table to be outputted.

        if hasattr(record, 'table'):

            for just_key, just_value in justify([
                (
                    ('<' , str(key  )),
                    (None, str(value)),
                )
                for key, value in record.table
            ]):
                message += f'\n{just_key} : {just_value}'



        # Any newlines will be indented so it'll look nice.

        indent = ' ' * len(f'[{record.levelname}] ')

        message = '\n'.join([
            message.splitlines()[0],
            *[f'{indent}{line}' for line in message.splitlines()[1:]]
        ])



        # Give each log a bit of breathing room.

        message += '\n'



        # Prepend the log level name and color based on severity.

        coloring = {
            'DEBUG'    : '\x1B[0;35m',
            'INFO'     : '\x1B[0;36m',
            'WARNING'  : '\x1B[0;33m',
            'ERROR'    : '\x1B[0;31m',
            'CRITICAL' : '\x1B[1;31m',
        }[record.levelname]

        reset = '\x1B[0m'

        message = f'{coloring}[{record.levelname}]{reset} {message}'



        return message



logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger_handler = logging.StreamHandler(sys.stdout)
logger_handler.setFormatter(RootFormatter())

logger.addHandler(logger_handler)



class InterfaceFormatter(logging.Formatter):

    def format(self, record):



        message = super().format(record)



        # The `table` property allows for a
        # simple, justified table to be outputted.

        if hasattr(record, 'table'):

            for just_key, just_value in justify([
                (
                    ('<' , str(key  )),
                    (None, str(value)),
                )
                for key, value in record.table
            ]):
                message += f'\n{just_key} : {just_value}'



        if record.levelname != 'INFO':

            # Any newlines will be indented so it'll look nice.

            indent = ' ' * len(f'[{record.levelname}] ')

            message = '\n'.join([
                message.splitlines()[0],
                *[f'{indent}{line}' for line in message.splitlines()[1:]]
            ])



            # Give each log a bit of breathing room.

            message += '\n'



            # Prepend the log level name and color based on severity.

            coloring = {
                'DEBUG'    : '\x1B[0;35m',
                'INFO'     : '\x1B[0;36m',
                'WARNING'  : '\x1B[0;33m',
                'ERROR'    : '\x1B[0;31m',
                'CRITICAL' : '\x1B[1;31m',
            }[record.levelname]

            reset = '\x1B[0m'

            message = f'{coloring}[{record.levelname}]{reset} {message}'



        return message



interface_logger = logging.getLogger('interface')
interface_logger.setLevel(logging.DEBUG)

interface_logger_handler = logging.StreamHandler(sys.stdout)
interface_logger_handler.setFormatter(InterfaceFormatter())

interface_logger.addHandler(interface_logger_handler)

interface = prompter.Interface(
    name        = pathlib.Path(__file__).name,
    description = 'Command-line interface to do stuff.',
    logger      = interface_logger,
)


@interface.new_verb(
    {
        'name'        : 'subtract',
        'description' : 'Subtracts two given numbers.',
    },
    {
        'name'        : 'minuend',
        'description' : 'The value to be subtracted from.',
        'type'        : int,
    },
    {
        'name'        : 'subtrahend',
        'description' : 'The value to subtracted by.',
        'type'        : int,
    },
)
def some_verb_here(parameters):

    print(parameters)



@interface.new_verb(
    {
        'name'        : 'subtracter',
        'description' : 'Subtracts two given numbers.',
    },
    {
        'name'        : 'minuend',
        'description' : 'The value to be subtracted from.',
        'type'        : int,
        'default'     : False,
    },
    {
        'name'        : 'subtrahend',
        'description' : 'The value to subtracted by.',
        'type'        : int,
    },
)
def some_verb_here(parameters):

    print(parameters)



@interface.new_verb(
    {
        'name'        : 'subtracting',
        'description' : 'Subtracts two given numbers.',
    },
    {
        'name'        : 'minuend',
        'description' : 'The value to be subtracted from.',
        'type'        : ['meow', 'woof', 'bark'],
    },
    {
        'name'        : 'subtrahend',
        'description' : 'The value to subtracted by.',
        'type'        : int,
    },
)
def some_verb_here(parameters):

    print(parameters)




interface.invoke(sys.argv[1:])
