from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow.keras.callbacks import LearningRateScheduler
from tensorflow.keras.callbacks import ModelCheckpoint
from tensorflow.python.keras.engine.saving import load_model

import cnn.nn_architecture.keras_generators as gen
from cnn.keras_utils import set_dataset_flag, build_path_results, make_directory
from cnn.nn_architecture import keras_model
from cnn import keras_utils
import cnn.preprocessor.load_data as ld
from cnn.nn_architecture.custom_performance_metrics import keras_accuracy, accuracy_asloss
from cnn.nn_architecture.custom_loss import keras_loss_v3_nor, keras_loss_v3_lse, keras_loss_v3_lse01, \
    keras_loss_v3_mean, keras_loss_v3_max
from cnn.keras_preds import predict_patch_and_save_results
from cnn.preprocessor.load_data_datasets import load_process_xray14
from cnn.preprocessor.load_data_mura import load_mura, split_data_cv, filter_rows_on_class, filter_rows_and_columns
from cnn.preprocessor.load_data_pascal import load_pascal, construct_train_test_cv
from cnn.preprocessor.process_input import fetch_preprocessed_images_csv
from tensorflow.keras import backend as K


IMAGE_SIZE = 512
BATCH_SIZE = 10
BATCH_SIZE_TEST = 1
BOX_SIZE = 16


