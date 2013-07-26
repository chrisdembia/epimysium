"""Manages the movement and use of data files."""

# TODO must edit cmc setup after it's moved, as well as grf.
# TODO put a comment in all files giving their original Hamner location? Not
# really necessary unless I share this code.
# TODO why is the model file so nested? there's definitely not that many
# changes that need to be made to the model file.
# TODO allow specifying which cycles to manage.

import csv
import difflib
import filecmp
import os
import shutil
import sys
import xml.etree.ElementTree as etree

try: import tables
except ImportError, e: print e.message

try: import numpy as np
except ImportError, e: print e.message

if sys.version_info[0] == 2 and sys.version_info[1] < 6:
    # Taken from /usr/lib/python2.7/posixpath.py
    # This method does not exist prior to python2.6.
    def relpath(path, start=os.path.curdir):
        """Return a relative version of a path"""
    
        if not path:
            raise ValueError("no path specified")
    
        start_list = [x for x in os.path.abspath(start).split(os.path.sep) if x]
        path_list = [x for x in os.path.abspath(path).split(os.path.sep) if x]
    
        # Work out how much of the filepath is shared by start and path.
        i = len(os.path.commonprefix([start_list, path_list]))
    
        rel_list = [os.path.pardir] * (len(start_list)-i) + path_list[i:]
        if not rel_list:
            return curdir
        return os.path.join(*rel_list)
    os.path.relpath = relpath


def storage2numpy(storage_file):
    """Returns the data from a storage file in a numpy format. Skips all lines
    up to and including the line that says 'endheader'.

    Parameters
    ----------
    storage_file : str
        Path to an OpenSim Storage (.sto) file.

    Returns
    -------
    data : np.ndarry (or numpy structure array or something?)
        Contains all columns from the storage file, indexable by column name.

    Examples
    --------
    Columns from the storage file can be obtained as follows:
    
        >>> data = storage2numpy('<filename>')
        >>> data['ground_force_vy']

    """
    # What's the line number of the line containing 'endheader'?
    f = open(storage_file, 'r')

    for i, line in enumerate(f):
        if line.count('endheader') != 0:
            line_number_of_line_containing_endheader = i + 1
            break
    f.close()

    # With this information, go get the data.
    data = np.genfromtxt(storage_file, names=True,
            skip_header=line_number_of_line_containing_endheader)

    return data

def _splitall(path):
    """Splits a path into a list of the directories in the path. Copied from http://my.safaribooksonline.com/book/programming/python/0596001673/files/pythoncook-chp-4-sect-16.

    Parameters
    ----------
    path : str
        The path to split up.

    Returns
    -------
    allparts : list of str's
        One entry for each directory in the provided path; kept in the correct
        order.

    """
    allparts = []
    while 1:
        parts = os.path.split(path)
        if parts[0] == path:  # sentinel for absolute paths
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path: # sentinel for relative paths
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts

def cmc_input_fpaths():
    """Assumes the input files refer to valid file paths (which copy_cmc_inputs
    does not assume).

    """
    pass

