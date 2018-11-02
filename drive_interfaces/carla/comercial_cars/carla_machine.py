import sys, pygame, scipy, cv2, random, time, math, os, pickle
import tensorflow as tf
from pygame.locals import *
import numpy as np
from PIL import ImageDraw, Image, ImageFont

sys.path.append('../train')
sys.path.append("../")
sys.path.append('drive_interfaces/carla/carla_client')
sys.path.append('utils')
sys.path.append('train')
sys.path.append('drive_interfaces')
sys.path.append('configuration')

sldist = lambda c1, c2: math.sqrt((c2[0] - c1[0])**2 + (c2[1] - c1[1])**2)
# carla related import
from carla.agent.agent import Agent
from carla.client import VehicleControl
#from carla.client import make_carla_client
from carla.client import CarlaClient
from carla import image_converter

from codification import *
from training_manager import TrainManager
import machine_output_functions
from driver import Driver
from drawing_tools import *
from common_util import restore_session, preprocess_image, split_camera_middle, camera_middle_zoom, plot_waypoints_on_image
from all_perceptions import Perceptions

slim = tf.contrib.slim

def load_system(config):
    config.batch_size = 1
    config.is_training = False

    training_manager = TrainManager(config, None)
    if hasattr(config, 'seg_network_erfnet_one_hot'):
        training_manager.build_seg_network_erfnet_one_hot()
        print("Bulding: seg_network_erfnet_one_hot")
    else:
        training_manager.build_network()
        print("Bulding: standard_network")

    return training_manager


