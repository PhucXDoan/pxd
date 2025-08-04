import re, sys, types, pathlib, string, collections, difflib
from ..pxd.ui    import UI
from ..pxd.log   import log, did_you_mean
from ..pxd.utils import *

CITATION_TAG = '@' '/' # Written like this so that the script won't accidentally think this is a citation.
ui           = UI('cite', 'Manage citations within the codebase.')


def get_file_paths():

    #
    # TODO We have dumb logic here to get something that sort of
    # resembles .gitignore. It's not very good, because apparently
    # there's no easy way to do recursive `**` globs that's built-in. Sigh.
    #

    citeignore_file_path = root(f'./.citeignore')

    if citeignore_file_path.is_file():

        citeignore_entries = [
            line.strip()
            for line in citeignore_file_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]

    else:
        citeignore_entries = []

    def is_ignored(file_path):

        for pattern in citeignore_entries:
            if pattern.startswith('*.'):
                if file_path.match(pattern):
                    return True
            elif pattern.endswith('/'):
                if any(part == pattern.removesuffix('/') for part in file_path.parts):
                    return True
            else:
                assert False, f'Unsupported pattern: {pattern}'

        return False

    return [
        pathlib.Path(root, file_name)
        for root, dirs, file_names in root('./').walk()
        for file_name in file_names
        if not pathlib.Path(root, file_name).is_dir() and not is_ignored(pathlib.Path(root, file_name))
    ]



################################################################################################################################