def copy_cmc_inputs(cmc_setup_fpath, destination, replace=None,
        do_not_copy=None, **kwargs):
    """Given a CMC setup file, copies all files necessary to run CMC over to
    `destination`. All files necessary to run CMC are stored in the same
    directory. The CMC setup file and the external loads files are edited so
    that they refer to the correct copied files.

    Also sets the results_directory to be 'results'.

    TODO allow placing files in another location (not a flat structure); but
    then update the path in the file so that it's relative to the file.

    Parameters
    ----------
    cmc_setup_fpath : str
        Path to a CMC setup file.
    destination : str
        Directory in which to place the setup files.
    replace : dict, optional
        In case the paths in the files may be invalid, replace parts of the
        paths with the strings given in this dict. Keys are strings to look
        for, values are what to replace the key with.
    do_not_copy : list of str's, optional
        Names of keys ('model', 'tasks', etc.; see the remaining parameters)
        for which files should not be copied over. The corresponding tags in
        the files will be updated so they refer to these original files, even
        if the setup files have moved. This takes precedence over the
        specification of new filenames for the remaining optional arguments.
        'setup' and 'external_loads' are necessarily copied over.
    setup : str, optional
        A new filename for the cmc setup file (the first argument to this
        method).
    model : str, optional
        A new filename for this file.
    tasks : str, optional
        A new filename for this file.
    actuators : str, optional
        A new filename for this file.
    control_constraints : str, optional
        A new filename for this file.
    desired_kinematics : str, optional
        A new filename for this file.
    external_loads : str, optional
        A new filename for this file.
    force_plates : str, optional
        A new filename for this file.
    extload_kinematics : str, optional
        A new filename for this file.

    Returns
    -------
    old_fpaths : dict
        A valid filepath to all the original CMC input files related to the
        provided CMC setup file.
        - setup
        - model
        - tasks
        - actuators
        - control_constraints
        - desired_kinematics
        - external_loads
        - force_plates
        - extload_kinematics
    new_fpaths : dict
        A valid filepath to the all the new files that were just copied over.
        The keys are as above for `old_fpaths`.

    """
    if do_not_copy != None:
        if 'setup' in do_not_copy or 'external_loads' in do_not_copy:
            raise Exception('`do_not_copy` cannot contain `setup` or '
                    '`external_loads`.')
    fname = cmc_setup_fpath

    setup = etree.parse(fname)

    old = dict()

    def valid_path(file_containing_path, xml, tag):

        path = xml.findall('.//%s' % tag)[0].text
        if path == None or path.lstrip() == '': return None
        if os.path.exists(path): return path

        if replace:
            for key, val in replace.items():
                path = path.replace(key, val)
        if os.path.exists(path): return path

        path = path.replace('\\', '/')
        if os.path.exists(path): return path

        path2 = os.path.normpath(
                os.path.join(os.path.split(file_containing_path)[0], path))
        if os.path.exists(path2): return path2

        path2 = os.path.normpath(
                os.path.join(os.path.split(file_containing_path)[0], path.lstrip()))
        if os.path.exists(path2): return path2

        path2 = os.path.normpath(
                os.path.join(os.path.split(file_containing_path)[0], path.rstrip()))
        if os.path.exists(path2): return path2

        raise Exception('Paths %s and %s do not exist.' % (path, path2))

    # Get file names.
    # ---------------
    # Settings / parameters.
    old['model'] = valid_path(fname, setup, 'model_file')
    old['tasks'] = valid_path(fname, setup, 'task_set_file')
    old['actuators'] = valid_path(fname, setup, 'force_set_files')
    old['control_constraints'] = valid_path(fname, setup, 'constraints_file')

    # Data.
    old['desired_kinematics'] = valid_path(fname, setup,
            'desired_kinematics_file')
    old['external_loads'] = valid_path(fname, setup, 'external_loads_file')

    # Try to open the external loads file.
    extloads = etree.parse(old['external_loads'])
    old['force_plates'] = valid_path(old['external_loads'], extloads,
            'datafile')
    old['extload_kinematics'] = valid_path(old['external_loads'],
            extloads, 'external_loads_model_kinematics_file')

    # Copy files over.
    # ----------------
    # We'll store the location of the copies.
    new_fpaths = dict()
    new_fpaths['setup'] = None
    new_fpaths['model'] = None
    new_fpaths['tasks'] = None
    new_fpaths['actuators'] = None
    new_fpaths['control_constraints'] = None
    new_fpaths['desired_kinematics'] = None
    new_fpaths['external_loads'] = None
    new_fpaths['force_plates'] = None
    new_fpaths['extload_kinematics'] = None

    if not os.path.exists(destination): os.makedirs(destination)
    for key, val in old.items():
        if val and key != 'external_loads' and (do_not_copy == None or key not
                in do_not_copy):
            if key in kwargs:
                new_fpath = os.path.join(destination, kwargs[key])
                shutil.copy(val, new_fpath)
                new_fpaths[key] = new_fpath
            else:
                shutil.copy(val, destination)
                new_fpaths[key] = os.path.join(destination,
                        os.path.basename(val))

    # Edit the names of the files in the setup files.
    # -----------------------------------------------
    def edit_field(xml, tag, key):
        if old[key]:
            if do_not_copy != None and key in do_not_copy:
                xml.findall('.//%s' % tag)[0].text = os.path.relpath(old[key], destination)
            else:
                if key in kwargs:
                    newvalue = kwargs[key]
                else:
                    newvalue = os.path.basename(old[key])
                xml.findall('.//%s' % tag)[0].text = newvalue

    setup.findall('.//results_directory')[0].text = 'results'
    edit_field(setup, 'model_file', 'model')
    edit_field(setup, 'task_set_file', 'tasks')
    edit_field(setup, 'force_set_files', 'actuators')
    edit_field(setup, 'constraints_file', 'control_constraints')
    edit_field(setup, 'desired_kinematics_file', 'desired_kinematics')
    edit_field(setup, 'external_loads_file', 'external_loads')

    edit_field(extloads, 'datafile', 'force_plates')
    edit_field(extloads, 'external_loads_model_kinematics_file',
            'extload_kinematics')

    if 'setup' in kwargs:
        setup_new_fpath = os.path.join(destination, kwargs['setup'])
    else:
        setup_new_fpath = os.path.join(destination,
                os.path.basename(cmc_setup_fpath))
    setup.write(setup_new_fpath)
    new_fpaths['setup'] = setup_new_fpath

    if 'external_loads' in kwargs:
        extloads_new_fpath = os.path.join(destination, kwargs['external_loads'])
    else:
        extloads_new_fpath = os.path.join(destination,
                os.path.basename(old['external_loads']))
    extloads.write(extloads_new_fpath)
    new_fpaths['external_loads'] = extloads_new_fpath

    return old, new_fpaths


