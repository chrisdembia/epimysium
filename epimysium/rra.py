"""Iteratively run RRA until the kinematics errors are within a desired range.

"""
import os
import re
import sys
import subprocess

import numpy as np
from scipy.optimize import minimize
from lxml import etree

from epimysium import dataman
from epimysium import postprocessing as pproc


# So the tasks.xml we save retains comments.
xml_parser = etree.XMLParser(remove_comments=False)

def write_task_weights_to_file(task_weights, tasks_fpath, task_names,
        do_round=False):
    cmcts = etree.parse(tasks_fpath, parser=xml_parser)
    # Ignore defaults; only look at 'objects'.
    if do_round: format_str = '%i'
    else: format_str ='%f'

    for task in cmcts.find('.//objects').findall('.//CMC_Joint'):
        if task.attrib['name'] in task_names:
            itask = task_names.index(task.attrib['name'])
            task.find('weight').text = format_str % task_weights[itask]
    cmcts.write(tasks_fpath)

def task_weights_from_file(fpath, task_names):
    array_weights = np.empty(len(task_names))
    file_weights = dict()
    cmcts = etree.parse(fpath)
    # Using two loops ensure that the ordering of task_names and the ordering
    # of tags in the XML file are independent.
    for task in cmcts.findall('.//CMC_Joint'):
        file_weights[task.attrib['name']] = float(task.find('weight').text)
    for itask, name in enumerate(task_names):
        array_weights[itask] = file_weights[name]
    return array_weights

def all_task_names(tasks_fpath):
    task_names = []
    for task in cmcts.findall('.//CMC_Joint'):
        task_names.append(task.attrib['name'])
    return task_names

def max_error(pErr, task_names):
    # Maximum error across the tasks we care about.
    maxerr = -np.inf
    for colname in pErr.dtype.names:
        if colname in task_names:
            if colname.startswith('pelvis_t'):
                this_max_err = 100.0 * np.max(np.abs(pErr[colname]))
            else:
                this_max_err = np.rad2deg(np.max(np.abs(pErr[colname])))
            if this_max_err > maxerr:
                max_colname = colname
                maxerr = this_max_err
    return maxerr, max_colname

def min_error(pErr, task_names):
    # Maximum error across the tasks we care about.
    minerr = np.inf
    for colname in pErr.dtype.names:
        if colname in task_names:
            if colname.startswith('pelvis_t'):
                this_min_err = 100.0 * np.max(np.abs(pErr[colname]))
            else:
                this_min_err = np.rad2deg(np.max(np.abs(pErr[colname])))
            if this_min_err < minerr:
                min_colname = colname
                minerr = this_min_err
    return minerr, min_colname


