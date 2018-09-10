# ---------------------------------------------------------
# Tensorflow DiscoGAN Implementation
# Licensed under The MIT License [see LICENSE for details]
# Written by Cheng-Bin Jin, based on code from vanhuyz
# Email: sbkim0407@gmail.com
# ---------------------------------------------------------
import collections
import numpy as np
import matplotlib as mpl
import tensorflow as tf
mpl.use('TkAgg')  # or whatever other backend that you want to solve Segmentation fault (core dumped)
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

import tensorflow_utils as tf_utils
import utils as utils
from reader import Reader


# noinspection PyPep8Naming
class DiscoGAN(object):
    def __init__(self, sess, flags, image_size, data_path):
        self.sess = sess
        self.flags = flags
        self.image_size = image_size
        self.x_path, self.y_path = data_path[0], data_path[1]

        self.norm = 'instance'
        self.lambda1, self.lambda2 = 10.0, 10.0
        self.ngf, self.ndf = 64, 64
        self.eps = 1e-12

        self._G_gen_train_ops, self._F_gen_train_ops = [], []
        self._Dy_dis_train_ops, self._Dx_dis_train_ops = [], []

        self._build_net()
        self._tensorboard()

    def _build_net(self):
        # tfph: tensorflow placeholder
        self.x_test_tfph = tf.placeholder(tf.float32, shape=[None, *self.image_size], name='A_test_tfph')
        self.y_test_tfph = tf.placeholder(tf.float32, shape=[None, *self.image_size], name='B_test_tfph')

        self.G_gen = Generator(name='G', ngf=self.ngf, norm=self.norm, image_size=self.image_size,
                               _ops=self._G_gen_train_ops)
        self.Dy_dis = Discriminator(name='Dy', ndf=self.ndf, norm=self.norm, _ops=self._Dy_dis_train_ops)
        self.F_gen = Generator(name='F', ngf=self.ngf, norm=self.norm, image_size=self.image_size,
                               _ops=self._F_gen_train_ops)
        self.Dx_dis = Discriminator(name='Dx', ndf=self.ndf, norm=self.norm, _ops=self._Dx_dis_train_ops)

        if self.flags.dataset == 'handbags2shoes':
            side_1, side_2 = 'right', 'right'
        else:
            side_1, side_2 = 'left', 'right'
        x_reader = Reader(self.x_path, name='X', image_size=self.image_size, batch_size=self.flags.batch_size,
                          side=side_1)
        y_reader = Reader(self.y_path, name='Y', image_size=self.image_size, batch_size=self.flags.batch_size,
                          side=side_2)
        self.x_imgs = x_reader.feed()
        self.y_imgs = y_reader.feed()

        # cycle consistency loss
        cycle_loss = self.cycle_consistency_loss(self.x_imgs, self.y_imgs)

        # X -> Y
        self.fake_y_imgs = self.G_gen(self.x_imgs)
        self.G_gen_loss = self.generator_loss(self.Dy_dis, self.fake_y_imgs)
        self.G_loss = self.G_gen_loss + cycle_loss
        self.Dy_dis_loss = self.discriminator_loss(self.Dy_dis, self.y_imgs, self.fake_y_imgs)

        # Y -> X
        self.fake_x_imgs = self.F_gen(self.y_imgs)
        self.F_gen_loss = self.generator_loss(self.Dx_dis, self.fake_x_imgs)
        self.F_loss = self.F_gen_loss + cycle_loss
        self.Dx_dis_loss = self.discriminator_loss(self.Dx_dis, self.x_imgs, self.fake_x_imgs)

        G_optim = tf.train.AdamOptimizer(
            learning_rate=self.flags.learning_rate, beta1=self.flags.beta1, beta2=self.flags.beta2).minimize(
            self.G_loss, var_list=self.G_gen.variables, name='Adam_G')
        Dy_optim = tf.train.AdamOptimizer(
            learning_rate=self.flags.learning_rate, beta1=self.flags.beta1, beta2=self.flags.beta2).minimize(
            self.Dy_dis_loss, var_list=self.Dy_dis.variables, name='Adam_Dy')
        F_optim = tf.train.AdamOptimizer(
            learning_rate=self.flags.learning_rate, beta1=self.flags.beta1, beta2=self.flags.beta2).minimize(
            self.F_loss, var_list=self.F_gen.variables, name='Adam_F')
        Dx_optim = tf.train.AdamOptimizer(
            learning_rate=self.flags.learning_rate, beta1=self.flags.beta1, beta2=self.flags.beta2).minimize(
            self.Dx_dis_loss, var_list=self.Dx_dis.variables, name='Adam_Dx')
        self.optims = tf.group([G_optim, Dy_optim, F_optim, Dx_optim])

        # for sampling function
        self.fake_y_sample = self.G_gen(self.x_test_tfph)
        self.fake_x_sample = self.F_gen(self.y_test_tfph)

    def cycle_consistency_loss(self, x_imgs, y_imgs):
        # use mean squared error
        forward_loss = tf.reduce_mean(tf.losses.mean_squared_error(labels=x_imgs,
                                                                   predictions=self.F_gen(self.G_gen(x_imgs))))
        backward_loss = tf.reduce_mean(tf.losses.mean_squared_error(labels=y_imgs,
                                                                    predictions=self.G_gen(self.F_gen(y_imgs))))
        loss = self.lambda1 * forward_loss + self.lambda2 * backward_loss
        return loss

    def generator_loss(self, dis_obj, fake_img):
        loss = -tf.reduce_mean(tf.log(dis_obj(fake_img) + self.eps))
        return loss

    def discriminator_loss(self, dis_obj, real_img, fake_img):
        error_real = -tf.reduce_mean(tf.log(dis_obj(real_img) + self.eps))
        error_fake = -tf.reduce_mean(tf.log(1. - dis_obj(fake_img) + self.eps))
        loss = 0.5 * (error_real + error_fake)
        return loss

    def _tensorboard(self):
        tf.summary.scalar('loss/G_loss', self.G_loss)
        tf.summary.scalar('loss/F_loss', self.F_loss)
        tf.summary.scalar('loss/Dy_loss', self.Dy_dis_loss)
        tf.summary.scalar('loss/Dx_loss', self.Dx_dis_loss)
        self.summary_op = tf.summary.merge_all()

    def train_step(self):
        _, G_loss, Dy_loss, F_loss, Dx_loss, summary = \
            self.sess.run([self.optims, self.G_loss, self.Dy_dis_loss,
                           self.F_loss, self.Dx_dis_loss, self.summary_op])

        return [G_loss, Dy_loss, F_loss, Dx_loss], summary

    def sample_imgs(self):
        x_val, y_val = self.sess.run([self.x_imgs, self.y_imgs])
        # minimum between batch_size and sample_batch
        batch_size = np.minimum(self.flags.batch_size, self.flags.sample_batch)
        batch_x, batch_y = x_val[:batch_size], y_val[:batch_size]
        fake_y, fake_x = self.sess.run([self.fake_y_sample, self.fake_x_sample],
                                       feed_dict={self.x_test_tfph: batch_x, self.y_test_tfph: batch_y})

        return [batch_x, fake_x, batch_y, fake_y]

    def test_step(self, x_img, y_img):
        fake_y = self.sess.run(self.fake_y_sample, feed_dict={self.x_test_tfph: x_img})
        fake_x = self.sess.run(self.fake_x_sample, feed_dict={self.y_test_tfph: y_img})
        return [x_img, fake_y, y_img, fake_x]

    def print_info(self, loss, iter_time):
        if np.mod(iter_time, self.flags.print_freq) == 0:
            ord_output = collections.OrderedDict([('cur_iter', iter_time), ('tar_iters', self.flags.iters),
                                                  ('batch_size', self.flags.batch_size),
                                                  ('G_loss', loss[0]), ('Dy_loss', loss[1]),
                                                  ('F_loss', loss[2]), ('Dx_loss', loss[3]),
                                                  ('dataset', self.flags.dataset),
                                                  ('gpu_index', self.flags.gpu_index)])

            utils.print_metrics(iter_time, ord_output)

    def plots(self, imgs, iter_time, save_file):
        # parameters for plot size
        scale, margin = 0.02, 0.02
        n_cols, n_rows = len(imgs), imgs[0].shape[0]
        cell_size_h, cell_size_w = imgs[0].shape[1] * scale, imgs[0].shape[2] * scale

        fig = plt.figure(figsize=(cell_size_w * n_cols, cell_size_h * n_rows))  # (column, row)
        gs = gridspec.GridSpec(n_rows, n_cols)  # (row, column)
        gs.update(wspace=margin, hspace=margin)

        # we don't need inverse transform, becasue discoGAN use sigmoid at the end of the generator
        # imgs = [utils.inverse_transform(imgs[idx]) for idx in range(len(imgs))]

        # save more bigger image
        for col_index in range(n_cols):
            for row_index in range(n_rows):
                ax = plt.subplot(gs[row_index * n_cols + col_index])
                plt.axis('off')
                ax.set_xticklabels([])
                ax.set_yticklabels([])
                ax.set_aspect('equal')
                plt.imshow((imgs[col_index][row_index]).reshape(
                    self.image_size[0], self.image_size[1], self.image_size[2]), cmap='Greys_r')

        plt.savefig(save_file + '/sample_{}.png'.format(str(iter_time)), bbox_inches='tight')
        plt.close(fig)