def cross_validation(config, number_splits=5):
    """
    performs cross validation on a specific architecture
    :param config: yaml config file
    :param number_splits: number of different cross validation splits to test on
    :return: Returns predictions, image indices and patch labels saved in .npy file for train,test and validation set
    and for each CV split.
    """
    skip_processing = config['skip_processing_labels']
    image_path = config['image_path']
    classication_labels_path = config['classication_labels_path']
    localization_labels_path = config['localization_labels_path']
    results_path = config['results_path']
    train_mode = config['train_mode']
    dataset_name = config['dataset_name']
    class_name = config['class_name']
    mura_test_img_path = config['mura_test_img_path']
    mura_train_labels_path = config['mura_train_labels_path']
    mura_train_img_path = config['mura_train_img_path']
    mura_test_labels_path= config['mura_test_labels_path']
    mura_processed_train_labels_path = config['mura_processed_train_labels_path']
    mura_processed_test_labels_path = config['mura_processed_test_labels_path']
    mura_interpolation = config['mura_interpolation']
    pascal_image_path = config['pascal_image_path']
    resized_images_before_training=config['resized_images_before_training']

    nr_epochs = config['nr_epochs']
    lr = config['lr']
    reg_weight = config['reg_weight']
    pooling_operator = config['pooling_operator']

    use_xray, use_pascal = set_dataset_flag(dataset_name)

    script_suffix = 'CV'
    trained_models_path = build_path_results(results_path, dataset_name, pooling_operator, script_suffix=script_suffix,
                                             result_suffix='trained_models')
    prediction_results_path = build_path_results(results_path, dataset_name, pooling_operator,
                                                 script_suffix=script_suffix,
                                                 result_suffix='predictions')
    make_directory(trained_models_path)
    make_directory(prediction_results_path)

    if use_xray:
        if resized_images_before_training:
            xray_df = fetch_preprocessed_images_csv(image_path, 'processed_imgs')
            #todo: delete - just for testing
            # xray_df = xray_df[-50:]
        else:
            xray_df = load_process_xray14(config)
    elif use_pascal:
        pascal_df = load_pascal(pascal_image_path)

    else:
        df_train_val, test_df_all_classes = load_mura(skip_processing, mura_processed_train_labels_path,
                                                      mura_processed_test_labels_path, mura_train_img_path,
                                                      mura_train_labels_path, mura_test_labels_path, mura_test_img_path)

    for split in range(0, number_splits):

        if use_xray:
            df_train, df_val, df_test, _, _,_ = ld.split_xray_cv(xray_df, number_splits,
                                                                 split, class_name)

        elif use_pascal:
            df_train, df_val, df_test = construct_train_test_cv(pascal_df, number_splits, split)

        else:
            df_train, df_val = split_data_cv(df_train_val, number_splits, split, random_seed=1, diagnose_col=class_name,
                                             ratio_to_keep=None)
            # df_test = filter_rows_on_class(test_df_all_classes, class_name=class_name)
            df_test = filter_rows_and_columns(test_df_all_classes, class_name)

        if train_mode:
            tf.keras.backend.clear_session()
            K.clear_session()

            ############################################ TRAIN ###########################################################
            train_generator = gen.BatchGenerator(
                instances=df_train.values,
                resized_image=resized_images_before_training,
                batch_size=BATCH_SIZE,
                net_h=IMAGE_SIZE,
                net_w=IMAGE_SIZE,
                norm=keras_utils.normalize,
                box_size=BOX_SIZE,
                processed_y=skip_processing,
                interpolation=mura_interpolation,
                shuffle=True)

            valid_generator = gen.BatchGenerator(
                instances=df_val.values,
                resized_image=resized_images_before_training,
                batch_size=BATCH_SIZE,
                net_h=IMAGE_SIZE,
                net_w=IMAGE_SIZE,
                box_size=BOX_SIZE,
                norm=keras_utils.normalize,
                processed_y=skip_processing,
                interpolation=mura_interpolation,
                shuffle=True)
            model = keras_model.build_model(reg_weight)

            model = keras_model.compile_model_accuracy(model, lr, pool_op=pooling_operator)

            #   checkpoint on every epoch is not really needed here, not used, CALLBACK REMOVED from the generator
            filepath = trained_models_path + "CV_"+str(split)+"_epoch-{epoch:02d}-{val_loss:.2f}.hdf5"
            checkpoint_on_epoch_end = ModelCheckpoint(filepath, monitor='val_loss', verbose=1, save_best_only=False,
                                                      mode='min')

            lrate = LearningRateScheduler(keras_model.step_decay, verbose=1)
            print("df train STEPS")
            print(len(df_train)//BATCH_SIZE)
            print(train_generator.__len__())

            history = model.fit_generator(
                generator=train_generator,
                steps_per_epoch=train_generator.__len__(),
                epochs=nr_epochs,
                validation_data=valid_generator,
                validation_steps=valid_generator.__len__(),
                verbose=1,
                callbacks=[checkpoint_on_epoch_end]
            )

            print("history")
            print(history.history)
            print(history.history['keras_accuracy'])
            np.save(trained_models_path + 'train_info_'+str(split)+'.npy', history.history)

            settings = np.array({'lr: ': lr, 'reg_weight: ': reg_weight, 'pooling_operator: ': pooling_operator})
            np.save(trained_models_path + 'train_settings.npy', settings)
            keras_utils.plot_train_validation(history.history['loss'], history.history['val_loss'], 'train loss',
                                              'validation loss', 'CV_loss'+str(split), 'loss', trained_models_path)

            ############################################    PREDICTIONS      #############################################
            predict_patch_and_save_results(model, 'test_set_CV'+str(split), df_test, skip_processing,
                                           BATCH_SIZE_TEST, BOX_SIZE, IMAGE_SIZE, prediction_results_path,
                                           mura_interpolation, resized_images_before_training)
            predict_patch_and_save_results(model, 'train_set_CV' + str(split), df_train,
                                           skip_processing,
                                           BATCH_SIZE_TEST, BOX_SIZE, IMAGE_SIZE, prediction_results_path,
                                           mura_interpolation, resized_images_before_training)
            predict_patch_and_save_results(model, 'val_set_CV' + str(split), df_val,
                                           skip_processing,
                                           BATCH_SIZE_TEST, BOX_SIZE, IMAGE_SIZE, prediction_results_path,
                                           mura_interpolation, resized_images_before_training)
            ##### EVALUATE function

            print("evaluate validation")
            evaluate = model.evaluate_generator(
                generator=valid_generator,
                steps=valid_generator.__len__(),
                verbose=1)

            evaluate_train = model.evaluate_generator(
                generator=train_generator,
                steps=train_generator.__len__(),
                verbose=1)
            test_generator = gen.BatchGenerator(
                instances=df_test.values,
                resized_image=resized_images_before_training,
                batch_size=BATCH_SIZE,
                net_h=IMAGE_SIZE,
                net_w=IMAGE_SIZE,
                shuffle=True,
                norm=keras_utils.normalize,
                box_size=BOX_SIZE,
                processed_y=skip_processing,
                interpolation=mura_interpolation)

            evaluate_test = model.evaluate_generator(
                generator=test_generator,
                steps=test_generator.__len__(),
                verbose=1)
            print("Evaluate Train")
            print(evaluate_train)
            print("Evaluate Valid")
            print(evaluate)
            print("Evaluate test")
            print(evaluate_test)
        else:
            files_found = 0
            print(trained_models_path)
            trained_models_name = "CV_" + str(split) + "_epoch-" + str(nr_epochs)
            if nr_epochs < 10:
                trained_models_name = "CV_" + str(split) + "_epoch-0" + str(nr_epochs)
            for file_path in Path(trained_models_path).glob(trained_models_name + "*.hdf5"):
                print(file_path)
                files_found += 1

            assert files_found == 1, "No model found/ Multiple models found, not clear which to use "
            print(str(files_found))
            loss_function_dict = {'nor': keras_loss_v3_nor,
                                  "lse": keras_loss_v3_lse,
                                  "lse01": keras_loss_v3_lse01,
                                  "max": keras_loss_v3_max,
                                  "mean": keras_loss_v3_mean
                                  }
            model = load_model(str(file_path),
                               custom_objects={
                                   loss_function_dict[pooling_operator].__name__: loss_function_dict[pooling_operator],
                                   'keras_accuracy': keras_accuracy,
                                   'accuracy_asloss': accuracy_asloss})
            model = keras_model.compile_model_accuracy(model, lr, pooling_operator)

            predict_patch_and_save_results(model, "train_set_CV" + (str(split)), df_train, skip_processing,
                                           BATCH_SIZE_TEST, BOX_SIZE, IMAGE_SIZE, prediction_results_path,
                                           mura_interpolation, resized_images_before_training)
            predict_patch_and_save_results(model, "val_set_CV" + (str(split)), df_val, skip_processing,
                                           BATCH_SIZE_TEST, BOX_SIZE, IMAGE_SIZE, prediction_results_path,
                                           mura_interpolation, resized_images_before_training)
            predict_patch_and_save_results(model, "test_set_CV" + (str(split)), df_test, skip_processing,
                                           BATCH_SIZE_TEST, BOX_SIZE, IMAGE_SIZE, prediction_results_path,
                                           mura_interpolation, resized_images_before_training)


