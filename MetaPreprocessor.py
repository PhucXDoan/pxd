#!/usr/bin/env python3
import builtins, os, sys, datetime, copy, types, traceback, contextlib, collections

################################################################ Meta Primitives ################################################################

class Meta:

	class Error(Exception):
		pass

	class Obj:

		def __init__(self, **fields):
			for field_name, field_value in fields.items():
				setattr(self, field_name, field_value)

		def __getitem__(self, key):
			return getattr(self, key)

		def __iter__(self):
			for name, value in self.__dict__.items():
				yield (name, value)

		def __repr__(self):
			return repr(self.__dict__)

	@staticmethod
	def Table(fields, *entries):
		assert isinstance(fields, tuple)
		assert all(len(entry) == len(fields) for entry in entries if entry is not None)

		table = []

		for entry in entries:
			if entry is not None: # Allows for an entry to be easily omitted.
				table += [Meta.Obj(**dict(zip(fields, entry)))]

		return table

	@staticmethod
	def line(string='\n\n'):

		# Split to process each line in order to do indenting correctly for multilined input strings.
		lines = (string + '\n').splitlines()

		# Remove first empty line; useful for multilined strings.
		if lines and lines[0].strip() == '':
			lines = lines[1:]

		# Remove last empty line; useful for multilined strings.
		if lines and lines[-1].strip() == '':
			lines = lines[:-1]

		global_indent = None
		for line in lines:

			# Determine line's indent level.
			line_indent = len(line) - len(line.lstrip('\t'))

			# Determine the whole string's indent level based on the first line with actual text.
			if global_indent is None and line.strip():
				global_indent = line_indent

			# Set indents appropriately.
			line         = line.removeprefix('\t' * min(line_indent, global_indent or 0))
			line         = '\t' * Meta.indent + line if line.strip() else ''
			Meta.string += line + (' \\' if Meta.within_macro else '') + '\n'

	@staticmethod
	def macro(lhs, rhs, *, do_while=False):

		if isinstance(rhs, str) and '\n' in rhs:
			with Meta.enter(f'#define {lhs}'):
				if do_while:
					with Meta.enter('do', '{', '}\nwhile (false)'):
						Meta.line(rhs)
				else:
					Meta.line(rhs)
		else:
			expansion = (str(rhs).lower() if isinstance(rhs, bool) else str(rhs)).strip()

			if do_while:
				Meta.line(f'#define {lhs} do {{ {expansion} }} while (false)')
			else:
				Meta.line(f'#define {lhs} {expansion}')

	@staticmethod
	def overload(macro_name, args, expansion):

		arg_names                           = [arg[0] if isinstance(arg, tuple) else arg for arg in args]
		determiner_names, determiner_values = zip(*[ arg for arg in args if     isinstance(arg, tuple)])
		nondeterminer_names                 =      [ arg for arg in args if not isinstance(arg, tuple)]
		overload                            = (arg_names, determiner_names, nondeterminer_names)

		if macro_name in Meta.overloads:
			assert Meta.overloads[macro_name] == overload
		else:
			Meta.overloads[macro_name] = overload

		determiner_values = [str(value).lower() if isinstance(value, bool) else str(value) for value in determiner_values]

		Meta.macro(f'_{macro_name}__{'__'.join(determiner_values)}({', '.join(nondeterminer_names)})', expansion)

	@contextlib.contextmanager
	@staticmethod
	def enter(header, opening=None, closing=None, *, indented=None):

		defining_macro = False

		# Automatically configure the opening and closing lines if possible.
		if header is not None:

			if header.startswith(('#if', '#ifdef')):
				if closing is None: closing = '#endif'

			if header.startswith(('struct', 'union', 'enum')):
				if opening is None: opening = '{'
				if closing is None: closing = '};'

			if header.startswith('switch'):
				if opening is None: opening = '{'
				if closing is None: closing = '}'

			if header.startswith('case'):
				if opening is None: opening  = '{'
				if closing is None: closing  = '} break;'

			if header.startswith('#define '):
				defining_macro    = True
				Meta.within_macro = True

		# Header and opening lines.
		if header is not None:
			Meta.line(header)
		if indented:
			Meta.indent += 1
		if opening:
			Meta.line(opening)

		# Body.
		Meta.indent += 1
		yield
		Meta.indent -= 1

		# Closing lines.
		if closing is not None:
			Meta.line(closing)
		if indented:
			Meta.indent -= 1
		if defining_macro:
			Meta.within_macro = False
			Meta.line()

	@staticmethod
	def enums(enum_name, type, members, *, counted=False):

		if not members and not counted:

			# An empty enumeration is ill-formed according to the C/C++ standard, so we'll have to forward-declare it.
			Meta.line(f'enum {enum_name} : {type};')

		else:
			with Meta.enter(f'enum {enum_name} : {type}'):

				# Determine the longest name.
				justification = max([0, *(len(member[0]) for member in members if isinstance(member, tuple))])

				for member in members:

					# Enumeration with explicit value.
					if isinstance(member, tuple):

						member_name, member_value = member

						if isinstance(member_value, bool):
							member_value = str(member_value).lower()

						Meta.line(f'{enum_name}_{member_name.ljust(justification)} = {member_value},')

					# With implicit value.
					else:
						Meta.line(f'{enum_name}_{member},')

				# Provide member count; it's a macro so it won't have to be explicitly handled in switch statements.
				if counted:
					Meta.macro(f'{enum_name}_COUNT', len(members))

