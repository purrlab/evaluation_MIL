import cv2
import numpy as np
from keras.utils import Sequence
import threading

from keras.preprocessing.image import load_img, img_to_array

# dataset_path = 'nih_data/'

LOCAL_PATH_I = "C:/Users/s161590/Desktop/Data/X_Ray/images/"

class BatchGenerator(Sequence):
    def __init__(self,
                 instances,
                 batch_size=16,
                 shuffle=True,
                 norm=None,
                 net_h=512,
                 net_w=512,
                 box_size=16
                 ):
        '''

        :param instances: Lista em que a primeira posicao sao as imagens e a segunda sao os labels
        :param downsample:
        :param batch_size:
        :param min_net_size:
        :param max_net_size:
        :param shuffle:
        :param jitter:
        :param norm:
        '''
        self.instances = instances
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.norm = norm
        self.net_h = net_h
        self.net_w = net_w
        self.box_size = box_size

        if shuffle: np.random.shuffle(self.instances)

    def __len__(self):
        return int(np.ceil(float(len(self.instances)) / self.batch_size))

    def __getitem__(self, idx):

        # determine the first and the last indices of the batch
        l_bound = idx * self.batch_size
        r_bound = (idx + 1) * self.batch_size

        if r_bound > len(self.instances):
            r_bound = len(self.instances)
            l_bound = r_bound - self.batch_size

        x_batch = np.zeros((r_bound - l_bound, self.net_w, self.net_h, 3))  # input images
        y_batch = np.zeros((r_bound - l_bound, self.box_size, self.box_size, 14))

        instance_count = 0

        # do the logic to fill in the inputs and the output
        for train_instance in self.instances[l_bound:r_bound]:
            # print(train_instance)
            print(train_instance.shape)
            image_name = train_instance[0]

            image = img_to_array(

                load_img(LOCAL_PATH_I + '' + image_name, target_size=(self.net_w, self.net_h), color_mode='rgb'))

            if self.norm != None:
                x_batch[instance_count] = self.norm(image)
            else:
                x_batch[instance_count] = image

            train_instances_classes = []
            for i in range(1, train_instance.shape[0]):  # (15)

                train_instances_classes.append(train_instance[i])

            t = np.transpose(np.asarray(train_instances_classes), [1, 2, 0])

            y_batch[instance_count] = np.transpose(np.asarray(train_instances_classes), [1, 2, 0])
            # increase instance counter in the current batch
            instance_count += 1

        return x_batch, y_batch

    def on_epoch_end(self):
        if self.shuffle: np.random.shuffle(self.instances)

    def num_classes(self):
        return len(self.labels)

    def size(self):
        return len(self.instances)

    def load_image(self, i):
        image_name = self.instances[i]

        image = img_to_array(load_img(image_name, target_size=(self.net_w, self.net_h), color_mode='rgb'))
        return image



