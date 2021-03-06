import numpy as np

from network import Network


def create_structure(tf, x, input_data, input_size, dropout, config):
    branches = []

    network_manager = Network(config, dropout)

    """conv1"""
    x = network_manager.conv_block(x, 5, 2, 32, padding_in='VALID')
    print(x)
    x = network_manager.conv_block(x, 3, 1, 32, padding_in='VALID')
    print(x)

    """conv2"""
    x = network_manager.conv_block(x, 3, 2, 64, padding_in='VALID')
    print(x)
    x = network_manager.conv_block(x, 3, 1, 64, padding_in='VALID')
    print(x)

    print(x)
    """conv3"""
    x = network_manager.conv_block(x, 3, 2, 128, padding_in='VALID')
    print(x)
    x = network_manager.conv_block(x, 3, 1, 128, padding_in='VALID')
    print(x)

    """conv4"""
    x = network_manager.conv_block(x, 3, 2, 256, padding_in='VALID')
    print(x)
    x = network_manager.conv_block(x, 3, 1, 256, padding_in='VALID')
    print(x)
    """mp3 (default values)"""

    """ reshape """
    x = tf.reshape(x, [-1, int(np.prod(x.get_shape()[1:]))], name='reshape')
    print(x)

    """ fc1 """
    x = network_manager.fc_block(x, 512)
    print(x)
    """ fc2 """
    x = network_manager.fc_block(x, 512)

    """Process Control"""
    # control = tf.reshape(control, [-1, int(np.prod(control.get_shape()[1:]))],name = 'reshape_control')
    # print control

    """ Speed (measurements)"""
    with tf.name_scope("Speed"):
        speed = input_data[config.inputs_names.index("Speed")]  # get the speed from input data
        speed = network_manager.fc_block(speed, 128)
        speed = network_manager.fc_block(speed, 128)

    """ Joint sensory """
    j = tf.concat([x, speed], 1)
    j = network_manager.fc_block(j, 512)

    """Start BRANCHING"""
    for i in range(0, len(config.branch_config)):
        with tf.name_scope("Branch_" + str(i) + "_" + config.branch_config[i][0]):
            if config.branch_config[i][0] == "Speed":
                # we only use the image as input to speed prediction
                branch_output = network_manager.fc_block(x, 256)
                branch_output = network_manager.fc_block(branch_output, 256)
            else:
                branch_output = network_manager.fc_block(j, 256)
                branch_output = network_manager.fc_block(branch_output, 256)

            branches.append(network_manager.fc(branch_output, len(config.branch_config[i])))

        print(branch_output)

    weights = network_manager.get_weigths_dict()

    features = network_manager.get_feat_tensors_dict()

    return branches, None, features, weights