def select_rra_task_weights(setup_fpath,
        task_names=None,
        task_name_regex_omit=None,
        min_max_err=0.5,
        max_max_err=1.5,
        rra_executable='rra',
        suppress_rra_stdout=True,
        ):
    """Alters all RRA task weights simultaneously to bring kinematics errors
    within the specified range.

    The resulting tasks are written to the tasks file specified in the RRA
    setup file. We write over your original tasks!

    We do NOT check what the resulting residuals are; we only care about the
    kinematics errors here.

    At each iteration, the script outputs plots of
    the residuals and the kinematics errors. These plots are saved in a PDF
    file in the same directory as the provided setup file.

    Parameters
    ----------
    setup_fpath : str
        Valid path to an RRA setup file. We'll pull from this your task set,
        which should contain initial values for the task weights, as well as
        the location of the output pErr file.
    task_names : list of str's, None
        A list of the names of the tasks for whicih we alter the weights
        of/change the error. It is likely that you want us to focus on only a
        few of the tasks here, and you want to take care of the other ones
        manually.
        If None, all tasks modified.
    task_name_regex_omit : str, optional
        Regular expression used to omit tasks from list of task names. If set
        to 'arm*|elbow*', both arm_flex_r and elbow_flex_r will be ignored.
        Omission takes precedence over specification in `task_names`. That is,
        we obtain `task_names`, then go through and omit all those that match
        this regular expression.
    min_max_err : float, optional
        Each kinematics error/task (e.g., ankle_angle_r) has a maximum value in
        time. What is the minimum value that this maximum can have?
    max_max_err : float, optional
        Each kinematics error/task (e.g., ankle_angle_r) has a maximum value in
        time. What is the maximum value that this maximum can have?
    rra_executable : str, optional
        Valid path to an RRA executable. This is useful if:
        * OpenSim is installed in a nonstandard location,
        * rra is not on the system path, or
        * You have multiple OpenSim installations, and want to use a particular
          one for this task.
    suppress_rra_stdout : bool, optional
        Suppress the command-window output of RRA?

    """
    # Get necessary file paths.
    rra = etree.parse(setup_fpath, parser=xml_parser)
    setup_dir = os.path.dirname(setup_fpath)

    # The tasks file.
    # Leading/trailing whitespace could yield an incorrect path.
    task_setup_path = rra.findall('.//task_set_file')[0].text.strip()
    if not os.path.isabs(task_setup_path):
        tasks_fpath = task_setup_path
    else:
        tasks_fpath = os.path.join(setup_dir, task_setup_path)

    if task_names == None:
        task_names = all_task_names(tasks_fpath)

    # Remove task names via regular expression.
    if task_name_regex_omit:
        orig_task_names = task_names
        for taskn in orig_task_names:
            if re.match(task_name_regex_omit, taskn):
                task_names.remove(taskn)

    # The pErr RRA output.
    resdir_name = rra.findall('.//results_directory')[0].text.strip()
    rratool_name = rra.findall('.//RRATool')[0].attrib['name']
    pErr_fname = rratool_name + '_pErr.sto'
    pErr_fpath = os.path.join(setup_dir, 'results', pErr_fname)

    # For the figure we'll be making.
    fig_fpath = os.path.join(setup_dir,
            'residuals_and_kinematics_error_auto_rra.pdf')

    avg_max_err = 0.5 * (min_max_err + max_max_err)

    # To suppress output in a cross-platform way.
    if suppress_rra_stdout:
        our_stdout = open(os.devnull, 'w')
    else:
        our_stdout = sys.stdout

    rra_command = [rra_executable, '-S', setup_fpath]

    task_weights = task_weights_from_file(tasks_fpath, task_names)

    if not os.path.exists(pErr_fpath):
        print('Running RRA...')
        subprocess.call(rra_command, stdout=our_stdout)
    pErr = dataman.storage2numpy(pErr_fpath)
    maxerr, max_colname = max_error(pErr, task_names)
    minerr, min_colname = min_error(pErr, task_names)
    iter_count = 0
    while maxerr > max_max_err or minerr < min_max_err:

        iter_count += 1
        print('')
        itr_str = 'Iteration %i' % iter_count
        print(itr_str)
        print(len(itr_str) * '=')

        # Choose new task weights to get the error where we want it.
        for colname in pErr.dtype.names:
            if colname in task_names:
                if colname.startswith('pelvis_t'):
                    this_err = 100.0 * np.max(np.abs(pErr[colname]))
                else:
                    this_err = np.rad2deg(np.max(np.abs(pErr[colname])))

                if this_err > max_max_err or this_err < min_max_err:
                    if this_err > max_max_err:
                        increment = this_err - avg_max_err
                    elif this_err < min_max_err:
                        increment = -np.abs(avg_max_err - this_err)
                    else:
                        raise Exception("Unexpected error value.")

                    # Compute new weights.
                    prev_weight = task_weights[task_names.index(colname)]
                    new_weight = prev_weight + 0.5 * increment * prev_weight
                    task_weights[task_names.index(colname)] = new_weight

                    # Update the user.
                    print('Task %s has max error %.2f: %.2f -> %.2f' % (
                        colname, this_err, prev_weight, new_weight))

        # Run RRA with the new weights.
        write_task_weights_to_file(task_weights, tasks_fpath, task_names)
        print('Running RRA...')
        subprocess.call(rra_command, stdout=our_stdout)

        # Update plot.
        fig = pproc.plot_rra_gait_info('results')
        fig.savefig(fig_fpath)

        # Update error.
        # We don't REALLY need to update the task weights from the file, but we
        # do so for safety, in case an inconsistency arises somehow.
        task_weights = task_weights_from_file(tasks_fpath)
        pErr = dataman.storage2numpy(pErr_fpath)
        maxerr, max_colname = max_error(pErr, task_names)
        minerr, min_colname = min_error(pErr, task_names)

    print("All maximum pErr's are within the desired range now!")