def dock_output_in_pytable(h5file, output_path, group_path, allow_one=False,
        title=''):
    """Docks an OpenSim output, via a table for each STO file, in a pyTable
    file.  It's assumed the tables don't already exist in the last group
    specified.

    Parameters
    ----------
    h5file : tables.File
        pyTables File object, opened using tables.openFile(...). Does NOT close
        the file.
    output_path : str
        File path in which the OpenSim output is located (e.g. .STO files).
        Only .STO files are loaded, and it is assumed that all .STO files in
        this directory are from one run. That is, they have the same prefix,
        which is the name of the run.
    group_path : str, or list of str's
        The group tree hierarchy specifying where the output is to be docked in
        the h5file; as a path or as list of each directory's name (e.g.:
        'path/to/file' or ['path', 'to', 'file'])
    allow_one : bool, optional (default: False)
        Allows the loading of just one STO file. Otherwise, an exception is
        thrown. It is common that if only one STO file exists, it is a partial
        states file and means that the simulation did not complete.
    title : str, optional
        Title, in the pyTables file, for this group.

    Returns
    -------
    current_group : tables.Group
        The pyTables group in which the output has been stored.

    """
    # If output_path doesn't exist, can't do anything.
    if not os.path.exists(output_path):
        raise Exception("Output path {0:r} doesn't exist.".format(output_path))

    # Convert group_path to list of str's, if necessary.
    if type(group_path) == str:
        group_path = _splitall(group_path)

    # -- Make all necessary groups to get to where we're going.
    current_group = _blaze_group_trail(h5file, group_path, title)

    # -- Determine which files we want to use to create tables.

    # Make a list of all files in this directory ending is 'sto'.
    storage_files = [f for f in os.listdir(output_path) if f.endswith('.sto')]

    # If there are no storage files, the user probably gave a bad path.
    if len(storage_files) == 0:
        raise Exception("No .STO files found in {0}.".format(output_path))

    # If there's only one, usually the states file, forget about this output.
    if (not allow_one) and len(storage_files) == 1:
        raise Exception("Only one .STO file found: {0}.".format(
            storage_files[0]))


    # Get the length of the common prefix of these files.
    n_shared = _length_of_shared_prefix(storage_files)

    # -- Add tables in the current group.

    # Loop through all storage files.
    for f in storage_files:

        # Path to the data file.
        filepath = os.path.join(output_path, f)

        # Get name of the table: after the run name and before the file ext.
        if len(storage_files) == 1:
            table_name = os.path.splitext(f)[0]
        else:
            table_name = os.path.splitext(f)[0][n_shared:]

        # Create and populate a table with the data from this file.
        _populate_table(h5file, current_group, table_name, filepath)

    return current_group

