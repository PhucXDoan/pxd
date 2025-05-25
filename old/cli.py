#!/usr/bin/env python3
import os, sys, types, pathlib, filecmp, shutil
import MetaPreprocessor

################################################################ Helpers ################################################################

def ROOT(*subpaths):

    # Easy way to make multiple paths relative to project root.
    if len(subpaths) == 1 and '\n' in subpaths[0]:
        return [Common.ROOT(path) for path in Common.lines_of(subpaths[0])]

    # Easy way to concatenate paths together to make a path relative to project root.
    else:
        return pathlib.Path(
            pathlib.Path(__name__).absolute().relative_to(pathlib.Path.cwd(), walk_up=True).parent,
            *subpaths
        )

commands = {}
def Command(description):
    def decorator(function):
        global commands
        assert function.__name__ not in commands
        commands[function.__name__] = types.SimpleNamespace(
                description = description,
                function    = function,
            )
        return function
    return decorator

################################################################ Commands ################################################################

@Command(f'Run the Meta-Preprocessor on all examples and verify the output.')
def test():

    example_dirs  = [path for path in ROOT('./examples/').iterdir() if path.is_dir()]
    examplei_just = len(str(len(example_dirs)))

    for examplei, example_dir in enumerate(example_dirs):

        if examplei:
            print()

        print(f'[{str(examplei + 1).rjust(examplei_just)}/{len(example_dirs)}] {example_dir.stem}')

        #
        # Clean build folders.
        #

        build_dir = pathlib.Path(example_dir, 'build')
        shutil.rmtree(build_dir, ignore_errors=True)

        #
        # Run preprocessor.
        #

        files = [
            path
            for path in pathlib.Path(example_dir).iterdir()
            if path.is_file() and str(path).endswith(('.c', '.h', '.py'))
        ]

        try:
            MetaPreprocessor.do(
                output_dir_path   = build_dir,
                source_file_paths = files,
            )

        except MetaPreprocessor.MetaError as err:
            print()
            sys.exit(err)

        #
        # Get the prebuilt files and the files that were just generated in the build folder.
        #

        prebuilt_dir = pathlib.Path(example_dir, 'prebuilt')

        if not prebuilt_dir.is_dir():
            print(f'\t> `{prebuilt_dir.name}` folder does not exist.')
            continue

        prebuilt_files, build_files = (
            [
                path
                for path in pathlib.Path(example_dir, dir).iterdir()
                if path.suffix not in ('.swp',) # Ignore Vim scratch files.
            ]
            for dir in ('prebuilt', 'build')
        )

        #
        # Check if there's files generated that aren't in the prebuilt folder.
        #

        for build_file in build_files:
            if build_file.name not in { prebuilt_file.name for prebuilt_file in prebuilt_files }:
                print(f'\t> `{build_file.name}` is unexpected!')

        #
        # Check to make sure all of the generated files match what's in the prebuilt folder.
        #

        for prebuilt_file in prebuilt_files:

            build_file = pathlib.Path(build_dir, prebuilt_file.name)

            if build_file not in build_files:
                print(f'\t> `{build_file.name}` is missing!')
            elif not filecmp.cmp(build_file, prebuilt_file):
                print(f'\t> `{build_file.name}` is different!')

@Command(f'Show usage of `{ROOT(os.path.basename(__file__))}`.')
def help():

    name_just = max(len(name) for name in commands.keys())

    print(f'Usage: {ROOT(os.path.basename(__file__))} [COMMAND]')

    for command_name, command in commands.items():
        print(f'\t{command_name.ljust(name_just)} : {command.description}')

################################################################ Execute ################################################################

if len(sys.argv) <= 1: # No arguments given.
    help()

elif sys.argv[1] not in commands:
    help()
    print()
    sys.exit(f'Unknown command `{sys.argv[1]}`; see usage above.')

elif len(sys.argv) == 2:
    commands[sys.argv[1]].function()

else: # Command name with arguments provided; currently not supported however...
    sys.exit(f'Invalid syntax: {' '.join(map(str, sys.argv))}')