def get_ledger():



    # Find the citations and sources.

    ledger = types.SimpleNamespace(
        citations = [],
        sources   = collections.defaultdict(lambda: []),
        issues    = [],
    )

    for file_path in get_file_paths():



        # Some stuff might be binary, so we'll skip over it when we can't read it properly.

        try:
            file_content = open(file_path).read()
        except UnicodeDecodeError:
            continue



        # Find every citation tag and attempt to parse.

        class CitationIssue(Exception):
            pass

        for line_num, line, start_index in (
            (line_i + 1, line, iter.start())
            for line_i, line in enumerate(file_content.splitlines())
            for iter in re.finditer(CITATION_TAG, line)
        ):

            try:

                remainder = line[start_index + len(CITATION_TAG):]



                # Get every citation field until we reach the source.
                # e.g:
                # >
                # >    (AT)/pg 123/sec abc/`The Bible`.
                # >         ^^^^^^ ^^^^^^^ ^
                # >

                fields = {}

                while True:



                    # See if we've found the source type and name.
                    # e.g:
                    # >
                    # >    (AT)/pg 123/sec abc/`The Bible`.
                    # >                        ^
                    # >
                    # >    (AT)/pg 123/sec abc/by:`Phuc Doan`.
                    # >                        ^
                    # >
                    # >    (AT)/pg 123/sec abc/url:`www.google.com`.
                    # >                        ^
                    # >

                    for source_type in (None, 'by', 'url'):

                        if not remainder.startswith(prefix := '`' if source_type is None else f'{source_type}:`'):
                            continue

                        remainder = remainder.removeprefix(prefix)



                        # Get the source name.
                        # e.g:
                        # >
                        # >    (AT)/pg 123/sec abc/url:`www.google.com`.
                        # >                             ^^^^^^^^^^^^^^
                        # >

                        source_name_start_index = len(line) - len(remainder)
                        source_name, *remainder = remainder.split('`', 1)
                        source_name_end_index   = source_name_start_index + len(source_name)

                        if remainder == []:
                            raise CitationIssue(f'Missing a "`" after the name of the source.')

                        remainder,  = remainder
                        source_name = source_name.strip()

                        break

                    else:
                        source_type = ... # Haven't found the source yet.

                    if source_type is not ...:
                        break



                    # Find the end of the field.
                    # e.g:
                    # >
                    # >    (AT)/pg 123/sec abc/`The Bible`.
                    # >         ~~~~~~^
                    # >

                    field, *remainder = remainder.split('/', 1)

                    if remainder == []:
                        raise CitationIssue(f'Missing "/".')

                    remainder, = remainder



                    # Get the field name and content.
                    # e.g:
                    # >
                    # >    (AT)/pg 123/sec abc/`The Bible`.
                    # >         ^^ ^^^
                    # >

                    field_name, *field_content = field.split(' ', 1)

                    if field_content == []:
                        raise CitationIssue(f'Missing value for field {field_name}.')

                    field_content, = field_content

                    if field_name in fields:
                        raise CitationIssue(f'Duplicate field {field_name}.')

                    fields[field_name] = field_content



                # Validate and parse each field.

                listing_type = None

                for field_name, field_content in fields.items():

                    match field_name:



                        # Get the author.

                        case 'by':

                            if not field_content:
                                raise CitationIssue(f'The "{field_name}" field is empty.')

                            allowable = string.ascii_letters + string.digits + '- '
                            if not all(c in allowable for c in field_content):
                                raise CitationIssue(
                                    f'The "{field_name}" field value is "{field_content}" '
                                    f'which has a character that\'s not typically found for such a field ({allowable}); '
                                    f'this might be a typo?'
                                )



                        # Get the date.

                        case 'on':

                            pass # TODO Validate.



                        # Get the page number.

                        case 'pg':

                            if not all(character in string.digits for character in field_content):
                                raise CitationIssue(f'The "pg" field value can only contain digits 0-9; got "{field_content}".')

                            try:
                                field_content = int(field_content)
                            except ValueError as error:
                                raise CitationIssue(f'Page number "{field_content}" couldn\'t be parsed.') from error



                        # Get the listing code.

                        case 'tbl' | 'fig' | 'sec':

                            if listing_type is not None:
                                raise CitationIssue(f'Multiple listing fields.')

                            if not field_content:
                                raise CitationIssue(f'The "{field_name}" field is empty.')

                            if not field_content.startswith(tuple(string.ascii_letters + string.digits)):
                                raise CitationIssue(
                                    f'The "{field_name}" field value is "{field_content}" '
                                    f'which doesn\'t start with an alphanumeric character; '
                                    f'this might be a typo?'
                                )

                            if not field_content.endswith(tuple(string.ascii_letters + string.digits)):
                                raise CitationIssue(
                                    f'The "{field_name}" field value is "{field_content}" '
                                    f'which doesn\'t end with an alphanumeric character; '
                                    f'this might be a typo?'
                                )

                            if any(c in field_content for c in string.whitespace):
                                raise CitationIssue(
                                    f'The "{field_name}" field value is "{field_content}" '
                                    f'which has whitespace; '
                                    f'this might be a typo?'
                                )

                            allowable = string.ascii_letters + string.digits + '.-'
                            if not all(c in allowable for c in field_content):
                                raise CitationIssue(
                                    f'The "{field_name}" field value is "{field_content}" '
                                    f'which has a character that\'s not typically found for such a field ({allowable}); '
                                    f'this might be a typo?'
                                )



                        # Unknown field.

                        case _:
                            raise CitationIssue(f'Unknown field {field_name}.')



                    # Update field with the parsed contents.

                    fields[field_name] = field_content

                text = line[start_index : len(line) - len(remainder)]



                # If a colon immediately follows, then it's a source definition; otherwise, it's a proper citation.

                if remainder.strip().startswith(':'):

                    if fields.get('pg', None) is not None:
                        ledger.issues += [types.SimpleNamespace(
                            file_path = file_path,
                            line_num  = line_num,
                            reason    = f'Source declaration shouldn\'t need to have a "pg" attribute.',
                        )]

                    if listing_type is not None:
                        ledger.issues += [types.SimpleNamespace(
                            file_path = file_path,
                            line_num  = line_num,
                            reason    = f'Source declaration shouldn\'t need to have a "{listing_type}" attribute.',
                        )]

                    if source_type is not None:
                        ledger.issues += [types.SimpleNamespace(
                            file_path = file_path,
                            line_num  = line_num,
                            reason    = f'Source declaration shouldn\'t need to have a source type.',
                        )]

                    ledger.sources[source_name] += [types.SimpleNamespace(
                        file_path        = file_path,
                        line_num         = line_num,
                        name             = source_name,
                        name_start_index = source_name_start_index,
                        name_end_index   = source_name_end_index,
                        text             = text,
                        line             = line,
                        duplicated       = False,
                    )]

                else:

                    ledger.citations += [types.SimpleNamespace(
                        file_path               = file_path,
                        line_num                = line_num,
                        pg                      = fields.get('pg', None),
                        listing_type            = listing_type,
                        listing_code            = fields[listing_type] if listing_type is not None else None,
                        source_type             = source_type,
                        source_name             = source_name,
                        source_name_start_index = source_name_start_index,
                        source_name_end_index   = source_name_end_index,
                        text                    = text,
                        line                    = line,
                    )]

            except CitationIssue as error:
                ledger.issues += [types.SimpleNamespace(
                    file_path = file_path,
                    line_num  = line_num,
                    reason    = str(error),
                )]



    # Other consistency checks.

    for source_name, source in ledger.sources.items():

        if len(source) >= 2:

            fst, *others = source

            ledger.issues += [types.SimpleNamespace(
                file_path = fst.file_path,
                line_num  = fst.line_num,
                reason    =
                    f'Source "{source_name}" is already defined at {' and '.join(
                        f'[{other.file_path}:{other.line_num}]' for other in others
                    )}.'
            )]

    for source in ledger.sources.values():

        if len(source) >= 2:
            continue

        source, = source

        if not any(citation.source_name == source.name for citation in ledger.citations):
            ledger.issues += [types.SimpleNamespace(
                file_path = source.file_path,
                line_num  = source.line_num,
                reason    = f'Source "{source.name}" is never used.',
            )]

    for citation in ledger.citations:
        if citation.source_type is None and citation.source_name not in ledger.sources:
            ledger.issues += [types.SimpleNamespace(
                file_path = citation.file_path,
                line_num  = citation.line_num,
                reason    = f'Citation uses undeclared source "{citation.source_name}".', # TODO difflib.
            )]

    return ledger



