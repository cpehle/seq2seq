#! /usr/bin/env python

""" Script to generates model profiling information
"""

import os
import six

#pylint: disable=E0611
from google.protobuf import text_format

import tensorflow as tf
from tensorflow.contrib.tfprof import model_analyzer
from tensorflow.contrib.tfprof.python.tools.tfprof import tfprof_logger
from tensorflow.tools.tfprof import tfprof_log_pb2

tf.flags.DEFINE_string("model_dir", None, "path to model directory")

FLAGS = tf.flags.FLAGS

def load_metadata(model_dir):
  """Loads RunMetadata, Graph and OpLog from files
  """
  # Import RunMetadata
  run_meta_path = os.path.join(model_dir, "metadata/run_meta")
  run_meta = tf.RunMetadata()
  if os.path.exists(run_meta_path):
    with open(run_meta_path, "rb") as file:
      run_meta.MergeFromString(file.read())
    print("Loaded RunMetadata from {}".format(run_meta_path))
  else:
    print("RunMetadata does not exist a {}. Skipping.".format(run_meta_path))

  # Import Graph
  graph_def_path = os.path.join(model_dir, "graph.pbtxt")
  graph = tf.Graph()
  if os.path.exists(graph_def_path):
    with graph.as_default():
      graph_def = tf.GraphDef()
      with open(graph_def_path, "rb") as file:
        text_format.Parse(file.read(), graph_def)
      tf.import_graph_def(graph_def, name="")
      print("Loaded Graph from {}".format(graph_def_path))
  else:
    print("Graph does not exist a {}. Skipping.".format(graph_def_path))

  # Import OpLog
  op_log_path = os.path.join(model_dir, "metadata/tfprof_log")
  op_log = tfprof_log_pb2.OpLog()
  if os.path.exists(op_log_path):
    with open(op_log_path, "rb") as file:
      op_log.MergeFromString(file.read())
      print("Loaded OpLog from {}".format(op_log_path))
  else:
    print("OpLog does not exist a {}. Skipping.".format(op_log_path))

  return run_meta, graph, op_log


def merge_default_with_oplog(graph, op_log=None, run_meta=None):
  """Monkeypatch. There currently is a bug in tfprof_logger._merge_default_with_oplog that
    prevents it from being used with Python 3. So we override the method manually until the fix
    comes in.
  """
  tmp_op_log = tfprof_log_pb2.OpLog()
  # pylint: disable=W0212
  logged_ops = tfprof_logger._get_logged_ops(graph, run_meta)
  if not op_log:
    tmp_op_log.log_entries.extend(logged_ops.values())
  else:
    all_ops = dict()
    for entry in op_log.log_entries:
      all_ops[entry.name] = entry
    for op_name, entry in six.iteritems(logged_ops):
      if op_name in all_ops:
        all_ops[op_name].types.extend(entry.types)
        if entry.float_ops > 0 and all_ops[op_name].float_ops == 0:
          all_ops[op_name].float_ops = entry.float_ops
      else:
        all_ops[op_name] = entry
    tmp_op_log.log_entries.extend(all_ops.values())
  return tmp_op_log


def param_analysis_options(output_dir):
  """Options for model parameter analysis
  """
  options = model_analyzer.TRAINABLE_VARS_PARAMS_STAT_OPTIONS.copy()
  options["select"] = ["params", "bytes"]
  options["order_by"] = "params"
  options["account_type_regexes"] = ["Variable"]
  if output_dir:
    options["dump_to_file"] = os.path.join(output_dir, "params.txt")
  return "scope", options

def micro_anaylsis_options(output_dir):
  """Options for microsecond analysis
  """
  options = model_analyzer.TRAINABLE_VARS_PARAMS_STAT_OPTIONS.copy()
  options["select"] = ["micros", "device"]
  options["min_micros"] = 1000
  options["account_type_regexes"] = [".*"]
  options["order_by"] = "micros"
  if output_dir:
    options["dump_to_file"] = os.path.join(output_dir, "micro.txt")
  return "graph", options

def flops_analysis_options(output_dir):
  """Options for FLOPS analysis
  """
  options = model_analyzer.TRAINABLE_VARS_PARAMS_STAT_OPTIONS.copy()
  options["select"] = ["float_ops", "micros", "device"]
  options["min_float_ops"] = 1
  options["order_by"] = "float_ops"
  options["account_type_regexes"] = [".*"]
  if output_dir:
    options["dump_to_file"] = os.path.join(output_dir, "flops.txt")
  return "scope", options

def device_analysis_options(output_dir):
  """Options for device placement analysis
  """
  options = model_analyzer.TRAINABLE_VARS_PARAMS_STAT_OPTIONS.copy()
  options["select"] = ["device", "float_ops", "micros"]
  options["order_by"] = "name"
  options["account_type_regexes"] = [".*"]
  if output_dir:
    options["dump_to_file"] = os.path.join(output_dir, "device.txt")
  return "scope", options

def main(_argv):
  """Main functions. Runs all anaylses."""
  # pylint: disable=W0212
  tfprof_logger._merge_default_with_oplog = merge_default_with_oplog

  FLAGS.model_dir = os.path.abspath(os.path.expanduser(FLAGS.model_dir))
  output_dir = os.path.join(FLAGS.model_dir, "profile")
  os.makedirs(output_dir, exist_ok=True)

  run_meta, graph, op_log = load_metadata(FLAGS.model_dir)

  param_arguments = [
    param_analysis_options(output_dir),
    micro_anaylsis_options(output_dir),
    flops_analysis_options(output_dir),
    device_analysis_options(output_dir),
  ]

  for tfprof_cmd, params in param_arguments:
    model_analyzer.print_model_analysis(
      graph=graph,
      run_meta=run_meta,
      op_log=op_log,
      tfprof_cmd=tfprof_cmd,
      tfprof_options=params)

    if params["dump_to_file"] != "":
      print("Wrote {}".format(params["dump_to_file"]))

if __name__ == '__main__':
  tf.app.run()