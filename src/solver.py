# ---------------------------------------------------------
# Tensorflow DiscoGAN Implementation
# Licensed under The MIT License [see LICENSE for details]
# Written by Cheng-Bin Jin
# Email: sbkim0407@gmail.com
# ---------------------------------------------------------
import os
import numpy as np
import tensorflow as tf
from datetime import datetime

# noinspection PyPep8Naming
from dataset import Dataset
from discogan import DiscoGAN


class Solver(object):
    def __init__(self, flags):
        run_config = tf.ConfigProto()
        run_config.gpu_options.allow_growth = True
        self.sess = tf.Session(config=run_config)

        self.flags = flags
        self.dataset = Dataset(self.flags.dataset, self.flags)
        self.model = DiscoGAN(self.sess, self.flags, self.dataset.image_size, self.dataset.ori_image_size,
                              self.dataset())

        self._make_folders()
        self.iter_time = 0

        self.saver = tf.train.Saver()
        self.sess.run([tf.global_variables_initializer(), tf.local_variables_initializer()])

        # tf_utils.show_all_variables()

    def _make_folders(self):
        if self.flags.is_train:  # train stage
            if self.flags.load_model is None:
                cur_time = datetime.now().strftime("%Y%m%d-%H%M")
                self.model_out_dir = "{}/model/{}".format(self.flags.dataset, cur_time)
                if not os.path.isdir(self.model_out_dir):
                    os.makedirs(self.model_out_dir)
            else:
                cur_time = self.flags.load_model
                self.model_out_dir = "{}/model/{}".format(self.flags.dataset, cur_time)

            self.sample_out_dir = "{}/sample/{}".format(self.flags.dataset, cur_time)
            if not os.path.isdir(self.sample_out_dir):
                os.makedirs(self.sample_out_dir)

            self.train_writer = tf.summary.FileWriter("{}/logs/{}".format(self.flags.dataset, cur_time),
                                                      graph_def=self.sess.graph_def)

        elif not self.flags.is_train:  # test stage
            self.model_out_dir = "{}/model/{}".format(self.flags.dataset, self.flags.load_model)
            self.test_out_dir = "{}/test/{}".format(self.flags.dataset, self.flags.load_model)
            if not os.path.isdir(self.test_out_dir):
                os.makedirs(self.test_out_dir)

    def train(self):
        # load initialized checkpoint that provided
        if self.flags.load_model is not None:
            if self.load_model():
                print(' [*] Load SUCCESS!\n')
            else:
                print(' [!] Load Failed...\n')

        # threads for tfrecord
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(sess=self.sess, coord=coord)

        try:
            # for iter_time in range(self.flags.iters):
            while self.iter_time < self.flags.iters:
                # samppling images and save them
                self.sample(self.iter_time)

                # train_step
                loss, summary = self.model.train_step()
                self.model.print_info(loss, self.iter_time)
                self.train_writer.add_summary(summary, self.iter_time)
                self.train_writer.flush()

                # save model
                self.save_model(self.iter_time)
                self.iter_time += 1

            # infinitely generate
            imgs, names = self.model.test_infinitely(input_type='A', count=5)
            self.model.plots(imgs, self.iter_time, self.sample_out_dir, names)

            imgs, names = self.model.test_infinitely(input_type='B', count=5)
            self.model.plots(imgs, self.iter_time, self.sample_out_dir, names)

            self.save_model(self.flags.iters)
        except KeyboardInterrupt:
            coord.request_stop()
        except Exception as e:
            coord.request_stop(e)
        finally:
            # when done, ask the threads to stop
            coord.request_stop()
            coord.join(threads)

    def test(self):
        if self.load_model():
            print(' [*] Load SUCCESS!')
        else:
            print(' [!] Load Failed...')

        # threads for tfrecord
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(sess=self.sess, coord=coord)

        try:
            num_iters = 20
            for iter_time in range(num_iters):
                print('iter_time: {}'.format(iter_time))

                # infinitely generate
                imgs, names = self.model.test_infinitely(input_type='A', count=3)
                self.model.plots(imgs, iter_time, self.test_out_dir, names)
                imgs, names = self.model.test_infinitely(input_type='B', count=3)
                self.model.plots(imgs, iter_time, self.test_out_dir, names)

        except KeyboardInterrupt:
            coord.request_stop()
        except Exception as e:
            coord.request_stop(e)
        finally:
            # when done, ask the threads to stop
            coord.request_stop()
            coord.join(threads)

    def sample(self, iter_time):
        if np.mod(iter_time, self.flags.sample_freq) == 0:
            imgs, names = self.model.sample_imgs()
            self.model.plots(imgs, iter_time, self.sample_out_dir, names)

    def save_model(self, iter_time):
        if np.mod(iter_time + 1, self.flags.save_freq) == 0:
            model_name = 'model'
            self.saver.save(self.sess, os.path.join(self.model_out_dir, model_name), global_step=iter_time)
            print('[*] Model saved!')

    def load_model(self):
        print(' [*] Reading checkpoint...')

        ckpt = tf.train.get_checkpoint_state(self.model_out_dir)
        if ckpt and ckpt.model_checkpoint_path:
            ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
            self.saver.restore(self.sess, os.path.join(self.model_out_dir, ckpt_name))

            meta_graph_path = ckpt.model_checkpoint_path + '.meta'
            self.iter_time = int(meta_graph_path.split('-')[-1].split('.')[0])

            print('[*] Load iter_time: {}'.format(self.iter_time))
            return True
        else:
            return False