################################################################################################################################



def log_issues(issues):
    for issue, columns in zip(issues, ljusts((x.file_path, x.line_num) for x in issues)):
        log('[WARNING] {0} : {1} : {2}'.format(*columns, issue.reason), ansi = 'fg_yellow')


@ui('Find citations and source declarations that refer to a specific source name.')
def find(
    specific_source_name : (str           , 'Source name to search for; otherwise, list everything.') = None,
    rename               : ((str, 'flag') , 'Change the source name of all occurrences.'            ) = None,
):

    ledger = get_ledger()

    if specific_source_name is None:

        #
        # Can't do a rename without a source name first.
        #

        if rename is not None:
            ui.help(subcommand_name = 'find')
            log()
            log(
                f'[ERROR] A source name must be provided in order to do a renaming; '
                f'see subcommand help above.',
                ansi = 'fg_red'
            )
            return 1

        #
        # Find all the citations and group them based on the source.
        #

        sources_named = coalesce(ledger.citations, lambda x: (x.source_type, x.source_name))

        def source_sorting(item):

            (source_type, source_name), citations = item

            ordering = []

            # Sources with a unique declaration.
            if (
                source_type is None
                and source_name in ledger.sources
                and len(ledger.sources[source_name]) == 1
            ):
                ordering += [0]

            # Sources with inlined declaration.
            elif source_type is not None:
                ordering += [1]

            # Sources that are missing a declaration;
            # placed last so it'd be the first thing to be seen when user scrolls up.
            else:
                ordering += [2]

            ordering += [source_type if source_type is not None else '']

            if (
                source_type is None
                and (source := ledger.sources.get(source_name, None)) is not None
                and len(source) == 1
            ):
                source,   = source
                ordering += [(source.file_path, source.line_num)]
            else:
                ordering += [()]

            return ordering

        def citation_sorting(citation):
            return citation.pg if citation.pg is not None else 0

        #
        # Dump the results.
        #

        rows = [
            (citation_sub_index, citation)
            for (source_type, source_name), citations in sorted(sources_named.items(), key = source_sorting)
            for citation_sub_index, citation in enumerate(sorted(citations, key = citation_sorting))
        ]

        rows = zip(rows, ljusts({
            'file_path' : citation.file_path,
            'line_num'  : citation.line_num,
            'pg'        : '' if citation.pg           is None else f'pg {citation.pg}' ,
            'listing'   : '' if citation.listing_type is None else f'{citation.listing_type} {citation.listing_code}',
        } for citation_sub_index, citation in rows))

        for (citation_sub_index, citation), columns in rows:

            log('| {file_path} : {line_num} | {pg} | {listing} |'.format(**columns), end = '')

            if citation_sub_index:
                log('')

            elif citation.source_type:
                log(f' {citation.text}')

            elif (source := ledger.sources.get(citation.source_name, None)) is not None and len(source) == 1:
                source, = source
                log(f' [{source.file_path}:{source.line_num}] {source.text}')

            else:
                log(f' [???] {CITATION_TAG}`{citation.source_name}`')

        if ledger.issues:
            log()
            log_issues(ledger.issues)

    else:

        #
        # If we're renaming, do some basic checks.
        #

        if rename is not None:

            rename = rename.strip()

            if '`' in rename:
                log(f'[ERROR] The new source name "{rename}" cannot have a backtick "`".', ansi = 'fg_red')
                return 1

        if rename == '':
            log(f'[ERROR] The source cannot be renamed to an empty string.', ansi = 'fg_red')
            return 1

        if rename == specific_source_name:
            log(f'[WARNING] The new source name "{rename}" is the same as the old one; no renaming will be done.', ansi = 'fg_yellow')
            return 0

        #
        # Find all citations and source declaration instances that match the given name.
        #

        occurrences = collections.defaultdict(lambda: [])

        for source in ledger.sources.values():
            for src in source:
                if src.name == specific_source_name:
                    occurrences[src.file_path] += [types.SimpleNamespace(
                        line_num    = src.line_num,
                        start_index = src.name_start_index,
                        end_index   = src.name_end_index,
                        line        = src.line,
                    )]

        for citation in ledger.citations:
            if citation.source_name == specific_source_name:
                occurrences[citation.file_path] += [types.SimpleNamespace(
                    line_num    = citation.line_num,
                    start_index = citation.source_name_start_index,
                    end_index   = citation.source_name_end_index,
                    line        = citation.line,
                )]

        occurrences = dict(occurrences)

        if not occurrences:
            did_you_mean(
                f'No citations or source declarations associated with "{specific_source_name}" was found.',
                specific_source_name,
                { *ledger.sources, *[citation.source_name for citation in ledger.citations] },
                ansi = 'fg_yellow',
            )
            return 0

        #
        # Show the findings.
        #

        rows = [
            (file_path, instance)
            for file_path, instances in occurrences.items()
            for instance in instances
        ]

        rows = zip(rows, ljusts((file_path, instance.line_num) for file_path, instance in rows))

        for (file_path, instance), columns in rows:
            log('| {0} : {1} | '.format(*columns), end = '')
            log(instance.line[                     : instance.start_index].lstrip(), end = '')
            log(instance.line[instance.start_index : instance.end_index  ]         , end = '', ansi = ('fg_magenta', 'bold', 'underline'))
            log(instance.line[instance.end_index   :                     ].rstrip(), end = '')
            log()

        #
        # Rename the sources if requested.
        #

        if rename is not None:

            if ledger.issues:
                log()
                log_issues(ledger.issues)

            if (
                any(source_name          == rename for source_name in ledger.sources  ) or
                any(citation.source_name == rename for source_name in ledger.citations)
            ):
                if not ledger.issues:
                    log()
                log(f'[WARNING] The new source name "{rename}" is the name of an already existing source.', ansi = 'fg_yellow')

            log()
            log(f'[NOTE]', end = '', ansi = ('bg_green', 'fg_black'))
            log(f' Enter "yes" to replace the source names with "{rename}" (otherwise, abort): ', end ='')

            if input() != 'yes':
                log(f'[NOTE]', end = '', ansi = ('bg_green', 'fg_black'))
                log(f' Aborted the renaming.')
                return 1

            for file_path, instances in occurrences.items():

                file_lines = open(file_path).read().splitlines()

                # Iterate through the citations on the line backwards
                # so we can replace the source name properly.
                for instance in sorted(instances, key = lambda instance: (instance.line_num, -instance.start_index)):

                    file_lines[instance.line_num - 1] = (
                        file_lines[instance.line_num - 1][:instance.start_index] +
                        rename +
                        file_lines[instance.line_num - 1][instance.end_index:]
                    )

                file_path.write_text('\n'.join(file_lines) + '\n')

            ledger = get_ledger()

            log(f'[NOTE]', end = '', ansi = ('bg_green', 'fg_black'))
            log(f' Renamed {len([instance for instances in occurrences.values() for instance in instances])} instances.')

        #
        # Report issues.
        #

        if ledger.issues:
            log()
            log_issues(ledger.issues)