################################################################ Meta-Preprocessor ################################################################

def do(*, output_dir_path, source_file_paths, additional_context, quiet=False, noexec=False):

	meta_decls    = []
	meta_includes = []

	def location_of(a, b = None, *, line_offset=0):
		match (a, b):
			case (source_file_path, line_number) if isinstance(source_file_path, str) and isinstance(line_number, int):
				return f'[{source_file_path}:{line_number + line_offset}]'
			case (meta_directive, None):
				return location_of(meta_directive.source_file_path, meta_directive.line_number, line_offset=line_offset)

	def execute(directive, gbls):

		prepended_lines = []

		try:

			# We have to introduce a wrapper since `exec` assumes class definition context
			# and some weird non-intuitive variable binding stuff can happen.
			prepended_lines += ['def __META_MAIN__():']

			# In case there's no code.
			prepended_lines += ['\tpass']

			# Declare globals for the exports.
			if hasattr(directive, 'exports') and directive.exports:
				prepended_lines += [f'\tglobal {', '.join(directive.exports)}']

			# Execute.
			meta_code  = ''
			meta_code += '\n'.join(prepended_lines)
			meta_code += '\n'
			meta_code += '\n'.join(f'\t{line}' for line in directive.lines)
			meta_code += '\n'
			meta_code += '__META_MAIN__()\n'
			exec(meta_code, gbls, {})

		except Exception as err:

			err_trace = traceback.format_exc()

			match type(err):
				case builtins.SyntaxError      : err_lineno = err.lineno
				case builtins.IndentationError : err_lineno = err.lineno
				case _                         : err_lineno = [stack.lineno for stack in traceback.extract_tb(sys.exc_info()[2]) if stack.name == '__META_MAIN__'][0]

			match type(err):
				case Meta.Error              : err_detail = str(err)
				case builtins.SyntaxError    : err_detail = 'Syntax error!'
				case builtins.AssertionError : err_detail = f'Assertion failed!'
				case _                       : err_detail = repr(err)

			diagnostic  = ''
			diagnostic += 128 * '#' + '\n'
			diagnostic += err_trace
			diagnostic += 128 * '#' + '\n'
			diagnostic += '\n'
			diagnostic += f'{location_of(directive, line_offset = err_lineno - len(prepended_lines))}: {err_detail}'
			raise Meta.Error(diagnostic)

	################################ Get Meta-Directives ################################

	for source_file_path in source_file_paths:

		remaining_lines       = open(source_file_path, 'rb').read().decode('UTF-8').splitlines()
		remaining_line_number = 1

		while remaining_lines:

			header_line            = remaining_lines[0]
			header_line_number     = remaining_line_number
			remaining_lines        = remaining_lines[1:]
			remaining_line_number += 1

			def eat_body_lines():

				nonlocal remaining_lines, remaining_line_number

				if remaining_lines[0].strip().startswith('/*'):

					body_lines    = []
					global_indent = None

					for body_line in [remaining_lines[0].strip().removeprefix('/*').strip(), *remaining_lines[1:]]:

						remaining_lines        = remaining_lines[1:]
						remaining_line_number += 1

						# Truncate up to the end of the block comment.
						if (ending := body_line.find('*/')) != -1:
							body_line = body_line[:ending]

						# Determine indent level.
						original_line_indent = len(body_line) - len(body_line.lstrip('\t'))

						# Determine global indent if needed and possible.
						a_comment = body_line.strip().startswith('#')
						nonempty  = body_line.strip() != ''
						if global_indent is None and len(body_lines) and nonempty and not a_comment:
							global_indent = original_line_indent

						# Cut away the extraneous indent. It's possible the the line has less
						# indentation than the global indentation, but we won't worry too much about that honestly.
						body_line = body_line.removeprefix('\t' * min(original_line_indent, global_indent or 0))

						# Got line!
						body_lines += [body_line]
						if ending != -1:
							break

					return body_lines

				else:
					return None

			#
			# Parse for a meta-decl.
			#

			tmp = header_line
			tmp = tmp.strip()

			if tmp.startswith('/*'): # Meta-decls are identified in comment blocks...
				tmp = tmp.removeprefix('/*')
				tmp = tmp.strip()

				if tmp.startswith('#meta'): # ... with a special tag.
					tmp = tmp.removeprefix('#meta')
					tmp = tmp.strip()
					tmp = tmp.split(':')

					#
					# Process meta-decl header.
					#

					meta_decl = types.SimpleNamespace(
						source_file_path = source_file_path,
						line_number      = header_line_number,
						lines            = eat_body_lines(),
						exports          = [],
						imports          = [],
					)

					if meta_decl.lines is None:
						raise Meta.Error(f'{location_of(meta_decl)} Meta-decl is missing body.')

					def parse_for_symbols(string):

						symbols = []

						for symbol in [x.strip() for x in string.strip().split(',')]:
							if symbol in symbols:
								raise Meta.Error(f'{location_of(meta_decl)} Duplicate symbol "{symbol}" in meta-decl header.')
							elif symbol == '':
								pass # Likely means there's an extra comma; we'll just ignore it instead of being anal about it.
							else:
								symbols += [symbol]

						return symbols

					match tmp:
						case [exports_string]:
							meta_decl.exports = parse_for_symbols(exports_string)
							meta_decl.imports = []
						case [exports_string, imports_string]:
							meta_decl.exports = parse_for_symbols(exports_string)
							meta_decl.imports = parse_for_symbols(imports_string)
						case _:
							raise Meta.Error(f'{location_of(meta_decl)} Invalid arguments to meta-decl header.')

					#
					# Check for export collisions.
					#

					for symbol in meta_decl.exports:
						for conflict in meta_decls:
							if symbol in conflict.exports:
								raise Meta.Error(f'Two meta-decls export the same symbol "{symbol}": {location_of(meta_decl)} and {location_of(conflict)}.')

					meta_decls += [meta_decl]

			#
			# Parse for a meta-include.
			#

			tmp = header_line
			tmp = tmp.strip()

			if tmp.startswith('#include'): # Meta-includes are identified by preprocessor include directives...
				tmp = tmp.removeprefix('#include')
				tmp = tmp.strip()

				match tmp[0] if tmp else None:
					case '<': end_quote = '>'
					case '"': end_quote = '"'
					case _  : end_quote = None

				if end_quote is not None and (include_file_path_len := tmp[1:].find(end_quote)) != -1:
					if (include_file_path := tmp[1:][:include_file_path_len]).endswith('.meta'): # ... with a specific file extension.

						meta_include = types.SimpleNamespace(
							source_file_path = source_file_path,
							output_file_path = f'{output_dir_path}/{include_file_path}',
							line_number      = header_line_number,
							lines            = eat_body_lines(),
						)

						# Meta-includes are not required to have a body, so this allows the same generated code to be used multiple times.
						if meta_include.lines is not None:

							conflict = None

							for other in meta_includes:
								if other.output_file_path == meta_include.output_file_path:
									conflict = other
									break

							if conflict is None:
								meta_includes += [meta_include]
							else:
								raise Meta.Error(f'Conflicting meta-include for "{meta_include.output_file_path}": {location_of(meta_include)} and {location_of(conflict)}.')

	#
	# Check for missing exports.
	#

	for meta_decl in meta_decls:
		for symbol in meta_decl.imports:
			if not any(symbol in other.exports for other in meta_decls):
				raise Meta.Error(f'{location_of(meta_decl)} The meta-decl depends on "{symbol}" but no meta-decl exports it.')

	################################ Evaluate Meta-Decls ################################

	initial_context = copy.deepcopy(additional_context | { 'Meta' : Meta })
	full_context    = copy.deepcopy(initial_context)

	if tasks := [[False, meta_decl] for meta_decl in meta_decls]:

		if not quiet:
			if noexec:
				print("Meta-decls that would've been evaluated:")
			else:
				print('Meta-decls evaluated:')

		# Still got some meta-decl left to execute?
		while any(not executed for executed, meta_decl in tasks):

			deadend = True

			for task_index, (executed, meta_decl) in enumerate(tasks):

				# No need to evaluate the meta-decl again.
				if executed:
					continue

				# There's still some unsatisfied dependencies.
				if not all(symbol in full_context for symbol in meta_decl.imports):
					continue

				if not quiet:
					print(f'\t{location_of(meta_decl)} {', '.join(meta_decl.exports)}')

				# Skip evaluation.
				if noexec:
					continue

				# Execute meta-decl with the necessary context.
				tasks[task_index][0] = True
				deadend              = False
				gbls                 = copy.deepcopy(initial_context | { symbol : full_context[symbol] for symbol in meta_decl.imports })
				execute(meta_decl, gbls)

				# Process the execution's resulting global namespace.
				for gbl, value in gbls.items():

					# Ignore certain globals that were already a part of the context.
					if gbl == '__builtins__' or gbl in initial_context or gbl in meta_decl.imports:
						continue

					# Export global into the full context.
					if gbl in meta_decl.exports:
						full_context[gbl] = value

				# Ensure all exports were found.
				for symbol in meta_decl.exports:
					if symbol not in full_context:
						raise Meta.Error(f'{location_of(meta_decl)} Missing definition for exported symbol "{symbol}".')

			# No meta-decl managed to execute? Must be some sort of circular dependency!
			if not noexec and deadend:
				for executed, meta_decl in tasks:
					if unsatisfied_symbols := [f'"{symbol}"' for symbol in meta_decl.imports if symbol not in full_context]:
						raise Meta.Error(f'{location_of(meta_decl)} Unsatisfiable import encountered (likely due to circular dependencies): {', '.join(unsatisfied_symbols)}.')

			if noexec:
				break

	elif not quiet:
		print('No meta-decls found.')

	################################ Evaluate Meta-Includes ################################

	if meta_includes:

		if not quiet:
			if noexec:
				print("Meta-includes that would've been evaluated:")
			else:
				print('Meta-includes evaluated:')

		for meta_include in meta_includes:

			if not quiet:
				print(f'\t{location_of(meta_include)} "{meta_include.output_file_path}"')

			# Skip evaluation.
			if noexec:
				continue

			# Execute.
			Meta.string       = ''
			Meta.indent       = 0
			Meta.overloads    = {}
			Meta.within_macro = False
			if not noexec:
				execute(meta_include, copy.deepcopy(full_context))

			# Format generated code.
			generated   = Meta.string
			Meta.string = ''

			Meta.line(f'// {location_of(meta_include)} {datetime.datetime.now()}.') # Some info about the generated code.

			if Meta.overloads: # Put any overloaded macros first.
				Meta.line()
				for macro_name, (arg_names, determiner_names, nondeterminer_names) in Meta.overloads.items():
					Meta.macro(f'{macro_name}({', '.join(arg_names)})', f'_{macro_name}__##{'##'.join(determiner_names)}({', '.join(nondeterminer_names)})')

			if generated: # Insert rest of the code that was generated.
				Meta.line()
				Meta.line(generated)

			os.makedirs(os.path.dirname(meta_include.output_file_path), exist_ok=True) # Make directory path.
			open(meta_include.output_file_path, 'w').write(Meta.string)                # Save generated code.

	elif not quiet:
		print('No meta-includes found.')
