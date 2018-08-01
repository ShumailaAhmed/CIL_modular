class Spliter(object):
    def __init__(self, sequence_size, sequence_stride, steering_bins_perc):
        # a typical value for those inputs are: 1, 1, self.steering_bins_perc = [0.05, 0.05, 0.1, 0.3, 0.3, 0.1, 0.05, 0.05]
        self._sequence_size = sequence_size
        self._sequence_stride = sequence_stride
        self._steering_bins_perc = steering_bins_perc

    def order_sequence(self, steerings, keys_sequence):
        # select the subset based on the keys_sequence and
        # return a list of indexes that sorts the steers, the selected steers (in original order)
        sequence_average = []
        for i in keys_sequence:
            sampled_sequence = steerings[(i):(i + self._sequence_size)]
            sequence_average.append(sum(sampled_sequence) / len(sampled_sequence))

        # the first return item is a list of ids that sorts sequence_average
        return [i[0] for i in sorted(enumerate(sequence_average), key=lambda x: x[1])], sequence_average

    def partition_keys_by_steering_quad(self, steerings, keys):
        # split the keys based on the percentage defined by self._steering_bins_perc, as well as len(steerings)
        iter_index = 0
        quad_pos = 0
        splited_keys = []
        # self.steering_bins_perc = [0.05, 0.05, 0.1, 0.3, 0.3, 0.1, 0.05, 0.05]
        quad_vec = [self._steering_bins_perc[0]]
        for i in range(1, len(self._steering_bins_perc)):
            quad_vec.append(quad_vec[-1] + self._steering_bins_perc[i])

        for i in range(0, len(steerings)):
            if i >= quad_vec[quad_pos] * len(steerings) - 1:
                splited_keys.append(keys[iter_index:i])
                iter_index = i
                quad_pos += 1
                print('split on ', i, 'with ', steerings[i])

        return splited_keys

    def select_data_sequence(self, control, selected_data):
        break_sequence = False
        count = 0
        del_pos = []

        while count * self._sequence_stride <= (len(control) - self._sequence_size):
            for iter_sequence in range((count * self._sequence_stride),
                                       (count * self._sequence_stride) + self._sequence_size):
                if control[iter_sequence] not in selected_data:
                    del_pos.append(count * self._sequence_stride)
                    break_sequence = True
                    break

            if break_sequence:
                break_sequence = False
                count += 1
                continue

            count += 1

        return del_pos

    """ Split the outputs keys with respect to the labels. The selected labels represents how it is going to be split """

    def divide_keys_by_labels(self, labels, selected_data):
        # example input to this function: labels: a sequence of control variables;
        # selected_data: [[0, 2, 5], [3], [4]]
        keys_for_divison = []  # The set of all possible keys for each division
        for j in range(len(selected_data)):
            keys_to_delete = self.select_data_sequence(labels, selected_data[j])
            keys_for_this_part = range(0, len(labels) - self._sequence_size, self._sequence_stride)
            keys_for_this_part = list(set(keys_for_this_part) - set(keys_to_delete))
            keys_for_divison.append(keys_for_this_part)

        # returns a list, where each entry is the ids with the current selected_data[i]
        return keys_for_divison

    def split_by_output(self, output_to_split, divided_keys):
        # example input: output_to_split: a list of steers. Divided_keys: the output of divide_keys_by_labels
        splited_keys = []
        for i in range(len(divided_keys)):
            # We use this keys to grab the steerings we want... divided into groups
            # TODO: revisit here.
            keys_ordered, average_outputs = self.order_sequence(output_to_split, divided_keys[i])
            # we get new keys and order steering, each steering group
            # the sorted subset of the steers
            sorted_outputs = [average_outputs[j] for j in keys_ordered]

            # We split each group...
            if len(keys_ordered) > 0:
                # TODO: potential buggy code here, since this output does not depend on the actual content of sorted_outputs
                # TODO: instead, it only depend on the length of it, which is just len(keys_ordered)==len(divided_keys[i])
                splited_keys_part = self.partition_keys_by_steering_quad(sorted_outputs,
                                                                         divided_keys[i])  # config.balances_train)
            else:
                splited_keys_part = []
            # as a result, each of the splited_keys_part is a division of the divided_keys[i], in its original order,
            # into several bins, defined by self._steering_bins_perc
            splited_keys.append(splited_keys_part)

        return splited_keys