class Generator(object):
    def __init__(self, name=None, ngf=64, norm='instance', image_size=(64, 64, 3), _ops=None):
        self.name = name
        self.ngf = ngf
        self.norm = norm
        self.image_size = image_size
        self._ops = _ops
        self.reuse = False

    def __call__(self, x):
        with tf.variable_scope(self.name, reuse=self.reuse):
            tf_utils.print_activations(x)

            # conv1: (N, H, W, C) -> (N, H/2, W/2, 64)
            conv1 = tf_utils.conv2d(x, self.ngf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv1_conv2d')
            conv1 = tf_utils.lrelu(conv1, name='conv1_lrelu', is_print=True)

            # conv2: (N, H/2, W/2, 64) -> (N, H/4, W/4, 128)
            conv2 = tf_utils.conv2d(conv1, 2*self.ngf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv2_conv2d')
            conv2 = tf_utils.norm(conv2, _type='batch', _ops=self._ops, name='conv2_norm')
            conv2 = tf_utils.lrelu(conv2, name='conv2_lrelu', is_print=True)

            # conv3: (N, H/4, W/4, 128) -> (N, H/8, W/8, 256)
            conv3 = tf_utils.conv2d(conv2, 4*self.ngf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv3_conv2d')
            conv3 = tf_utils.norm(conv3, _type='batch', _ops=self._ops, name='conv3_norm')
            conv3 = tf_utils.lrelu(conv3, name='conv3_lrelu', is_print=True)

            # conv4: (N, H/8, W/8, 256) -> (N, H/16, W/16, 512)
            conv4 = tf_utils.conv2d(conv3, 8*self.ngf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv4_conv2d')
            conv4 = tf_utils.norm(conv4, _type='batch', _ops=self._ops, name='conv4_norm')
            conv4 = tf_utils.lrelu(conv4, name='conv4_lrelu', is_print=True)

            # conv5: (N, H/16, W/16, 512) -> (N, H/8, W/8, 256)
            conv5 = tf_utils.deconv2d(conv4, 4*self.ngf, k_h=4, k_w=4, name='conv5_deconv2d')
            conv5 = tf_utils.norm(conv5, _type='batch', _ops=self._ops, name='conv5_norm')
            conv5 = tf_utils.relu(conv5, name='conv5_relu', is_print=True)

            # conv6: (N, H/8, W/8, 256) -> (N, H/4, W/4, 128)
            conv6 = tf_utils.deconv2d(conv5, 2*self.ngf, k_h=4, k_w=4, name='conv6_deconv2d')
            conv6 = tf_utils.norm(conv6, _type='batch', _ops=self._ops, name='conv6_norm')
            conv6 = tf_utils.relu(conv6, name='conv6_relu', is_print=True)

            # conv7: (N, H/4, W/4, 128) -> (N, H/2, W/2, 64)
            conv7 = tf_utils.deconv2d(conv6, self.ngf, k_h=4, k_w=4, name='conv7_deconv2d')
            conv7 = tf_utils.norm(conv7, _type='batch', _ops=self._ops, name='conv7_norm')
            conv7 = tf_utils.relu(conv7, name='conv7_relu', is_print=True)

            # conv8: (N, H/2, W/2, 64) -> (N, W, H, 3)
            conv8 = tf_utils.deconv2d(conv7, self.image_size[2], k_h=4, k_w=4, name='conv8_deconv2d')
            output = tf_utils.sigmoid(conv8, name='conv8_sigmoid', is_print=True)

            # set reuse=True for next call
            self.reuse = True
            self.variables = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope=self.name)
            return output


class Discriminator(object):
    def __init__(self, name=None, ndf=64, norm='instance', _ops=None):
        self.name = name
        self.ndf = ndf
        self.norm = norm
        self._ops = _ops
        self.reuse = False

    def __call__(self, x):
        with tf.variable_scope(self.name, reuse=self.reuse):
            tf_utils.print_activations(x)

            # conv1: (N, H, W, 3) -> (N, H/2, W/2, 64)
            conv1 = tf_utils.conv2d(x, self.ndf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv1_conv2d')
            conv1 = tf_utils.lrelu(conv1, name='conv1_lrelu', is_print=True)

            # conv2: (N, H/2, W/2, 64) -> (N, H/4, W/4, 128)
            conv2 = tf_utils.conv2d(conv1, 2*self.ndf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv2_conv2d')
            conv2 = tf_utils.norm(conv2, _type='batch', _ops=self._ops, name='conv2_norm')
            conv2 = tf_utils.lrelu(conv2, name='conv2_lrelu', is_print=True)

            # conv3: (N, H/4, W/4, 128) -> (N, H/8, W/8, 256)
            conv3 = tf_utils.conv2d(conv2, 4*self.ndf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv3_conv2d')
            conv3 = tf_utils.norm(conv3, _type='batch', _ops=self._ops, name='con3_norm')
            conv3 = tf_utils.lrelu(conv3, name='conv3_lrelu', is_print=True)

            # conv4: (N, H/8, W/8, 256) -> (N, H/16, W/16, 512)
            conv4 = tf_utils.conv2d(conv3, 8*self.ndf, k_h=4, k_w=4, d_h=2, d_w=2, padding='SAME', name='conv4_conv2d')
            conv4 = tf_utils.norm(conv4, _type='batch', _ops=self._ops, name='conv4_norm')
            conv4 = tf_utils.lrelu(conv4, name='conv4_lrelu', is_print=True)

            # conv5: (N, H/16, W/16, 512) -> (N, H/16, W/16, 1)
            conv5 = tf_utils.conv2d(conv4, 1, k_h=4, k_w=4, d_h=1, d_w=1, padding='SAME', name='conv5_conv2d')
            output = tf_utils.sigmoid(conv5)

            # set reuse=True for next call
            self.reuse = True
            self.variables = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope=self.name)
            return output