# Older code:
def alter_weights_to_bring_kinematics_error_below_threshold():
    task_weights = task_weights_from_file(tasks_fpath)

    # To suppress output in a cross-platform way.
    fnull = open(os.devnull, 'w')

    rra_command = [
            '%s/bin/rra' % os.environ['OPENSIM_SPRINGACTIVE'],
            '-S',
            'setup.xml'
            ]

    pErr = dataman.storage2numpy(pErr_fpath)
    maxerr, max_colname = max_error(pErr)
    minerr, min_colname = min_error(pErr)
    while maxerr > 2.0 or minerr < 1.0:

        # Determine the direction (and how much) in which to move the weights.
        if maxerr > 2.0:
            increment = maxerr - 1.5
            colname = max_colname
            errstr = 'max; pErr = %.2f' % maxerr
        elif minerr < 1.0:
            increment = -np.abs(1.5 - minerr)
            colname = min_colname
            errstr = 'min; pErr = %.2f' % minerr
        else:
            raise Exception("minerr and maxerr have unexpected values.")

        # Compute new weights.
        prev_weight = task_weights[task_names.index(colname)]
        new_weight = prev_weight + 0.5 * increment * prev_weight
        task_weights[task_names.index(colname)] = new_weight

        # Update the user.
        print('Focusing on %s (%s): %.2f -> %.2f' % (
            colname, errstr, prev_weight, new_weight))

        # Run RRA with the new weights.
        write_task_weights_to_file(task_weights, do_round=True)
        # Suppress the RRA output.
        subprocess.call(rra_command, stdout=fnull)

        # Update plot.
        fig = pproc.plot_rra_gait_info('results')
        fig.savefig('residual_and_kinematics_error_auto_rra.pdf')

        # Update error.
        pErr = dataman.storage2numpy(pErr_fpath)
        maxerr, max_colname = max_error(pErr)
        minerr, min_colname = min_error(pErr)


# The code below poses this as a more generic optimization problem. I found
# more success with the methods below. However, I did NOT thoroughly explore
# this optimization.
def objective_function(task_weights):
    print task_weights
    if any(np.isnan(task_weights)):
        raise Exception("Some weights are nan.")
    # Update the tasks file with the new values for the weights.
    write_task_weights_to_file(task_weights)

    # Run RRA.
    os.system('%s/bin/rra -S setup.xml' % os.environ['OPENSIM_SPRINGACTIVE'])

    # Update plot.
    fig = pproc.plot_rra_gait_info('results')
    fig.savefig('residual_and_kinematics_error_auto_rra.pdf') 

    # Read in RRA output.
    pErr = dataman.storage2numpy(pErr_fpath)

    # Only want to minimize our excess over 2.0.
    return min(max_error(pErr)[0] - 2.0, 0.0)
    # Alternative objective to keep max error a 2.0:
    # return (max_error(pErr)[0] - 2.0)**2


## Prepare arguments.
#init_weights = task_weights_from_file(tasks_fpath)
## Constraints: weights are positive.
#bounds = len(task_names) * ( (0.0, None), )
#
## Go!
#optimal_weights = minimize(objective_function, init_weights, method='SLSQP',
#        bounds=bounds,
#        tol=0.1,
#        options={'eps': 2.0},
#        )
#
## Save the optimal weights.
#write_task_weights_to_file(optimal_weights)
