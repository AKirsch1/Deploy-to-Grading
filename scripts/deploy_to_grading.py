#!/bin/python3

# Main script of the Deploy-to-Grading pipeline for checking student
# assignments. It runs all steps described in the
# [documentation](https://github.com/Programmiermethoden/Deploy-to-Grading/blob/master/doc/design_document/d2g_procedure.md#ablauf-in-der-gh-action).
# Make sure that the script is executed inside an assignment folder
# and that the env variable D2G_PATH is set to a path to the
# Deploy-to-Grading pipeline.
# The results of the Deploy-to-Grading can be found in the `results`
# folder. Additional data is saved in each tasks `build/results` folder.
# All results are also made available in an archive inside the 'results'
# folder in the root directory of the assignment and.
#
# usage: deploy_to_grading.py
#
# Error handling:
# - Exits with an error code when any of the Deploy-to-Grading steps fails
#   to execute correctly.
#

import load_yaml as conf_loader
import os
import subprocess
from yaml import YAMLError

ASSIGNMENT_FILE_NAME = "assignment.yml"
TASK_FILENAME = "task.yml"

def _print_usage():
    print("usage: deploy_to_grading.py")
    print("       Executes the Deploy-to-Grading pipeline. Make sure to")
    print("       execute the script inside an assignment folder and")
    print("       that the D2G_PATH env variable is set.")

def _print_error_and_exit(error_msg):
    print(error_msg)
    _print_usage()
    exit(-1)

def _load_assignment_config():
    # Step 1 of the Deploy-to-Grading pipeline
    print("Loading assignment configuration")
    try:
        return conf_loader.load_yaml(ASSIGNMENT_FILE_NAME)
    except (FileNotFoundError, YAMLError) as err:
        _print_error_and_exit("Failed to load %s" % ASSIGNMENT_FILE_NAME)

def _checkout_due_date(due_date):
    # Step 2 of the Deploy-to-Grading pipeline
    print("Checking out due date")
    script_path = os.path.join(os.environ["D2G_PATH"],
        "scripts/checkout_due_date.sh")
    proc = subprocess.run([script_path, due_date])
    if proc.returncode != 0:
        _print_error_and_exit("Failed to evaluate checkout commit")

def _load_task_config(taskname):
    # Step 3 of the Deploy-to-Grading pipeline
    print("Loading task configuration for task %s" % taskname)
    task_config_path = os.path.join(taskname, TASK_FILENAME)
    try:
        return conf_loader.load_yaml(task_config_path, taskname.upper())
    except (FileNotFoundError, YAMLError) as err:
        _print_error_and_exit("Failed to load %s" % task_config_path)

def _override_repo(taskname, repository, task_configuration):
    # Step 4 of the Deploy-to-Grading pipeline
    print("Overriding repository for task %s" % taskname)
    script_path = os.path.join(os.environ["D2G_PATH"],
        "scripts/override_repo.py")

    # Run override_repo.py either for a task or the assignment.yml. It is
    # executed for the assignment.yml if the taskname is None.
    proc = None
    if taskname:
        proc = subprocess.run(
            [script_path, "-t", taskname, "-r", repository], cwd=taskname,
            env=task_configuration)
    else:
        proc = subprocess.run([script_path, "-a", "-r", repository])

    # Exit D2G completely on error, as we can't validate the correctness
    # of the student submission.
    if proc.returncode != 0:
        _print_error_and_exit("Failed to execute override_repo.py")

def _get_metric_script_path(metric):
    # Search for an evaluation script for the given metrics. Looks for 
    # scripts written in bash or python. If such a script does not exist,
    # it assumes that the metric is a gradle task.
    base_path = os.path.join(os.environ["D2G_PATH"],
        "scripts/metrics/%s" % metric)
    if os.path.exists(base_path + ".sh"):
        return [base_path + ".sh"]
    elif os.path.exists(base_path + ".py"):
        return [base_path + ".py"]
    else:
        return ["./gradlew", metric]

def _execute_metrics(taskname, metrics):
    # Runs step 5 of the Deploy-to-Grading pipeline for every metric
    for metric in metrics.split(" "):
        print("Executing metric %s for task %s" % (metric, taskname))
        metric_script = _get_metric_script_path(metric)
        
        proc = subprocess.run(metric_script, cwd=taskname)
        if proc.returncode != 0:
            _print_error_and_exit("Failed to execute metric %s" % metric)

def _evaluate_metrics(taskname, metrics, task_configuration, assignment_configuration):
    # Step 6 fo the Deploy-to-Grading pipeline
    print("Evaluating metrics for task %s" % taskname)
    script_path = os.path.join(os.environ["D2G_PATH"],
        "scripts/evaluate_task.py")
    proc = subprocess.run([script_path, taskname], cwd=taskname,
        env=dict(os.environ, **task_configuration, **assignment_configuration))
    if proc.returncode != 0:
        _print_error_and_exit("Failed to execute evaluate_task.py")

def _evaluate_task(taskname, assignment_configuration):
    # Runs step 3 to 6 of the Deploy-to-Grading pipeline
    task_conf = _load_task_config(taskname)
    _override_repo(taskname,
        assignment_configuration["ASSIGNMENT_TEMPLATE_REPOSITORY"], task_conf)
    _execute_metrics(taskname, task_conf["%s_METRICS" % taskname.upper()])
    _evaluate_metrics(taskname, task_conf["%s_METRICS" % taskname.upper()],
        task_conf, assignment_configuration)

def _create_artifact(assignment_configuration):
    # Runs a script to collect individual metric results of every task and create
    # an archive containing all results
    print("Creating artifact")
    script_path = os.path.join(os.environ["D2G_PATH"],
        "scripts/create_artifact.sh")
    proc = subprocess.run([script_path], env=dict(os.environ, **assignment_configuration))
    if proc.returncode != 0:
        _print_error_and_exit("Failed to execute create_artifact.sh")

def _present_results(assignment_configuration):
    # Step 7 of the Deploy-to-Grading pipeline
    _create_artifact(assignment_configuration)

    script_path = os.path.join(os.environ["D2G_PATH"],
        "scripts/print_results_student.py")
    proc = subprocess.run([script_path], env=dict(os.environ, **assignment_configuration))
    if proc.returncode != 0:
        _print_error_and_exit("Failed to print student results")

def _revert_checkout():
    # Revert step 2 of the Deploy-to-Grading pipeline
    script_path = os.path.join(os.environ["D2G_PATH"],
        "scripts/revert_checkout.sh")
    subprocess.run([script_path])

def _main():
    assignment_conf = _load_assignment_config()
    _checkout_due_date(assignment_conf["ASSIGNMENT_DUE_DATE"])
    _override_repo(None,
        assignment_conf["ASSIGNMENT_TEMPLATE_REPOSITORY"], None)

    for task in assignment_conf["ASSIGNMENT_TASKS"].split(" "):
        _evaluate_task(task, assignment_conf)

    _present_results(assignment_conf)
    
    _revert_checkout()

if __name__ == "__main__":
    _main()
