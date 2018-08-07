import sys, time, os
import tensorflow as tf
import tensorflow.contrib.slim as slim
sys.path.append('train')
sys.path.append('utils')

import loss_functions
from enet import *
from erfnet import *
from network import one_hot_to_image, image_to_one_hot, label_to_one_hot

def save_model(saver, sess, models_path, i):
    if not os.path.exists(models_path):
        os.mkdir(models_path)

    saver.save(sess, models_path + '/model.ckpt', global_step=i)
    print(('Model saved at iteration:', i))


def get_last_iteration(ckpt):
    if ckpt:
        return int(ckpt.model_checkpoint_path.split('-')[1])
    else:
        return 1

# with the name of TrainManager, it actually is a Network manager
class TrainManager(object):
    def __init__(self, config, reuse, old_mode=True, batch_tensor=None):
        # TODO: update the initializer
        self._config = config
        self._reuse = reuse
        self._old_mode = old_mode

        with tf.device('/gpu:0'):
            if old_mode:
                self._input_images = tf.placeholder(tf.uint8, shape=[None,
                                                                    config.image_size[0],
                                                                    config.image_size[1],
                                                                    config.image_size[2]], name="input_image")
                self._targets_data = []
                for i in range(len(self._config.targets_names)):
                    self._targets_data.append(tf.placeholder(tf.float32, shape=[None, self._config.targets_sizes[i]],
                                                             name="target_" + self._config.targets_names[i]))
                self._input_data = []
                for i in range(len(self._config.inputs_names)):
                    self._input_data.append(tf.placeholder(tf.float32, shape=[None, self._config.inputs_sizes[i]],
                                                           name="input_" + self._config.inputs_names[i]))
            else:
                self._input_images = batch_tensor[0]
                self._targets_data = batch_tensor[1:(1+len(self._config.targets_names))]
                self._input_data   = batch_tensor[(1+len(self._config.targets_names)):]

            assert(len(config.sensors_normalize)==1)
            self._input_images_f = tf.cast(self._input_images, tf.float32)
            if config.sensors_normalize[0]:
                self._input_images_f = self._input_images_f / 255.0

            self._dout = tf.placeholder("float", shape=[len(config.dropout)])
            self._variable_learning = tf.placeholder("float", name="learning")

        self._feedDict = {}

        self._create_structure = __import__(config.network_name).create_structure
        self._loss_function = getattr(loss_functions, config.loss_function)  # The function to call


    def build_network(self):
        """ Depends on the actual input """
        with tf.name_scope("Network"):
            self._output_network, self._vis_images, self._features, self._weights = self._create_structure(tf,
                                                                                                           self._input_images_f,
                                                                                                           self._input_data,
                                                                                                           self._config.image_size,
                                                                                                           self._dout,
                                                                                                           self._config)

    def build_seg_network_erfnet_one_hot(self):
        """ Depends on the actual input """
        self._seg_network = ErfNet_Small(self._input_images_f[:, :, :, 0:3], self._config.number_of_labels,
                                         batch_size=self._config.batch_size, reuse=self._reuse,
                                         is_training=self._config.train_segmentation)[0]
        with tf.name_scope("Network"):
            # with tf.variable_scope("Network",reuse=self._reuse):
            # print  self._seg_network

            self._sensor_input = self._seg_network
            # Just for visualization
            self._gray = one_hot_to_image(self._seg_network)
            self._gray = tf.expand_dims(self._gray, -1)

            self._output_network, self._vis_images, self._features, self._weights \
                = self._create_structure(tf, self._sensor_input, self._input_data, self._config.image_size, self._dout,
                                         self._config)

    def build_loss(self):
        with tf.name_scope("Loss"):
            self._loss, self._variable_error, self._variable_energy, self._image_loss, self._branch \
                = self._loss_function(self._output_network,
                                      self._targets_data,
                                      self._input_data[self._config.inputs_names.index("Control")],
                                      self._config)

    def build_optimization(self):
        """ List of Interesting Parameters """
        #		beta1=0.7,beta2=0.85
        #		beta1=0.99,beta2=0.999
        with tf.name_scope("Optimization"):
            if hasattr(self._config, 'finetune_segmentation') or \
                    not (hasattr(self._config, 'segmentation_model_name')) or \
                    self._config.segmentation_model is None:
                self._train_step = tf.train.AdamOptimizer(self._variable_learning).minimize(self._loss)
                print("Optimizer: All variables")
            else:
                train_vars = list(set(tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES)) -
                                  set(slim.get_variables(scope=str(self._config.segmentation_model_name))))
                self._train_step = tf.train.AdamOptimizer(self._variable_learning).minimize(self._loss, var_list=train_vars)
                print("Optimizer: Exclude variables from: ", str(self._config.segmentation_model_name))

    def run_train_step(self, batch_tensor, sess, i):
        # TODO: make sure no one use batch_tensor for val
        capture_time = time.time()

        # Get the change in the learning rate]
        decrease_factor = 1
        for position in self._config.training_schedule:
            if i > position[0]:  # already got to this iteration
                decrease_factor = position[1]
                break
        self._feedDict = {self._variable_learning: decrease_factor * self._config.learning_rate,
                          self._dout: self._config.dropout}
        if self._old_mode:
            batch = sess.run(batch_tensor)
            self._feedDict.update({self._input_images: batch[0]})

            count = 1
            for i in range(len(self._config.targets_names)):
                self._feedDict.update({self._targets_data[i]: batch[count]})
                count += 1

            for i in range(len(self._config.inputs_names)):
                self._feedDict.update({self._input_data[i]: batch[count]})
                count += 1

        sess.run(self._train_step, feed_dict=self._feedDict)

        return time.time() - capture_time

    def get_variable_energy(self):
        return self._variable_energy

    def get_loss(self):
        return self._loss

    def get_variable_error(self):
        return self._variable_error

    def get_feed_dict(self):
        return self._feedDict