def _blaze_group_trail(h5file, group_path, title=''):

    # Start at the root.
    current_group = h5file.root

    # Loop through each group in the path the user provided.
    for next_group_name in group_path:

        # This group has not been created yet.
        if not hasattr(current_group, next_group_name):

            # Create the group.
            h5file.createGroup(current_group, next_group_name, title=title)

        # Set this group as the current group.
        current_group = getattr(current_group, next_group_name)

    # Return this leaf group.
    return current_group


def _populate_table(h5file, group, table_name, filepath):
    """Populates a pyTables file with a table, using data from CSV file at
    filepath.

    Parameters
    ----------
    h5file : tables.File
        The file to which the table is to be added.
    group : tables.Group
        The group in the file to which the table is to be added.
    table_name : str
        Name of the table to be added.
    filepath : str
        Path to the data file containing data to put in this table.

    Returns
    -------
    table : tables.Table
        The table that has just been created.

    """
    # Open data file.
    csvread = csv.reader(open(filepath, 'r'), delimiter='\t',
            skipinitialspace=True)

    # - Parse the data as a CSV file.
    do_parse = False
    take_header = False

    # For each row in the CSV file.
    for csvrow in csvread:

        # If this is the header line.
        if take_header:

            # Save this row for later; we'll need it.
            title_row = csvrow

            # Can't have periods in table column names in pyTables.
            for i in range(len(title_row)):
                title_row[i] = title_row[i].replace('.', '_')

            take_header = False

            # Grab table column names.
            table_cols = dict()
            for col in title_row: 
                # Checking if the column is empty. This is a
                # once-in-a-blue-moon bug fix as a result of inconsistency in
                # Hamner's files. See CMC results for subject 2, speed 2 m/s,
                # cycle 1, states_OG.sto file.
                if col != '':
                    table_cols[col] = tables.Float32Col()

            # Create pyTables table.
            table = h5file.createTable(group, table_name, table_cols,
                    'Output file {0}'.format(table_name))

        # If this is a data row.
        elif do_parse:

            # For each column in the data file in this row.
            for i in range(len(table_cols.keys())):

                # Append the data into the table.
                table.row[title_row[i]] = csvrow[i]

            # Tell pyTables to append this data to the table.
            table.row.append()

        # The header is over.
        if csvrow == ['endheader']:
            take_header = True
            do_parse = True

    # Save (?).
    table.flush()

    # Give access to it.
    return table

def _length_of_shared_prefix(strings):
    """Determines, from a list of strings, the length of the string that is
    shared at the beginning of all strings.

    Parameters
    ----------
    strings : list of str's
        List of strings to compare.

    Returns
    -------
    n_shared : int
        The number of characters shared at the beginning of all strings.

    """
    # Initialize the number of shared caracters to something equal to or
    # greater than what it will finally be.
    n_shared = len(strings[0])
    for i_string in range(1, len(strings)):

        # Compare the 0th and 1st strings.
        diff = difflib.SequenceMatcher(a=strings[0], b=strings[i_string])

        # The 3rd element of the first element of matching blocks tells
        # how many characters these strings share.
        n_shared = min(n_shared, diff.get_matching_blocks()[0][2])

    return n_shared