class CarlaMachine(Agent, Driver):
    def __init__(self, gpu_number="0", experiment_name='None', driver_conf=None, memory_fraction=0.9,
                 gpu_perception=None, perception_paths=None, batch_size=1):
        Driver.__init__(self)

        conf_module = __import__(experiment_name)
        self._config = conf_module.configInput()
        self._config.train_segmentation = False

        if self._config.use_perception_stack:
            use_mode = {}
            for key in self._config.perception_num_replicates:
                if self._config.perception_num_replicates[key] > 0:
                    self._config.perception_num_replicates[key] = 1
                    use_mode[key] = True
                else:
                    use_mode[key] = False

            if gpu_perception is not None:
                self._config.perception_gpus = gpu_perception
            if perception_paths is not None:
                self._config.perception_paths = perception_paths

            self.perception_interface = Perceptions(
                batch_size={key: batch_size for key in use_mode if use_mode[key]},
                gpu_assignment=self._config.perception_gpus,
                compute_methods={},
                viz_methods={},
                num_replicates=self._config.perception_num_replicates,
                path_config =self._config.perception_paths,
                **use_mode
            )
            time.sleep(self._config.perception_initialization_sleep)

        self._train_manager = load_system(conf_module.configTrain())
        config_gpu = tf.ConfigProto()
        config_gpu.gpu_options.visible_device_list = gpu_number
        config_gpu.gpu_options.per_process_gpu_memory_fraction = memory_fraction
        self._sess = tf.Session(config=config_gpu)

        self._sess.run(tf.global_variables_initializer())
        variables_to_restore = tf.global_variables()
        saver = tf.train.Saver(variables_to_restore)
        restore_session(self._sess, saver, self._config.models_path)

        self._control_function = getattr(machine_output_functions, self._train_manager._config.control_mode)
        self._image_cut = driver_conf.image_cut

        assert(driver_conf.use_planner == False)

        self._host = driver_conf.host
        self._port = driver_conf.port
        self._config_path = driver_conf.carla_config

        self._straight_button = False
        self._left_button = False
        self._right_button = False

        self.debug_i = 0
        self.temp_image_path = "./temp/"

        self.batch_size = batch_size

        self.waypoint_centers = None
        if hasattr(self._config, "cluster_center_file") and os.path.exists(self._config.cluster_center_file):
            self.waypoint_centers = pickle.load(open(self._config.cluster_center_file, "rb"))

        self.error_i = 0.0
        self.error_p = 0.0

    def start(self):
        self.carla = CarlaClient(self._host, int(self._port), timeout=120)
        self.carla.connect()

        with open(self._config_path, "r") as f:
            self.positions = self.carla.load_settings(f.read()).player_start_spots
        self.carla.start_episode(random.randint(0, len(self.positions)))
        self._target = random.randint(0, len(self.positions))

    def __del__(self):
        if hasattr(self, 'carla'):
            print("destructing the connection")
            self.carla.disconnect()

    def _get_direction_buttons(self):
        # with suppress_stdout():if keys[K_LEFT]:
        keys = pygame.key.get_pressed()

        if (keys[K_s]):
            self._left_button = False
            self._right_button = False
            self._straight_button = False

        if (keys[K_a]):
            self._left_button = True
            self._right_button = False
            self._straight_button = False

        if (keys[K_d]):
            self._right_button = True
            self._left_button = False
            self._straight_button = False

        if (keys[K_w]):
            self._straight_button = True
            self._left_button = False
            self._right_button = False

        return [self._left_button, self._right_button, self._straight_button]

    def compute_direction(self, pos, ori):  # This should have maybe some global position... GPS stuff
        # Button 3 has priority
        if 'Control' not in set(self._config.inputs_names):
            return None

        button_vec = self._get_direction_buttons()
        if sum(button_vec) == 0:  # Nothing
            return 2
        elif button_vec[0] == True:  # Left
            return 3
        elif button_vec[1] == True:  # Right
            return 4
        else:
            return 5

    def get_recording(self):
        return False

    def get_reset(self):
        return False

    # TODO: change to the agent interface, this depend on the sensor names
    def run_step(self, measurements, sensor_data, direction, target):
        sensors = []
        for name in self._config.sensor_names:
            sensors.append(image_converter.to_bgra_array(sensor_data[name]))

        speed_kmh = measurements.player_measurements.forward_speed * 3.6

        # TODO: change the interface of compute action for all
        control = self.compute_action(sensors, speed_kmh, direction)

        return control

    @staticmethod
    def write_text_on_image(image, string, fontsize=10):
        image = image.copy()
        image = np.uint8(image)
        j = Image.fromarray(image)
        draw = ImageDraw.Draw(j)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", fontsize)
        draw.text((0, 0), string, (255, 0, 0), font=font)

        return np.array(j)

    def annotate_image(self, sensor, direction, extra):
        txtdt = {2.0: "follow",
                 3.0: "left",
                 4.0: "right",
                 5.0: "straight",
                 0.0: "goal"}
        font_sz = int(10.0 / 88 * sensor.shape[0]) + 1
        font_sz = min(font_sz, 35)
        viz = self.write_text_on_image(sensor, txtdt[direction]+extra, font_sz)
        return viz

    def save_image(self, viz):
        debug_path = self.temp_image_path + "/"
        cv2.imwrite(debug_path +
                    str(self.debug_i).zfill(9) +
                    ".png", viz[:,:,::-1])
        self.debug_i += 1
        print("output image id is: ", self.debug_i)

    def compute_action(self, sensors, speed_kmh, direction=None,
                       save_image_to_disk=True, return_vis=False, return_extra=True):
        # input image is bgr
        if direction == None:
            direction = self.compute_direction((0, 0, 0), (0, 0, 0))

        out_images = []
        out_vis = []

        if hasattr(self._config, "camera_middle_split") and self._config.camera_middle_split:
            sensors = split_camera_middle(sensors, self._config.sensor_names)

        if hasattr(self._config, "camera_middle_zoom"):
            sensors = camera_middle_zoom(sensors, self._config.sensor_names, self._config.camera_middle_zoom)

        nrow = 1
        ncol = 1
        if self.batch_size == 1:
            for sensor in sensors:
                image_input = preprocess_image(sensor, self._image_cut, self._config.image_size)
                # after this step, it's converted to RGB
                if hasattr(self._config, "hack_resize_image"):
                    image_input = cv2.resize(image_input, (self._config.hack_resize_image[1], self._config.hack_resize_image[0]))
                to_be_visualized = image_input

                if self._config.image_as_float[0]:
                    image_input = image_input.astype(np.float32)
                if self._config.sensors_normalize[0]:
                    image_input = np.multiply(image_input, 1.0 / 255.0)

                if self._config.use_perception_stack:
                    image_input = np.expand_dims(image_input, 0)
                    image_input = self.perception_interface.compute(image_input)
                    # here we should add the visualization
                    to_be_visualized = self.perception_interface.visualize(image_input, 0)
                    nrow, ncol = self.perception_interface.get_viz_nrow_ncol()
                    # done the visualization
                    image_input = self.perception_interface._merge_logits_all_perception(image_input)

                out_images.append(image_input)
                out_vis.append(to_be_visualized)

            # each element in the out_images has the shape of B H W C
            image_input = np.stack(out_images, axis=0)
            # now has shape num_sensors B H W C
            image_input = np.transpose(image_input, (1, 2, 3, 4, 0))
            image_input = np.reshape(image_input, (image_input.shape[0], image_input.shape[1], image_input.shape[2], -1))

            to_be_visualized = np.concatenate(out_vis, axis=1)
            if self._config.use_perception_stack:
                ncol *= len(out_vis)
        else:
            assert (self._config.image_as_float[0] == False)
            assert (self._config.sensors_normalize[0] == False)
            assert (self._config.use_perception_stack == True)
            assert (not hasattr(self._config, "hack_resize_image"))

            t0 = time.time()
            processed_images = []
            for sensor in sensors:
                image_input = preprocess_image(sensor, self._image_cut, self._config.image_size)
                processed_images.append(image_input)

            image_input = np.stack(processed_images, 0)

            #print("until stack images is ", time.time() - t0)
            t1 = time.time()
            image_input = self.perception_interface.compute(image_input)

            #print("compute takes ", time.time() - t1)

            t2 = time.time()
            # here we should add the visualization
            for i in [1]: #range(self.batch_size):
                to_be_visualized = self.perception_interface.visualize(image_input,i)
                nrow, ncol = self.perception_interface.get_viz_nrow_ncol()
                out_vis.append(to_be_visualized)
            #print(" visualize takes, ", time.time() - t2)


            t3 = time.time()
            # done the visualization
            image_input = self.perception_interface._merge_logits_all_perception(image_input)

            BN, H, W, C = image_input.shape
            image_input = np.reshape(image_input, (self.batch_size, BN//self.batch_size, H, W, C))
            # now has shape num_sensors B H W C
            image_input = np.transpose(image_input, (1, 2, 3, 4, 0))
            image_input = np.reshape(image_input, (image_input.shape[0], image_input.shape[1], image_input.shape[2], -1))

            to_be_visualized = np.concatenate(out_vis, axis=1)
            ncol *= len(out_vis)
            #print("compute logits and resizing takes", time.time() - t3)

        t4 = time.time()
        if (self._train_manager._config.control_mode == 'single_branch_wp'):
            # Yang: use the waypoints to predict the steer, in theory PID controller, but in reality just P controller
            # TODO: ask, only the regression target is different, others are the same
            steer, acc, brake, wp1angle, wp2angle = \
                self._control_function(image_input, speed_kmh, direction,
                                       self._config, self._sess, self._train_manager)

            steer_pred = steer

            steer_gain = 0.8
            steer = steer_gain * wp1angle
            print(('Predicted Steering: ', steer_pred, ' Waypoint Steering: ', steer))
        elif (self._train_manager._config.control_mode == 'single_branch_yang_wp'):
            waypoints, predicted_speed = self._control_function(image_input, speed_kmh, direction,
                                                       self._config, self._sess, self._train_manager)
            # visualize the image
            if ncol >= nrow*3:
                col_i = ncol // 3
            else:
                col_i = 0
            subpart = to_be_visualized[:to_be_visualized.shape[0]//nrow, col_i*to_be_visualized.shape[1]//ncol:(col_i+1)*to_be_visualized.shape[1]//ncol, :]
            # this plots the prediction as blue
            subpart = plot_waypoints_on_image(subpart, waypoints, 4, shift_ahead=2.46 - 0.7 + 2.0)

            if hasattr(self._config, "waypoint_interpolate_2point") and self._config.waypoint_interpolate_2point:
                # fit a spline and interpolate
                pass
                # TODO fit a spline and interpolate
                

            to_be_visualized[:to_be_visualized.shape[0] // nrow, col_i*to_be_visualized.shape[1]//ncol:(col_i+1)*to_be_visualized.shape[1]//ncol, :] = subpart

            if hasattr(self._config, "waypoint_return_control") and self._config.waypoint_return_control:
                # TODO: call the real MPC controller in the future, right now using a simple PID controller
                if speed_kmh - predicted_speed > 5.0:
                    acc = 0.0
                    brake = 0.5
                elif speed_kmh - predicted_speed < 0.0:
                    acc = 0.5
                    brake = 0.0
                else:
                    acc = 0.0
                    brake = 0.0
                wp = waypoints[6] # 0.8 seconds in the future
                theta = math.atan2(max(wp[0], 0.01), wp[1]) - math.pi/2  # range from -pi/2 to pi/2
                if waypoints[-2][0] < 0.5:
                    theta = 0.0
                print("wp0", wp[0], "wp1", wp[1], "theta", theta)

                dt = 0.1
                g_p = 0.8
                g_i = 0.0
                g_d = 0.0

                self.error_d = (theta - self.error_p) / dt
                self.error_i += dt * (self.error_p + theta) / 2.0
                self.error_p = theta

                steer = -(g_p * self.error_p + g_i * self.error_i + g_d * self.error_d)
            else:
                if save_image_to_disk:
                    self.save_image(to_be_visualized)
                if return_extra:
                    return waypoints, to_be_visualized, nrow, ncol, col_i
                else:
                    return waypoints, to_be_visualized
        elif  (self._train_manager._config.control_mode == 'single_branch_yang_cls_reg'):
            shape_id, scale = self._control_function(image_input, speed_kmh, direction,
                                                     self._config, self._sess, self._train_manager)
            shape_id = int(shape_id)
            # visualize the image
            if ncol >= nrow * 3:
                col_i = ncol // 3
            else:
                col_i = 0

            if shape_id < len(self.waypoint_centers):
                waypoints = self.waypoint_centers[shape_id] * scale
                waypoints = np.reshape(waypoints, (-1, 2))

                subpart = to_be_visualized[:to_be_visualized.shape[0] // nrow,
                          col_i * to_be_visualized.shape[1] // ncol:(col_i + 1) * to_be_visualized.shape[1] // ncol, :]
                subpart = plot_waypoints_on_image(subpart, waypoints, 4, shift_ahead=2.46 - 0.7 + 2.0)
                to_be_visualized[:to_be_visualized.shape[0] // nrow,
                col_i * to_be_visualized.shape[1] // ncol:(col_i + 1) * to_be_visualized.shape[1] // ncol, :] = subpart
            else:
                waypoints = None

            if save_image_to_disk:
                self.save_image(to_be_visualized)

            if return_extra:
                return waypoints, to_be_visualized, nrow, ncol, col_i
            else:
                return waypoints, to_be_visualized
        else:
            steer, acc, brake = self._control_function(image_input, speed_kmh, direction,
                                                       self._config, self._sess, self._train_manager)

        #print("policy takes ", time.time() - t4)

        steer = min(max(steer, -1), 1)
        acc =   min(max(acc, 0), 1)
        brake = min(max(brake, 0), 1)

        if brake < 0.1 or acc > brake:
            brake = 0.0

        if acc < brake:
            if acc > 0.1:
                print("warning: prediction acc < brake")
            acc = 0.0

        if speed_kmh > 35 and brake == 0.0:
            acc = 0.0

        control = VehicleControl()
        control.steer = steer
        control.throttle = acc
        control.brake = brake
        control.hand_brake = 0
        control.reverse = 0

        # print all info on the image
        extra = "\nSteer {:.2f} \nThrottle {:.2f} \nBrake {:.2f}".format(float(steer), float(acc), float(brake))
        t5 = time.time()
        to_be_visualized = self.annotate_image(to_be_visualized, direction, extra)
        #print("annotate image takes ", time.time() - t5)

        if save_image_to_disk:
            self.save_image(to_be_visualized)

        if return_vis:
            return control, to_be_visualized
        else:
            return control

    # The augmentation should be dependent on speed
    def get_sensor_data(self):
        measurements, sensor_data = self.carla.read_data()
        direction = 2.0

        return measurements, sensor_data, direction

    def compute_perception_activations(self, image_input, speed_kmh):
        image_input = scipy.misc.imresize(image_input, [self._config.image_size[0], self._config.image_size[1]])

        if self._config.image_as_float[0]:
            image_input = image_input.astype(np.float32)
        if self._config.sensors_normalize[0]:
            image_input = np.multiply(image_input, 1.0 / 255.0)

        if self._config.use_perception_stack:
            image_input = np.expand_dims(image_input, 0)
            image_input = self.perception_interface.compute(image_input)
            image_input = self.perception_interface._merge_logits_all_perception(image_input)

        vbp_image = machine_output_functions.seg_viz(image_input, speed_kmh, self._config, self._sess, self._train_manager)

        return 0.4 * grayscale_colormap(np.squeeze(vbp_image), 'jet') + 0.6 * image_input  # inferno

    def act(self, control):
        self.carla.send_control(control)

    def destroy(self):
        self.perception_interface.destroy()
