import argparse, logging, sys

sys.path.append('drive_interfaces/configuration')
sys.path.append('drive_interfaces')
sys.path.append('drive_interfaces/carla')
sys.path.append('drive_interfaces/carla/carla_client')
sys.path.append('drive_interfaces/carla/carla_client/planner')
sys.path.append('drive_interfaces/carla/carla_client/testing')
sys.path.append('test_interfaces')
sys.path.append('utils')
sys.path.append('dataset_manipulation')
sys.path.append('configuration')
sys.path.append('input')
sys.path.append('train')
sys.path.append('utils')
sys.path.append('input/spliter')
sys.path.append('structures')

from carla_machine import *

from carla.driving_benchmark import run_driving_benchmark
from carla.driving_benchmark.experiment_suites import YangExp
from common_util import parse_drive_arguments

def main(host, port, city, summary_name, agent):
    #TODO: make an agent; define the camera in the testing env; change city name
    experiment_suite = YangExp(city)
    run_driving_benchmark(agent, experiment_suite,
                          city_name=city,
                          log_name=summary_name,
                          continue_experiment=True,
                          host=host,
                          port=int(port),
                          save_images=True)


if (__name__ == '__main__'):

    parser = argparse.ArgumentParser(description='Chauffeur')

    parser.add_argument('-lg', '--log', help="activate the log file", action="store_true")
    parser.add_argument('-db', '--debug', help="put the log file to screen", action="store_true")

    # Train
    # TODO: some kind of dictionary to change the parameters
    parser.add_argument('-e', '--experiment-name',
                        help="The experiment name (NAME.py file should be in configuration folder, and the results will be saved to models/NAME)",
                        default="")

    parser.add_argument('-m', '--memory', default=1.0, help='The amount of memory this process is going to use')
    # Drive
    parser.add_argument('-l', '--host', type=str, default='127.0.0.1', help='The IP where DeepGTAV is running')
    parser.add_argument('-p', '--port', default=8000, help='The port where DeepGTAV is running')
    parser.add_argument('-s', '--summary', default="summary_number_1", help='summary')
    parser.add_argument('-cy', '--city', help='select the graph from the city being used')

    args = parser.parse_args()
    if args.log or args.debug:
        LOG_FILENAME = 'log_runtests.log'
        logging.basicConfig(filename=LOG_FILENAME, level=logging.DEBUG)
        if args.debug:  # set of functions to put the logging to screen
            root = logging.getLogger()
            root.setLevel(logging.DEBUG)
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            root.addHandler(ch)

    driver_conf = lambda: None # an object that could add attributes dynamically
    driver_conf.image_cut = [0, 100000]
    driver_conf.host = "127.0.0.1"
    driver_conf.port = 2000
    driver_conf.use_planner = False # fixed
    driver_conf.carla_config = None # This is not used by CarlaMachine but it's required
    # used by main
    driver_conf.city="Town01"

    driver_conf = parse_drive_arguments(args,
                                        driver_conf,
                                        attributes=['host', 'city'])
    print (driver_conf)

    with  open(args.summary + '.stats.csv', 'w+') as f:
        f.write(args.experiment_name + '\n')
        conf_module = __import__(args.experiment_name)
        config = conf_module.configMain()
        with open(config.models_path + '/checkpoint', 'r') as content_file:
            f.write(content_file.read())

    # instance your controller here
    runnable = CarlaMachine("0", args.experiment_name, driver_conf, float(args.memory))

    main(args.host, args.port, args.city, args.summary, runnable)
