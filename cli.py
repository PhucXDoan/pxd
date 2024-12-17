#!/usr/bin/env python3
import os, sys, types, pathlib, MetaPreprocessor

HERE = pathlib.Path(sys.argv[0]).parent

################################################################ Helpers ################################################################

class ExecutionError(Exception):
	pass

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

	examples = [
		str(path)
		for path in pathlib.Path(HERE, 'examples').iterdir()
		if path.is_dir()
	]

	for example_i, example in enumerate(examples):

		print(f'[{str(example_i + 1).rjust(len(str(len(examples))))}/{len(examples)}] {example}')

		metapreprocessor_file_paths = [
			str(path)
			for path in pathlib.Path(example).iterdir()
			if path.is_file() and str(path).endswith(('.c', '.h'))
		]

		try:
			MetaPreprocessor.do(
				output_dir_path    = str(pathlib.Path(example, 'build')),
				source_file_paths  = metapreprocessor_file_paths,
				additional_context = {},
			)
			print()
		except MetaPreprocessor.Meta.Error as err:
			raise ExecutionError(f'{err}\n\n# See the above meta-preprocessor error.')

@Command(f'Show usage of `{pathlib.Path(HERE, os.path.basename(__file__))}`.')
def help():

	name_just = max(len(name) for name in commands.keys())

	print(f'Usage: {HERE}/{os.path.basename(__file__)} [COMMAND]')
	for command_name, command in commands.items():
		print(f'\t{command_name.ljust(name_just)} : {command.description}')

################################################################ Execute ################################################################

if len(sys.argv) <= 1: # No arguments given.
	help()

elif len(sys.argv) == 2: # Command name provided.
	if sys.argv[1] in commands:
		try:
			commands[sys.argv[1]].function()
		except ExecutionError as err:
			sys.exit(f'\n{err.args[0]}')
	else:
		help()
		print()
		print(f'Unknown command `{sys.argv[1]}`; see usage above.')

else: # Command name with arguments provided; currently not supported however...
	sys.exit(f'Invalid syntax: {' '.join(map(str, sys.argv))}')
